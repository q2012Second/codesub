import { useState, useMemo } from 'react';
import type { Subscription, SubscriptionCreateRequest, SubscriptionUpdateRequest, CodeBrowserSelection } from '../types';
import { isContainerKind, parseSemanticLocation } from '../types';
import { createProjectSubscription, updateProjectSubscription } from '../api';
import { CodeBrowserModal } from './CodeBrowserModal';

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
  const [labelAutoFilled, setLabelAutoFilled] = useState(false);
  const [description, setDescription] = useState(subscription?.description || '');
  const [context, setContext] = useState(2);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showBrowser, setShowBrowser] = useState(false);

  // Container tracking options
  const [includeMembers, setIncludeMembers] = useState(false);
  const [includePrivate, setIncludePrivate] = useState(false);
  const [trackDecorators, setTrackDecorators] = useState(true);
  const [triggerOnDuplicate, setTriggerOnDuplicate] = useState(
    subscription?.trigger_on_duplicate ?? false
  );

  // Derive kind from location (works for both browser and manual entry)
  const parsedLocation = useMemo(() => parseSemanticLocation(location), [location]);
  const isSemanticLocation = parsedLocation !== null;
  const selectedKind = parsedLocation?.kind ?? null;
  const showContainerOptions = isContainerKind(selectedKind);

  const handleBrowserSelect = (selection: CodeBrowserSelection) => {
    setLocation(selection.location);
    // Update label if it was auto-filled or is empty
    if (selection.label && (labelAutoFilled || !label)) {
      setLabel(selection.label);
      setLabelAutoFilled(true);
    }
    // Reset container options if switching to non-container
    if (!isContainerKind(selection.kind)) {
      setIncludeMembers(false);
      setIncludePrivate(false);
      setTrackDecorators(true);
    }
    setShowBrowser(false);
  };

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
          trigger_on_duplicate: triggerOnDuplicate,
        };
        result = await updateProjectSubscription(projectId, subscription.id, data);
      } else {
        const data: SubscriptionCreateRequest = {
          location,
          label: label || undefined,
          description: description || undefined,
          context,
          trigger_on_duplicate: triggerOnDuplicate,
          include_members: showContainerOptions && includeMembers ? true : undefined,
          include_private: showContainerOptions && includeMembers && includePrivate ? true : undefined,
          track_decorators: showContainerOptions && includeMembers ? trackDecorators : undefined,
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
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="path/to/file.py:42 or path/to/file.py::ClassName.method"
                required
                style={{ flex: 1, fontFamily: 'monospace' }}
              />
              <button
                type="button"
                onClick={() => setShowBrowser(true)}
                style={{
                  padding: '8px 16px',
                  border: '1px solid #ddd',
                  borderRadius: 4,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  background: '#f8f9fa',
                }}
              >
                Browse...
              </button>
            </div>
            <small style={{ color: '#666', display: 'block', marginTop: 4 }}>
              <strong>Line-based:</strong> path:line or path:start-end (e.g., config.py:10-25)
              <br />
              <strong>Semantic:</strong> path::QualifiedName (e.g., auth.py::User.validate)
            </small>
            {isSemanticLocation && (
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
                Detected: <strong>semantic subscription</strong>
                {selectedKind && (
                  <>
                    {' - '}
                    <strong>{selectedKind}</strong>
                    {isContainerKind(selectedKind) && ' (container)'}
                  </>
                )}
                {!selectedKind && (
                  <span style={{ color: '#666', marginLeft: 8 }}>
                    (Tip: use <code>path::kind:qualname</code> for explicit kind)
                  </span>
                )}
              </div>
            )}

            {/* Configuration options for semantic subscriptions */}
            {isSemanticLocation && (
              <div style={{
                marginTop: 12,
                padding: 16,
                background: '#f8f9fa',
                borderRadius: 4,
                border: '1px solid #e9ecef',
              }}>
                <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>
                  Subscription Options
                </div>

                {/* Trigger on duplicate - available for all semantic subscriptions */}
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={triggerOnDuplicate}
                    onChange={(e) => setTriggerOnDuplicate(e.target.checked)}
                  />
                  <span>Trigger if construct found in multiple files</span>
                </label>

                {/* Container-specific options */}
                {showContainerOptions && (
                  <>
                    <div style={{
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid #dee2e6',
                      marginBottom: 8,
                      fontWeight: 500,
                      fontSize: 13,
                      color: '#495057',
                    }}>
                      Container Tracking
                    </div>

                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={includeMembers}
                        onChange={(e) => setIncludeMembers(e.target.checked)}
                      />
                      <span>Track all members (trigger on any member change)</span>
                    </label>

                    {includeMembers && (
                      <>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, marginLeft: 24, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={includePrivate}
                            onChange={(e) => setIncludePrivate(e.target.checked)}
                          />
                          <span>Include private members (_prefixed, Python only)</span>
                        </label>

                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 24, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={trackDecorators}
                            onChange={(e) => setTrackDecorators(e.target.checked)}
                          />
                          <span>Track decorator changes</span>
                        </label>
                      </>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {isEdit && subscription && (
          <div style={{ marginBottom: 20, padding: 16, background: '#f8f9fa', borderRadius: 4 }}>
            <div style={{ marginBottom: 12 }}>
              <strong>Location:</strong>{' '}
              <code style={{ fontSize: 13 }}>
                {subscription.semantic
                  ? `${subscription.path}::${subscription.semantic.kind}:${subscription.semantic.qualname}`
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
                    background: isContainerKind(subscription.semantic.kind) ? '#e3f2fd' : '#d1ecf1',
                    color: isContainerKind(subscription.semantic.kind) ? '#0d47a1' : '#0c5460',
                  }}
                >
                  {subscription.semantic.kind}
                  {isContainerKind(subscription.semantic.kind) && ' (container)'}
                </span>
              )}
            </div>

            {/* Editable trigger_on_duplicate for semantic subscriptions */}
            {subscription.semantic && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={triggerOnDuplicate}
                  onChange={(e) => setTriggerOnDuplicate(e.target.checked)}
                />
                <span>Trigger if construct found in multiple files</span>
              </label>
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
            onChange={e => { setLabel(e.target.value); setLabelAutoFilled(false); }}
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

      {showBrowser && (
        <CodeBrowserModal
          projectId={projectId}
          onSelect={handleBrowserSelect}
          onCancel={() => setShowBrowser(false)}
        />
      )}
    </div>
  );
}
