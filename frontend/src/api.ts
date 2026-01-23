import type {
  Subscription,
  SubscriptionListResponse,
  SubscriptionCreateRequest,
  SubscriptionUpdateRequest,
  ApiError,
  Project,
  ProjectStatus,
  ProjectCreateRequest,
  ProjectListResponse,
  ScanHistoryEntry,
  ScanHistoryEntryFull,
  ScanHistoryListResponse,
  ScanRequest,
  ApplyUpdatesRequest,
  ApplyUpdatesResponse,
} from './types';

const API_BASE = '/api';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail);
  }
  return response.json();
}

export async function listSubscriptions(includeInactive: boolean = false): Promise<SubscriptionListResponse> {
  const url = `${API_BASE}/subscriptions?include_inactive=${includeInactive}`;
  const response = await fetch(url);
  return handleResponse<SubscriptionListResponse>(response);
}

export async function getSubscription(id: string): Promise<Subscription> {
  const response = await fetch(`${API_BASE}/subscriptions/${id}`);
  return handleResponse<Subscription>(response);
}

export async function createSubscription(data: SubscriptionCreateRequest): Promise<Subscription> {
  const response = await fetch(`${API_BASE}/subscriptions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Subscription>(response);
}

export async function updateSubscription(id: string, data: SubscriptionUpdateRequest): Promise<Subscription> {
  const response = await fetch(`${API_BASE}/subscriptions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Subscription>(response);
}

export async function deleteSubscription(id: string, hard: boolean = false): Promise<Subscription> {
  const url = `${API_BASE}/subscriptions/${id}?hard=${hard}`;
  const response = await fetch(url, { method: 'DELETE' });
  return handleResponse<Subscription>(response);
}

export async function reactivateSubscription(id: string): Promise<Subscription> {
  const response = await fetch(`${API_BASE}/subscriptions/${id}/reactivate`, {
    method: 'POST',
  });
  return handleResponse<Subscription>(response);
}

export async function healthCheck(): Promise<{ status: string; config_initialized: boolean; baseline_ref?: string }> {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}

// --- Project API ---

export async function listProjects(): Promise<ProjectListResponse> {
  const response = await fetch(`${API_BASE}/projects`);
  return handleResponse<ProjectListResponse>(response);
}

export async function getProjectStatus(projectId: string): Promise<ProjectStatus> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`);
  return handleResponse<ProjectStatus>(response);
}

export async function createProject(data: ProjectCreateRequest): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Project>(response);
}

export async function deleteProject(projectId: string): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`, {
    method: 'DELETE',
  });
  return handleResponse<Project>(response);
}

// --- Project Subscriptions ---

export async function listProjectSubscriptions(
  projectId: string,
  includeInactive: boolean = false
): Promise<SubscriptionListResponse> {
  const url = `${API_BASE}/projects/${projectId}/subscriptions?include_inactive=${includeInactive}`;
  const response = await fetch(url);
  return handleResponse<SubscriptionListResponse>(response);
}

// --- Scan API ---

export async function runScan(
  projectId: string,
  request: ScanRequest
): Promise<ScanHistoryEntry> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<ScanHistoryEntry>(response);
}

export async function listScanHistory(
  projectId: string,
  limit: number = 50
): Promise<ScanHistoryListResponse> {
  const url = `${API_BASE}/projects/${projectId}/scan-history?limit=${limit}`;
  const response = await fetch(url);
  return handleResponse<ScanHistoryListResponse>(response);
}

export async function getScanResult(
  projectId: string,
  scanId: string
): Promise<ScanHistoryEntryFull> {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/scan-history/${scanId}`
  );
  return handleResponse<ScanHistoryEntryFull>(response);
}

export async function clearProjectScanHistory(
  projectId: string
): Promise<{ deleted: number }> {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/scan-history`,
    { method: 'DELETE' }
  );
  return handleResponse<{ deleted: number }>(response);
}

export async function clearAllScanHistory(): Promise<{ deleted: number }> {
  const response = await fetch(`${API_BASE}/scan-history`, {
    method: 'DELETE',
  });
  return handleResponse<{ deleted: number }>(response);
}

// --- Apply Updates ---

export async function applyUpdates(
  projectId: string,
  request: ApplyUpdatesRequest
): Promise<ApplyUpdatesResponse> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/apply-updates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<ApplyUpdatesResponse>(response);
}
