import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Button, Avatar, Badge } from '../ui';
import { api, type HealthStatus } from '../../api';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation();
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [checkingHealth, setCheckingHealth] = useState(false);
  
  const checkHealth = async () => {
    setCheckingHealth(true);
    try {
      const h = await api.getHealth();
      setHealth(h);
      setHealthError(null);
    } catch (err) {
      setHealth(null);
      setHealthError(err instanceof Error ? err.message : 'Health check failed');
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
    <header className="sticky top-0 z-30 bg-surface/80 backdrop-blur-sm border-b border-border">
      <div className="flex items-center justify-between h-16 px-4 lg:px-6">
        {/* Left side - Mobile menu button + Page title */}
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={onMenuClick}
            className="lg:hidden"
            aria-label="Open navigation menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </Button>
          
          <div className="hidden lg:block">
            <h1 className="text-xl font-semibold text-text-primary">{getPageTitle()}</h1>
            <p className="text-xs text-text-muted">RECALL Memory Engine Dashboard</p>
          </div>
        </div>
        
        {/* Right side - Health status + Quick actions */}
        <div className="flex items-center gap-4">
          {/* Connection status */}
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={checkHealth}
              disabled={checkingHealth}
              aria-label={checkingHealth ? 'Checking connection...' : 'Check API connection'}
            >
              {health && (
                <>
                  <span className={`
                    w-2 h-2 rounded-full
                    ${health.status === 'healthy' ? 'bg-success' : health.status === 'degraded' ? 'bg-warning' : 'bg-error'}
                  `} aria-hidden="true" />
                  <span className="hidden sm:inline text-sm font-medium">
                    {health.status === 'healthy' ? 'Connected' : health.status === 'degraded' ? 'Degraded' : 'Disconnected'}
                  </span>
                </>
              )}
              {!health && (
                <>
                  <span className={`w-2 h-2 rounded-full ${healthError ? 'bg-error' : 'bg-gray-400 animate-pulse'}`} aria-hidden="true" />
                  <span className="hidden sm:inline text-sm font-medium">
                    {healthError ? 'Disconnected' : checkingHealth ? 'Checking…' : 'Unknown'}
                  </span>
                </>
              )}
            </Button>
          </div>
          
          {/* Quick actions */}
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link to="/chat">
                <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                Ask
              </Link>
            </Button>
            <Button variant="primary" size="sm" asChild>
              <Link to="/memories">
                <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add Memory
              </Link>
            </Button>
          </div>
        </div>
      </div>
      
      {/* Health details dropdown - could be expanded later */}
      {healthError && (
        <div className="border-t border-border px-4 lg:px-6 py-2 bg-error/5 text-xs text-error">
          API unreachable: {healthError}. Database, ChromaDB, and Local LLM status are unknown until the API responds.
          <Button variant="ghost" size="sm" onClick={checkHealth} disabled={checkingHealth}>Retry</Button>
        </div>
      )}
      {health && health.status !== 'healthy' && (
        <div className="border-t border-border px-4 lg:px-6 py-2 bg-error/5 text-xs text-error">
          <div className="flex items-center gap-4 flex-wrap">
            <span>
              API reachable | Database: {health.database_connected ? 'Connected' : 'Unavailable'} |
              {' '}ChromaDB: {health.chromadb_connected ? 'Connected' : 'Unavailable'} |
              {' '}Local LLM: {health.local_llm_available ? 'Available' : 'Unavailable'}
            </span>
            <Button variant="ghost" size="sm" onClick={checkHealth} disabled={checkingHealth}>Retry</Button>
          </div>
        </div>
      )}
    </header>
  );
}