import type { Proposal } from '../types';
import { formatReasons } from '../utils/scanFormatters';

interface ProposalCardProps {
  proposal: Proposal;
}

export function ProposalCard({ proposal }: ProposalCardProps) {
  const hasSemanticRename = proposal.new_qualname != null;

  return (
    <div
      style={{
        padding: 12,
        border: '1px solid #ffeeba',
        background: '#fff3cd',
        borderRadius: 4,
        marginBottom: 8,
      }}
    >
      <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
        {proposal.label || proposal.subscription_id.slice(0, 8)}
        {hasSemanticRename && (
          <span
            style={{
              fontSize: 10,
              padding: '1px 4px',
              borderRadius: 3,
              background: '#e3f2fd',
              color: '#1565c0',
              border: '1px solid #90caf9',
            }}
          >
            RENAME
          </span>
        )}
      </div>
      <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
        {proposal.old_path}:{proposal.old_start}-{proposal.old_end}
        {' -> '}
        {proposal.new_path}:{proposal.new_start}-{proposal.new_end}
      </div>
      {hasSemanticRename && (
        <div
          style={{ fontSize: 13, fontFamily: 'monospace', color: '#1565c0', marginTop: 4 }}
        >
          Rename to: {proposal.new_qualname}
          {proposal.new_kind && ` (${proposal.new_kind})`}
        </div>
      )}
      <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
        {formatReasons(proposal.reasons)}
        {proposal.shift !== null && ` (${proposal.shift > 0 ? '+' : ''}${proposal.shift} lines)`}
      </div>
    </div>
  );
}
