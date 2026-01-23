export interface Anchor {
  context_before: string[];
  lines: string[];
  context_after: string[];
}

export interface Subscription {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  label: string | null;
  description: string | null;
  anchors: Anchor | null;
  active: boolean;
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
}

export interface SubscriptionUpdateRequest {
  label?: string;
  description?: string;
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
