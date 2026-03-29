import { Link, useLocation } from "react-router-dom";
import { TennisBall, VideoCamera, ClockCounterClockwise, Heart } from "@phosphor-icons/react";

export default function Navbar() {
  const location = useLocation();

  const navLinks = [
    { path: "/", label: "Upload", icon: VideoCamera },
    { path: "/history", label: "History", icon: ClockCounterClockwise },
  ];

  return (
    <nav className="glass-nav fixed top-0 left-0 right-0 z-50 h-16" data-testid="navbar">
      <div className="max-w-7xl mx-auto h-full flex items-center justify-between px-4 md:px-6">
        <Link to="/" className="flex items-center gap-2.5 group" data-testid="nav-logo">
          <div className="w-8 h-8 flex items-center justify-center" style={{ color: 'var(--volt-green)' }}>
            <TennisBall size={28} weight="fill" />
          </div>
          <span
            className="text-lg font-bold tracking-tight"
            style={{ fontFamily: 'Outfit, sans-serif' }}
          >
            DROP<span style={{ color: 'var(--volt-green)' }}>SHOT</span>
          </span>
        </Link>

        <div className="flex items-center gap-1">
          {navLinks.map(({ path, label, icon: Icon }) => {
            const isActive = location.pathname === path;
            return (
              <Link
                key={path}
                to={path}
                data-testid={`nav-${label.toLowerCase()}`}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors"
                style={{
                  color: isActive ? 'var(--volt-green)' : 'var(--text-secondary)',
                  borderBottom: isActive ? '2px solid var(--volt-green)' : '2px solid transparent',
                }}
              >
                <Icon size={18} weight={isActive ? "fill" : "regular"} />
                {label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
