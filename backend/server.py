from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Request, Query
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import asyncio
import tempfile
import time
import base64
import subprocess
import cv2
import numpy as np
import requests
from pathlib import Path
from collections import defaultdict
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Object Storage
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "dropshot"
storage_key = None

# ---- Production Config ----
MAX_VIDEO_DURATION = 30      # seconds
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}
MAX_CONCURRENT_JOBS = 3
RATE_LIMIT_WINDOW = 60       # seconds
RATE_LIMIT_MAX = 10          # requests per window per IP

# ---- Rate Limiter ----
rate_limit_store = defaultdict(list)

def check_rate_limit(client_ip: str):
    now = time.time()
    # Clean old entries
    rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    rate_limit_store[client_ip].append(now)

# ---- Processing Queue ----
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
processing_jobs = {}  # track active jobs

# ---- Storage with Retry ----
def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    for attempt in range(3):
        try:
            resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
            resp.raise_for_status()
            storage_key = resp.json()["storage_key"]
            return storage_key
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1)

def put_object_with_retry(path: str, data: bytes, content_type: str, retries: int = 3) -> dict:
    key = init_storage()
    for attempt in range(retries):
        try:
            resp = requests.put(
                f"{STORAGE_URL}/objects/{path}",
                headers={"X-Storage-Key": key, "Content-Type": content_type},
                data=data, timeout=180
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Storage put attempt {attempt+1} failed: {e}")
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)

def get_object_with_retry(path: str, retries: int = 3) -> tuple:
    key = init_storage()
    for attempt in range(retries):
        try:
            resp = requests.get(
                f"{STORAGE_URL}/objects/{path}",
                headers={"X-Storage-Key": key}, timeout=180
            )
            resp.raise_for_status()
            return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
        except Exception as e:
            logger.warning(f"Storage get attempt {attempt+1} failed: {e}")
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)

# Create app
app = FastAPI(title="DROPSHOT API", version="1.0.0")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---- Video Validation ----
def validate_video(file_path: str) -> dict:
    """Thorough video validation — returns metadata or raises."""
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Cannot read video file. It may be corrupted.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if fps <= 0 or total_frames <= 0:
        cap.release()
        raise HTTPException(status_code=400, detail="Video has no readable frames. Check format.")

    duration = total_frames / fps
    if duration > MAX_VIDEO_DURATION + 2:
        cap.release()
        raise HTTPException(status_code=400, detail=f"Video is {duration:.1f}s. Maximum is {MAX_VIDEO_DURATION} seconds.")

    if width < 120 or height < 120:
        cap.release()
        raise HTTPException(status_code=400, detail=f"Video resolution too low ({width}x{height}). Minimum 120x120.")

    # Read a test frame to confirm it's real video
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise HTTPException(status_code=400, detail="Video contains no decodable frames.")

    return {"total_frames": total_frames, "fps": fps, "width": width, "height": height, "duration": duration}

# ---- Video Compression ----
def compress_video(input_path: str) -> str:
    """Compress/normalize video for consistent processing. Returns path to compressed file."""
    output_path = input_path.replace(".mp4", "_compressed.mp4")
    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-vf", "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease",
            "-pix_fmt", "yuv420p",
            "-an",  # strip audio for processing
            "-movflags", "+faststart",
            output_path
        ], capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"Compressed: {os.path.getsize(input_path)} -> {os.path.getsize(output_path)} bytes")
            return output_path
    except Exception as e:
        logger.warning(f"Compression failed, using original: {e}")
    return input_path

# ---- OpenCV Analysis (Core — no AI dependency) ----
def extract_key_frames(video_path: str, num_frames: int = 5):
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0

    frame_indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
    frames = []
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append((idx, frame))
    cap.release()
    return frames, {"total_frames": total_frames, "fps": fps, "width": width, "height": height, "duration": duration}

def frame_to_base64(frame):
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buffer).decode('utf-8')

def analyze_motion(video_path: str):
    """Core OpenCV motion + ball + player analysis."""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    prev_frame = None
    motion_data = []
    ball_positions = []
    player_positions = []
    frame_idx = 0
    sample_interval = max(1, total_frames // 80)

    # Accumulate for heatmap
    motion_heatmap = np.zeros((height, width), dtype=np.float32)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_frame is not None:
                diff = cv2.absdiff(prev_frame, blur)
                _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                total_motion = sum(cv2.contourArea(c) for c in contours)
                motion_data.append({"frame": frame_idx, "motion_level": float(total_motion), "time": round(frame_idx / fps, 2) if fps > 0 else 0})

                # Accumulate heatmap
                motion_heatmap += thresh.astype(np.float32)

                # Ball detection — tennis ball yellow-green HSV range
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                lower_yellow = np.array([25, 80, 80])
                upper_yellow = np.array([45, 255, 255])
                mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
                mask = cv2.erode(mask, None, iterations=2)
                mask = cv2.dilate(mask, None, iterations=2)
                ball_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for c in ball_contours:
                    area = cv2.contourArea(c)
                    if 50 < area < 5000:
                        M = cv2.moments(c)
                        if M["m00"] > 0:
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"])
                            ball_positions.append({"frame": frame_idx, "x": cx, "y": cy, "time": round(frame_idx / fps, 2) if fps > 0 else 0})

                # Player detection — large motion contours with human-like aspect ratio
                for c in contours:
                    if cv2.contourArea(c) > 3000:
                        x, y, w, h = cv2.boundingRect(c)
                        if h > w * 0.8:
                            player_positions.append({
                                "frame": frame_idx,
                                "x": x + w // 2, "y": y + h // 2,
                                "width": w, "height": h,
                                "time": round(frame_idx / fps, 2) if fps > 0 else 0
                            })

            prev_frame = blur
        frame_idx += 1

    cap.release()

    # Compute derived stats
    motion_levels = [m["motion_level"] for m in motion_data] if motion_data else [0]
    avg_motion = float(np.mean(motion_levels))
    max_motion = float(np.max(motion_levels))
    peak_frames = sorted(motion_data, key=lambda x: x["motion_level"], reverse=True)[:10]

    # Detect high-activity bursts (potential shots)
    threshold = avg_motion * 1.8
    shot_moments = [m for m in motion_data if m["motion_level"] > threshold]

    # Ball speed estimation from consecutive positions
    ball_speeds = []
    for i in range(1, len(ball_positions)):
        p1, p2 = ball_positions[i-1], ball_positions[i]
        dt = p2["time"] - p1["time"]
        if dt > 0:
            dist = np.sqrt((p2["x"] - p1["x"])**2 + (p2["y"] - p1["y"])**2)
            speed_px_sec = dist / dt
            ball_speeds.append({"frame": p2["frame"], "speed_px_per_sec": round(speed_px_sec, 1), "time": p2["time"]})

    # Court coverage estimate from player positions
    if player_positions:
        xs = [p["x"] for p in player_positions]
        ys = [p["y"] for p in player_positions]
        x_range = (max(xs) - min(xs)) / width * 100 if width > 0 else 0
        y_range = (max(ys) - min(ys)) / height * 100 if height > 0 else 0
        court_coverage = round(min(100, (x_range + y_range) / 2), 1)
    else:
        court_coverage = 0

    return {
        "motion_data": motion_data[:120],
        "ball_positions": ball_positions[:300],
        "player_positions": player_positions[:300],
        "avg_motion": avg_motion,
        "max_motion": max_motion,
        "peak_activity_frames": peak_frames,
        "total_ball_detections": len(ball_positions),
        "total_player_detections": len(player_positions),
        "shot_moments": shot_moments[:20],
        "ball_speeds": ball_speeds[:100],
        "court_coverage_pct": court_coverage,
        "video_width": width,
        "video_height": height
    }

def generate_annotated_video(video_path: str, output_path: str, cv_analysis: dict):
    """Generate output video with analysis overlays."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    raw_output = output_path + ".raw.mp4"
    out = cv2.VideoWriter(raw_output, fourcc, fps, (width, height))

    ball_by_frame = {}
    for bp in cv_analysis.get("ball_positions", []):
        f = bp["frame"]
        ball_by_frame.setdefault(f, []).append(bp)

    player_by_frame = {}
    for pp in cv_analysis.get("player_positions", []):
        f = pp["frame"]
        player_by_frame.setdefault(f, []).append(pp)

    speed_by_frame = {}
    for sp in cv_analysis.get("ball_speeds", []):
        speed_by_frame[sp["frame"]] = sp

    trail_length = 30
    recent_balls = []
    shot_moments_set = {m["frame"] for m in cv_analysis.get("shot_moments", [])}

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        overlay = frame.copy()

        # Top analysis bar
        cv2.rectangle(overlay, (0, 0), (width, 55), (10, 10, 10), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        time_sec = frame_idx / fps if fps > 0 else 0
        cv2.putText(frame, "DROPSHOT ANALYTICS", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (206, 255, 0), 2)
        cv2.putText(frame, f"Frame {frame_idx}/{total_frames}  |  {time_sec:.1f}s", (15, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        # Shot moment flash
        is_shot = any(abs(sm - frame_idx) < 3 for sm in shot_moments_set)
        if is_shot:
            shot_overlay = frame.copy()
            cv2.rectangle(shot_overlay, (0, 0), (width, height), (0, 255, 206), -1)
            cv2.addWeighted(shot_overlay, 0.05, frame, 0.95, 0, frame)
            cv2.putText(frame, "SHOT DETECTED", (width - 250, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 206), 2)

        # Ball tracking
        if frame_idx in ball_by_frame:
            for bp in ball_by_frame[frame_idx]:
                recent_balls.append((bp["x"], bp["y"]))
                cv2.circle(frame, (bp["x"], bp["y"]), 14, (0, 255, 206), 2)
                cv2.circle(frame, (bp["x"], bp["y"]), 5, (0, 255, 206), -1)

                # Speed annotation if available
                if frame_idx in speed_by_frame:
                    spd = speed_by_frame[frame_idx]["speed_px_per_sec"]
                    cv2.putText(frame, f"{spd:.0f} px/s", (bp["x"] + 18, bp["y"] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 206), 1)

        if len(recent_balls) > trail_length:
            recent_balls = recent_balls[-trail_length:]

        # Trajectory trail with fade
        for i in range(1, len(recent_balls)):
            alpha = i / len(recent_balls)
            color = (0, int(255 * alpha), int(206 * alpha))
            thickness = max(1, int(3 * alpha))
            cv2.line(frame, recent_balls[i - 1], recent_balls[i], color, thickness)

        # Player bounding boxes
        if frame_idx in player_by_frame:
            for pp in player_by_frame[frame_idx]:
                x = pp["x"] - pp["width"] // 2
                y = pp["y"] - pp["height"] // 2
                w, h = pp["width"], pp["height"]
                # Volt green box with corner accents
                cv2.rectangle(frame, (x, y), (x + w, y + h), (206, 255, 0), 2)
                corner = 15
                cv2.line(frame, (x, y), (x + corner, y), (206, 255, 0), 3)
                cv2.line(frame, (x, y), (x, y + corner), (206, 255, 0), 3)
                cv2.line(frame, (x + w, y), (x + w - corner, y), (206, 255, 0), 3)
                cv2.line(frame, (x + w, y + h), (x + w, y + h - corner), (206, 255, 0), 3)
                cv2.putText(frame, "PLAYER", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (206, 255, 0), 2)

        # Bottom motion bar
        motion_level = 0
        for md in cv_analysis.get("motion_data", []):
            if abs(md["frame"] - frame_idx) < 5:
                motion_level = md["motion_level"]
                break
        max_m = cv_analysis.get("max_motion", 1)
        bar_width = min(int((motion_level / max(max_m, 1)) * width), width)
        cv2.rectangle(frame, (0, height - 6), (bar_width, height), (206, 255, 0), -1)

        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()

    # Convert to H.264 for browser playback
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_output,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            output_path
        ], check=True, capture_output=True, timeout=120)
        os.unlink(raw_output)
        logger.info("Annotated video converted to H.264")
    except Exception as e:
        logger.error(f"H.264 conversion failed: {e}")
        os.replace(raw_output, output_path)

# ---- AI Enhancement (supplements OpenCV, doesn't replace) ----
async def analyze_with_gpt(frames: list, video_info: dict, cv_stats: dict):
    """GPT-5.2 Vision supplements the OpenCV data with expert interpretation."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"dropshot-{uuid.uuid4()}",
            system_message="""You are an expert tennis analyst. You receive video frames from a tennis clip along with computer vision data.
Your job: provide expert INTERPRETATION of what's happening. The CV system already tracks ball/player — you add the tennis intelligence.
Return JSON only:
{
    "shot_analysis": [{"frame_number": 1, "shot_type": "forehand/backhand/serve/volley/overhead", "technique_rating": "1-10", "notes": "brief observation"}],
    "player_assessment": {"stance": "", "footwork": "", "swing_technique": "", "positioning": "", "overall_rating": "1-10"},
    "speed_estimates": {"estimated_ball_speed_mph": "range", "player_movement_intensity": "low/medium/high", "rally_tempo": "slow/medium/fast"},
    "tactical_analysis": {"shot_placement": "", "court_coverage": "% estimate", "strategy_notes": ""},
    "summary": "2-3 sentence analysis"
}
Only valid JSON, no markdown."""
        ).with_model("openai", "gpt-5.2")

        image_contents = []
        for idx, (frame_num, frame) in enumerate(frames[:4]):
            b64 = frame_to_base64(frame)
            image_contents.append(ImageContent(image_base64=b64))

        cv_context = f"CV Data: {cv_stats.get('total_ball_detections',0)} ball detections, {cv_stats.get('total_player_detections',0)} player detections, avg motion {cv_stats.get('avg_motion',0):.0f}, court coverage {cv_stats.get('court_coverage_pct',0)}%"

        user_msg = UserMessage(
            text=f"Analyze these {len(image_contents)} tennis frames. Video: {video_info['duration']:.1f}s, {video_info['fps']:.0f}fps, {video_info['width']}x{video_info['height']}. {cv_context}. Return JSON.",
            file_contents=image_contents
        )

        response = await chat.send_message(user_msg)

        import json
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        if clean.startswith("json"):
            clean = clean[4:]
        return json.loads(clean.strip())

    except Exception as e:
        logger.error(f"GPT analysis error: {e}")
        # Return empty — OpenCV data stands on its own
        return None

# ---- Processing Pipeline ----
async def process_video_task(analysis_id: str):
    async with processing_semaphore:
        processing_jobs[analysis_id] = True
        try:
            await _run_processing(analysis_id)
        finally:
            processing_jobs.pop(analysis_id, None)

async def _run_processing(analysis_id: str):
    tmp_files = []
    try:
        doc = await db.analyses.find_one({"id": analysis_id}, {"_id": 0})
        if not doc:
            return

        await db.analyses.update_one({"id": analysis_id}, {"$set": {"status": "processing", "processing_progress": 5}})

        # 1. Download from storage
        video_data, _ = get_object_with_retry(doc["storage_path"])
        tmp_input = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_input.write(video_data)
        tmp_input.close()
        tmp_files.append(tmp_input.name)
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"processing_progress": 10}})

        # 2. Compress/normalize
        compressed_path = compress_video(tmp_input.name)
        if compressed_path != tmp_input.name:
            tmp_files.append(compressed_path)
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"processing_progress": 20}})

        # 3. Validate & extract metadata
        video_info = validate_video(compressed_path)
        frames, frame_info = extract_key_frames(compressed_path, num_frames=5)
        await db.analyses.update_one({"id": analysis_id}, {"$set": {
            "processing_progress": 25,
            "duration_sec": video_info["duration"],
            "total_frames": video_info["total_frames"],
            "fps": video_info["fps"],
            "resolution": f"{video_info['width']}x{video_info['height']}"
        }})

        # 4. Core OpenCV analysis (primary source of truth)
        cv_analysis = analyze_motion(compressed_path)
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"processing_progress": 50}})

        # 5. AI enhancement (supplementary — degrades gracefully)
        ai_result = await analyze_with_gpt(frames, video_info, cv_analysis)
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"processing_progress": 65}})

        # 6. Generate annotated output video
        tmp_output = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_output.close()
        tmp_files.append(tmp_output.name)
        generate_annotated_video(compressed_path, tmp_output.name, cv_analysis)
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"processing_progress": 85}})

        # 7. Upload output video
        with open(tmp_output.name, "rb") as f:
            output_data = f.read()
        output_path = f"{APP_NAME}/output/{analysis_id}/annotated.mp4"
        put_object_with_retry(output_path, output_data, "video/mp4")
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"processing_progress": 92}})

        # 8. Compile results — CV data is primary, AI enriches
        ball_tracking = {
            "total_detections": cv_analysis["total_ball_detections"],
            "positions": cv_analysis["ball_positions"][:50],
            "trajectory_points": len(cv_analysis["ball_positions"]),
            "speeds": cv_analysis["ball_speeds"][:30],
        }

        player_stats = {
            "total_movement_detections": cv_analysis["total_player_detections"],
            "avg_motion_level": cv_analysis["avg_motion"],
            "max_motion_level": cv_analysis["max_motion"],
            "peak_activity_frames": [p["frame"] for p in cv_analysis["peak_activity_frames"][:5]],
            "court_coverage_pct": cv_analysis["court_coverage_pct"],
        }

        speed_metrics = {
            "motion_intensity_score": min(100, int(cv_analysis["avg_motion"] / 1000)),
            "shot_moments_detected": len(cv_analysis["shot_moments"]),
        }

        # Merge AI data if available
        if ai_result:
            player_stats.update({
                "stance": ai_result.get("player_assessment", {}).get("stance", ""),
                "footwork": ai_result.get("player_assessment", {}).get("footwork", ""),
                "swing_technique": ai_result.get("player_assessment", {}).get("swing_technique", ""),
                "positioning": ai_result.get("player_assessment", {}).get("positioning", ""),
                "overall_rating": ai_result.get("player_assessment", {}).get("overall_rating", ""),
            })
            speed_metrics.update({
                "estimated_ball_speed_mph": ai_result.get("speed_estimates", {}).get("estimated_ball_speed_mph", ""),
                "player_movement_intensity": ai_result.get("speed_estimates", {}).get("player_movement_intensity", ""),
                "rally_tempo": ai_result.get("speed_estimates", {}).get("rally_tempo", ""),
            })

        await db.analyses.update_one({"id": analysis_id}, {"$set": {
            "status": "completed",
            "processing_progress": 100,
            "shot_analysis": ai_result.get("shot_analysis", []) if ai_result else cv_analysis["shot_moments"][:10],
            "player_stats": player_stats,
            "ball_tracking": ball_tracking,
            "speed_metrics": speed_metrics,
            "tactical_analysis": ai_result.get("tactical_analysis", {}) if ai_result else {},
            "ai_summary": ai_result.get("summary", "") if ai_result else f"OpenCV detected {cv_analysis['total_ball_detections']} ball positions, {cv_analysis['total_player_detections']} player movements, {len(cv_analysis['shot_moments'])} shot moments across {video_info['duration']:.1f}s of footage.",
            "output_video_path": output_path,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }})

        logger.info(f"Analysis {analysis_id} completed successfully")

    except HTTPException:
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"status": "failed", "error": "Video validation failed"}})
    except Exception as e:
        logger.error(f"Processing error for {analysis_id}: {e}")
        await db.analyses.update_one({"id": analysis_id}, {"$set": {"status": "failed", "error": str(e)}})
    finally:
        for f in tmp_files:
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except Exception:
                pass

# ---- API Routes ----

@api_router.get("/")
async def root():
    return {"message": "DROPSHOT Tennis Video Analytics API", "version": "1.0.0"}

@api_router.get("/health")
async def health():
    """Production health check."""
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "storage": "initialized" if storage_key else "not initialized",
        "active_jobs": len(processing_jobs),
        "max_jobs": MAX_CONCURRENT_JOBS
    }

@api_router.post("/upload")
async def upload_video(request: Request, file: UploadFile = File(...)):
    """Upload a tennis video clip for analysis."""
    check_rate_limit(request.client.host)

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Accepted: MP4, MOV, AVI, WebM.")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large ({len(data)/(1024*1024):.1f}MB). Max {MAX_FILE_SIZE//(1024*1024)}MB.")

    # Write to temp for validation
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.write(data)
    tmp.close()

    try:
        video_info = validate_video(tmp.name)
    finally:
        os.unlink(tmp.name)

    # Upload to storage
    analysis_id = str(uuid.uuid4())
    ext = file.filename.split(".")[-1] if "." in file.filename else "mp4"
    storage_path = f"{APP_NAME}/uploads/{analysis_id}/original.{ext}"
    put_object_with_retry(storage_path, data, file.content_type or "video/mp4")

    analysis_doc = {
        "id": analysis_id,
        "original_filename": file.filename,
        "storage_path": storage_path,
        "status": "queued",
        "processing_progress": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": video_info["duration"],
        "file_size": len(data),
        "resolution": f"{video_info['width']}x{video_info['height']}",
        "fps": video_info["fps"],
        "total_frames": video_info["total_frames"]
    }
    await db.analyses.insert_one(analysis_doc)

    asyncio.create_task(process_video_task(analysis_id))

    return {
        "id": analysis_id,
        "status": "queued",
        "message": "Video uploaded. Processing queued.",
        "duration_sec": video_info["duration"],
        "queue_position": len(processing_jobs) + 1
    }

@api_router.get("/analyses")
async def list_analyses(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)):
    """Paginated analysis list."""
    skip = (page - 1) * limit
    total = await db.analyses.count_documents({})
    analyses = await db.analyses.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "items": analyses,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }

@api_router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str):
    doc = await db.analyses.find_one({"id": analysis_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return doc

@api_router.get("/analyses/{analysis_id}/output-video")
async def get_output_video(analysis_id: str, download: bool = False):
    doc = await db.analyses.find_one({"id": analysis_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if not doc.get("output_video_path"):
        raise HTTPException(status_code=404, detail="Output video not ready")

    video_data, _ = get_object_with_retry(doc["output_video_path"])
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(len(video_data))}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="dropshot_{analysis_id[:8]}.mp4"'
    else:
        headers["Content-Disposition"] = "inline"
    return Response(content=video_data, media_type="video/mp4", headers=headers)

@api_router.get("/analyses/{analysis_id}/original-video")
async def get_original_video(analysis_id: str):
    doc = await db.analyses.find_one({"id": analysis_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    video_data, _ = get_object_with_retry(doc["storage_path"])
    return Response(content=video_data, media_type="video/mp4", headers={
        "Accept-Ranges": "bytes", "Content-Length": str(len(video_data)), "Content-Disposition": "inline"
    })

@api_router.delete("/analyses/{analysis_id}")
async def delete_analysis(analysis_id: str):
    result = await db.analyses.delete_one({"id": analysis_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"message": "Analysis deleted"}

@api_router.post("/analyses/{analysis_id}/retry")
async def retry_analysis(analysis_id: str):
    """Retry a failed analysis."""
    doc = await db.analyses.find_one({"id": analysis_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if doc["status"] not in ("failed",):
        raise HTTPException(status_code=400, detail="Can only retry failed analyses")

    await db.analyses.update_one({"id": analysis_id}, {"$set": {"status": "queued", "processing_progress": 0, "error": None}})
    asyncio.create_task(process_video_task(analysis_id))
    return {"message": "Analysis re-queued for processing"}

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("DROPSHOT: Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    # Create indexes
    await db.analyses.create_index("id", unique=True)
    await db.analyses.create_index("created_at")
    await db.analyses.create_index("status")
    logger.info("DROPSHOT: Database indexes ensured")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
