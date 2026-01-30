export interface Anchor {
  context_before: string[];
  lines: string[];
  context_after: string[];
}

export interface MemberFingerprint {
  kind: string;
  interface_hash: string;
  body_hash: string;
}

export interface SemanticTarget {
  language: string; // "python" | "java"
  kind: string; // "variable" | "field" | "method" | "class" | "interface" | "enum"
  qualname: string; // "API_VERSION" | "User.role" | "Calculator.add" | "User"
  role?: string | null; // "const" for constants, null otherwise
  interface_hash?: string;
  body_hash?: string;
  fingerprint_version?: number;
  // Container tracking fields
  include_members?: boolean;
  include_private?: boolean;
  track_decorators?: boolean;
  baseline_members?: Record<string, MemberFingerprint> | null;
  baseline_container_qualname?: string | null;
}

// Defensive union type accepting both cases (backend uses UPPERCASE, but be tolerant)
export type ChangeType =
  | 'STRUCTURAL'
  | 'CONTENT'
  | 'MISSING'
  | 'AMBIGUOUS'
  | 'PARSE_ERROR'
  | 'structural'
  | 'content'
  | 'missing'
  | 'ambiguous'
  | 'parse_error';

export interface Subscription {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  label: string | null;
  description: string | null;
  anchors: Anchor | null;
  semantic?: SemanticTarget | null; // null/undefined for line-based subscriptions
  active: boolean;
  trigger_on_duplicate: boolean;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionListResponse {
  subscriptions: Subscription[];
  count: number;
  baseline_ref: string;
  baseline_title: string;
}

export interface SubscriptionCreateRequest {
  location: string;
  label?: string;
  description?: string;
  context?: number;
  // Container tracking options
  trigger_on_duplicate?: boolean;
  include_members?: boolean;
  include_private?: boolean;
  track_decorators?: boolean;
}

export interface SubscriptionUpdateRequest {
  label?: string;
  description?: string;
  trigger_on_duplicate?: boolean;
}

export interface ApiError {
  detail: string;
  error_type?: string;
}

export type FilterStatus = 'active' | 'all';

export type View =
  | 'projects'
  | 'project-add'
  | 'list'
  | 'detail'
  | 'create'
  | 'edit'
  | 'scan'
  | 'scan-history'
  | 'scan-detail';

// Project types
export interface Project {
  id: string;
  name: string;
  path: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectStatus {
  project: Project;
  path_exists: boolean;
  codesub_initialized: boolean;
  subscription_count: number;
  baseline_ref: string | null;
}

export interface ProjectCreateRequest {
  path: string;
  name?: string;
}

export interface ProjectListResponse {
  projects: Project[];
  count: number;
}

// Scan types
export interface Trigger {
  subscription_id: string;
  path: string;
  start_line: number;
  end_line: number;
  reasons: string[];
  label: string | null;
  change_type?: ChangeType | null; // semantic change classification
  details?: unknown; // Additional semantic details (string, object, or null)
}

export interface Proposal {
  subscription_id: string;
  old_path: string;
  old_start: number;
  old_end: number;
  new_path: string;
  new_start: number;
  new_end: number;
  reasons: string[];
  confidence: string;
  shift: number | null;
  label: string | null;
  new_qualname?: string | null; // For semantic renames
  new_kind?: string | null; // For semantic kind changes
}

export interface ScanResult {
  base_ref: string;
  target_ref: string;
  triggers: Trigger[];
  proposals: Proposal[];
}

export interface ScanHistoryEntry {
  id: string;
  project_id: string;
  base_ref: string;
  target_ref: string;
  trigger_count: number;
  proposal_count: number;
  unchanged_count: number;
  created_at: string;
}

export interface ScanHistoryEntryFull extends ScanHistoryEntry {
  scan_result: ScanResult;
}

export interface ScanRequest {
  base_ref: string;
  target_ref?: string;  // Empty/undefined for working directory
}

export interface ScanHistoryListResponse {
  scans: ScanHistoryEntry[];
  count: number;
}

export interface ApplyUpdatesRequest {
  scan_id: string;
  proposal_ids?: string[];
}

export interface ApplyUpdatesResponse {
  applied: string[];
  warnings: string[];
  new_baseline: string | null;
}

// Filesystem browser types
export interface FilesystemEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface FilesystemBrowseResponse {
  current_path: string;
  parent_path: string | null;
  entries: FilesystemEntry[];
}

// Code browser types
export interface FileEntry {
  path: string;
  name: string;
  extension: string;
}

export interface FileListResponse {
  files: FileEntry[];
  total: number;
  has_more: boolean;
}

export interface FileContentResponse {
  path: string;
  total_lines: number;
  lines: string[];
  language: string | null;
  supports_semantic: boolean;
  truncated: boolean;
}

export interface ConstructInfo {
  kind: string;
  qualname: string;
  role: string | null;
  start_line: number;
  end_line: number;
  target: string;
}

export interface SymbolsResponse {
  path: string;
  language: string;
  constructs: ConstructInfo[];
  has_parse_error: boolean;
  error_message?: string;
}

export interface CodeBrowserSelection {
  type: 'semantic' | 'lines';
  location: string;  // For semantic: path::kind:qualname
  label?: string;
  kind?: string | null;  // For semantic selections, the construct kind
}

// Container kinds that support aggregate tracking (include_members)
export const CONTAINER_KINDS: Record<string, Set<string>> = {
  python: new Set(['class', 'enum']),
  java: new Set(['class', 'interface', 'enum']),
};

// Helper to check if a kind is a container type
export function isContainerKind(kind: string | null | undefined): boolean {
  if (!kind) return false;
  return CONTAINER_KINDS.python.has(kind) || CONTAINER_KINDS.java.has(kind);
}

// Helper to parse kind from location string (path::kind:qualname or path::qualname)
export function parseSemanticLocation(location: string): { path: string; kind: string | null; qualname: string } | null {
  const match = location.match(/^(.+?)::(?:([a-z]+):)?(.+)$/);
  if (!match) return null;
  return {
    path: match[1],
    kind: match[2] || null,
    qualname: match[3],
  };
}
