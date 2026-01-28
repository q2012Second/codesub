import type { Trigger } from '../types';
import {
  normalizeChangeType,
  formatDetails,
  formatReasons,
  CHANGE_TYPE_STYLES,
} from '../utils/scanFormatters';

interface TriggerCardProps {
  trigger: Trigger;
}

export function TriggerCard({ trigger }: TriggerCardProps) {
  const ct = normalizeChangeType(trigger.change_type);
  const changeStyle = ct ? CHANGE_TYPE_STYLES[ct] : null;

  const cardStyle = changeStyle
    ? {
        padding: 12,
        border: `1px solid ${changeStyle.border}`,
        background: changeStyle.bg,
        color: changeStyle.color,
        borderRadius: 4,
        marginBottom: 8,
      }
    : {
        padding: 12,
        border: '1px solid #f5c6cb',
        background: '#f8d7da',
        color: '#721c24',
        borderRadius: 4,
        marginBottom: 8,
      };

  return (
    <div style={cardStyle}>
      <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center' }}>
        {ct && <span>[{ct}] </span>}
        {trigger.label || trigger.subscription_id.slice(0, 8)}
      </div>
      <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
        {trigger.path}:{trigger.start_line}-{trigger.end_line}
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>{formatReasons(trigger.reasons)}</div>
      {trigger.details != null && (
        <pre
          style={{
            marginTop: 8,
            padding: 8,
            background: 'rgba(255,255,255,0.6)',
            borderRadius: 4,
            overflowX: 'auto',
            fontSize: 12,
          }}
        >
          {formatDetails(trigger.details)}
        </pre>
      )}
    </div>
  );
}
