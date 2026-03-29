# DROPSHOT - Tennis Video Analytics App

## Problem Statement
Build a tennis video analytics app where users upload max 30s tennis clips and receive AI-powered analytics (shot detection, ball tracking, player movement, speed estimation) plus an annotated output video with overlays.

## Architecture
- **Frontend**: React + TailwindCSS + Shadcn UI + Recharts + Phosphor Icons
- **Backend**: FastAPI + OpenCV + GPT-5.2 Vision + Object Storage + MongoDB
- **Processing Pipeline**: Upload → Compress → OpenCV Analysis → GPT Enhancement → Annotated Video → Storage

## What's Been Implemented (March 29, 2026)
- Full video upload with drag-and-drop (MP4, MOV, AVI, WebM)
- OpenCV-based ball tracking, player detection, motion analysis, speed estimation
- GPT-5.2 Vision supplementary analysis (shot types, player assessment, tactical notes)
- H.264 annotated output video with ball trails, player boxes, shot detection overlays
- Production hardening: rate limiting, video compression, retry logic, processing queue (max 3), pagination, validation
- DROPSHOT branding with Outfit/Manrope fonts, volt green (#CEFF00) dark theme
- Dashboard with 4 tabs: Overview, Shots, Tracking, Video
- Recharts visualizations: radar chart, pie chart, area charts, bar charts
- History page with pagination
- Retry failed analyses
- Health check endpoint

## User Personas
- Tennis players wanting swing analysis
- Coaches reviewing player footage
- Tennis enthusiasts analyzing pro clips

## Prioritized Backlog
### P0 (Critical)
- [x] Video upload and processing
- [x] OpenCV analysis pipeline
- [x] AI-enhanced analysis
- [x] Output video with overlays
- [x] Analytics dashboard

### P1 (Important)
- [ ] User authentication (login/signup)
- [ ] Share analysis via link
- [ ] Side-by-side video comparison
- [ ] PDF report export

### P2 (Nice to have)
- [ ] Multi-video batch upload
- [ ] Training progress tracking over time
- [ ] Court heatmap visualization
- [ ] Social sharing (Twitter/Instagram cards)
- [ ] Mobile-optimized video capture

## Next Action Items
1. Add user auth to isolate analyses per user
2. Implement shareable public links for analyses
3. Add PDF/report export for coaching sessions
4. Side-by-side comparison of two clips
