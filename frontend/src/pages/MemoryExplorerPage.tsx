import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { ChangeEvent, FormEvent } from 'react';
import { api, type Memory, type MemoryListResponse, type MemoryQuery, type Project } from '../api';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Avatar } from '../components/ui/Avatar';

const MEMORY_TYPES = [
  { value: '', label: 'All Types' },
  { value: 'fact', label: 'Fact' },
  { value: 'decision', label: 'Decision' },
  { value: 'pattern', label: 'Pattern' },
  { value: 'preference', label: 'Preference' },
  { value: 'context', label: 'Context' },
  { value: 'constraint', label: 'Constraint' },
] as const satisfies Array<{ value: string; label: string }>;

const STATUSES = [
  { value: '', label: 'All Statuses' },
  { value: 'active', label: 'Active' },
  { value: 'superseded', label: 'Superseded' },
  { value: 'archived', label: 'Archived' },
  { value: 'conflicted', label: 'Conflicted' },
] as const satisfies Array<{ value: string; label: string }>;

export function MemoryExplorerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  
  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 20;
  
  // Filters from URL
  const search = searchParams.get('search') || '';
  const projectId = searchParams.get('project') || '';
  const memoryType = searchParams.get('type') || '';
  const status = searchParams.get('status') || '';
  
  const fetchMemories = async () => {
    try {
      setLoading(true);
      setError(null);
      const query: MemoryQuery = {
        search: search || undefined,
        project_id: projectId || undefined,
        memory_type: memoryType as MemoryQuery['memory_type'] || undefined,
        status: status as MemoryQuery['status'] || undefined,
        page,
        page_size: pageSize,
        sort_by: 'updated_at',
        sort_order: 'desc',
      };
      
      const response: MemoryListResponse = await api.getMemories(query);
      setMemories(response.memories);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memories');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchMemories();
  }, [search, projectId, memoryType, status, page]);
  
  useEffect(() => {
    api.getProjects().then(res => setProjects(res.projects)).catch(console.error);
  }, []);
  
  const handleFilterChange = (key: string, value: string) => {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    newParams.delete('page'); // Reset to first page
    setSearchParams(newParams);
    setPage(1);
  };
  
  const handleSearchSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    handleFilterChange('search', search);
  };
  
  const totalPages = Math.ceil(total / pageSize);
  
  if (loading && memories.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-1/3" />
            <div className="h-4 bg-gray-200 rounded w-1/4 mt-1" />
          </div>
          <div className="animate-pulse flex gap-2">
            <div className="h-10 bg-gray-200 rounded w-48" />
            <div className="h-10 bg-gray-200 rounded w-48" />
            <div className="h-10 bg-gray-200 rounded w-48" />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="pt-6">
                <div className="h-4 bg-gray-200 rounded w-1/2 mb-3" />
                <div className="h-16 bg-gray-200 rounded" />
                <div className="h-4 bg-gray-200 rounded w-1/3 mt-3" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      {/* Header & Filters */}
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Memory Explorer</h1>
            <p className="text-text-secondary mt-1">
              Browse and search {total > 0 ? `${total} memories` : 'memories'} across projects
            </p>
          </div>
          <Button variant="primary" asChild>
            <Link to="/memories/new">Create Memory</Link>
          </Button>
        </div>
        
        {/* Filter Bar */}
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handleSearchSubmit} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div className="lg:col-span-2">
                  <Input
                    value={search}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => handleFilterChange('search', e.target.value)}
                    placeholder="Search memories..."
                    label="Search"
                  />
                </div>
                <div>
                  <Select
                    value={projectId}
                    onChange={(e: ChangeEvent<HTMLSelectElement>) => handleFilterChange('project', e.target.value)}
                    options={[
                      { value: '', label: 'All Projects' },
                      ...projects.map(p => ({ value: p.project_id, label: p.name })),
                    ]}
                    label="Project"
                  />
                </div>
                <div>
                  <Select
                    value={memoryType}
                    onChange={(e: ChangeEvent<HTMLSelectElement>) => handleFilterChange('type', e.target.value)}
                    options={MEMORY_TYPES}
                    label="Type"
                  />
                </div>
                <div>
                  <Select
                    value={status}
                    onChange={(e: ChangeEvent<HTMLSelectElement>) => handleFilterChange('status', e.target.value)}
                    options={STATUSES}
                    label="Status"
                  />
                </div>
              </div>
              
              {(search || projectId || memoryType || status) && (
                <Button type="button" variant="ghost" size="sm" onClick={() => setSearchParams(new URLSearchParams())}>
                  Clear all filters
                </Button>
              )}
            </form>
          </CardContent>
        </Card>
      </div>
      
      {/* Results */}
      {error && (
        <Card className="border-error/50">
          <CardContent className="py-8 text-center">
            <svg className="w-12 h-12 mx-auto text-error mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-text-secondary">Failed to load memories: {error}</p>
            <Button onClick={fetchMemories} className="mt-3">Retry</Button>
          </CardContent>
        </Card>
      )}
      
      {!loading && memories.length === 0 && !error && (
        <Card>
          <CardContent className="py-12 text-center">
            <svg className="w-16 h-16 mx-auto text-text-muted mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h2 className="text-xl font-semibold text-text-primary mb-2">No memories found</h2>
            <p className="text-text-secondary mb-4">
              {search || projectId || memoryType || status
                ? 'Try adjusting your filters or search terms.'
                : 'No memories have been captured yet.'}
            </p>
            <Button variant="primary" asChild>
              <Link to="/memories/new">Create your first memory</Link>
            </Button>
          </CardContent>
        </Card>
      )}
      
      {!loading && memories.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {memories.map((memory) => (
              <Card key={memory.memory_id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <Avatar name={memory.project_name || 'Project'} size="sm" />
                      <div className="min-w-0">
                        <Link to={`/memories/${memory.memory_id}`} className="font-medium text-text-primary hover:text-primary truncate block">
                          {memory.project_name || memory.project_id}
                        </Link>
                        <p className="text-xs text-text-secondary truncate">{memory.provenance}</p>
                      </div>
                    </div>
                    <Badge variant="outline" size="sm">{memory.importance}</Badge>
                  </div>
                  
                  <p className="text-text-primary mb-3 line-clamp-3">{memory.content}</p>
                  
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={memory.status === 'active' ? 'success' : memory.status === 'superseded' ? 'warning' : memory.status === 'conflicted' ? 'error' : 'default'} size="sm">
                      {memory.status}
                    </Badge>
                    <Badge variant="outline" size="sm">{memory.memory_type}</Badge>
                    {memory.tags && memory.tags.length > 0 && (
                      <>
                        {memory.tags.slice(0, 2).map(tag => (
                          <Badge key={tag} variant="outline" size="sm">#{tag}</Badge>
                        ))}
                        {memory.tags.length > 2 && (
                          <Badge variant="outline" size="sm">+{memory.tags.length - 2} more</Badge>
                        )}
                      </>
                    )}
                  </div>
                  
                  <div className="mt-3 pt-3 border-t border-border flex items-center justify-between">
                    <time className="text-xs text-text-muted" dateTime={memory.updated_at}>
                      Updated {new Date(memory.updated_at).toLocaleDateString()}
                    </time>
                    <Link
                      to={`/memories/${memory.memory_id}`}
                      className="text-sm text-primary hover:underline"
                    >
                      View details →
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          
          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                Previous
              </Button>
              <span className="px-4 text-sm text-text-secondary">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}