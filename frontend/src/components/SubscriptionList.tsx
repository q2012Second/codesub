import type { Subscription } from '../types';

interface Props {
  subscriptions: Subscription[];
  onSelect: (id: string) => void;
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
            <td style={{ padding: '12px 8px', fontFamily: 'monospace', fontSize: 13 }}>
              {sub.path}:{sub.start_line === sub.end_line
                ? sub.start_line
                : `${sub.start_line}-${sub.end_line}`}
            </td>
            <td style={{ padding: '12px 8px' }}>{sub.label || <span style={{ color: '#999' }}>-</span>}</td>
            <td style={{ padding: '12px 8px' }}>
              <span style={{
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 12,
                background: sub.active ? '#d4edda' : '#e9ecef',
                color: sub.active ? '#155724' : '#6c757d',
              }}>
                {sub.active ? 'active' : 'inactive'}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
