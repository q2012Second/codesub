import { useState } from 'react';
import type { Subscription, SubscriptionCreateRequest, SubscriptionUpdateRequest } from '../types';
import { createProjectSubscription, updateProjectSubscription } from '../api';

interface Props {
  subscription: Subscription | null;  // null = create mode
  projectId: string;
  onCancel: () => void;
  onSaved: (sub: Subscription, isNew: boolean) => void;
  showMessage: (type: 'success' | 'error', text: string) => void;
}

export function SubscriptionForm({ subscription, projectId, onCancel, onSaved, showMessage }: Props) {
  const isEdit = subscription !== null;

  const [location, setLocation] = useState('');
  const [label, setLabel] = useState(subscription?.label || '');
  const [description, setDescription] = useState(subscription?.description || '');
  const [context, setContext] = useState(2);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      let result: Subscription;

      if (isEdit && subscription) {
        const data: SubscriptionUpdateRequest = {
          label: label || undefined,
          description: description || undefined,
        };
        result = await updateProjectSubscription(projectId, subscription.id, data);
      } else {
        const data: SubscriptionCreateRequest = {
          location,
          label: label || undefined,
          description: description || undefined,
          context,
        };
        result = await createProjectSubscription(projectId, data);
      }

      onSaved(result, !isEdit);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to save';
      setError(msg);
      showMessage('error', msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: 20, fontSize: 18 }}>
        {isEdit ? 'Edit Subscription' : 'Create Subscription'}
      </h2>

      <form onSubmit={handleSubmit} style={{ maxWidth: 500 }}>
        {!isEdit && (
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
              Location <span style={{ color: '#dc3545' }}>*</span>
            </label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="path/to/file.py:42 or path/to/file.py::ClassName.method"
              required
              style={{ width: '100%', fontFamily: 'monospace' }}
            />
            <small style={{ color: '#666', display: 'block', marginTop: 4 }}>
              <strong>Line-based:</strong> path:line or path:start-end (e.g., config.py:10-25)
              <br />
              <strong>Semantic:</strong> path::QualifiedName (e.g., auth.py::User.validate)
            </small>
            {location.includes('::') && location.split('::')[1]?.trim() && (
              <div
                style={{
                  marginTop: 8,
                  padding: '8px 12px',
                  background: '#d1ecf1',
                  borderRadius: 4,
                  fontSize: 13,
                  color: '#0c5460',
                }}
              >
                Detected: <strong>semantic subscription</strong> - will track code construct by identity
              </div>
            )}
          </div>
        )}

        {isEdit && subscription && (
          <div style={{ marginBottom: 20, padding: 16, background: '#f8f9fa', borderRadius: 4 }}>
            <strong>Location:</strong>{' '}
            <code style={{ fontSize: 13 }}>
              {subscription.semantic
                ? `${subscription.path}::${subscription.semantic.qualname}`
                : subscription.start_line === subscription.end_line
                  ? `${subscription.path}:${subscription.start_line}`
                  : `${subscription.path}:${subscription.start_line}-${subscription.end_line}`}
            </code>
            {subscription.semantic && (
              <span
                style={{
                  marginLeft: 8,
                  padding: '2px 6px',
                  borderRadius: 3,
                  fontSize: 11,
                  background: '#d1ecf1',
                  color: '#0c5460',
                }}
              >
                {subscription.semantic.kind}
              </span>
            )}
          </div>
        )}

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
            Label
          </label>
          <input
            type="text"
            value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder="Optional label"
            style={{ width: '100%' }}
          />
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
            Description
          </label>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Optional description"
            rows={3}
            style={{ width: '100%', resize: 'vertical' }}
          />
        </div>

        {!isEdit && (
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
              Context lines
            </label>
            <input
              type="number"
              value={context}
              onChange={e => setContext(parseInt(e.target.value) || 0)}
              min={0}
              max={10}
              style={{ width: 80 }}
            />
            <small style={{ color: '#666', marginLeft: 8 }}>
              Lines before/after for anchors (0-10)
            </small>
          </div>
        )}

        {error && (
          <div style={{ marginBottom: 20, padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 4 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" disabled={saving} style={{ background: '#0066cc', color: 'white', borderColor: '#0066cc' }}>
            {saving ? 'Saving...' : (isEdit ? 'Save Changes' : 'Create')}
          </button>
          <button type="button" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
