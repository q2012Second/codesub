import type { Project } from '../types';

interface ProjectSelectorProps {
  projects: Project[];
  currentProjectId: string | null;
  onSelect: (projectId: string | null) => void;
}

export function ProjectSelector({
  projects,
  currentProjectId,
  onSelect,
}: ProjectSelectorProps) {
  return (
    <select
      value={currentProjectId || ''}
      onChange={e => onSelect(e.target.value || null)}
      style={{ padding: '4px 8px', fontSize: 14, border: '1px solid #ddd', borderRadius: 4 }}
    >
      <option value="">Select project...</option>
      {projects.map(p => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}
