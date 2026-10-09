import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, type Memory } from '../api';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Avatar } from '../components/ui/Avatar';

export function MemoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  useEffect(() => {
    if (!id) return;
    
    const fetchMemory = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getMemory(id);
        setMemory(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load memory');
      } finally {
        setLoading(false);
      }
    };
    
    fetchMemory();
  }, [id]);
  
  if (loading) {
    return (
      <div className="max-w-3xl mx-auto space-y-6 animate-pulse">
        <Card><CardContent className="pt-6"><div className="h-8 bg-gray-200 rounded w-1/3 mb-2" /><div className="h-4 bg-gray-200 rounded w-1/4" /></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="h-32 bg-gray-200 rounded" /></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="h-4 bg-gray-200 rounded w-1/2 mb-2" /><div className="h-4 bg-gray-200 rounded w-1/3" /></CardContent></Card>
      </div>
    );
  }
  
  if (error || !memory) {
    return (
      <div className="max-w-3xl mx-auto text-center py-12">
        <svg className="w-16 h-16 mx-auto text-error mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <h2 className="text-xl font-semibold text-text-primary mb-2">Memory not found</h2>
        <p className="text-text-secondary mb-4">{error || `Memory ${id} does not exist`}</p>
        <Button variant="primary" asChild>
          <Link to="/memories">Back to Memories</Link>
        </Button>
      </div>
    );
  }
  
  const getStatusColor = (status: Memory['status']) => {
    switch (status) {
      case 'active': return 'success';
      case 'superseded': return 'warning';
      case 'conflicted': return 'error';
      default: return 'default';
    }
  };
  
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/memories">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </Link>
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Memory Details</h1>
            <p className="text-text-secondary">View and manage memory record</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to={`/memories/${memory.memory_id}/edit`}>Edit</Link>
          </Button>
          <Button variant="danger">Delete</Button>
        </div>
      </div>
      
      {/* Main Content */}
      <Card>
        <CardHeader className="flex flex-row items-start justify-between">
          <div className="flex items-center gap-3">
            <Avatar name={memory.project_name || 'Project'} size="lg" />
            <div>
              <Link to={`/memories?project=${memory.project_id}`} className="font-semibold text-text-primary hover:text-primary">
                {memory.project_name || memory.project_id}
              </Link>
              <p className="text-sm text-text-secondary">{memory.provenance}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={getStatusColor(memory.status)}>{memory.status}</Badge>
            <Badge variant="outline">{memory.memory_type}</Badge>
            <Badge variant="outline">Importance: {memory.importance}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="prose prose-sm max-w-none text-text-primary whitespace-pre-wrap">
            {memory.content}
          </div>
        </CardContent>
      </Card>
      
      {/* Metadata */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Metadata</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-4">
              <div>
                <dt className="text-sm text-text-secondary">Memory ID</dt>
                <dd className="font-mono text-sm text-text-primary break-all">{memory.memory_id}</dd>
              </div>
              <div>
                <dt className="text-sm text-text-secondary">Project ID</dt>
                <dd className="font-mono text-sm text-text-primary">{memory.project_id}</dd>
              </div>
              <div>
                <dt className="text-sm text-text-secondary">Created</dt>
                <dd className="text-sm text-text-primary">{new Date(memory.created_at).toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-sm text-text-secondary">Last Updated</dt>
                <dd className="text-sm text-text-primary">{new Date(memory.updated_at).toLocaleString()}</dd>
              </div>
              {memory.tags && memory.tags.length > 0 && (
                <div>
                  <dt className="text-sm text-text-secondary">Tags</dt>
                  <dd className="flex flex-wrap gap-1 mt-1">
                    {memory.tags.map(tag => (
                      <Badge key={tag} variant="outline" size="sm">#{tag}</Badge>
                    ))}
                  </dd>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle>Lineage & Relationships</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-4">
              {memory.lineage.supersedes && (
                <div>
                  <dt className="text-sm text-text-secondary">Supersedes</dt>
                  <dd className="flex items-center gap-2 mt-1">
                    <Button variant="ghost" size="sm" asChild>
                      <Link to={`/memories/${memory.lineage.supersedes!}`}>{memory.lineage.supersedes}</Link>
                    </Button>
                  </dd>
                </div>
              )}
              {memory.lineage.superseded_by && (
                <div>
                  <dt className="text-sm text-text-secondary">Superseded By</dt>
                  <dd className="flex items-center gap-2 mt-1">
                    <Button variant="ghost" size="sm" asChild>
                      <Link to={`/memories/${memory.lineage.superseded_by!}`}>{memory.lineage.superseded_by}</Link>
                    </Button>
                  </dd>
                </div>
              )}
              {memory.lineage.related_memories && memory.lineage.related_memories.length > 0 && (
                <div>
                  <dt className="text-sm text-text-secondary">Related Memories</dt>
                  <dd className="flex flex-wrap gap-1 mt-1">
                    {memory.lineage.related_memories.map(relId => (
                      <Button key={relId} variant="ghost" size="sm" asChild>
                        <Link to={`/memories/${relId}`}>{relId}</Link>
                      </Button>
                    ))}
                  </dd>
                </div>
              )}
              {!memory.lineage.supersedes && !memory.lineage.superseded_by && (!memory.lineage.related_memories || memory.lineage.related_memories.length === 0) && (
                <p className="text-text-secondary text-center py-4">No lineage relationships recorded</p>
              )}
            </dl>
          </CardContent>
        </Card>
      </div>
      
      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" asChild>
              <Link to={`/memories/${memory.memory_id}/edit`}>Edit Memory</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to={`/memories?project=${memory.project_id}`}>Back to Project Memories</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/memories">All Memories</Link>
            </Button>
            <Button variant="danger">Delete Memory</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}