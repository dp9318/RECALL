import { useState, useEffect } from 'react';
import { api, type CustomInstruction, type CustomInstructionListResponse, type CreateCustomInstructionRequest, type Project } from '../api';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Select } from '../components/ui/Select';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Avatar } from '../components/ui/Avatar';

export function CustomInstructionsPage() {
  const [instructions, setInstructions] = useState<CustomInstruction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editActive, setEditActive] = useState(true);

  // Projects state
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
  
  // Create form state
  const [createScope, setCreateScope] = useState<'global' | 'project'>('global');
  const [createProjectId, setCreateProjectId] = useState('');
  const [createContent, setCreateContent] = useState('');
  const [createActive, setCreateActive] = useState(true);
  
  const fetchInstructions = async () => {
    try {
      setLoading(true);
      setError(null);
      const response: CustomInstructionListResponse = await api.getCustomInstructions();
      setInstructions(response.instructions);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load instructions');
    } finally {
      setLoading(false);
    }
  };

  const fetchProjects = async () => {
    try {
      setProjectsLoading(true);
      setProjectsError(null);
      const response = await api.getProjects();
      setProjects(response.projects || []);
    } catch (err) {
      setProjectsError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setProjectsLoading(false);
    }
  };
  
  useEffect(() => {
    fetchInstructions();
    fetchProjects();
  }, []);

  useEffect(() => {
    if (showCreateModal) {
      fetchProjects();
    }
  }, [showCreateModal]);

  const handleOpenCreateModal = () => {
    setModalError(null);
    setCreateScope('global');
    setCreateProjectId('');
    setCreateContent('');
    setCreateActive(true);
    setShowCreateModal(true);
  };
  
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);
    if (!createContent.trim()) {
      setModalError('Instruction content cannot be empty');
      return;
    }
    if (createScope === 'project' && !createProjectId) {
      setModalError('Please select a project for project-scoped instructions');
      return;
    }
    
    try {
      const request: CreateCustomInstructionRequest = {
        scope: createScope,
        project_id: createScope === 'project' ? createProjectId : undefined,
        content: createContent.trim(),
        active: createActive,
      };
      
      await api.createCustomInstruction(request);
      setShowCreateModal(false);
      setCreateContent('');
      setCreateProjectId('');
      setCreateScope('global');
      setModalError(null);
      fetchInstructions();
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Failed to create instruction');
    }
  };
  
  const handleUpdate = async (id: string) => {
    if (!editContent.trim()) return;
    
    try {
      await api.updateCustomInstruction(id, {
        content: editContent,
        active: editActive,
      });
      setEditingId(null);
      fetchInstructions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update instruction');
    }
  };
  
  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this instruction?')) return;
    
    try {
      await api.deleteCustomInstruction(id);
      fetchInstructions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete instruction');
    }
  };
  
  const handleToggleActive = async (instruction: CustomInstruction) => {
    try {
      await api.updateCustomInstruction(instruction.instruction_id, {
        active: !instruction.active,
      });
      fetchInstructions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update instruction');
    }
  };
  
  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="h-8 bg-gray-200 rounded w-1/3" />
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <Card key={i}><CardContent className="pt-6"><div className="h-24 bg-gray-200 rounded" /></CardContent></Card>
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
          <h1 className="text-2xl font-bold text-text-primary">Custom Instructions</h1>
          <p className="text-text-secondary mt-1">
            Manage {total} user-authored instruction{total !== 1 ? 's' : ''}
          </p>
        </div>
        <Button variant="primary" onClick={handleOpenCreateModal}>
          <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create Instruction
        </Button>
      </div>
      
      {/* Error display */}
      {error && (
        <div className="p-3 rounded-lg bg-error/10 border border-error/20 text-error text-sm flex items-center justify-between" role="alert">
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={() => setError(null)}>Dismiss</Button>
        </div>
      )}
      
      {/* Instructions List */}
      {instructions.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <svg className="w-16 h-16 mx-auto text-text-muted mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h2 className="text-xl font-semibold text-text-primary mb-2">No custom instructions</h2>
            <p className="text-text-secondary mb-4">Create your first instruction to guide RECALL's behavior.</p>
            <Button variant="primary" onClick={handleOpenCreateModal}>Create Instruction</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {instructions.map((instruction) => (
            <Card key={instruction.instruction_id} className={!instruction.active ? 'opacity-60' : ''}>
              <CardContent className="p-4">
                {editingId === instruction.instruction_id ? (
                  <div className="space-y-4">
                    <Textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      label="Instruction Content"
                      rows={4}
                    />
                    <div className="flex items-center gap-4">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={editActive}
                          onChange={(e) => setEditActive(e.target.checked)}
                          className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                        />
                        <span className="text-sm text-text-secondary">Active</span>
                      </label>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => handleUpdate(instruction.instruction_id)}>Save</Button>
                      <Button variant="outline" size="sm" onClick={() => setEditingId(null)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                      <div className={`
                        w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0
                        ${instruction.scope === 'global' ? 'bg-primary-light text-primary' : 'bg-info-light text-info'}
                      `}>
                        {instruction.scope === 'global' ? (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-1.343 3-3s-1.343-3-3-3" />
                          </svg>
                        ) : (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                          </svg>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant={instruction.scope === 'global' ? 'primary' : 'info'} size="sm">
                            {instruction.scope}
                          </Badge>
                          {instruction.project_name && (
                            <Badge variant="outline" size="sm">{instruction.project_name}</Badge>
                          )}
                          <Badge variant={instruction.active ? 'success' : 'default'} size="sm">
                            {instruction.active ? 'Active' : 'Inactive'}
                          </Badge>
                          <Badge variant="outline" size="sm">v{instruction.version}</Badge>
                        </div>
                        <p className="text-text-primary whitespace-pre-wrap">{instruction.content}</p>
                        <p className="text-xs text-text-muted mt-2">
                          Created {new Date(instruction.created_at).toLocaleString()}
                          {instruction.updated_at !== instruction.created_at && ` · Updated ${new Date(instruction.updated_at).toLocaleString()}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 sm:ml-4">
                      <Button variant="ghost" size="sm" onClick={() => {
                        setEditContent(instruction.content);
                        setEditActive(instruction.active);
                        setEditingId(instruction.instruction_id);
                      }}>
                        Edit
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => handleToggleActive(instruction)}>
                        {instruction.active ? 'Deactivate' : 'Activate'}
                      </Button>
                      <Button variant="ghost" size="sm" className="text-error" onClick={() => handleDelete(instruction.instruction_id)}>
                        Delete
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      
      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={() => setShowCreateModal(false)}>
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <CardHeader>
              <CardTitle>Create Custom Instruction</CardTitle>
            </CardHeader>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              {modalError && (
                <div className="p-3 rounded-lg bg-error/10 border border-error/20 text-error text-sm flex items-center justify-between" role="alert">
                  <span>{modalError}</span>
                  <Button variant="ghost" size="sm" type="button" onClick={() => setModalError(null)}>Dismiss</Button>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">Scope</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="scope"
                      value="global"
                      checked={createScope === 'global'}
                      onChange={() => {
                        setCreateScope('global');
                        setCreateProjectId('');
                        if (modalError) setModalError(null);
                      }}
                      className="w-4 h-4 text-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm text-text-primary">Global</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="scope"
                      value="project"
                      checked={createScope === 'project'}
                      onChange={() => {
                        setCreateScope('project');
                        if (modalError) setModalError(null);
                      }}
                      className="w-4 h-4 text-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm text-text-primary">Project</span>
                  </label>
                </div>
              </div>
              
              {createScope === 'project' && (
                <div className="space-y-1.5">
                  <Select
                    value={createProjectId}
                    onChange={(e) => {
                      setCreateProjectId(e.target.value);
                      if (modalError) setModalError(null);
                    }}
                    options={
                      projectsLoading
                        ? [{ value: '', label: 'Loading projects...' }]
                        : projectsError
                        ? [{ value: '', label: 'Failed to load projects' }]
                        : projects.length === 0
                        ? [{ value: '', label: 'No projects available' }]
                        : [
                            { value: '', label: 'Select a project...' },
                            ...projects.map((p) => ({ value: p.project_id, label: p.name })),
                          ]
                    }
                    disabled={projectsLoading || (projects.length === 0 && !projectsError)}
                    label="Project"
                    error={projectsError || undefined}
                    helperText={
                      projectsLoading
                        ? 'Loading available projects...'
                        : projects.length === 0 && !projectsError
                        ? 'No projects found. Please create a project in Settings first.'
                        : undefined
                    }
                  />
                  {projectsError && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={fetchProjects}
                      className="text-xs text-primary"
                    >
                      Retry loading projects
                    </Button>
                  )}
                </div>
              )}
              
              <Textarea
                value={createContent}
                onChange={(e) => setCreateContent(e.target.value)}
                label="Instruction Content"
                placeholder="Enter the instruction content..."
                rows={5}
                required
              />
              
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={createActive}
                    onChange={(e) => setCreateActive(e.target.checked)}
                    className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                  />
                  <span className="text-sm text-text-secondary">Active immediately</span>
                </label>
              </div>
              
              <div className="flex justify-end gap-2 pt-4 border-t border-border">
                <Button type="button" variant="outline" onClick={() => setShowCreateModal(false)}>Cancel</Button>
                <Button type="submit" variant="primary">Create Instruction</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}