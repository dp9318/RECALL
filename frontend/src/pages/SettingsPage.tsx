import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api, type Project, type Session, type Stats, type HealthStatus } from '../api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Avatar } from '../components/ui/Avatar';

export function SettingsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'projects' | 'sessions' | 'system' | 'api'>('projects');
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  
  const fetchData = async () => {
    try {
      setLoading(true);
      const [projectsRes, sessionsRes, statsRes, healthRes] = await Promise.all([
        api.getProjects(),
        api.getSessions(),
        api.getStats(),
        api.getHealth(),
      ]);
      setProjects(projectsRes.projects);
      setSessions(sessionsRes.sessions);
      setStats(statsRes);
      setHealth(healthRes);
    } catch (err) {
      console.error('Failed to load settings data:', err);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchData();
  }, []);
  
  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newProjectName.trim();
    if (!name || creating) return;
    
    setCreating(true);
    setCreateError(null);
    try {
      await api.createProject({
        name,
        description: newProjectDesc.trim() || undefined,
      });
      setNewProjectName('');
      setNewProjectDesc('');
      await fetchData();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create project');
      console.error('Failed to create project:', err);
    } finally {
      setCreating(false);
    }
  };
  
  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-gray-200 rounded w-1/3" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card><CardContent className="pt-6"><div className="h-64 bg-gray-200 rounded" /></CardContent></Card>
          <Card className="lg:col-span-2"><CardContent className="pt-6"><div className="h-64 bg-gray-200 rounded" /></CardContent></Card>
        </div>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        <p className="text-text-secondary mt-1">Manage projects, sessions, and system configuration</p>
      </div>
      
      {/* Tabs */}
      <div className="border-b border-border">
        <nav className="flex gap-1" aria-label="Settings tabs">
          {[
            { id: 'projects', label: 'Projects', count: projects.length },
            { id: 'sessions', label: 'Sessions', count: sessions.length },
            { id: 'system', label: 'System', count: null },
            { id: 'api', label: 'API', count: null },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as typeof activeTab)}
              className={`
                px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-all
                ${activeTab === tab.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-secondary hover:text-text-primary hover:border-gray-300'
                }
              `}
            >
              {tab.label}
              {tab.count !== null && (
                <span className="ml-2 px-2 py-0.5 text-xs bg-gray-100 rounded-full">{tab.count}</span>
              )}
            </button>
          ))}
        </nav>
      </div>
      
      {/* Projects Tab */}
      {activeTab === 'projects' && (
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Projects</CardTitle>
              <Button variant="outline" size="sm" onClick={() => setActiveTab('projects')}>
                <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                New Project
              </Button>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreateProject} className="mb-6 p-4 bg-gray-50 rounded-lg">
                {createError && (
                  <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-md text-sm">
                    {createError}
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Input
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    label="Project Name"
                    placeholder="My Project"
                    required
                  />
                  <Input
                    value={newProjectDesc}
                    onChange={(e) => setNewProjectDesc(e.target.value)}
                    label="Description (optional)"
                    placeholder="Project description"
                  />
                  <div className="flex items-end">
                    <Button type="submit" disabled={creating || !newProjectName.trim()}>
                      {creating ? 'Creating...' : 'Create Project'}
                    </Button>
                  </div>
                </div>
              </form>
              
              {projects.length === 0 ? (
                <div className="text-center py-8">
                  <svg className="w-12 h-12 mx-auto text-text-muted mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                  </svg>
                  <p className="text-text-secondary">No projects yet. Create your first project above.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {projects.map(project => (
                    <div
                      key={project.project_id}
                      className="flex flex-col sm:flex-row sm:items-center sm:justify-between p-4 rounded-lg border border-border hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center gap-3 mb-3 sm:mb-0">
                        <Avatar name={project.name} size="md" />
                        <div>
                          <Link to={`/memories?project=${project.project_id}`} className="font-semibold text-text-primary hover:text-primary">
                            {project.name}
                          </Link>
                          <p className="text-sm text-text-secondary">{project.description || 'No description'}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <Badge variant="outline" size="sm">{project.memory_count} memories</Badge>
                        <Badge variant="outline" size="sm">{project.session_count} sessions</Badge>
                        <span className="text-xs text-text-muted">
                          Updated {new Date(project.updated_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
      
      {/* Sessions Tab */}
      {activeTab === 'sessions' && (
        <Card>
          <CardHeader>
            <CardTitle>Recent Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            {sessions.length === 0 ? (
              <div className="text-center py-8">
                <svg className="w-12 h-12 mx-auto text-text-muted mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-text-secondary">No sessions recorded</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {sessions.map(session => (
                  <div
                    key={session.session_id}
                    className="p-4 rounded-lg border border-border hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <Avatar name={session.project_name} size="sm" />
                        <div>
                          <p className="font-medium text-text-primary">{session.project_name}</p>
                          <p className="text-sm text-text-secondary">
                            {new Date(session.started_at).toLocaleString()} · {session.message_count} messages · {session.memory_captures} memories
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 text-sm text-text-muted">
                        {session.ended_at && (
                          <span>Ended {new Date(session.ended_at).toLocaleTimeString()}</span>
                        )}
                        <span className="font-mono">{session.session_id.slice(0, 8)}...</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
      
      {/* System Tab */}
      {activeTab === 'system' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>System Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              {stats && (
                <dl className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Total Memories</dt>
                      <dd className="text-2xl font-bold text-text-primary">{stats.total_memories}</dd>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Active Memories</dt>
                      <dd className="text-2xl font-bold text-success">{stats.active_memories}</dd>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Projects</dt>
                      <dd className="text-2xl font-bold text-text-primary">{stats.total_projects}</dd>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Sessions</dt>
                      <dd className="text-2xl font-bold text-text-primary">{stats.total_sessions}</dd>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Instructions</dt>
                      <dd className="text-2xl font-bold text-text-primary">{stats.total_instructions}</dd>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Active Instructions</dt>
                      <dd className="text-2xl font-bold text-success">{stats.active_instructions}</dd>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Unresolved Conflicts</dt>
                      <dd className="text-2xl font-bold {stats.unresolved_conflicts > 0 ? 'text-error' : 'text-success'}">{stats.unresolved_conflicts}</dd>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50">
                      <dt className="text-sm text-text-secondary">Semantic Index</dt>
                      <dd className="flex items-center gap-2">
                        <Badge variant={stats.semantic_index_status === 'healthy' ? 'success' : 'warning'}>
                          {stats.semantic_index_status}
                        </Badge>
                      </dd>
                    </div>
                  </div>
                  {stats.last_indexed_at && (
                    <div className="pt-4 border-t border-border">
                      <dt className="text-sm text-text-secondary">Last Indexed</dt>
                      <dd className="text-text-primary">{new Date(stats.last_indexed_at).toLocaleString()}</dd>
                    </div>
                  )}
                </dl>
              )}
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader>
              <CardTitle>Health Status</CardTitle>
            </CardHeader>
            <CardContent>
              {health && (
                <dl className="space-y-4">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                    <dt className="text-sm text-text-secondary">Overall Status</dt>
                    <dd className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${health.status === 'healthy' ? 'bg-success' : health.status === 'degraded' ? 'bg-warning' : 'bg-error'}`} />
                      <span className="font-medium capitalize">{health.status}</span>
                    </dd>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                    <dt className="text-sm text-text-secondary">Database</dt>
                    <dd className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${health.database_connected ? 'bg-success' : 'bg-error'}`} />
                      <span>{health.database_connected ? 'Connected' : 'Disconnected'}</span>
                    </dd>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                    <dt className="text-sm text-text-secondary">ChromaDB</dt>
                    <dd className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${health.chromadb_connected ? 'bg-success' : 'bg-error'}`} />
                      <span>{health.chromadb_connected ? 'Connected' : 'Disconnected'}</span>
                    </dd>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                    <dt className="text-sm text-text-secondary">Local LLM</dt>
                    <dd className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${health.local_llm_available ? 'bg-success' : 'bg-warning'}`} />
                      <span>{health.local_llm_available ? 'Available' : 'Unavailable'}</span>
                    </dd>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                    <dt className="text-sm text-text-secondary">API Version</dt>
                    <dd className="font-mono text-sm">{health.api_version}</dd>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                    <dt className="text-sm text-text-secondary">Last Check</dt>
                    <dd className="text-text-muted">{new Date(health.timestamp).toLocaleString()}</dd>
                  </div>
                </dl>
              )}
            </CardContent>
          </Card>
        </div>
      )}
      
      {/* API Tab */}
      {activeTab === 'api' && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>API Configuration</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1">API Base URL</label>
                  <Input
                    value={import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'}
                    disabled
                    helperText="Configured via VITE_API_BASE_URL environment variable"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1">Mock API Mode</label>
                  <Input
                    value={import.meta.env.VITE_USE_MOCK_API === 'true' ? 'Enabled (Explicit Opt-In)' : 'Disabled (Default)'}
                    disabled
                    helperText="Set VITE_USE_MOCK_API=true only for UI-only mock development; otherwise use the real backend API."
                  />
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader>
              <CardTitle>Available Endpoints</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                {[
                  'GET /health',
                  'GET /projects',
                  'GET /memories',
                  'GET /memories/{id}',
                  'POST /memories',
                  'PATCH /memories/{id}',
                  'DELETE /memories/{id}',
                  'GET /custom-instructions',
                  'POST /custom-instructions',
                  'PATCH /custom-instructions/{id}',
                  'DELETE /custom-instructions/{id}',
                  'GET /conflicts',
                  'GET /sessions',
                  'GET /stats',
                  'POST /context/query',
                  'POST /context/compact',
                ].map(endpoint => (
                  <code key={endpoint} className="block px-3 py-2 bg-gray-100 rounded font-mono text-primary">{endpoint}</code>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}