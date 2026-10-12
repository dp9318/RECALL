import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Button, Avatar, Badge } from '../ui';
import { api, type HealthStatus } from '../../api';
import { LuBrain, LuSun, LuMoon } from 'react-icons/lu';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation();
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('recall-theme');
      if (stored) return stored === 'dark';
      return true; // Default to dark theme for developer cockpit
    }
    return true;
  });
  
  const toggleTheme = () => {
    const nextDark = !isDarkMode;
    setIsDarkMode(nextDark);
    if (nextDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('recall-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.setAttribute('data-theme', 'light');
      localStorage.setItem('recall-theme', 'light');
    }
  };

  const checkHealth = async () => {
    setCheckingHealth(true);
    try {
      const h = await api.getHealth();
      setHealth(h);
    } catch {
      setHealth({ status: 'unhealthy', api_version: 'unknown', database_connected: false, chromadb_connected: false, local_llm_available: false, timestamp: new Date().toISOString() });
    } finally {
      setCheckingHealth(false);
    }
  };
  
  // Check health on mount and periodically
  useEffect(() => {
    checkHealth();
    const checkInterval = setInterval(checkHealth, 60000);
    return () => clearInterval(checkInterval);
  }, []);
  
  const getPageTitle = () => {
    switch (location.pathname) {
      case '/overview': return 'Overview';
      case '/chat': return 'Chat / Ask RECALL';
      case '/memories': return 'Memory Explorer';
      case '/conflicts': return 'Conflict Center';
      case '/instructions': return 'Custom Instructions';
      case '/settings': return 'Settings';
      default: return 'Dashboard';
    }
  };
  
  return (
    <header className="sticky top-0 z-30 bg-surface/80 backdrop-blur-sm border-b border-border w-full">
      <div className="max-w-7xl mx-auto flex items-center justify-between h-16 px-4 sm:px-6 lg:px-8">
        {/* Left side - Mobile menu button + Page title */}
        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={onMenuClick}
            className="lg:hidden p-2 text-text-secondary hover:text-text-primary"
            aria-label="Open navigation menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </Button>
          
          <div className="min-w-0">
            <h1 className="text-lg sm:text-xl font-bold text-text-primary tracking-tight truncate">{getPageTitle()}</h1>
            <p className="text-xs text-text-muted hidden sm:block truncate">RECALL Persistent Memory Engine</p>
          </div>
        </div>
        
        {/* Right side - Theme toggle + Health status + Quick actions */}
        <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
          {/* Connection status */}
          <div className="flex items-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={checkHealth}
              disabled={checkingHealth}
              aria-label={checkingHealth ? 'Checking connection...' : 'Check API connection'}
              className="px-2 sm:px-3 text-text-secondary hover:text-text-primary"
            >
              {health && (
                <>
                  <span className={`
                    w-2 h-2 rounded-full
                    ${health.status === 'healthy' ? 'bg-success' : health.status === 'degraded' ? 'bg-warning' : 'bg-error'}
                  `} aria-hidden="true" />
                  <span className="hidden md:inline text-xs font-medium ml-1.5">
                    {health.status === 'healthy' ? 'Connected' : health.status === 'degraded' ? 'Degraded' : 'Disconnected'}
                  </span>
                </>
              )}
              {!health && <span className="w-2 h-2 rounded-full bg-gray-400 animate-pulse" aria-hidden="true" />}
            </Button>
          </div>

          {/* Theme toggle */}
          <Button
            variant="ghost"
            onClick={toggleTheme}
            aria-label={isDarkMode ? 'Switch to light theme' : 'Switch to dark theme'}
            title={isDarkMode ? 'Switch to light theme' : 'Switch to dark theme'}
            className="p-0 h-8 w-8 flex items-center justify-center hover:bg-surface-hover rounded-lg"
          >
            {isDarkMode ? (
              <LuSun className="w-5 h-5 shrink-0" style={{ color: '#f59e0b' }} aria-hidden="true" />
            ) : (
              <LuMoon className="w-5 h-5 shrink-0" style={{ color: '#334155' }} aria-hidden="true" />
            )}
          </Button>
          
          {/* Quick actions */}
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link to="/memories" aria-label="List memories" className="inline-flex items-center gap-1.5">
                <LuBrain className="w-4 h-4 shrink-0" aria-hidden="true" />
                <span className="hidden sm:inline">List Memories</span>
                <span className="sm:hidden">Memories</span>
              </Link>
            </Button>
            <Button variant="primary" size="sm" asChild>
              <Link to="/chat" aria-label="Ask RECALL" className="inline-flex items-center gap-1.5">
                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <span>Ask</span>
              </Link>
            </Button>
          </div>
        </div>
      </div>
      
      {/* Health details dropdown */}
      {health && health.status !== 'healthy' && (
        <div className="border-t border-border px-4 sm:px-6 lg:px-8 py-2 bg-error/10 text-xs text-error">
          <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
            <span>API: {health.database_connected ? '✓' : '✗'} Database | {health.chromadb_connected ? '✓' : '✗'} ChromaDB | {health.local_llm_available ? '✓' : '✗'} Local LLM</span>
            <Button variant="ghost" size="sm" onClick={checkHealth} className="text-error hover:bg-error/20">Retry</Button>
          </div>
        </div>
      )}
    </header>
  );
}