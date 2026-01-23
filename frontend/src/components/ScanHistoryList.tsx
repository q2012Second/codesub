import type { ScanHistoryEntry } from '../types';

interface ScanHistoryListProps {
  scans: ScanHistoryEntry[];
  onSelect: (scanId: string) => void;
  onClear: () => void;
  onBack: () => void;
}

export function ScanHistoryList({
  scans,
  onSelect,
  onClear,
  onBack,
}: ScanHistoryListProps) {
  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleString();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
        <button onClick={onBack} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>Back</button>
        <button
          onClick={onClear}
          disabled={scans.length === 0}
          style={{ color: '#dc3545', padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}
        >
          Clear History
        </button>
      </div>

      <h2 style={{ marginBottom: 16 }}>Scan History</h2>

      {scans.length === 0 ? (
        <p style={{ color: '#666' }}>No scan history yet.</p>
      ) : (
        <div>
          {scans.map(scan => (
            <div
              key={scan.id}
              onClick={() => onSelect(scan.id)}
              style={{
                padding: 12,
                border: '1px solid #ddd',
                borderRadius: 4,
                marginBottom: 8,
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = '#f9f9f9')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
                  {scan.base_ref.slice(0, 8)}...{scan.target_ref.slice(0, 8)}
                </span>
                <span style={{ fontSize: 12, color: '#666' }}>
                  {formatDate(scan.created_at)}
                </span>
              </div>
              <div style={{ fontSize: 13, marginTop: 4, display: 'flex', gap: 16 }}>
                {scan.trigger_count > 0 && (
                  <span style={{ color: '#dc3545' }}>
                    {scan.trigger_count} triggered
                  </span>
                )}
                {scan.proposal_count > 0 && (
                  <span style={{ color: '#856404' }}>
                    {scan.proposal_count} proposals
                  </span>
                )}
                {scan.trigger_count === 0 && scan.proposal_count === 0 && (
                  <span style={{ color: '#666' }}>No changes</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
