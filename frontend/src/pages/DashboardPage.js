import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  TennisBall, Lightning, Target, Gauge,
  ArrowLeft, DownloadSimple, Clock, FilmStrip, Crosshair,
  ArrowsClockwise, XCircle
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import axios from "axios";
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  AreaChart, Area, PieChart, Pie, Cell, BarChart, Bar
} from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function DashboardPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let interval;
    const fetchAnalysis = async () => {
      try {
        const res = await axios.get(`${API}/analyses/${id}`);
        setAnalysis(res.data);
        setLoading(false);
        if (res.data.status === "completed" || res.data.status === "failed") {
          clearInterval(interval);
        }
      } catch {
        toast.error("Failed to load analysis");
        setLoading(false);
      }
    };
    fetchAnalysis();
    interval = setInterval(fetchAnalysis, 2500);
    return () => clearInterval(interval);
  }, [id]);

  const downloadVideo = () => {
    window.open(`${API}/analyses/${id}/output-video?download=true`, '_blank');
  };

  const retryAnalysis = async () => {
    try {
      await axios.post(`${API}/analyses/${id}/retry`);
      toast.success("Re-queued for processing");
      setAnalysis(prev => ({ ...prev, status: "queued", processing_progress: 0 }));
    } catch (e) {
      toast.error(e.response?.data?.detail || "Retry failed");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" data-testid="loading-state">
        <div className="text-center">
          <TennisBall size={48} weight="fill" className="mx-auto mb-4 animate-bounce" style={{ color: 'var(--volt-green)' }} />
          <p style={{ color: 'var(--text-secondary)' }}>Loading analysis...</p>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" data-testid="not-found-state">
        <p className="text-lg mb-4">Analysis not found</p>
        <Button onClick={() => navigate("/")} data-testid="back-home-btn">Go Back</Button>
      </div>
    );
  }

  // Processing / Queued state
  if (["processing", "uploaded", "queued"].includes(analysis.status)) {
    const progress = analysis.processing_progress || 0;
    const steps = [
      { label: "Queued", threshold: 5 },
      { label: "Downloading", threshold: 10 },
      { label: "Compressing", threshold: 20 },
      { label: "Extracting Frames", threshold: 25 },
      { label: "Motion Analysis", threshold: 50 },
      { label: "AI Enhancement", threshold: 65 },
      { label: "Generating Video", threshold: 85 },
      { label: "Uploading Result", threshold: 92 },
      { label: "Finalizing", threshold: 100 },
    ];

    return (
      <div className="max-w-2xl mx-auto px-4 py-20" data-testid="processing-state">
        <Button variant="ghost" onClick={() => navigate("/")} className="mb-8" style={{ color: 'var(--text-secondary)' }} data-testid="back-btn">
          <ArrowLeft size={18} className="mr-2" /> Back
        </Button>
        <div className="text-center">
          <div className="w-20 h-20 mx-auto mb-6 flex items-center justify-center rounded-md" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)' }}>
            <Lightning size={36} weight="fill" className="animate-pulse" style={{ color: 'var(--volt-green)' }} />
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-2" style={{ fontFamily: 'Outfit, sans-serif' }}>
            Analyzing Your Clip
          </h2>
          <p className="text-sm mb-8" style={{ color: 'var(--text-secondary)' }}>
            {analysis.original_filename} — YOLO + ResNet-50 + Claude Opus 4.6 processing
          </p>
          <div className="w-full max-w-md mx-auto mb-3">
            <Progress value={progress} className="h-2" />
          </div>
          <p className="text-sm font-mono mb-8" style={{ color: 'var(--volt-green)' }}>{progress}%</p>
          <div className="grid grid-cols-3 gap-2 max-w-sm mx-auto text-left">
            {steps.map(({ label, threshold }) => {
              const done = progress >= threshold;
              const active = progress >= threshold - 15 && progress < threshold;
              return (
                <div key={label} className="flex items-center gap-2 text-xs py-1"
                  style={{ color: done ? 'var(--volt-green)' : active ? '#fff' : 'var(--text-secondary)' }}>
                  <div className="w-1.5 h-1.5 rounded-full" style={{
                    background: done ? 'var(--volt-green)' : active ? 'var(--volt-green)' : 'var(--border-color)',
                    animation: active ? 'pulse-volt 1s ease-in-out infinite' : 'none'
                  }} />
                  {label}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // Failed state
  if (analysis.status === "failed") {
    return (
      <div className="max-w-2xl mx-auto px-4 py-20 text-center" data-testid="failed-state">
        <XCircle size={48} className="mx-auto mb-4" style={{ color: 'var(--accent-danger)' }} />
        <p className="text-lg mb-2" style={{ color: 'var(--accent-danger)' }}>Processing Failed</p>
        <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>{analysis.error || "An error occurred during analysis"}</p>
        <div className="flex gap-3 justify-center">
          <Button onClick={retryAnalysis} style={{ background: 'var(--volt-green)', color: 'var(--bg-primary)', borderRadius: 0 }} data-testid="retry-btn">
            <ArrowsClockwise size={18} className="mr-2" /> Retry Analysis
          </Button>
          <Button variant="outline" onClick={() => navigate("/")} style={{ borderColor: 'var(--border-color)', borderRadius: 0 }} data-testid="new-upload-btn">
            New Upload
          </Button>
        </div>
      </div>
    );
  }

  // ---- COMPLETED DASHBOARD ----
  const shotTypes = analysis.shot_analysis?.filter(s => s.shot_type).map(s => s.shot_type) || [];
  const shotCounts = shotTypes.reduce((acc, t) => { acc[t] = (acc[t] || 0) + 1; return acc; }, {});
  const shotChartData = Object.entries(shotCounts).map(([name, value]) => ({ name, value }));

  const playerStats = analysis.player_stats || {};
  const speedMetrics = analysis.speed_metrics || {};
  const ballTracking = analysis.ball_tracking || {};
  const tactical = analysis.tactical_analysis || {};

  const radarData = [
    { metric: "Footwork", value: parseInt(playerStats.overall_rating || "7") * 10 },
    { metric: "Power", value: speedMetrics.motion_intensity_score || 50 },
    { metric: "Coverage", value: playerStats.court_coverage_pct || 50 },
    { metric: "Technique", value: parseInt(playerStats.overall_rating || "7") * 10 },
    { metric: "Speed", value: Math.min(100, (speedMetrics.motion_intensity_score || 50) + 20) },
  ];

  const ballPositions = (ballTracking.positions || []).slice(0, 40).map((p, i) => ({ frame: i, x: p.x, y: p.y }));
  const ballSpeeds = (ballTracking.speeds || []).slice(0, 30).map((s, i) => ({ frame: i, speed: s.speed_px_per_sec }));

  const COLORS = ['#CEFF00', '#FFFFFF', '#007AFF', '#FF3B30', '#B3E600'];

  return (
    <div className="max-w-7xl mx-auto px-4 py-8" data-testid="dashboard-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-8 gap-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/")} style={{ color: 'var(--text-secondary)' }} data-testid="dashboard-back-btn">
            <ArrowLeft size={20} />
          </Button>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: 'Outfit, sans-serif' }}>
              Analysis <span style={{ color: 'var(--volt-green)' }}>Complete</span>
            </h1>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {analysis.original_filename} — {analysis.duration_sec?.toFixed(1)}s @ {analysis.fps?.toFixed(0)}fps
            </p>
          </div>
        </div>
        <Button onClick={downloadVideo} className="font-bold" style={{ background: 'var(--volt-green)', color: 'var(--bg-primary)', borderRadius: 0 }} data-testid="download-video-btn">
          <DownloadSimple size={18} className="mr-2" /> DOWNLOAD ANALYZED VIDEO
        </Button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        {[
          { label: "Duration", value: `${analysis.duration_sec?.toFixed(1)}s`, icon: Clock },
          { label: "Frames", value: analysis.total_frames?.toLocaleString(), icon: FilmStrip },
          { label: "Ball Hits", value: ballTracking.total_detections || 0, icon: Crosshair },
          { label: "Coverage", value: `${playerStats.court_coverage_pct || 0}%`, icon: Target },
          { label: "Motion Score", value: speedMetrics.motion_intensity_score || 0, icon: Gauge },
        ].map(({ label, value, icon: Icon }, i) => (
          <div key={label} className={`stat-card rounded-md animate-slide-up stagger-${i + 1}`} data-testid={`stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
            <div className="flex items-center gap-2 mb-2">
              <Icon size={14} style={{ color: 'var(--volt-green)' }} />
              <span className="overline">{label}</span>
            </div>
            <p className="stat-value text-2xl">{value}</p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="w-full justify-start mb-6 rounded-none h-auto p-0 gap-0" style={{ background: 'transparent', borderBottom: '1px solid var(--border-color)' }}>
          {["overview", "shots", "tracking", "video"].map(tab => (
            <TabsTrigger key={tab} value={tab} className="rounded-none px-5 py-3 text-sm font-medium capitalize data-[state=active]:bg-transparent data-[state=active]:shadow-none" style={{ borderBottom: '2px solid transparent' }} data-testid={`tab-${tab}`}>
              {tab}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" data-testid="tab-content-overview">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 stat-card rounded-md">
              <div className="flex items-center gap-2 mb-4">
                <Lightning size={18} style={{ color: 'var(--volt-green)' }} />
                <span className="overline" style={{ color: 'var(--volt-green)' }}>ANALYSIS SUMMARY</span>
              </div>
              <p className="text-base leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{analysis.ai_summary || "Analysis complete."}</p>
              {tactical.strategy_notes && (
                <div className="mt-4 p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                  <p className="overline mb-1">TACTICAL NOTES</p>
                  <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{tactical.strategy_notes}</p>
                </div>
              )}
            </div>

            <div className="stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>PERFORMANCE RADAR</p>
              <ResponsiveContainer width="100%" height={220}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#2A2A2A" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: '#A1A1AA', fontSize: 11 }} />
                  <PolarRadiusAxis tick={false} axisLine={false} domain={[0, 100]} />
                  <Radar dataKey="value" stroke="#CEFF00" fill="#CEFF00" fillOpacity={0.15} strokeWidth={2} />
                </RadarChart>
              </ResponsiveContainer>
              {playerStats.overall_rating && (
                <div className="text-center mt-2">
                  <span className="stat-value text-3xl">{playerStats.overall_rating}</span>
                  <span className="text-sm ml-1" style={{ color: 'var(--text-secondary)' }}>/10</span>
                </div>
              )}
            </div>

            <div className="lg:col-span-2 stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>PLAYER ASSESSMENT</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { label: "Stance", value: playerStats.stance },
                  { label: "Footwork", value: playerStats.footwork },
                  { label: "Swing Technique", value: playerStats.swing_technique },
                  { label: "Positioning", value: playerStats.positioning },
                ].map(({ label, value }) => value && (
                  <div key={label} className="p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                    <p className="overline mb-1">{label}</p>
                    <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{value}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>SPEED METRICS</p>
              <div className="space-y-4">
                {speedMetrics.estimated_ball_speed_mph && (
                  <div>
                    <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Ball Speed</p>
                    <p className="stat-value text-xl">{speedMetrics.estimated_ball_speed_mph}</p>
                    <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>mph (estimated)</p>
                  </div>
                )}
                {speedMetrics.player_movement_intensity && (
                  <div>
                    <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Movement</p>
                    <Badge variant="outline" className="capitalize" style={{ borderColor: 'var(--volt-green)', color: 'var(--volt-green)' }}>{speedMetrics.player_movement_intensity}</Badge>
                  </div>
                )}
                {speedMetrics.rally_tempo && (
                  <div>
                    <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Rally Tempo</p>
                    <Badge variant="outline" className="capitalize" style={{ borderColor: 'var(--accent-info)', color: 'var(--accent-info)' }}>{speedMetrics.rally_tempo}</Badge>
                  </div>
                )}
                <div>
                  <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Shot Moments</p>
                  <p className="stat-value text-2xl">{speedMetrics.shot_moments_detected || 0}</p>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Shots */}
        <TabsContent value="shots" data-testid="tab-content-shots">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>SHOT DISTRIBUTION</p>
              {shotChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={shotChartData} cx="50%" cy="50%" outerRadius={100} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} stroke="#0A0A0A" strokeWidth={2}>
                      {shotChartData.map((e, i) => <Cell key={e.name} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: '#1A1A1A', border: '1px solid #2A2A2A', borderRadius: 4, color: '#fff' }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm py-10 text-center" style={{ color: 'var(--text-secondary)' }}>No shot type data — CV detected {speedMetrics.shot_moments_detected || 0} motion bursts</p>
              )}
            </div>

            <div className="stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>SHOT DETAILS</p>
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {(analysis.shot_analysis || []).map((shot, i) => (
                  <div key={i} className="flex items-center justify-between p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                    <div className="flex items-center gap-3">
                      <Target size={16} style={{ color: 'var(--volt-green)' }} />
                      <div>
                        <p className="text-sm font-medium capitalize">{shot.shot_type || `Moment #${i+1}`}</p>
                        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{shot.notes || `Frame ${shot.frame || '?'}`}</p>
                      </div>
                    </div>
                    {shot.technique_rating && (
                      <div className="text-right">
                        <span className="stat-value text-lg">{shot.technique_rating}</span>
                        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>/10</span>
                      </div>
                    )}
                  </div>
                ))}
                {(!analysis.shot_analysis || analysis.shot_analysis.length === 0) && (
                  <p className="text-sm py-6 text-center" style={{ color: 'var(--text-secondary)' }}>No detailed shot data</p>
                )}
              </div>
            </div>

            {tactical.shot_placement && (
              <div className="lg:col-span-2 stat-card rounded-md">
                <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>TACTICAL ANALYSIS</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                    <p className="overline mb-1">Shot Placement</p>
                    <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{tactical.shot_placement}</p>
                  </div>
                  <div className="p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                    <p className="overline mb-1">Court Coverage</p>
                    <p className="stat-value text-xl">{tactical.court_coverage || `${playerStats.court_coverage_pct || 0}%`}</p>
                  </div>
                  <div className="p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                    <p className="overline mb-1">Strategy</p>
                    <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{tactical.strategy_notes}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </TabsContent>

        {/* Tracking */}
        <TabsContent value="tracking" data-testid="tab-content-tracking">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>BALL TRAJECTORY (X)</p>
              {ballPositions.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={ballPositions}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2A2A2A" />
                    <XAxis dataKey="frame" tick={{ fill: '#A1A1AA', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#A1A1AA', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: '#1A1A1A', border: '1px solid #2A2A2A', borderRadius: 4, color: '#fff' }} />
                    <Area type="monotone" dataKey="x" stroke="#CEFF00" fill="#CEFF00" fillOpacity={0.1} strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : <p className="text-sm py-10 text-center" style={{ color: 'var(--text-secondary)' }}>No tracking data</p>}
            </div>

            <div className="stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>BALL SPEED OVER TIME</p>
              {ballSpeeds.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={ballSpeeds}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2A2A2A" />
                    <XAxis dataKey="frame" tick={{ fill: '#A1A1AA', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#A1A1AA', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: '#1A1A1A', border: '1px solid #2A2A2A', borderRadius: 4, color: '#fff' }} />
                    <Bar dataKey="speed" fill="#CEFF00" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <p className="text-sm py-10 text-center" style={{ color: 'var(--text-secondary)' }}>No speed data</p>}
            </div>

            <div className="lg:col-span-2 stat-card rounded-md">
              <p className="overline mb-4" style={{ color: 'var(--volt-green)' }}>TRACKING STATS</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { l: "Ball Detections", v: ballTracking.total_detections || 0 },
                  { l: "Trajectory Points", v: ballTracking.trajectory_points || 0 },
                  { l: "Player Detections", v: playerStats.total_movement_detections || 0 },
                  { l: "Avg Motion", v: playerStats.avg_motion_level?.toFixed(0) || 0 },
                ].map(({ l, v }) => (
                  <div key={l} className="p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                    <p className="overline mb-1">{l}</p>
                    <p className="stat-value text-xl">{v}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Video */}
        <TabsContent value="video" data-testid="tab-content-video">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="stat-card rounded-md">
              <p className="overline mb-4">ORIGINAL</p>
              <div className="video-container rounded-md aspect-video">
                <video controls className="w-full h-full object-contain" src={`${API}/analyses/${id}/original-video`} data-testid="original-video-player" />
              </div>
              <p className="mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>{analysis.resolution} | {analysis.fps?.toFixed(0)} FPS | {analysis.duration_sec?.toFixed(1)}s</p>
            </div>

            <div className="stat-card rounded-md">
              <div className="flex items-center gap-2 mb-4">
                <span className="overline" style={{ color: 'var(--volt-green)' }}>ANALYZED</span>
                <Badge variant="outline" style={{ borderColor: 'var(--volt-green)', color: 'var(--volt-green)' }}>DROPSHOT</Badge>
              </div>
              <div className="video-container rounded-md aspect-video volt-glow">
                <video controls className="w-full h-full object-contain" src={`${API}/analyses/${id}/output-video`} data-testid="output-video-player" />
              </div>
              <div className="mt-2 flex items-center justify-between">
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Ball tracking + Player boxes + Shot detection</p>
                <Button size="sm" variant="outline" onClick={downloadVideo} style={{ borderColor: 'var(--border-color)', color: 'var(--text-secondary)', borderRadius: 0 }} data-testid="download-btn-inline">
                  <DownloadSimple size={14} className="mr-1" /> Download
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
