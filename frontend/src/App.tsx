import { useState, useEffect, useCallback, useRef } from 'react';
import type { Subscription, FilterStatus, View, Project, ScanHistoryEntry } from './types';
import {
  listProjects,
  listProjectSubscriptions,
  listScanHistory,
  clearProjectScanHistory,
} from './api';
import { StatusFilter } from './components/StatusFilter';
import { SubscriptionList } from './components/SubscriptionList';
import { SubscriptionDetail } from './components/SubscriptionDetail';
import { SubscriptionForm } from './components/SubscriptionForm';
import { ProjectList } from './components/ProjectList';
import { ProjectForm } from './components/ProjectForm';
import { ProjectSelector } from './components/ProjectSelector';
import { ScanView } from './components/ScanView';
import { ScanHistoryList } from './components/ScanHistoryList';
import { ScanDetailView } from './components/ScanDetailView';

// Navigation state stored in browser history
interface NavState {
  view: View;
  projectId: string | null;
  subscriptionId: string | null;
  scanId: string | null;
}

function getInitialNavState(): NavState {
  // Try to restore from history state on page load
  const historyState = window.history.state as NavState | null;
  if (historyState?.view) {
    return historyState;
  }
  return {
    view: 'projects',
    projectId: null,
    subscriptionId: null,
    scanId: null,
  };
}

export default function App() {
  // Project state
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectLoading, setProjectLoading] = useState(true);

  // Subscription state
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [baselineRef, setBaselineRef] = useState<string>('');
  const [baselineTitle, setBaselineTitle] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterStatus>('active');

  // Navigation state (synced with browser history)
  const [navState, setNavState] = useState<NavState>(getInitialNavState);
  const isNavigatingRef = useRef(false);

  // Scan history state
  const [scanHistory, setScanHistory] = useState<ScanHistoryEntry[]>([]);

  // Messages
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Derived values from navState
  const view = navState.view;
  const currentProjectId = navState.projectId;
  const selectedId = navState.subscriptionId;
  const selectedScanId = navState.scanId;

  // Navigate to a new state (pushes to history)
  const navigate = useCallback((newState: Partial<NavState>) => {
    const fullState: NavState = {
      view: newState.view ?? navState.view,
      projectId: newState.projectId !== undefined ? newState.projectId : navState.projectId,
      subscriptionId: newState.subscriptionId !== undefined ? newState.subscriptionId : navState.subscriptionId,
      scanId: newState.scanId !== undefined ? newState.scanId : navState.scanId,
    };

    isNavigatingRef.current = true;
    window.history.pushState(fullState, '', window.location.pathname);
    setNavState(fullState);
  }, [navState]);

  // Handle browser back/forward buttons
  useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      const state = event.state as NavState | null;
      if (state) {
        setNavState(state);
      } else {
        // No state means we're at the initial entry
        setNavState({
          view: 'projects',
          projectId: null,
          subscriptionId: null,
          scanId: null,
        });
      }
    };

    window.addEventListener('popstate', handlePopState);

    // Replace initial state so back button works from first navigation
    if (!window.history.state) {
      window.history.replaceState(navState, '', window.location.pathname);
    }

    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Load projects on mount
  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      setProjectLoading(true);
      const data = await listProjects();
      setProjects(data.projects);
    } catch (e) {
      showMessage('error', 'Failed to load projects');
    } finally {
      setProjectLoading(false);
    }
  };

  // Load subscriptions when project changes
  const fetchSubscriptions = useCallback(async () => {
    if (!currentProjectId) return;

    try {
      setLoading(true);
      setError(null);
      const data = await listProjectSubscriptions(currentProjectId, filter === 'all');
      setSubscriptions(data.subscriptions);
      setBaselineRef(data.baseline_ref);
      setBaselineTitle(data.baseline_title || '');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load subscriptions');
    } finally {
      setLoading(false);
    }
  }, [currentProjectId, filter]);

  useEffect(() => {
    if (currentProjectId) {
      fetchSubscriptions();
    }
  }, [currentProjectId, filter, fetchSubscriptions]);

  const loadScanHistory = async () => {
    if (!currentProjectId) return;

    try {
      const data = await listScanHistory(currentProjectId);
      setScanHistory(data.scans);
    } catch (e) {
      showMessage('error', 'Failed to load scan history');
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  // Navigation handlers
  const handleSelectProject = (projectId: string) => {
    navigate({ view: 'list', projectId, subscriptionId: null, scanId: null });
  };

  const handleProjectSaved = (project: Project) => {
    loadProjects();
    navigate({ view: 'list', projectId: project.id, subscriptionId: null, scanId: null });
    showMessage('success', 'Project added');
  };

  const handleSelect = (id: string) => {
    navigate({ view: 'detail', subscriptionId: id });
  };

  const handleBack = () => {
    window.history.back();
  };

  const handleEdit = (id: string) => {
    navigate({ view: 'edit', subscriptionId: id });
  };

  const handleCreate = () => {
    navigate({ view: 'create' });
  };

  const handleSaved = (sub: Subscription, isNew: boolean) => {
    fetchSubscriptions();
    navigate({ view: 'detail', subscriptionId: sub.id });
    showMessage('success', isNew ? 'Subscription created' : 'Subscription updated');
  };

  const handleDeleted = () => {
    fetchSubscriptions();
    navigate({ view: 'list', subscriptionId: null });
    showMessage('success', 'Subscription deleted');
  };

  const handleClearHistory = async () => {
    if (!currentProjectId) return;
    if (!confirm('Clear all scan history for this project?')) return;

    try {
      await clearProjectScanHistory(currentProjectId);
      setScanHistory([]);
      showMessage('success', 'Scan history cleared');
    } catch (e) {
      showMessage('error', 'Failed to clear history');
    }
  };

  const selectedSub = subscriptions.find(s => s.id === selectedId) || null;
  const currentProject = projects.find(p => p.id === currentProjectId);

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      <header style={{ marginBottom: 24, paddingBottom: 16, borderBottom: '1px solid #eee' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1 style={{ fontSize: 24, marginBottom: 0 }}>codesub</h1>
          {projects.length > 0 && (
            <ProjectSelector
              projects={projects}
              currentProjectId={currentProjectId}
              onSelect={(id) => {
                if (id) {
                  handleSelectProject(id);
                } else {
                  navigate({ view: 'projects', projectId: null, subscriptionId: null, scanId: null });
                }
              }}
            />
          )}
        </div>
        {currentProject && baselineRef && (
          <p style={{ color: '#666', fontSize: 13, marginTop: 4 }}>
            <span style={{ fontFamily: 'monospace' }}>{baselineRef.slice(0, 8)}</span>
            {baselineTitle && <span> - {baselineTitle}</span>}
          </p>
        )}
      </header>

      {message && (
        <div style={{
          padding: '12px 16px',
          marginBottom: 20,
          borderRadius: 4,
          background: message.type === 'success' ? '#d4edda' : '#f8d7da',
          color: message.type === 'success' ? '#155724' : '#721c24',
        }}>
          {message.text}
        </div>
      )}

      {/* Project Views */}
      {view === 'projects' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
            <h2>Projects</h2>
            <button
              onClick={() => navigate({ view: 'project-add' })}
              style={{ background: '#0066cc', color: 'white', border: '1px solid #0066cc', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}
            >
              + Add Project
            </button>
          </div>
          {projectLoading ? (
            <p style={{ color: '#666' }}>Loading...</p>
          ) : (
            <ProjectList
              projects={projects}
              onSelect={handleSelectProject}
              onAddProject={() => navigate({ view: 'project-add' })}
            />
          )}
        </>
      )}

      {view === 'project-add' && (
        <ProjectForm
          onCancel={handleBack}
          onSaved={handleProjectSaved}
          showMessage={showMessage}
        />
      )}

      {/* Subscription List */}
      {view === 'list' && currentProjectId && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <button onClick={handleBack} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>Back to Projects</button>
              <StatusFilter value={filter} onChange={setFilter} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => navigate({ view: 'scan' })} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>
                Run Scan
              </button>
              <button
                onClick={handleCreate}
                style={{ background: '#0066cc', color: 'white', border: '1px solid #0066cc', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}
              >
                + New Subscription
              </button>
            </div>
          </div>

          {loading && <p style={{ color: '#666' }}>Loading...</p>}

          {error && (
            <div style={{ padding: 16, background: '#f8d7da', color: '#721c24', borderRadius: 4 }}>
              <strong>Error:</strong> {error}
            </div>
          )}

          {!loading && !error && (
            <SubscriptionList
              subscriptions={subscriptions}
              onSelect={handleSelect}
            />
          )}
        </>
      )}

      {/* Subscription Detail */}
      {view === 'detail' && selectedSub && currentProjectId && (
        <SubscriptionDetail
          subscription={selectedSub}
          projectId={currentProjectId}
          onBack={handleBack}
          onEdit={() => handleEdit(selectedSub.id)}
          onDeleted={handleDeleted}
          onReactivated={fetchSubscriptions}
          showMessage={showMessage}
        />
      )}

      {/* Subscription Form */}
      {(view === 'create' || view === 'edit') && currentProjectId && (
        <SubscriptionForm
          subscription={view === 'edit' ? selectedSub : null}
          projectId={currentProjectId}
          onCancel={handleBack}
          onSaved={handleSaved}
          showMessage={showMessage}
        />
      )}

      {/* Scan View */}
      {view === 'scan' && currentProjectId && (
        <ScanView
          projectId={currentProjectId}
          baselineRef={baselineRef}
          onBack={handleBack}
          onViewHistory={() => {
            loadScanHistory();
            navigate({ view: 'scan-history' });
          }}
          showMessage={showMessage}
          onBaselineUpdated={fetchSubscriptions}
        />
      )}

      {/* Scan History */}
      {view === 'scan-history' && currentProjectId && (
        <ScanHistoryList
          scans={scanHistory}
          onSelect={(id) => {
            navigate({ view: 'scan-detail', scanId: id });
          }}
          onClear={handleClearHistory}
          onBack={handleBack}
        />
      )}

      {/* Scan Detail */}
      {view === 'scan-detail' && currentProjectId && selectedScanId && (
        <ScanDetailView
          projectId={currentProjectId}
          scanId={selectedScanId}
          onBack={handleBack}
          showMessage={showMessage}
          onBaselineUpdated={fetchSubscriptions}
        />
      )}
    </div>
  );
}
