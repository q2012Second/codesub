import { useState } from 'react';
import type { Subscription } from '../types';
import { deleteSubscription, reactivateSubscription } from '../api';

interface Props {
  subscription: Subscription;
  onBack: () => void;
  onEdit: () => void;
  onDeleted: () => void;
  onReactivated: () => void;
  showMessage: (type: 'success' | 'error', text: string) => void;
}

export function SubscriptionDetail({ subscription: sub, onBack, onEdit, onDeleted, onReactivated, showMessage }: Props) {
  const [deleting, setDeleting] = useState(false);
  const [confirmHardDelete, setConfirmHardDelete] = useState(false);

  const location = sub.start_line === sub.end_line
    ? `${sub.path}:${sub.start_line}`
    : `${sub.path}:${sub.start_line}-${sub.end_line}`;

  const handleDelete = async (hard: boolean) => {
    if (hard && !confirmHardDelete) {
      setConfirmHardDelete(true);
      return;
    }
    try {
      setDeleting(true);
      await deleteSubscription(sub.id, hard);
      onDeleted();
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Failed to delete');
      setDeleting(false);
    }
  };

  const handleReactivate = async () => {
    try {
      await reactivateSubscription(sub.id);
      onReactivated();
      showMessage('success', 'Subscription reactivated');
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Failed to reactivate');
    }
  };

  return (
    <div>
      <button onClick={onBack} style={{ marginBottom: 16 }}>&larr; Back to list</button>

      <div style={{ background: '#f8f9fa', padding: 20, borderRadius: 6, marginBottom: 20 }}>
        <h2 style={{ marginBottom: 20, fontSize: 18 }}>Subscription Details</h2>

        <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '12px 20px' }}>
          <dt style={{ fontWeight: 600, color: '#555' }}>ID:</dt>
          <dd style={{ fontFamily: 'monospace', fontSize: 13 }}>{sub.id}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Location:</dt>
          <dd style={{ fontFamily: 'monospace', fontSize: 13 }}>{location}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Label:</dt>
          <dd>{sub.label || <span style={{ color: '#999' }}>-</span>}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Description:</dt>
          <dd>{sub.description || <span style={{ color: '#999' }}>-</span>}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Status:</dt>
          <dd>
            <span style={{
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 12,
              background: sub.active ? '#d4edda' : '#e9ecef',
              color: sub.active ? '#155724' : '#6c757d',
            }}>
              {sub.active ? 'Active' : 'Inactive'}
            </span>
          </dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Lines watched:</dt>
          <dd>{sub.end_line - sub.start_line + 1}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Created:</dt>
          <dd>{new Date(sub.created_at).toLocaleString()}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Updated:</dt>
          <dd>{new Date(sub.updated_at).toLocaleString()}</dd>
        </dl>

        {sub.anchors && (
          <div style={{ marginTop: 24 }}>
            <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Watched Lines:</h3>
            <pre style={{
              background: '#fff',
              padding: 16,
              borderRadius: 4,
              overflow: 'auto',
              fontSize: 13,
              lineHeight: 1.6,
              border: '1px solid #e9ecef',
            }}>
              {sub.anchors.context_before.map((line, i) => (
                <div key={`before-${i}`} style={{ color: '#6c757d' }}>{line || ' '}</div>
              ))}
              {sub.anchors.lines.map((line, i) => (
                <div key={`line-${i}`} style={{ background: '#fff3cd', margin: '0 -16px', padding: '0 16px' }}>{line || ' '}</div>
              ))}
              {sub.anchors.context_after.map((line, i) => (
                <div key={`after-${i}`} style={{ color: '#6c757d' }}>{line || ' '}</div>
              ))}
            </pre>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button onClick={onEdit}>Edit</button>

        {!sub.active && (
          <button onClick={handleReactivate} style={{ background: '#d4edda', borderColor: '#c3e6cb' }}>
            Reactivate
          </button>
        )}

        {sub.active && (
          <button onClick={() => handleDelete(false)} disabled={deleting}>
            Deactivate
          </button>
        )}

        {confirmHardDelete ? (
          <>
            <button
              onClick={() => handleDelete(true)}
              disabled={deleting}
              style={{ background: '#dc3545', color: 'white', borderColor: '#dc3545' }}
            >
              Confirm Delete Forever
            </button>
            <button onClick={() => setConfirmHardDelete(false)}>Cancel</button>
          </>
        ) : (
          <button
            onClick={() => handleDelete(true)}
            disabled={deleting}
            style={{ color: '#dc3545', borderColor: '#dc3545' }}
          >
            Delete Forever
          </button>
        )}
      </div>
    </div>
  );
}
