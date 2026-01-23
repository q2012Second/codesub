import { useState } from 'react';
import type { Proposal } from '../types';

interface ApplyUpdatesModalProps {
  proposals: Proposal[];
  onConfirm: (proposalIds?: string[]) => void;
  onCancel: () => void;
}

export function ApplyUpdatesModal({
  proposals,
  onConfirm,
  onCancel,
}: ApplyUpdatesModalProps) {
  const [selected, setSelected] = useState<Set<string>>(
    new Set(proposals.map(p => p.subscription_id))
  );

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelected(next);
  };

  const handleConfirm = () => {
    if (selected.size === proposals.length) {
      onConfirm(); // Apply all
    } else {
      onConfirm(Array.from(selected));
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: 'white',
          borderRadius: 8,
          padding: 24,
          maxWidth: 500,
          width: '90%',
          maxHeight: '80vh',
          overflow: 'auto',
        }}
      >
        <h3 style={{ marginBottom: 16 }}>Apply Updates</h3>
        <p style={{ marginBottom: 16, color: '#666' }}>
          This will update the selected subscriptions and advance the baseline.
          This action cannot be undone.
        </p>

        <div style={{ marginBottom: 16 }}>
          {proposals.map(p => (
            <label
              key={p.subscription_id}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                padding: 8,
                border: '1px solid #ddd',
                borderRadius: 4,
                marginBottom: 4,
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(p.subscription_id)}
                onChange={() => toggleSelect(p.subscription_id)}
              />
              <div>
                <div style={{ fontWeight: 500 }}>
                  {p.label || p.subscription_id.slice(0, 8)}
                </div>
                <div style={{ fontSize: 12, fontFamily: 'monospace', color: '#666' }}>
                  {p.old_path}:{p.old_start}-{p.old_end}
                  {' -> '}
                  {p.new_path}:{p.new_start}-{p.new_end}
                </div>
              </div>
            </label>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onCancel} style={{ padding: '8px 16px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>Cancel</button>
          <button
            onClick={handleConfirm}
            disabled={selected.size === 0}
            style={{
              background: '#28a745',
              color: 'white',
              border: '1px solid #28a745',
              padding: '8px 16px',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Apply {selected.size} Update(s)
          </button>
        </div>
      </div>
    </div>
  );
}
