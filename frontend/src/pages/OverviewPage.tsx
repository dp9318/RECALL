import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Stats, type Project, type Session } from '../api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Avatar } from '../components/ui/Avatar';

type BadgeColor = 'primary' | 'success' | 'info' | 'warning' | 'error';

interface StatCard {
  label: string;
  value: number | string;
  icon: string;
  color: BadgeColor;
}

export function OverviewPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [statsRes, projectsRes, sessionsRes] = await Promise.all([
        api.getStats(),
        api.getProjects(),
        api.getSessions(),
      ]);
      setStats(statsRes);
      setProjects(projectsRes.projects);
      setSessions(sessionsRes.sessions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load overview data');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchData();
  }, []);
  
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map(i => (
            <Card key={i} className="animate-pulse">
              <CardContent className="pt-6">
                <div className="h-4 bg-gray-200 rounded w-1/4 mb-2" />
                <div className="h-8 bg-gray-200 rounded w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="animate-pulse"><CardContent className="pt-6"><div className="h-64 bg-gray-200 rounded" /></CardContent></Card>
          <Card className="animate-pulse"><CardContent className="pt-6"><div className="h-64 bg-gray-200 rounded" /></CardContent></Card>
        </div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="text-center py-12">
        <svg className="w-16 h-16 mx-auto text-error mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <h2 className="text-xl font-semibold text-text-primary mb-2">Failed to load overview</h2>
        <p className="text-text-secondary mb-4">{error}</p>
        <Button onClick={fetchData}>Retry</Button>
      </div>
    );
  }
  
  const unresolvedColor: BadgeColor = (stats?.unresolved_conflicts ?? 0) > 0 ? 'error' : 'success';
  const indexColor: BadgeColor = stats?.semantic_index_status === 'healthy' ? 'success' : 'warning';
  
  const statCards: StatCard[] = [
    { label: 'Total Memories', value: stats?.total_memories ?? 0, icon: '🧠', color: 'primary' },
    { label: 'Active Memories', value: stats?.active_memories ?? 0, icon: '✅', color: 'success' },
    { label: 'Projects', value: stats?.total_projects ?? 0, icon: '📁', color: 'info' },
    { label: 'Sessions', value: stats?.total_sessions ?? 0, icon: '💬', color: 'warning' },
    { label: 'Custom Instructions', value: stats?.total_instructions ?? 0, icon: '📝', color: 'primary' },
    { label: 'Active Instructions', value: stats?.active_instructions ?? 0, icon: '⚡', color: 'success' },
    { label: 'Unresolved Conflicts', value: stats?.unresolved_conflicts ?? 0, icon: '⚠️', color: unresolvedColor },
    { label: 'Semantic Index', value: stats?.semantic_index_status ?? 'unknown', icon: '🔍', color: indexColor },
  ];
  
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Overview</h1>
          <p className="text-text-secondary mt-1">System-wide memory statistics and recent activity</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/memories">View All Memories</Link>
          </Button>
          <Button variant="primary" asChild>
            <Link to="/chat">Ask RECALL</Link>
          </Button>
        </div>
      </div>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-text-secondary">{stat.label}</p>
                  <p className="text-3xl font-bold text-text-primary mt-1">
                    {typeof stat.value === 'number' ? stat.value.toLocaleString() : stat.value}
                  </p>
                </div>
                <span className="text-3xl" aria-hidden="true">{stat.icon}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      
      {/* Projects & Recent Sessions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Projects */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Projects</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/settings">View All</Link>
            </Button>
          </CardHeader>
          <CardContent className="pt-0">
            {projects.length === 0 ? (
              <div className="text-center py-8">
                <svg className="w-12 h-12 mx-auto text-text-muted mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                <p className="text-text-secondary">No projects yet</p>
                <Button size="sm" className="mt-2" asChild>
                  <Link to="/settings">Create Project</Link>
                </Button>
              </div>
            ) : (
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {projects.slice(0, 5).map((project) => (
                  <Link
                    key={project.project_id}
                    to={`/memories?project=${project.project_id}`}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <Avatar name={project.name} size="md" />
                      <div className="min-w-0">
                        <p className="font-medium text-text-primary truncate">{project.name}</p>
                        <p className="text-sm text-text-secondary truncate">{project.description || 'No description'}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" size="sm">{project.memory_count} memories</Badge>
                      <Badge variant="outline" size="sm">{project.session_count} sessions</Badge>
                    </div>
                  </Link>
                ))}
                {projects.length > 5 && (
                  <Button variant="ghost" size="sm" className="w-full" asChild>
                    <Link to="/settings">View all {projects.length} projects</Link>
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
        
        {/* Recent Sessions */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Sessions</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/settings">View All</Link>
            </Button>
          </CardHeader>
          <CardContent className="pt-0">
            {sessions.length === 0 ? (
              <div className="text-center py-8">
                <svg className="w-12 h-12 mx-auto text-text-muted mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-text-secondary">No recent sessions</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {sessions.slice(0, 5).map((session) => (
                  <div
                    key={session.session_id}
                    className="p-3 rounded-lg hover:bg-gray-50 transition-colors border border-border"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-text-primary truncate">{session.project_name}</p>
                        <p className="text-sm text-text-secondary">
                          {new Date(session.started_at).toLocaleString()} · {session.message_count} messages · {session.memory_captures} memories
                        </p>
                      </div>
                      {session.ended_at && (
                        <span className="text-xs text-text-muted whitespace-nowrap">
                          Ended {new Date(session.ended_at).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
                {sessions.length > 5 && (
                  <Button variant="ghost" size="sm" className="w-full" asChild>
                    <Link to="/settings">View all {sessions.length} sessions</Link>
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      
      {/* System Status */}
      <Card>
        <CardHeader>
          <CardTitle>System Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-lg bg-gray-50">
              <p className="text-sm text-text-secondary">Database</p>
              <p className="font-medium text-text-primary flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${stats?.database_connected ? 'bg-success' : 'bg-error'}`} />
                {stats?.database_connected ? 'Connected' : 'Disconnected'}
              </p>
            </div>
            <div className="p-4 rounded-lg bg-gray-50">
              <p className="text-sm text-text-secondary">ChromaDB</p>
              <p className="font-medium text-text-primary flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${stats?.chromadb_connected ? 'bg-success' : 'bg-error'}`} />
                {stats?.chromadb_connected ? 'Connected' : 'Disconnected'}
              </p>
            </div>
            <div className="p-4 rounded-lg bg-gray-50">
              <p className="text-sm text-text-secondary">Local LLM</p>
              <p className="font-medium text-text-primary flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${stats?.local_llm_available ? 'bg-success' : 'bg-warning'}`} />
                {stats?.local_llm_available ? 'Available' : 'Unavailable'}
              </p>
            </div>
            <div className="p-4 rounded-lg bg-gray-50">
              <p className="text-sm text-text-secondary">Last Indexed</p>
              <p className="font-medium text-text-primary">
                {stats?.last_indexed_at ? new Date(stats.last_indexed_at).toLocaleString() : 'Never'}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}