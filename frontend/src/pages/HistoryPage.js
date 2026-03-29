import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ClockCounterClockwise, VideoCamera, Trash, CheckCircle,
  Spinner, XCircle, ArrowRight, CaretLeft, CaretRight
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const statusConfig = {
  completed: { icon: CheckCircle, color: "var(--volt-green)", label: "Completed" },
  processing: { icon: Spinner, color: "var(--accent-info)", label: "Processing" },
  uploaded: { icon: Spinner, color: "var(--accent-info)", label: "Queued" },
  queued: { icon: Spinner, color: "var(--accent-info)", label: "Queued" },
  failed: { icon: XCircle, color: "var(--accent-danger)", label: "Failed" },
};

export default function HistoryPage() {
  const [analyses, setAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const navigate = useNavigate();
  const limit = 15;

  useEffect(() => {
    fetchAnalyses();
  }, [page]);

  const fetchAnalyses = async () => {
    try {
      const res = await axios.get(`${API}/analyses?page=${page}&limit=${limit}`);
      setAnalyses(res.data.items || []);
      setTotalPages(res.data.pages || 1);
      setTotal(res.data.total || 0);
    } catch {
      toast.error("Failed to load history");
    }
    setLoading(false);
  };

  const deleteAnalysis = async (id, e) => {
    e.stopPropagation();
    try {
      await axios.delete(`${API}/analyses/${id}`);
      setAnalyses(prev => prev.filter(a => a.id !== id));
      setTotal(prev => prev - 1);
      toast.success("Analysis deleted");
    } catch {
      toast.error("Failed to delete");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" data-testid="history-loading">
        <Spinner size={32} className="animate-spin" style={{ color: 'var(--volt-green)' }} />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-12" data-testid="history-page">
      <div className="flex items-center justify-between mb-8">
        <div>
          <p className="overline mb-2" style={{ color: 'var(--volt-green)' }}>ANALYSIS HISTORY</p>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: 'Outfit, sans-serif' }}>
            Your Analyses
            <span className="text-sm font-normal ml-3" style={{ color: 'var(--text-secondary)' }}>({total} total)</span>
          </h1>
        </div>
        <Button onClick={() => navigate("/")} className="font-bold" style={{ background: 'var(--volt-green)', color: 'var(--bg-primary)', borderRadius: 0 }} data-testid="new-analysis-btn">
          New Analysis
        </Button>
      </div>

      {analyses.length === 0 && page === 1 ? (
        <div className="text-center py-20" data-testid="empty-history">
          <ClockCounterClockwise size={48} className="mx-auto mb-4" style={{ color: 'var(--border-color)' }} />
          <p className="text-lg mb-2">No analyses yet</p>
          <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>Upload a tennis clip to get started</p>
          <Button onClick={() => navigate("/")} style={{ background: 'var(--volt-green)', color: 'var(--bg-primary)', borderRadius: 0 }}>Upload Video</Button>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {analyses.map((a, i) => {
              const config = statusConfig[a.status] || statusConfig.queued;
              const StatusIcon = config.icon;
              return (
                <div
                  key={a.id}
                  onClick={() => navigate(`/analysis/${a.id}`)}
                  className={`stat-card rounded-md cursor-pointer flex items-center justify-between animate-slide-up stagger-${Math.min(i + 1, 6)}`}
                  style={{ opacity: 0 }}
                  data-testid={`analysis-row-${a.id}`}
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 flex items-center justify-center rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                      <VideoCamera size={20} style={{ color: config.color }} />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{a.original_filename}</p>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="flex items-center gap-1 text-xs" style={{ color: config.color }}>
                          <StatusIcon size={12} weight="fill" className={a.status === "processing" ? "animate-spin" : ""} />
                          {config.label}
                        </span>
                        {a.duration_sec && <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{a.duration_sec.toFixed(1)}s</span>}
                        {a.resolution && <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{a.resolution}</span>}
                        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{new Date(a.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="icon" variant="ghost" onClick={(e) => deleteAnalysis(a.id, e)} style={{ color: 'var(--text-secondary)' }} data-testid={`delete-analysis-${a.id}`}>
                      <Trash size={16} />
                    </Button>
                    <ArrowRight size={16} style={{ color: 'var(--text-secondary)' }} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 mt-8">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
                style={{ borderColor: 'var(--border-color)', borderRadius: 0 }}
                data-testid="prev-page-btn"
              >
                <CaretLeft size={16} /> Prev
              </Button>
              <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
                style={{ borderColor: 'var(--border-color)', borderRadius: 0 }}
                data-testid="next-page-btn"
              >
                Next <CaretRight size={16} />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
