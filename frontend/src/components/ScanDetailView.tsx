import { useState, useEffect, useRef } from 'react';
import { getScanResult, applyUpdates } from '../api';
import type { ScanHistoryEntryFull } from '../types';
import { ApplyUpdatesModal } from './ApplyUpdatesModal';
import { TriggerCard } from './TriggerCard';
import { ProposalCard } from './ProposalCard';

interface ScanDetailViewProps {
  projectId: string;
  scanId: string;
  onBack: () => void;
  showMessage: (type: 'success' | 'error', text: string) => void;
  onBaselineUpdated: () => void;
}

export function ScanDetailView({
  projectId,
  scanId,
  onBack,
  showMessage,
  onBaselineUpdated,
}: ScanDetailViewProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<ScanHistoryEntryFull | null>(null);
  const [showApplyModal, setShowApplyModal] = useState(false);

  // Use ref to avoid showMessage in useEffect deps
  const showMessageRef = useRef(showMessage);
  showMessageRef.current = showMessage;

  useEffect(() => {
    async function loadScan() {
      try {
        setLoading(true);
        setError(null);
        const data = await getScanResult(projectId, scanId);
        setScanResult(data);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to load scan';
        setError(msg);
        showMessageRef.current('error', msg);
      } finally {
        setLoading(false);
      }
    }
    loadScan();
  }, [projectId, scanId]);

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
        // Reload to reflect applied state
        const data = await getScanResult(projectId, scanId);
        setScanResult(data);
      }

      setShowApplyModal(false);
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Failed to apply updates');
    }
  };

  const result = scanResult?.scan_result;

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <button
          onClick={onBack}
          style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}
        >
          Back to History
        </button>
      </div>

      {loading && <p style={{ color: '#666' }}>Loading scan details...</p>}

      {!loading && error && (
        <div style={{ padding: 16, background: '#f8d7da', color: '#721c24', borderRadius: 4 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {!loading && scanResult && result && (
        <>
          <h2 style={{ marginBottom: 8 }}>Scan Details</h2>
          <div style={{ marginBottom: 20, fontSize: 14, color: '#666' }}>
            <div>
              <strong>Refs:</strong>{' '}
              <span style={{ fontFamily: 'monospace' }}>
                {scanResult.base_ref.slice(0, 8)}...{scanResult.target_ref.slice(0, 8)}
              </span>
            </div>
            <div>
              <strong>Date:</strong> {new Date(scanResult.created_at).toLocaleString()}
            </div>
          </div>

          {/* Triggers */}
          {result.triggers.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#dc3545', marginBottom: 8 }}>
                Triggered ({result.triggers.length})
              </h4>
              {result.triggers.map((t, idx) => (
                <TriggerCard key={`${t.subscription_id}-${idx}`} trigger={t} />
              ))}
            </div>
          )}

          {/* Proposals */}
          {result.proposals.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#856404', marginBottom: 8 }}>
                Proposed Updates ({result.proposals.length})
              </h4>
              {result.proposals.map((p) => (
                <ProposalCard key={p.subscription_id} proposal={p} />
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

          {/* Unchanged */}
          {scanResult.unchanged_count > 0 && (
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#28a745', marginBottom: 8 }}>
                Unchanged ({scanResult.unchanged_count})
              </h4>
              <p style={{ fontSize: 13, color: '#666' }}>
                {scanResult.unchanged_count} subscription(s) had no changes detected.
              </p>
            </div>
          )}

          {/* No changes message - only show when nothing happened */}
          {result.triggers.length === 0 && result.proposals.length === 0 && scanResult.unchanged_count === 0 && (
            <p style={{ color: '#666' }}>No subscriptions were analyzed in this scan.</p>
          )}
        </>
      )}

      {showApplyModal && scanResult?.scan_result && (
        <ApplyUpdatesModal
          proposals={scanResult.scan_result.proposals}
          onConfirm={handleApplyUpdates}
          onCancel={() => setShowApplyModal(false)}
        />
      )}
    </div>
  );
}
