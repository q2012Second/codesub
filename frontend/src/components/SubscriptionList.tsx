import type { Subscription } from '../types';

interface Props {
  subscriptions: Subscription[];
  onSelect: (id: string) => void;
}

// Helper to check if subscription is semantic
function isSemantic(sub: Subscription): boolean {
  return sub.semantic != null;
}

// Helper to format location display
function formatLocation(sub: Subscription): string {
  if (sub.semantic) {
    return `${sub.path}::${sub.semantic.qualname}`;
  }
  return sub.start_line === sub.end_line
    ? `${sub.path}:${sub.start_line}`
    : `${sub.path}:${sub.start_line}-${sub.end_line}`;
}

// Badge component for subscription type
function TypeBadge({ semantic }: { semantic: boolean }) {
  const style = {
    display: 'inline-block',
    padding: '1px 4px',
    borderRadius: 3,
    fontSize: 10,
    fontWeight: 600 as const,
    marginRight: 6,
    background: semantic ? '#d1ecf1' : '#f5f5f5',
    color: semantic ? '#0c5460' : '#666',
    border: `1px solid ${semantic ? '#bee5eb' : '#ddd'}`,
  };
  return <span style={style}>{semantic ? 'S' : 'L'}</span>;
}

export function SubscriptionList({ subscriptions, onSelect }: Props) {
  if (subscriptions.length === 0) {
    return <p style={{ color: '#666', padding: '20px 0' }}>No subscriptions found.</p>;
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd' }}>
          <th style={{ padding: '12px 8px' }}>ID</th>
          <th style={{ padding: '12px 8px' }}>Type</th>
          <th style={{ padding: '12px 8px' }}>Location</th>
          <th style={{ padding: '12px 8px' }}>Label</th>
          <th style={{ padding: '12px 8px' }}>Status</th>
        </tr>
      </thead>
      <tbody>
        {subscriptions.map((sub) => (
          <tr
            key={sub.id}
            onClick={() => onSelect(sub.id)}
            style={{
              cursor: 'pointer',
              borderBottom: '1px solid #eee',
              opacity: sub.active ? 1 : 0.6,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = '#f9f9f9')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <td style={{ padding: '12px 8px', fontFamily: 'monospace', fontSize: 13 }}>
              {sub.id.slice(0, 8)}
            </td>
            <td style={{ padding: '12px 8px' }}>
              <TypeBadge semantic={isSemantic(sub)} />
            </td>
            <td style={{ padding: '12px 8px' }}>
              {isSemantic(sub) && sub.semantic ? (
                <span>
                  <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
                    {sub.semantic.qualname}
                  </span>
                  <span style={{ color: '#666', marginLeft: 4 }}>({sub.semantic.kind})</span>
                  {sub.semantic.role === 'const' && (
                    <span
                      style={{
                        marginLeft: 6,
                        padding: '1px 4px',
                        borderRadius: 10,
                        fontSize: 10,
                        background: '#fff3cd',
                        color: '#856404',
                      }}
                    >
                      const
                    </span>
                  )}
                  <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#999', marginLeft: 8 }}>
                    {sub.path}:{sub.start_line}-{sub.end_line}
                  </span>
                </span>
              ) : (
                <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
                  {formatLocation(sub)}
                </span>
              )}
            </td>
            <td style={{ padding: '12px 8px' }}>{sub.label || <span style={{ color: '#999' }}>-</span>}</td>
            <td style={{ padding: '12px 8px' }}>
              <span
                style={{
                  padding: '2px 8px',
                  borderRadius: 4,
                  fontSize: 12,
                  background: sub.active ? '#d4edda' : '#e9ecef',
                  color: sub.active ? '#155724' : '#6c757d',
                }}
              >
                {sub.active ? 'active' : 'inactive'}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
