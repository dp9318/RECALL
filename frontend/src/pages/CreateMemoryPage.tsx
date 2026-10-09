import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import { api, type Memory, type MemoryQuery, type Project } from '../api';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Avatar } from '../components/ui/Avatar';

const MEMORY_TYPE_OPTIONS = [
  { value: 'fact', label: 'Fact' },
  { value: 'decision', label: 'Decision' },
  { value: 'pattern', label: 'Pattern' },
  { value: 'preference', label: 'Preference' },
  { value: 'context', label: 'Context' },
  { value: 'constraint', label: 'Constraint' },
];

const MEMORY_STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'superseded', label: 'Superseded' },
  { value: 'archived', label: 'Archived' },
  { value: 'conflicted', label: 'Conflicted' },
];

export function CreateMemoryPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [memoryType, setMemoryType] = useState<'fact' | 'decision' | 'pattern' | 'preference' | 'context' | 'constraint'>('fact');
  const [status, setStatus] = useState<'active' | 'superseded' | 'archived' | 'conflicted'>('active');
  const [importance, setImportance] = useState(50);
  const [provenance, setProvenance] = useState('');
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState('');

  // Load projects on mount
  useEffect(() => {
    api.getProjects().then(res => setProjects(res.projects)).catch(console.error);
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const memory = {
        project_id: projectId || 'proj-001',
        project_name: projects.find(p => p.project_id === projectId)?.name || 'Unknown Project',
        memory_type: memoryType,
        content: content,
        status: status,
        importance,
        provenance: provenance || 'User-created memory',
        lineage: {
          supersedes: undefined,
          superseded_by: undefined,
          related_memories: tags.split(',').map(t => t.trim()).filter(t => t.length > 0),
        },
        tags: tags.split(',').map(t => t.trim()).filter(t => t.length > 0),
      };

      const created = await api.createMemory(memory as any);
      navigate(`/memories/${created.memory_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create memory');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto space-y-6 animate-pulse">
        <Card><CardContent className="pt-6"><div className="h-8 bg-gray-200 rounded w-1/3 mb-2" /><div className="h-4 bg-gray-200 rounded w-1/4" /></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="h-32 bg-gray-200 rounded" /></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="h-4 bg-gray-200 rounded w-1/2 mb-2" /><div className="h-4 bg-gray-200 rounded w-1/3" /></CardContent></Card>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-text-primary mb-6">Create Memory</h1>

      <form onSubmit={handleCreate} className="space-y-6">
        {/* Project selector */}
        <Card>
          <CardHeader>
            <CardTitle>Project</CardTitle>
          </CardHeader>
          <CardContent>
            <Select
              value={projectId}
              onChange={(e) => setProjectId((e.target as HTMLSelectElement).value)}
              options={[
                { value: '', label: 'Select project...' },
                ...projects.map(p => ({ value: p.project_id, label: p.name })),
              ]}
              label="Project"
              placeholder="Select project"
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
              onChange={(e) => setMemoryType((e.target as HTMLSelectElement).value as any)}
              options={MEMORY_TYPE_OPTIONS}
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
              onChange={(e) => setStatus((e.target as HTMLSelectElement).value as any)}
              options={MEMORY_STATUS_OPTIONS}
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
                onChange={(e) => setImportance(Number(e.target.value))}
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
            <Input
              value={content}
              onChange={(e) => setContent(e.target.value)}
              label="Memory Content"
              placeholder="What did you learn or decide?"
            />
          </CardContent>
        </Card>

        {/* Provenance */}
        <Card>
          <CardHeader>
            <CardTitle>Provenance (source reference)</CardTitle>
          </CardHeader>
          <CardContent>
            <Input
              value={provenance}
              onChange={(e) => setProvenance(e.target.value)}
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
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              label="Tags"
              placeholder="architecture, database, core"
            />
            <p className="text-xs text-text-muted mt-1">Leave blank if none.</p>
          </CardContent>
        </Card>

        <div>
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? 'Creating...' : 'Create Memory'}
          </Button>
          <Button variant="outline" type="button" onClick={() => navigate('/memories')}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}