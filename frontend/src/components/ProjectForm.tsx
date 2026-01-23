import { useState } from 'react';
import { createProject } from '../api';
import type { Project } from '../types';

interface ProjectFormProps {
  onCancel: () => void;
  onSaved: (project: Project) => void;
  showMessage: (type: 'success' | 'error', text: string) => void;
}

export function ProjectForm({ onCancel, onSaved, showMessage }: ProjectFormProps) {
  const [path, setPath] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!path.trim()) {
      showMessage('error', 'Path is required');
      return;
    }

    try {
      setLoading(true);
      const project = await createProject({
        path: path.trim(),
        name: name.trim() || undefined,
      });
      onSaved(project);
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Failed to add project');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2 style={{ marginBottom: 20 }}>Add Project</h2>

      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
          Repository Path *
        </label>
        <input
          type="text"
          value={path}
          onChange={e => setPath(e.target.value)}
          placeholder="~/projects/my-repo or ./relative/path"
          style={{ width: '100%', padding: 8, fontFamily: 'monospace', border: '1px solid #ddd', borderRadius: 4 }}
          autoFocus
        />
        <small style={{ color: '#666' }}>
          Absolute, relative, or ~/path to a git repo with codesub initialized
        </small>
      </div>

      <div style={{ marginBottom: 24 }}>
        <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
          Display Name
        </label>
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Optional (defaults to directory name)"
          style={{ width: '100%', padding: 8, border: '1px solid #ddd', borderRadius: 4 }}
        />
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" onClick={onCancel} disabled={loading} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>
          Cancel
        </button>
        <button
          type="submit"
          disabled={loading}
          style={{ background: '#0066cc', color: 'white', border: '1px solid #0066cc', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}
        >
          {loading ? 'Adding...' : 'Add Project'}
        </button>
      </div>
    </form>
  );
}
