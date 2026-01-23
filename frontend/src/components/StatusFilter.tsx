import type { FilterStatus } from '../types';

interface Props {
  value: FilterStatus;
  onChange: (value: FilterStatus) => void;
}

export function StatusFilter({ value, onChange }: Props) {
  return (
    <div>
      <label style={{ marginRight: 12 }}>
        <input
          type="radio"
          name="filter"
          checked={value === 'active'}
          onChange={() => onChange('active')}
        />{' '}
        Active only
      </label>
      <label>
        <input
          type="radio"
          name="filter"
          checked={value === 'all'}
          onChange={() => onChange('all')}
        />{' '}
        Show all
      </label>
    </div>
  );
}
