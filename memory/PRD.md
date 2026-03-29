# DROPSHOT - Tennis Video Analytics App

## Problem Statement
Build a tennis video analytics app where users upload max 30s tennis clips and receive AI-powered analytics (shot detection, ball tracking, player movement, speed estimation) plus an annotated output video with overlays. Uses Tennis-Vision pipeline (YOLO-based detection) + Claude Opus 4.6 AI.

## Architecture
- **Frontend**: React 18 + TailwindCSS + Shadcn/UI + Recharts + Phosphor Icons
- **Backend**: FastAPI + Tennis-Vision (YOLOv8 + ResNet-50) + Claude Opus 4.6 + Object Storage + MongoDB
- **Pipeline**: Upload > Compress > YOLOv8 Player Detection > Custom YOLO Ball Detection > ResNet-50 Court Keypoints > Mini-Court > Shot Classification > Claude Opus 4.6 > H.264 Video

## Implemented (March 29, 2026)
- Full Tennis-Vision pipeline (YOLOv8s player, custom YOLO ball, ResNet-50 court)
- Claude Opus 4.6 AI expert tennis commentary
- H.264 output video with ball trails, player boxes, court keypoints, mini-court
- Production: rate limiting, compression, retry logic, queue, pagination, validation
- DROPSHOT branding, 4-tab dashboard, Recharts charts, history with pagination
- Detailed GitHub README with architecture diagram

## Models
| Model | Size | Purpose |
|-------|------|---------|
| yolov8s.pt | ~22 MB | Player detection |
| last.pt | 165 MB | Custom ball detection |
| keypoints_model.pth | 91 MB | Court keypoint detection |

## Next Actions
1. User authentication
2. Shareable analysis links
3. GPU acceleration for faster processing
4. PDF report export
5. Side-by-side comparison
