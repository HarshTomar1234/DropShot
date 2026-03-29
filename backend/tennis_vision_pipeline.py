"""
DROPSHOT — Tennis Vision Pipeline Wrapper
Integrates Tennis-Vision's YOLO-based detection, court keypoints,
mini-court visualization, and shot classification into the DROPSHOT backend.
"""
import sys
import os
import cv2
import numpy as np
import subprocess
import logging
import random

logger = logging.getLogger(__name__)

# Add Tennis-Vision to path for module imports
TV_DIR = os.path.join(os.path.dirname(__file__), "Tennis-Vision")
sys.path.insert(0, TV_DIR)

from trackers import PlayerTracker, BallTracker
from court_line_detector import CourtLineDetector
from mini_visual_court import MiniCourt
from utils import read_video, save_video
from utils.shot_classifier import ShotClassifier
from utils.bbox_utils import get_center_of_bbox, measure_distance_between_points, get_foot_position
from utils.conversions import convert_pixel_distance_to_meters

# Model paths
YOLO_PLAYER_MODEL = "yolov8s"  # yolov8s for CPU speed (use yolov8x for GPU)
BALL_MODEL = os.path.join(TV_DIR, "models", "last.pt")
KEYPOINTS_MODEL = os.path.join(TV_DIR, "models", "keypoints_model.pth")


def run_tennis_vision_pipeline(input_video_path: str, output_video_path: str):
    """
    Full Tennis-Vision pipeline:
    1. YOLO player detection
    2. Custom YOLO ball detection
    3. Court keypoint detection (ResNet-50)
    4. Mini-court visualization
    5. Shot classification
    6. Player stats (speed, distance)
    7. Annotated output video

    Returns dict of analytics data.
    """
    analytics = {}

    # 1. Read video frames
    logger.info("Reading video frames...")
    video_frames = read_video(input_video_path)
    if not video_frames or len(video_frames) == 0:
        raise ValueError("Could not read any frames from video")

    cap = cv2.VideoCapture(input_video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0
    cap.release()

    analytics["video_info"] = {
        "fps": fps, "total_frames": total_frames,
        "width": width, "height": height, "duration": round(duration, 2)
    }

    # 2. Player detection (YOLOv8x)
    logger.info("Detecting players with YOLOv8x...")
    player_tracker = PlayerTracker(model_path=YOLO_PLAYER_MODEL)
    player_detections = player_tracker.detect_frames(video_frames, read_from_stub=False)

    # 3. Ball detection (custom YOLO)
    logger.info("Detecting ball with custom model...")
    ball_tracker = BallTracker(model_path=BALL_MODEL)
    ball_detections = ball_tracker.detect_frames(video_frames, read_from_stub=False)
    try:
        ball_detections = ball_tracker.interpolate_ball_positions(ball_detections)
    except Exception as e:
        logger.warning(f"Ball interpolation failed: {e}")

    # 4. Court keypoint detection
    logger.info("Detecting court keypoints...")
    court_model = CourtLineDetector(model_path=KEYPOINTS_MODEL)
    try:
        court_keypoints = court_model.predict(video_frames[0])
        if court_keypoints is not None:
            court_keypoints = np.array(court_keypoints).flatten()
            if len(court_keypoints) < 4:
                court_keypoints = None
    except Exception as e:
        logger.warning(f"Court keypoint detection failed: {e}")
        court_keypoints = None

    # 5. Filter players — keep only 2 closest to court
    player_detections = _filter_players_by_court(player_detections, court_keypoints)

    # 6. Mini court setup
    logger.info("Setting up mini court visualization...")
    mini_court = MiniCourt(video_frames[0])

    # 7. Convert positions to mini court coordinates (only if court keypoints detected)
    player_mini_court_positions = {}
    ball_mini_court_positions = {}
    if court_keypoints is not None and len(court_keypoints) >= 28:
        try:
            player_mini_court_positions, ball_mini_court_positions = (
                mini_court.convert_bounding_boxes_to_mini_court_coordinates(
                    player_detections, ball_detections, court_keypoints
                )
            )
        except Exception as e:
            logger.warning(f"Mini court coordinate conversion failed: {e}")
    else:
        logger.info("Court keypoints not detected — skipping mini court positioning")

    # 8. Shot classification
    logger.info("Classifying shots...")
    shot_classifier = ShotClassifier()
    shots = _classify_shots(player_detections, ball_detections, fps)

    # 9. Player stats
    logger.info("Computing player statistics...")
    player_stats = _compute_player_stats(player_detections, ball_detections, fps, width, height)

    # 10. Draw annotations on frames
    logger.info("Drawing annotations on frames...")
    output_frames = _draw_all_annotations(
        video_frames, player_detections, ball_detections,
        court_keypoints, mini_court, player_mini_court_positions,
        ball_mini_court_positions, shots, player_stats, fps
    )

    # 11. Write output video
    logger.info("Writing annotated output video...")
    raw_output = output_video_path + ".raw.mp4"
    save_video(output_frames, raw_output)

    # 12. Convert to H.264 for browser playback
    _convert_to_h264(raw_output, output_video_path)

    # 13. Compile analytics
    ball_positions_list = []
    for frame_num, frame_balls in enumerate(ball_detections):
        for ball_id, bbox in frame_balls.items():
            cx, cy = get_center_of_bbox(bbox)
            ball_positions_list.append({
                "frame": frame_num,
                "x": int(cx), "y": int(cy),
                "time": round(frame_num / fps, 2) if fps > 0 else 0
            })

    player_positions_list = []
    for frame_num, frame_players in enumerate(player_detections):
        for pid, bbox in frame_players.items():
            cx, cy = get_center_of_bbox(bbox)
            player_positions_list.append({
                "frame": frame_num, "player_id": int(pid),
                "x": int(cx), "y": int(cy),
                "time": round(frame_num / fps, 2) if fps > 0 else 0
            })

    analytics["ball_tracking"] = {
        "total_detections": len(ball_positions_list),
        "positions": ball_positions_list[:100],
        "trajectory_points": len(ball_positions_list),
        "speeds": player_stats.get("ball_speeds", [])[:50],
    }
    analytics["player_stats"] = player_stats
    analytics["shot_analysis"] = shots
    analytics["court_keypoints"] = [int(k) for k in court_keypoints] if court_keypoints is not None else []
    analytics["speed_metrics"] = {
        "motion_intensity_score": min(100, max(10, len(ball_positions_list) // 2)),
        "shot_moments_detected": len(shots),
    }

    logger.info(f"Pipeline complete: {len(shots)} shots, {len(ball_positions_list)} ball positions")
    return analytics


def _filter_players_by_court(player_detections, court_keypoints):
    """Keep only the 2 players closest to the court."""
    if court_keypoints is None or len(court_keypoints) < 4:
        return player_detections

    court_center_x = np.mean([court_keypoints[i] for i in range(0, min(len(court_keypoints), 8), 2)])
    court_center_y = np.mean([court_keypoints[i] for i in range(1, min(len(court_keypoints), 8), 2)])

    filtered = []
    for frame_players in player_detections:
        if len(frame_players) <= 2:
            filtered.append(frame_players)
            continue

        distances = {}
        for pid, bbox in frame_players.items():
            cx, cy = get_center_of_bbox(bbox)
            dist = np.sqrt((cx - court_center_x)**2 + (cy - court_center_y)**2)
            distances[pid] = dist

        # Keep 2 closest
        sorted_players = sorted(distances.items(), key=lambda x: x[1])[:2]
        new_frame = {}
        for i, (pid, _) in enumerate(sorted_players):
            new_frame[i + 1] = frame_players[pid]
        filtered.append(new_frame)

    return filtered


def _classify_shots(player_detections, ball_detections, fps):
    """Classify shots based on ball-player proximity and motion patterns."""
    shots = []
    prev_closest = None

    for frame_num in range(1, len(ball_detections)):
        if not ball_detections[frame_num]:
            continue

        for ball_id, ball_bbox in ball_detections[frame_num].items():
            ball_center = get_center_of_bbox(ball_bbox)

            if not player_detections[frame_num]:
                continue

            # Find closest player
            closest_pid = None
            min_dist = float('inf')
            for pid, p_bbox in player_detections[frame_num].items():
                p_center = get_center_of_bbox(p_bbox)
                dist = measure_distance_between_points(ball_center, p_center)
                if dist < min_dist:
                    min_dist = dist
                    closest_pid = pid

            if min_dist > 200:
                continue

            # Detect shot moment: ball changes closest player
            if prev_closest is not None and closest_pid != prev_closest:
                # Determine shot type based on ball and player positions
                p_bbox = player_detections[frame_num].get(prev_closest, {})
                if p_bbox:
                    p_center = get_center_of_bbox(p_bbox)
                    shot_type = _determine_shot_type(ball_center, p_center, ball_bbox, p_bbox)
                    shots.append({
                        "frame_number": frame_num,
                        "shot_type": shot_type,
                        "player_id": int(prev_closest),
                        "time": round(frame_num / fps, 2) if fps > 0 else 0,
                        "notes": f"Player {prev_closest} hit a {shot_type} at {round(frame_num/fps, 1)}s"
                    })

            prev_closest = closest_pid

    return shots[:30]


def _determine_shot_type(ball_center, player_center, ball_bbox, player_bbox):
    """Determine shot type based on geometric relationships."""
    bx, by = ball_center
    px, py = player_center

    # Ball above player significantly → overhead/serve
    if by < py - 100:
        return "serve"

    # Player at bottom → player 1 shots
    p_foot = get_foot_position(player_bbox)

    # Ball on left side relative to player → backhand (for right-handed)
    if bx < px - 30:
        return "backhand"
    elif bx > px + 30:
        return "forehand"

    # Close to net → volley
    if abs(by - py) < 50 and abs(bx - px) < 50:
        return "volley"

    return "forehand"


def _compute_player_stats(player_detections, ball_detections, fps, vid_width, vid_height):
    """Compute speed, distance, court coverage for each player."""
    stats = {
        "total_movement_detections": 0,
        "court_coverage_pct": 0,
        "avg_motion_level": 0,
    }

    player_trails = {1: [], 2: []}
    ball_speeds = []

    for frame_num, frame_players in enumerate(player_detections):
        for pid, bbox in frame_players.items():
            if pid in player_trails:
                cx, cy = get_center_of_bbox(bbox)
                player_trails[pid].append({"x": cx, "y": cy, "frame": frame_num})
                stats["total_movement_detections"] += 1

    # Calculate distances and speeds per player
    for pid in [1, 2]:
        trail = player_trails.get(pid, [])
        if len(trail) < 2:
            continue

        total_dist = 0
        for i in range(1, len(trail)):
            dx = trail[i]["x"] - trail[i-1]["x"]
            dy = trail[i]["y"] - trail[i-1]["y"]
            total_dist += np.sqrt(dx**2 + dy**2)

        stats[f"player_{pid}_total_distance_px"] = round(total_dist, 1)
        duration_s = len(trail) / fps if fps > 0 else 1
        stats[f"player_{pid}_avg_speed_px_s"] = round(total_dist / max(duration_s, 0.1), 1)

    # Ball speed between frames
    prev_ball = None
    for frame_num, frame_balls in enumerate(ball_detections):
        for ball_id, bbox in frame_balls.items():
            ball_center = get_center_of_bbox(bbox)
            if prev_ball is not None:
                dt = 1.0 / fps if fps > 0 else 1
                dist = np.sqrt((ball_center[0] - prev_ball[0])**2 + (ball_center[1] - prev_ball[1])**2)
                speed = dist / dt
                ball_speeds.append({"frame": frame_num, "speed_px_per_sec": round(speed, 1), "time": round(frame_num / fps, 2) if fps > 0 else 0})
            prev_ball = ball_center

    stats["ball_speeds"] = ball_speeds[:100]

    # Court coverage
    all_positions = []
    for pid in [1, 2]:
        all_positions.extend(player_trails.get(pid, []))
    if all_positions and vid_width > 0 and vid_height > 0:
        xs = [p["x"] for p in all_positions]
        ys = [p["y"] for p in all_positions]
        x_range = (max(xs) - min(xs)) / vid_width * 100
        y_range = (max(ys) - min(ys)) / vid_height * 100
        stats["court_coverage_pct"] = round(min(100, (x_range + y_range) / 2), 1)

    # Average motion
    if ball_speeds:
        stats["avg_motion_level"] = round(np.mean([s["speed_px_per_sec"] for s in ball_speeds]), 1)
        stats["max_motion_level"] = round(np.max([s["speed_px_per_sec"] for s in ball_speeds]), 1)
    else:
        stats["avg_motion_level"] = 0
        stats["max_motion_level"] = 0

    return stats


def _draw_all_annotations(video_frames, player_detections, ball_detections,
                          court_keypoints, mini_court, player_mini_positions,
                          ball_mini_positions, shots, player_stats, fps):
    """Draw all Tennis-Vision style annotations on frames."""
    output_frames = []
    total = len(video_frames)
    shot_frames = {s["frame_number"] for s in shots}
    ball_trail = []

    for frame_num in range(len(video_frames)):
        frame = video_frames[frame_num].copy()

        # --- Draw player bounding boxes ---
        if frame_num < len(player_detections):
            for pid, bbox in player_detections[frame_num].items():
                x1, y1, x2, y2 = [int(v) for v in bbox]
                color = (0, 255, 0) if pid == 1 else (0, 200, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                # Corner accents
                l = 20
                cv2.line(frame, (x1, y1), (x1 + l, y1), color, 3)
                cv2.line(frame, (x1, y1), (x1, y1 + l), color, 3)
                cv2.line(frame, (x2, y1), (x2 - l, y1), color, 3)
                cv2.line(frame, (x2, y2), (x2, y2 - l), color, 3)
                cv2.putText(frame, f"P{pid}", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # --- Draw ball with trail ---
        if frame_num < len(ball_detections):
            for ball_id, bbox in ball_detections[frame_num].items():
                cx, cy = int((bbox[0]+bbox[2])/2), int((bbox[1]+bbox[3])/2)
                ball_trail.append((cx, cy))
                # Ball highlight
                cv2.circle(frame, (cx, cy), 8, (0, 255, 255), 2)
                cv2.circle(frame, (cx, cy), 3, (0, 255, 255), -1)

        # Keep trail length
        if len(ball_trail) > 30:
            ball_trail = ball_trail[-30:]

        # Draw trail
        for i in range(1, len(ball_trail)):
            alpha = i / len(ball_trail)
            color = (0, int(255 * alpha), int(255 * alpha))
            thickness = max(1, int(3 * alpha))
            cv2.line(frame, ball_trail[i-1], ball_trail[i], color, thickness)

        # --- Draw court keypoints ---
        if court_keypoints is not None:
            for i in range(0, len(court_keypoints), 2):
                x, y = int(court_keypoints[i]), int(court_keypoints[i+1])
                cv2.circle(frame, (x, y), 4, (0, 100, 255), -1)

        # --- Draw HUD ---
        h, w = frame.shape[:2]
        # Top bar
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 55), (10, 10, 10), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        time_sec = frame_num / fps if fps > 0 else 0
        cv2.putText(frame, "DROPSHOT ANALYTICS", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (206, 255, 0), 2)
        cv2.putText(frame, f"Frame {frame_num}/{total}  |  {time_sec:.1f}s", (15, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        # Shot detection flash
        if frame_num in shot_frames:
            shot_overlay = frame.copy()
            cv2.rectangle(shot_overlay, (0, 0), (w, h), (0, 255, 200), -1)
            cv2.addWeighted(shot_overlay, 0.04, frame, 0.96, 0, frame)
            cv2.putText(frame, "SHOT DETECTED", (w - 260, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 206), 2)

        # Bottom motion bar
        if player_stats.get("ball_speeds"):
            for bs in player_stats["ball_speeds"]:
                if abs(bs.get("frame", -1) - frame_num) < 3:
                    bar_w = min(int(bs["speed_px_per_sec"] / max(player_stats.get("max_motion_level", 1), 1) * w), w)
                    cv2.rectangle(frame, (0, h - 6), (bar_w, h), (206, 255, 0), -1)
                    break

        # --- Draw mini court ---
        try:
            frame = mini_court.draw_background_rectangle(frame)
            frame = mini_court.draw_court_with_styling(frame)

            # Draw player positions on mini court
            if frame_num in player_mini_positions:
                for pid, pos in player_mini_positions[frame_num].items():
                    px, py = int(pos[0]), int(pos[1])
                    color = (0, 200, 0) if pid == 1 else (0, 180, 255)
                    cv2.circle(frame, (px, py), 8, (0, 0, 0), -1)
                    cv2.circle(frame, (px, py), 6, color, -1)

            # Draw ball on mini court
            if frame_num in ball_mini_positions:
                for bid, pos in ball_mini_positions[frame_num].items():
                    bx, by = int(pos[0]), int(pos[1])
                    cv2.circle(frame, (bx, by), 5, (0, 0, 0), -1)
                    cv2.circle(frame, (bx, by), 4, (0, 255, 255), -1)
        except Exception:
            pass  # Mini court drawing is optional

        output_frames.append(frame)

    return output_frames


def _convert_to_h264(raw_path: str, output_path: str):
    """Convert raw OpenCV video to H.264 for browser playback."""
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            output_path
        ], check=True, capture_output=True, timeout=180)
        os.unlink(raw_path)
        logger.info("Output video converted to H.264")
    except Exception as e:
        logger.error(f"H.264 conversion failed: {e}")
        os.replace(raw_path, output_path)
