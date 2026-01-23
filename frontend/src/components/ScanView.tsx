import { useState } from 'react';
import { runScan, getScanResult, applyUpdates } from '../api';
import type { ScanHistoryEntryFull, Trigger, Proposal } from '../types';
import { ApplyUpdatesModal } from './ApplyUpdatesModal';

const REASON_LABELS: Record<string, string> = {
  overlap_hunk: 'Lines in range were modified',
  insert_inside_range: 'New lines inserted inside range',
  file_deleted: 'File was deleted',
  line_shift: 'Lines shifted due to changes above',
  rename: 'File was renamed or moved',
};

function formatReasons(reasons: string[]): string {
  return reasons.map(r => REASON_LABELS[r] || r).join('; ');
}

interface ScanViewProps {
  projectId: string;
  baselineRef: string;
  onBack: () => void;
  onViewHistory: () => void;
  showMessage: (type: 'success' | 'error', text: string) => void;
  onBaselineUpdated: () => void;
}

export function ScanView({
  projectId,
  baselineRef,
  onBack,
  onViewHistory,
  showMessage,
  onBaselineUpdated,
}: ScanViewProps) {
  const [baseRef, setBaseRef] = useState(baselineRef);
  const [targetRef, setTargetRef] = useState('HEAD');
  const [loading, setLoading] = useState(false);
  const [scanResult, setScanResult] = useState<ScanHistoryEntryFull | null>(null);
  const [showApplyModal, setShowApplyModal] = useState(false);

  const handleScan = async () => {
    try {
      setLoading(true);
      const entry = await runScan(projectId, { base_ref: baseRef, target_ref: targetRef });
      const full = await getScanResult(projectId, entry.id);
      setScanResult(full);
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Scan failed');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickScan = async (base: string, target: string, label: string) => {
    setBaseRef(base);
    setTargetRef(target);
    try {
      setLoading(true);
      const entry = await runScan(projectId, { base_ref: base, target_ref: target });
      const full = await getScanResult(projectId, entry.id);
      setScanResult(full);
      showMessage('success', `${label} scan complete`);
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Scan failed');
    } finally {
      setLoading(false);
    }
  };

  const handleApplyUpdates = async (proposalIds?: string[]) => {
    if (!scanResult) return;

    try {
      const result = await applyUpdates(projectId, {
        scan_id: scanResult.id,
        proposal_ids: proposalIds,
      });

      if (result.warnings.length > 0) {
        showMessage('error', `Warnings: ${result.warnings.join(', ')}`);
      }

      if (result.applied.length > 0) {
        showMessage('success', `Applied ${result.applied.length} update(s)`);
        onBaselineUpdated();
        setScanResult(null);
      }

      setShowApplyModal(false);
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Failed to apply updates');
    }
  };

  const result = scanResult?.scan_result;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
        <button onClick={onBack} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>Back</button>
        <button onClick={onViewHistory} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>View History</button>
      </div>

      <h2 style={{ marginBottom: 16 }}>Run Scan</h2>

      {/* Quick Actions */}
      <div style={{ marginBottom: 20, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          onClick={() => handleQuickScan('HEAD', '', 'Uncommitted')}
          disabled={loading}
          style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}
        >
          Scan Uncommitted
        </button>
        <button
          onClick={() => handleQuickScan('HEAD~1', 'HEAD', 'Last commit')}
          disabled={loading}
          style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}
        >
          Scan Last Commit
        </button>
        <button
          onClick={() => handleQuickScan(baselineRef, 'HEAD', 'Since baseline')}
          disabled={loading}
          style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}
        >
          Scan Since Baseline
        </button>
      </div>

      {/* Custom Scan Form */}
      <div style={{ marginBottom: 20, padding: 16, background: '#f5f5f5', borderRadius: 4 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
              Base Ref
            </label>
            <input
              type="text"
              value={baseRef}
              onChange={e => setBaseRef(e.target.value)}
              style={{ width: '100%', padding: 6, fontFamily: 'monospace', border: '1px solid #ddd', borderRadius: 4 }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
              Target Ref
            </label>
            <input
              type="text"
              value={targetRef}
              onChange={e => setTargetRef(e.target.value)}
              style={{ width: '100%', padding: 6, fontFamily: 'monospace', border: '1px solid #ddd', borderRadius: 4 }}
            />
          </div>
        </div>
        <button
          onClick={handleScan}
          disabled={loading || !baseRef}
          style={{ background: '#0066cc', color: 'white', border: '1px solid #0066cc', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}
        >
          {loading ? 'Scanning...' : 'Run Scan'}
        </button>
      </div>

      {/* Scan Results */}
      {result && (
        <div>
          <h3 style={{ marginBottom: 12 }}>
            Results: {scanResult.base_ref.slice(0, 8)}...{scanResult.target_ref.slice(0, 8)}
          </h3>

          {/* Triggers */}
          {result.triggers.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#dc3545', marginBottom: 8 }}>
                Triggered ({result.triggers.length})
              </h4>
              {result.triggers.map((t: Trigger) => (
                <div
                  key={t.subscription_id}
                  style={{
                    padding: 12,
                    border: '1px solid #f5c6cb',
                    background: '#f8d7da',
                    borderRadius: 4,
                    marginBottom: 8,
                  }}
                >
                  <div style={{ fontWeight: 500 }}>
                    {t.label || t.subscription_id.slice(0, 8)}
                  </div>
                  <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
                    {t.path}:{t.start_line}-{t.end_line}
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                    {formatReasons(t.reasons)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Proposals */}
          {result.proposals.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#856404', marginBottom: 8 }}>
                Proposed Updates ({result.proposals.length})
              </h4>
              {result.proposals.map((p: Proposal) => (
                <div
                  key={p.subscription_id}
                  style={{
                    padding: 12,
                    border: '1px solid #ffeeba',
                    background: '#fff3cd',
                    borderRadius: 4,
                    marginBottom: 8,
                  }}
                >
                  <div style={{ fontWeight: 500 }}>
                    {p.label || p.subscription_id.slice(0, 8)}
                  </div>
                  <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
                    {p.old_path}:{p.old_start}-{p.old_end}
                    {' -> '}
                    {p.new_path}:{p.new_start}-{p.new_end}
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                    {formatReasons(p.reasons)}
                    {p.shift !== null && ` (${p.shift > 0 ? '+' : ''}${p.shift} lines)`}
                  </div>
                </div>
              ))}

              <button
                onClick={() => setShowApplyModal(true)}
                style={{
                  marginTop: 8,
                  background: '#28a745',
                  color: 'white',
                  border: '1px solid #28a745',
                  padding: '8px 16px',
                  borderRadius: 4,
                  cursor: 'pointer',
                }}
              >
                Apply Updates
              </button>
            </div>
          )}

          {result.triggers.length === 0 && result.proposals.length === 0 && (
            <p style={{ color: '#666' }}>No changes detected for subscriptions.</p>
          )}
        </div>
      )}

      {showApplyModal && scanResult && (
        <ApplyUpdatesModal
          proposals={scanResult.scan_result.proposals}
          onConfirm={handleApplyUpdates}
          onCancel={() => setShowApplyModal(false)}
        />
      )}
    </div>
  );
}
