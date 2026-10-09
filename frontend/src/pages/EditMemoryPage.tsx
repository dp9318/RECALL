import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useParams } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import { api, type Memory, type Project } from '../api';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Select } from '../components/ui/Select';
import { Card, CardHeader, CardContent, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Avatar } from '../components/ui/Avatar';

export function EditMemoryPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [content, setContent] = useState('');
  const [memoryType, setMemoryType] = useState<Memory['memory_type']>('fact');
  const [status, setStatus] = useState<Memory['status']>('active');
  const [importance, setImportance] = useState(50);
  const [provenance, setProvenance] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [projectId, setProjectId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load memory and projects for edit form
  const memoryId = id ?? '';

  useEffect(() => {
    if (!memoryId) {
      navigate('/memories');
      return;
    }

    const fetchMemory = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getMemory(memoryId);
        setMemory(data);
        setContent(data.content || '');
        setMemoryType(data.memory_type || 'fact');
        setStatus(data.status || 'active');
        setImportance(data.importance ?? 50);
        setProvenance(data.provenance || '');
        setTags(data.tags || []);
        setProjectId(data.project_id || '');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load memory for edit');
        navigate('/memories');
      } finally {
        setLoading(false);
      }
    };

    const fetchProjects = async () => {
      try {
        const data = await api.getProjects();
        setProjects(data.projects);
      } catch (err) {
        console.error('Failed to load projects:', err);
      }
    };

    fetchProjects();
    fetchMemory();
  }, [id]);

  if (!memory && !loading) {
    return (
      <div className="max-w-3xl mx-auto text-center py-12">
        <svg className="w-16 h-16 mx-auto text-error mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <h2 className="text-xl font-semibold text-text-primary mb-2">Memory not found</h2>
        <p className="text-text-secondary mb-4">Memory not found</p>
        <Button variant="primary" asChild>
          <Link to="/memories">Back to Memories</Link>
        </Button>
      </div>
    );
  }

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!memoryId) {
      navigate('/memories');
      return;
    }

    if (!content.trim()) {
      setError('Memory content cannot be empty');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await api.updateMemory(memoryId, {
        content: content.trim(),
        status: status,
        importance: importance,
        tags: tags,
      });

      navigate(`/memories/${memoryId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update memory');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto animate-pulse space-y-6">
        <Card><CardContent className="pt-6"><div className="h-8 bg-gray-200 rounded w-1/3 mb-2" /><div className="h-4 bg-gray-200 rounded w-1/4" /></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="h-32 bg-gray-200 rounded" /></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="h-4 bg-gray-200 rounded w-1/2 mb-2" /><div className="h-4 bg-gray-200 rounded w-1/3" /></CardContent></Card>
      </div>
    );
  }

  if (!memory) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center gap-4 mb-6">
          <Link to="/memories" className="text-secondary hover:text-primary">
            ← Back to Memories
          </Link>
          <h1 className="text-2xl font-bold text-text-primary">Memory Not Found</h1>
        </div>
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
          {error || 'Memory could not be loaded.'}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header for edit page */}
      <div className="flex items-center justify-between gap-4 mb-6">
        <Link to={`/memories/${id}`} className="text-secondary hover:text-primary">
          ← Back to Memory
        </Link>
        <h1 className="text-2xl font-bold text-text-primary">Edit Memory</h1>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm mb-4">
          {error}
        </div>
      )}

      {/* Summary of the memory being edited */}
      <div className="p-4 bg-gray-50 rounded mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Avatar name={memory.project_name || (memory.project_id ? 'Project' : 'Global')} size="sm" />
          <div>
            <p className="font-medium text-text-primary">
              {memory.project_name || (memory.project_id ? memory.project_id : 'Global Scope')}
            </p>
            <p className="text-xs text-text-secondary">ID: {memory.memory_id}</p>
          </div>
        </div>
        <Badge variant={status === 'active' ? 'success' : status === 'superseded' ? 'warning' : 'default'}>
          {status}
        </Badge>
      </div>

      <form onSubmit={handleUpdate} className="space-y-6">
        {/* Content */}
        <Card>
          <CardHeader>
            <CardTitle>Content</CardTitle>
          </CardHeader>
          <CardContent>
            <textarea
              className="w-full px-4 py-2 rounded-lg border bg-surface text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
              rows={5}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Enter memory content..."
              required
            />
          </CardContent>
        </Card>

        {/* Status */}
        <Card>
          <CardHeader>
            <CardTitle>Status</CardTitle>
          </CardHeader>
          <CardContent>
            <Select
              value={status}
              onChange={(e) => setStatus((e.target as any).value)}
              options={[
                { value: 'active', label: 'Active' },
                { value: 'superseded', label: 'Superseded' },
                { value: 'archived', label: 'Archived' },
              ]}
              label="Status"
            />
          </CardContent>
        </Card>

        {/* Importance */}
        <Card>
          <CardHeader>
            <CardTitle>Importance (0-100)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <span className="text-sm font-semibold text-text-primary w-8">{importance}</span>
              <input
                type="range"
                min="0"
                max="100"
                value={importance}
                onChange={(e) => setImportance(Number((e.target as any).value))}
                className="w-64 appearance-none rounded-lg bg-primary/20"
                aria-label="Importance"
              />
            </div>
          </CardContent>
        </Card>

        {/* Tags */}
        <Card>
          <CardHeader>
            <CardTitle>Tags (comma-separated, optional)</CardTitle>
          </CardHeader>
          <CardContent>
            <Input
              value={tags.join(', ')}
              onChange={(e) => setTags((e.target.value || '').split(',').map(t => t.trim()).filter(t => t.length > 0))}
              label="Tags"
              placeholder="architecture, database, core"
            />
            <p className="text-xs text-text-muted mt-1">Leave blank if none.</p>
          </CardContent>
        </Card>

        {/* Actions */}
        <div className="flex gap-3 pt-4 border-t border-border">
          <Button type="button" variant="outline" onClick={() => navigate(`/memories/${id}`)}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={loading || !content.trim()}>
            {loading ? 'Updating...' : 'Update Memory'}
          </Button>
        </div>
      </form>
    </div>
  );
}