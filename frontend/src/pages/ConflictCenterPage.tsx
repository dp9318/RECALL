import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api, type Conflict, type ConflictListResponse } from '../api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge, type BadgeVariant } from '../components/ui/Badge';
import { Avatar } from '../components/ui/Avatar';
import { Button } from '../components/ui/Button';

type ConflictStatus = 'detected' | 'resolved' | 'partially_resolved' | 'unresolved' | 'abstained';

const STATUS_CONFIG: Record<ConflictStatus, { label: string; color: BadgeVariant }> = {
  detected: { label: 'Detected', color: 'warning' },
  resolved: { label: 'Resolved', color: 'success' },
  partially_resolved: { label: 'Partially Resolved', color: 'info' },
  unresolved: { label: 'Unresolved', color: 'error' },
  abstained: { label: 'Abstained', color: 'default' },
};

interface ConflictMemory {
  memory_id: string;
  content: string;
  status: 'preferred' | 'superseded' | 'conflicting' | 'abstained';
  confidence?: number;
}

export function ConflictCenterPage() {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const fetchConflicts = async () => {
    try {
      setLoading(true);
      setError(null);
      const response: ConflictListResponse = await api.getConflicts();
      setConflicts(response.conflicts);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conflicts');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchConflicts();
  }, []);
  
  const getStatusBadge = (status: Conflict['status']) => {
    const config = STATUS_CONFIG[status];
    return <Badge variant={config.color}>{config.label}</Badge>;
  };
  
  const getMemoryStatusBadge = (status: ConflictMemory['status']) => {
    const colors: Record<ConflictMemory['status'], BadgeVariant> = {
      preferred: 'success',
      superseded: 'warning',
      conflicting: 'error',
      abstained: 'default',
    };
    return <Badge variant={colors[status]} size="sm">{status.replace('_', ' ')}</Badge>;
  };
  
  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="h-8 bg-gray-200 rounded w-1/3" />
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <Card key={i}><CardContent className="pt-6"><div className="h-32 bg-gray-200 rounded" /></CardContent></Card>
          ))}
        </div>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Conflict Center</h1>
          <p className="text-text-secondary mt-1">
            {total} conflict{total !== 1 ? 's' : ''} detected across projects
          </p>
        </div>
        <Button variant="outline" onClick={fetchConflicts}>
          <svg className="w-4 h-4 mr-1.5 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          Refresh
        </Button>
      </div>
      
      {/* Stats Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {(Object.keys(STATUS_CONFIG) as ConflictStatus[]).map((status) => {
          const config = STATUS_CONFIG[status];
          const count = conflicts.filter(c => c.status === status).length;
          return (
            <Card key={status}>
              <CardContent className="pt-6 text-center">
                <p className="text-3xl font-bold text-text-primary">{count}</p>
                <Badge variant={config.color} className="mt-1">{config.label}</Badge>
              </CardContent>
            </Card>
          );
        })}
      </div>
      
      {/* Conflicts List */}
      {error && (
        <Card className="border-error/50">
          <CardContent className="py-8 text-center">
            <svg className="w-12 h-12 mx-auto text-error mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-text-secondary">Failed to load conflicts: {error}</p>
            <Button onClick={fetchConflicts} className="mt-3">Retry</Button>
          </CardContent>
        </Card>
      )}
      
      {conflicts.length === 0 && !error && !loading && (
        <Card>
          <CardContent className="py-12 text-center">
            <svg className="w-16 h-16 mx-auto text-success mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 className="text-xl font-semibold text-text-primary mb-2">No conflicts detected</h2>
            <p className="text-text-secondary">All memories are consistent across projects.</p>
          </CardContent>
        </Card>
      )}
      
      {conflicts.length > 0 && (
        <div className="space-y-4">
          {conflicts.map((conflict) => (
            <Card key={conflict.conflict_id} className="overflow-hidden">
              <CardContent className="p-0">
                <div className="p-4 border-b border-border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <Avatar name={conflict.project_name || 'Project'} size="md" />
                    <div>
                      <Link to={`/memories?project=${conflict.project_id}`} className="font-semibold text-text-primary hover:text-primary">
                        {conflict.project_name || conflict.project_id}
                      </Link>
                      <p className="text-sm text-text-secondary">
                        Detected {new Date(conflict.detected_at).toLocaleString()}
                        {conflict.resolved_at && ` · Resolved ${new Date(conflict.resolved_at).toLocaleString()}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {getStatusBadge(conflict.status)}
                    {conflict.resolution?.local_model_used && (
                      <Badge variant="info" size="sm">
                        <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/>
                        </svg>
                        LLM Used
                      </Badge>
                    )}
                  </div>
                </div>
                
                {/* Conflicting Memories */}
                <div className="p-4 space-y-3">
                  <h4 className="text-sm font-medium text-text-secondary">Conflicting Memories</h4>
                  <div className="space-y-2">
                    {conflict.conflicting_memories.map((cm, i) => (
                      <div
                        key={`${conflict.conflict_id}-${i}`}
                        className="p-3 rounded-lg border border-border bg-gray-50"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm text-text-primary flex-1">{cm.content}</p>
                          {getMemoryStatusBadge(cm.status)}
                        </div>
                        {cm.confidence !== undefined && (
                          <div className="mt-2 flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-primary rounded-full transition-all"
                                style={{ width: `${cm.confidence * 100}%` }}
                              />
                            </div>
                            <span className="text-xs text-text-muted w-12 text-right">
                              {(cm.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
                
                {/* Resolution Details */}
                {conflict.resolution && (
                  <div className="p-4 bg-primary-light/50 border-t border-border">
                    <h4 className="text-sm font-medium text-text-secondary mb-2">Resolution</h4>
                    <p className="text-sm text-text-primary mb-3">{conflict.resolution.reason}</p>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Badge variant="outline">Deterministic: {conflict.resolution.deterministic ? 'Yes' : 'No'}</Badge>
                      <Badge variant="outline">Local LLM: {conflict.resolution.local_model_used ? 'Yes' : 'No'}</Badge>
                      {conflict.resolution.confidence !== undefined && (
                        <Badge variant="outline">Confidence: {(conflict.resolution.confidence * 100).toFixed(0)}%</Badge>
                      )}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {conflict.resolution.preferred_memories.length > 0 && (
                        <div>
                          <span className="text-xs text-text-secondary mr-1">Preferred:</span>
                          {conflict.resolution.preferred_memories.map(mid => (
                            <Button key={mid} variant="ghost" size="sm" asChild>
                              <Link to={`/memories/${mid}`}>{mid}</Link>
                            </Button>
                          ))}
                        </div>
                      )}
                      {conflict.resolution.superseded_memories.length > 0 && (
                        <div>
                          <span className="text-xs text-text-secondary mr-1">Superseded:</span>
                          {conflict.resolution.superseded_memories.map(mid => (
                            <Button key={mid} variant="ghost" size="sm" asChild>
                              <Link to={`/memories/${mid}`} className="text-error">{mid}</Link>
                            </Button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
                
                {/* Actions for unresolved conflicts */}
                {conflict.status === 'unresolved' || conflict.status === 'detected' ? (
                  <div className="p-4 border-t border-border flex gap-2">
                    <Button variant="primary" size="sm">Resolve Manually</Button>
                    <Button variant="outline" size="sm">Request LLM Arbitration</Button>
                    <Button variant="ghost" size="sm">Dismiss</Button>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}