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
  const [memoryType, setMemoryType] = useState('fact');
  const [status, setStatus] = useState('active');
  const [importance, setImportance] = useState(50);
  const [provenance, setProvenance] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [projectId, setProjectId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load memory and projects for edit form
  useEffect(() => {
    if (!id) {
      navigate('/memories');
      return;
    }

    const fetchMemory = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getMemory(id);
        setMemory(data);
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

  if (!memory) {
    return (
      <div className="max-w-3xl mx-auto text-center py-12">
        <svg className="w-16 h-16 mx-auto text-error mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <h2 className="text-xl font-semibold text-text-primary mb-2">Memory not found</h2>
        <p className="text-text-secondary mb-4">Memory not found</p>
        <Button variant="primary" asChild>
          <Link to="/memories">Back to Memories</Link>
        </Button>
      </div>
    );
  }

  // Load projects for the form (run after memory is loaded)
  useEffect(() => {
    if (memory) {
      api.getProjects().then(res => setProjects(res.projects)).catch(console.error);
    }
  }, [memory]);

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const pid = projectId || memory.project_id;
    const pname = projects.find(p => p.project_id === pid)?.name || memory.project_name;

    try {
      await api.updateMemory(id, {
        project_id: pid,
        project_name: pname,
        memory_type: memoryType,
        content: memory.content,
        status: status,
        importance: importance,
        provenance: provenance || memory.provenance,
        lineage: memory.lineage,
        tags: tags,
      });

      navigate(`/memories/${id}`);
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

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header for edit page */}
      <div className="flex items-center justify-between gap-4 mb-6">
        <Link to="/memories" className="text-secondary hover:text-primary">
          ← Back to Memories
        </Link>
        <h1 className="text-2xl font-bold text-text-primary">Edit Memory</h1>
      </div>

      {/* Summary of the memory being edited */}
      <div className="p-4 bg-gray-50 rounded mb-6">
        <div className="flex items-center gap-3">
          <Avatar name={memory.project_name || 'Project'} size="sm" />
        </div>
        <div>
          <p className="text-lg text-text-primary">{memory.content}</p>
          <p className="text-sm text-text-secondary">Memory ID: {memory.memory_id}</p>
        </div>
      </div>

      {/* Project selector */}
      <Card>
        <CardHeader>
          <CardTitle>Project</CardTitle>
        </CardHeader>
        <CardContent>
          <Select
            value={projectId}
            onChange={(e) => setProjectId((e.target as any).value)}
            options={[
              { value: '', label: 'Select project...' },
              ...projects.map(p => ({ value: p.project_id, label: p.name })),
            ]}
            label="Project"
          />
        </CardContent>
      </Card>

      {/* Memory type */}
      <Card>
        <CardHeader>
          <CardTitle>Memory Type</CardTitle>
        </CardHeader>
        <CardContent>
          <Select
            value={memoryType}
            onChange={(e) => setMemoryType((e.target as any).value)}
            options={[
              { value: 'fact', label: 'Fact' },
              { value: 'decision', label: 'Decision' },
              { value: 'pattern', label: 'Pattern' },
              { value: 'preference', label: 'Preference' },
              { value: 'context', label: 'Context' },
              { value: 'constraint', label: 'Constraint' },
            ]}
            label="Type"
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
              { value: 'conflicted', label: 'Conflicted' },
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
            <span className="text-sm text-text-secondary">{importance}</span>
            <input
              type="range"
              min="0"
              max="100"
              value={importance}
              onChange={(e) => setImportance(Number((e.target as any).value))}
              className="w-48 appearance-none rounded-lg bg-primary/20"
              aria-label="Importance"
            />
          </div>
        </CardContent>
      </Card>

      {/* Content */}
      <Card>
        <CardHeader>
          <CardTitle>Content</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-text-primary whitespace-pre-wrap">{memory.content}</p>
          <textarea
            className="mt-2 w-full px-4 py-2 rounded-lg border bg-surface text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            rows={4}
            defaultValue={memory.content}
            readOnly
          />
        </CardContent>
      </Card>

      {/* Provenance */}
      <Card>
        <CardHeader>
          <CardTitle>Provenance</CardTitle>
        </CardHeader>
        <CardContent>
          <Input
            value={provenance}
            onChange={(e) => setProvenance((e.target as any).value)}
            label="Provenance"
            placeholder="e.g., Architecture decision recorded during initial design"
          />
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
        <Button type="submit" variant="primary" onClick={handleUpdate}>Update Memory</Button>
      </div>
    </div>
  );
}