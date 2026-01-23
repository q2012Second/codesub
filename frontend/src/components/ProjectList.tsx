import type { Project } from '../types';

interface ProjectListProps {
  projects: Project[];
  onSelect: (id: string) => void;
  onAddProject: () => void;
}

export function ProjectList({ projects, onSelect, onAddProject }: ProjectListProps) {
  if (projects.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <p style={{ color: '#666', marginBottom: 16 }}>No projects registered yet.</p>
        <button
          onClick={onAddProject}
          style={{ background: '#0066cc', color: 'white', border: '1px solid #0066cc', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}
        >
          + Add Project
        </button>
      </div>
    );
  }

  return (
    <div>
      {projects.map(project => (
        <div
          key={project.id}
          onClick={() => onSelect(project.id)}
          style={{
            padding: 16,
            border: '1px solid #ddd',
            borderRadius: 4,
            marginBottom: 8,
            cursor: 'pointer',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = '#f9f9f9')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          <div style={{ fontWeight: 500, marginBottom: 4 }}>{project.name}</div>
          <div style={{ fontSize: 13, color: '#666', fontFamily: 'monospace' }}>
            {project.path}
          </div>
        </div>
      ))}
    </div>
  );
}
