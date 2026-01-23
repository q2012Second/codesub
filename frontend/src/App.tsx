import { useState, useEffect, useCallback } from 'react';
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

export default function App() {
  // Project state
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [projectLoading, setProjectLoading] = useState(true);

  // Subscription state
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [baselineRef, setBaselineRef] = useState<string>('');
  const [baselineTitle, setBaselineTitle] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterStatus>('active');

  // View state
  const [view, setView] = useState<View>('projects');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Scan history state
  const [scanHistory, setScanHistory] = useState<ScanHistoryEntry[]>([]);

  // Messages
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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

  // Project handlers
  const handleSelectProject = async (projectId: string) => {
    setCurrentProjectId(projectId);
    setView('list');
  };

  const handleProjectSaved = (project: Project) => {
    loadProjects();
    setCurrentProjectId(project.id);
    setView('list');
    showMessage('success', 'Project added');
  };

  // Subscription handlers
  const handleSelect = (id: string) => {
    setSelectedId(id);
    setView('detail');
  };

  const handleBack = () => {
    if (view === 'scan' || view === 'scan-history') {
      setView('list');
    } else if (view === 'list') {
      setView('projects');
      setCurrentProjectId(null);
    } else {
      setView('list');
      setSelectedId(null);
    }
  };

  const handleEdit = (id: string) => {
    setSelectedId(id);
    setView('edit');
  };

  const handleCreate = () => {
    setView('create');
  };

  const handleSaved = (sub: Subscription, isNew: boolean) => {
    fetchSubscriptions();
    setView('detail');
    setSelectedId(sub.id);
    showMessage('success', isNew ? 'Subscription created' : 'Subscription updated');
  };

  const handleDeleted = () => {
    fetchSubscriptions();
    handleBack();
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
                  setCurrentProjectId(null);
                  setView('projects');
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
              onClick={() => setView('project-add')}
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
              onAddProject={() => setView('project-add')}
            />
          )}
        </>
      )}

      {view === 'project-add' && (
        <ProjectForm
          onCancel={() => setView('projects')}
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
              <button onClick={() => setView('scan')} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>
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
      {view === 'detail' && selectedSub && (
        <SubscriptionDetail
          subscription={selectedSub}
          onBack={handleBack}
          onEdit={() => handleEdit(selectedSub.id)}
          onDeleted={handleDeleted}
          onReactivated={fetchSubscriptions}
          showMessage={showMessage}
        />
      )}

      {/* Subscription Form */}
      {(view === 'create' || view === 'edit') && (
        <SubscriptionForm
          subscription={view === 'edit' ? selectedSub : null}
          onCancel={view === 'edit' && selectedSub ? () => setView('detail') : handleBack}
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
            setView('scan-history');
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
            // Could navigate to scan-detail view
            console.log('Selected scan:', id);
          }}
          onClear={handleClearHistory}
          onBack={() => setView('scan')}
        />
      )}
    </div>
  );
}
