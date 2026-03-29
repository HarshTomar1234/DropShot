import { useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Upload, VideoCamera, X, Lightning, Target, Gauge, Path,
  Warning, Info
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MAX_DURATION = 30;
const MAX_SIZE_MB = 50;
const VALID_TYPES = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"];

export default function UploadPage() {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [validationError, setValidationError] = useState(null);
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) validateAndSetFile(file);
  }, []);

  const validateAndSetFile = (file) => {
    setValidationError(null);

    if (!VALID_TYPES.includes(file.type)) {
      setValidationError("Invalid format. Upload MP4, MOV, AVI, or WebM.");
      toast.error("Invalid file type.");
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setValidationError(`Too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Max ${MAX_SIZE_MB}MB.`);
      toast.error("File too large.");
      return;
    }
    setSelectedFile(file);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) validateAndSetFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setUploadProgress(0);
    setValidationError(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await axios.post(`${API}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
        onUploadProgress: (e) => {
          const pct = Math.round((e.loaded * 100) / e.total);
          setUploadProgress(pct);
        },
      });

      toast.success("Video uploaded! Processing queued...");
      navigate(`/analysis/${response.data.id}`);
    } catch (error) {
      const msg = error.response?.data?.detail || "Upload failed. Check your connection and try again.";
      setValidationError(msg);
      toast.error(msg);
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const removeFile = () => {
    setSelectedFile(null);
    setUploadProgress(0);
    setValidationError(null);
  };

  const features = [
    { icon: Target, title: "Shot Detection", desc: "AI + CV identifies forehand, backhand, serve & volley from frame analysis" },
    { icon: Path, title: "Ball Tracking", desc: "Real-time trajectory with speed estimation across every frame" },
    { icon: Gauge, title: "Speed Analysis", desc: "Motion intensity scoring, ball speed estimates, and rally tempo" },
    { icon: Lightning, title: "Annotated Video", desc: "H.264 output video with ball trails, player boxes, and shot overlays" },
  ];

  return (
    <div className="max-w-5xl mx-auto px-4 py-12 md:py-20" data-testid="upload-page">
      {/* Hero */}
      <div className="text-center mb-12 animate-slide-up">
        <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>TENNIS VIDEO ANALYTICS ENGINE</p>
        <h1
          className="text-4xl sm:text-5xl lg:text-6xl tracking-tighter font-black mb-4"
          style={{ fontFamily: 'Outfit, sans-serif' }}
        >
          Drop Your Clip.<br />
          <span style={{ color: 'var(--volt-green)' }}>Get The Edge.</span>
        </h1>
        <p className="text-base max-w-xl mx-auto" style={{ color: 'var(--text-secondary)' }}>
          Upload a tennis clip (max {MAX_DURATION}s) and DROPSHOT breaks it down —
          shot detection, ball tracking, player movement, speed analysis, and a fully annotated output video.
        </p>
      </div>

      {/* Upload Zone */}
      <div className="mb-12 animate-slide-up stagger-2" style={{ opacity: 0 }}>
        <div
          className={`upload-zone rounded-md p-8 md:p-12 text-center cursor-pointer ${dragOver ? "drag-over" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !selectedFile && !uploading && fileInputRef.current?.click()}
          data-testid="upload-zone"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/x-msvideo,video/webm"
            className="hidden"
            onChange={handleFileSelect}
            data-testid="file-input"
          />

          {!selectedFile ? (
            <div>
              <div
                className="w-16 h-16 mx-auto mb-4 flex items-center justify-center rounded-md"
                style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
              >
                <Upload size={28} style={{ color: 'var(--volt-green)' }} />
              </div>
              <p className="text-lg font-semibold mb-1" style={{ fontFamily: 'Outfit, sans-serif' }}>
                Drop your tennis clip here
              </p>
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                MP4, MOV, AVI, WebM — Max {MAX_DURATION}s, {MAX_SIZE_MB}MB
              </p>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-center gap-3 mb-4">
                <VideoCamera size={24} style={{ color: 'var(--volt-green)' }} />
                <span className="font-medium truncate max-w-xs">{selectedFile.name}</span>
                <span className="text-sm whitespace-nowrap" style={{ color: 'var(--text-secondary)' }}>
                  ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)
                </span>
                {!uploading && (
                  <button
                    onClick={(e) => { e.stopPropagation(); removeFile(); }}
                    className="ml-2 p-1 rounded transition-colors hover:bg-white/10"
                    data-testid="remove-file-btn"
                  >
                    <X size={18} style={{ color: 'var(--text-secondary)' }} />
                  </button>
                )}
              </div>

              {uploading && (
                <div className="w-full max-w-md mx-auto mb-4">
                  <div className="progress-bar rounded-full">
                    <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }} />
                  </div>
                  <p className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                    {uploadProgress < 100 ? `Uploading... ${uploadProgress}%` : "Processing upload..."}
                  </p>
                </div>
              )}

              {!uploading && (
                <Button
                  onClick={(e) => { e.stopPropagation(); handleUpload(); }}
                  className="px-8 py-3 font-bold text-sm"
                  style={{ background: 'var(--volt-green)', color: 'var(--bg-primary)', borderRadius: 0 }}
                  data-testid="upload-button"
                >
                  <Lightning size={18} weight="fill" className="mr-2" />
                  ANALYZE VIDEO
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Validation Error */}
        {validationError && (
          <div
            className="mt-3 flex items-center gap-2 px-4 py-2 rounded text-sm"
            style={{ background: 'rgba(255,59,48,0.1)', border: '1px solid rgba(255,59,48,0.3)', color: 'var(--accent-danger)' }}
            data-testid="validation-error"
          >
            <Warning size={16} weight="fill" />
            {validationError}
          </div>
        )}

        {/* Info bar */}
        <div
          className="mt-3 flex items-center gap-2 px-4 py-2 rounded text-xs"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
        >
          <Info size={14} />
          Processing takes 2-5 minutes depending on video length (YOLO runs on CPU). Your clip is analyzed with YOLOv8 + ResNet-50 computer vision + Claude Opus 4.6 AI.
        </div>
      </div>

      {/* Features */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {features.map(({ icon: Icon, title, desc }, i) => (
          <div
            key={title}
            className={`stat-card rounded-md animate-slide-up stagger-${i + 3}`}
            style={{ opacity: 0 }}
            data-testid={`feature-card-${title.toLowerCase().replace(/\s/g, '-')}`}
          >
            <Icon size={24} style={{ color: 'var(--volt-green)' }} className="mb-3" />
            <h3 className="font-semibold text-sm mb-1" style={{ fontFamily: 'Outfit, sans-serif' }}>{title}</h3>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
