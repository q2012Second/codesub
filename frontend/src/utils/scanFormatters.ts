// Shared utilities for formatting scan-related data

// Helper to normalize change_type casing (backend uses UPPERCASE, tolerate lowercase)
export function normalizeChangeType(ct?: string | null): string | undefined {
  if (!ct) return undefined;
  return ct.toUpperCase();
}

// Helper to format details (can be string, object, or null)
export function formatDetails(details: unknown): string {
  if (details == null) return '';
  if (typeof details === 'string') return details;
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return String(details);
  }
}

// Change type styling for semantic subscriptions
export const CHANGE_TYPE_STYLES: Record<string, { bg: string; border: string; color: string; label: string }> = {
  STRUCTURAL: { bg: '#fff3e0', border: '#ffcc80', color: '#e65100', label: 'STRUCTURAL' },
  CONTENT: { bg: '#e3f2fd', border: '#90caf9', color: '#1565c0', label: 'CONTENT' },
  MISSING: { bg: '#ffebee', border: '#ef9a9a', color: '#c62828', label: 'MISSING' },
  AMBIGUOUS: { bg: '#fce4ec', border: '#f48fb1', color: '#ad1457', label: 'AMBIGUOUS' },
  PARSE_ERROR: { bg: '#f3e5f5', border: '#ce93d8', color: '#7b1fa2', label: 'PARSE ERROR' },
};

// Human-readable labels for trigger/proposal reasons
export const REASON_LABELS: Record<string, string> = {
  // Line-based reasons
  overlap_hunk: 'Lines in range were modified',
  insert_inside_range: 'New lines inserted inside range',
  file_deleted: 'File was deleted',
  line_shift: 'Lines shifted due to changes above',
  rename: 'File was renamed or moved',
  // Semantic reasons
  interface_changed: 'Interface/signature changed',
  body_changed: 'Implementation/value changed',
  semantic_location: 'Semantic target moved/renamed',
  semantic_target_missing: 'Semantic target not found',
  semantic_content: 'Content/body changed',
  semantic_structural: 'Type/signature changed',
  semantic_missing: 'Construct deleted or not found',
  semantic_rename: 'Construct was renamed',
  ambiguous: 'Multiple possible semantic matches',
  parse_error: 'Parser error while analyzing target',
};

export function formatReasons(reasons: string[]): string {
  return reasons.map((r) => REASON_LABELS[r] || r).join('; ');
}
