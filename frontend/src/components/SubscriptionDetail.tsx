import { useState } from 'react';
import type { Subscription } from '../types';
import { deleteProjectSubscription, reactivateProjectSubscription } from '../api';

interface Props {
  subscription: Subscription;
  projectId: string;
  onBack: () => void;
  onEdit: () => void;
  onDeleted: () => void;
  onReactivated: () => void;
  showMessage: (type: 'success' | 'error', text: string) => void;
}

export function SubscriptionDetail({
  subscription: sub,
  projectId,
  onBack,
  onEdit,
  onDeleted,
  onReactivated,
  showMessage,
}: Props) {
  const [deleting, setDeleting] = useState(false);
  const [confirmHardDelete, setConfirmHardDelete] = useState(false);

  const isSemantic = sub.semantic != null;
  // Include kind in location for semantic subscriptions
  const location = sub.semantic
    ? `${sub.path}::${sub.semantic.kind}:${sub.semantic.qualname}`
    : sub.start_line === sub.end_line
      ? `${sub.path}:${sub.start_line}`
      : `${sub.path}:${sub.start_line}-${sub.end_line}`;

  const handleDelete = async (hard: boolean) => {
    if (hard && !confirmHardDelete) {
      setConfirmHardDelete(true);
      return;
    }
    try {
      setDeleting(true);
      await deleteProjectSubscription(projectId, sub.id, hard);
      onDeleted();
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Failed to delete');
      setDeleting(false);
    }
  };

  const handleReactivate = async () => {
    try {
      await reactivateProjectSubscription(projectId, sub.id);
      onReactivated();
      showMessage('success', 'Subscription reactivated');
    } catch (e) {
      showMessage('error', e instanceof Error ? e.message : 'Failed to reactivate');
    }
  };

  return (
    <div>
      <button onClick={onBack} style={{ marginBottom: 16 }}>
        &larr; Back to list
      </button>

      <div style={{ background: '#f8f9fa', padding: 20, borderRadius: 6, marginBottom: 20 }}>
        <h2 style={{ marginBottom: 20, fontSize: 18 }}>Subscription Details</h2>

        <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '12px 20px' }}>
          <dt style={{ fontWeight: 600, color: '#555' }}>ID:</dt>
          <dd style={{ fontFamily: 'monospace', fontSize: 13 }}>{sub.id}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Type:</dt>
          <dd>
            <span
              style={{
                display: 'inline-block',
                padding: '2px 6px',
                borderRadius: 3,
                fontSize: 11,
                fontWeight: 600,
                background: isSemantic ? '#d1ecf1' : '#f5f5f5',
                color: isSemantic ? '#0c5460' : '#666',
                border: `1px solid ${isSemantic ? '#bee5eb' : '#ddd'}`,
              }}
            >
              {isSemantic ? 'Semantic' : 'Line-based'}
            </span>
          </dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Location:</dt>
          <dd style={{ fontFamily: 'monospace', fontSize: 13 }}>{location}</dd>

          {isSemantic && sub.semantic && (
            <>
              <dt style={{ fontWeight: 600, color: '#555' }}>Kind:</dt>
              <dd style={{ textTransform: 'capitalize' }}>
                {sub.semantic.kind}
                {sub.semantic.role && (
                  <span
                    style={{
                      marginLeft: 8,
                      fontSize: 11,
                      color: '#856404',
                      background: '#fff3cd',
                      padding: '1px 4px',
                      borderRadius: 3,
                    }}
                  >
                    {sub.semantic.role}
                  </span>
                )}
              </dd>

              <dt style={{ fontWeight: 600, color: '#555' }}>Qualified Name:</dt>
              <dd style={{ fontFamily: 'monospace', fontSize: 13 }}>{sub.semantic.qualname}</dd>

              <dt style={{ fontWeight: 600, color: '#555' }}>Language:</dt>
              <dd style={{ textTransform: 'capitalize' }}>{sub.semantic.language}</dd>

              <dt style={{ fontWeight: 600, color: '#555' }}>Tracking Options:</dt>
              <dd>
                {sub.trigger_on_duplicate && (
                  <span
                    style={{
                      display: 'inline-block',
                      padding: '2px 6px',
                      borderRadius: 3,
                      fontSize: 11,
                      background: '#e2e3e5',
                      color: '#41464b',
                      marginRight: 6,
                    }}
                  >
                    Trigger on duplicate
                  </span>
                )}
                {sub.semantic.include_members && (
                  <span
                    style={{
                      display: 'inline-block',
                      padding: '2px 6px',
                      borderRadius: 3,
                      fontSize: 11,
                      background: '#cfe2ff',
                      color: '#084298',
                      marginRight: 6,
                    }}
                  >
                    Track members
                  </span>
                )}
                {!sub.trigger_on_duplicate && !sub.semantic.include_members && (
                  <span style={{ color: '#999' }}>Default</span>
                )}
              </dd>
            </>
          )}

          <dt style={{ fontWeight: 600, color: '#555' }}>Label:</dt>
          <dd>{sub.label || <span style={{ color: '#999' }}>-</span>}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Description:</dt>
          <dd>{sub.description || <span style={{ color: '#999' }}>-</span>}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Status:</dt>
          <dd>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 12,
                background: sub.active ? '#d4edda' : '#e9ecef',
                color: sub.active ? '#155724' : '#6c757d',
              }}
            >
              {sub.active ? 'Active' : 'Inactive'}
            </span>
          </dd>

          {!isSemantic && (
            <>
              <dt style={{ fontWeight: 600, color: '#555' }}>Lines watched:</dt>
              <dd>{sub.end_line - sub.start_line + 1}</dd>
            </>
          )}

          <dt style={{ fontWeight: 600, color: '#555' }}>Created:</dt>
          <dd>{new Date(sub.created_at).toLocaleString()}</dd>

          <dt style={{ fontWeight: 600, color: '#555' }}>Updated:</dt>
          <dd>{new Date(sub.updated_at).toLocaleString()}</dd>
        </dl>

        {/* Fingerprint details for semantic subscriptions */}
        {isSemantic && sub.semantic && (
          <details style={{ marginTop: 16 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600, color: '#555', fontSize: 14 }}>
              Fingerprint Details
            </summary>
            <div
              style={{
                marginTop: 8,
                padding: 12,
                background: '#fff',
                border: '1px solid #e9ecef',
                borderRadius: 4,
              }}
            >
              <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px', margin: 0 }}>
                <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Interface Hash:</dt>
                <dd style={{ fontFamily: 'monospace', fontSize: 12, color: '#333' }}>
                  {sub.semantic.interface_hash || '-'}
                </dd>

                <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Body Hash:</dt>
                <dd style={{ fontFamily: 'monospace', fontSize: 12, color: '#333' }}>
                  {sub.semantic.body_hash || '-'}
                </dd>

                <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Fingerprint Version:</dt>
                <dd style={{ fontFamily: 'monospace', fontSize: 12, color: '#333' }}>
                  {sub.semantic.fingerprint_version ?? '-'}
                </dd>
              </dl>
            </div>
          </details>
        )}

        {/* Container Tracking details for aggregate subscriptions */}
        {isSemantic && sub.semantic && sub.semantic.include_members && (
          <details style={{ marginTop: 16 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600, color: '#555', fontSize: 14 }}>
              Container Tracking Details
            </summary>
            <div
              style={{
                marginTop: 8,
                padding: 12,
                background: '#fff',
                border: '1px solid #e9ecef',
                borderRadius: 4,
              }}
            >
              <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px', margin: 0 }}>
                <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Include Private:</dt>
                <dd style={{ fontSize: 13 }}>
                  <span
                    style={{
                      padding: '1px 6px',
                      background: sub.semantic.include_private ? '#d4edda' : '#f8d7da',
                      borderRadius: 3,
                      fontSize: 11,
                    }}
                  >
                    {sub.semantic.include_private ? 'Yes' : 'No'}
                  </span>
                </dd>

                <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Track Decorators:</dt>
                <dd style={{ fontSize: 13 }}>
                  <span
                    style={{
                      padding: '1px 6px',
                      background: sub.semantic.track_decorators ? '#d4edda' : '#f8d7da',
                      borderRadius: 3,
                      fontSize: 11,
                    }}
                  >
                    {sub.semantic.track_decorators ? 'Yes' : 'No'}
                  </span>
                </dd>

                {sub.semantic.baseline_container_qualname &&
                  sub.semantic.baseline_container_qualname !== sub.semantic.qualname && (
                    <>
                      <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Original Name:</dt>
                      <dd style={{ fontFamily: 'monospace', fontSize: 12 }}>
                        {sub.semantic.baseline_container_qualname}
                        <span style={{ color: '#dc3545', marginLeft: 8 }}>(renamed)</span>
                      </dd>
                    </>
                  )}

                {sub.semantic.baseline_members && (
                  <>
                    <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Tracked Members:</dt>
                    <dd style={{ fontSize: 13 }}>
                      {Object.keys(sub.semantic.baseline_members).length} members
                    </dd>
                  </>
                )}
              </dl>

              {sub.semantic.baseline_members &&
                Object.keys(sub.semantic.baseline_members).length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontWeight: 500, color: '#666', fontSize: 13, marginBottom: 8 }}>
                      Baseline Members:
                    </div>
                    <div
                      style={{
                        maxHeight: 200,
                        overflow: 'auto',
                        background: '#f8f9fa',
                        borderRadius: 4,
                        padding: 8,
                      }}
                    >
                      {Object.entries(sub.semantic.baseline_members).map(([name, fp]) => (
                        <div
                          key={name}
                          style={{
                            fontFamily: 'monospace',
                            fontSize: 12,
                            padding: '2px 0',
                            display: 'flex',
                            gap: 8,
                          }}
                        >
                          <span style={{ color: '#666', minWidth: 60 }}>{fp.kind}</span>
                          <span>{name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
            </div>
          </details>
        )}

        {sub.anchors && (
          <div style={{ marginTop: 24 }}>
            <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Watched Lines:</h3>
            <pre
              style={{
                background: '#fff',
                padding: 16,
                borderRadius: 4,
                overflow: 'auto',
                fontSize: 13,
                lineHeight: 1.6,
                border: '1px solid #e9ecef',
              }}
            >
              {sub.anchors.context_before.map((line, i) => (
                <div key={`before-${i}`} style={{ color: '#6c757d' }}>
                  {line || ' '}
                </div>
              ))}
              {sub.anchors.lines.map((line, i) => (
                <div
                  key={`line-${i}`}
                  style={{ background: '#fff3cd', margin: '0 -16px', padding: '0 16px' }}
                >
                  {line || ' '}
                </div>
              ))}
              {sub.anchors.context_after.map((line, i) => (
                <div key={`after-${i}`} style={{ color: '#6c757d' }}>
                  {line || ' '}
                </div>
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
