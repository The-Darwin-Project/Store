import { Label } from '@patternfly/react-core';

const statusColors: Record<string, 'blue' | 'green' | 'orange' | 'red' | 'purple' | 'yellow' | 'grey'> = {
  pending: 'yellow',
  processing: 'blue',
  shipped: 'purple',
  delivered: 'green',
  cancelled: 'red',
  returned: 'orange',
  active: 'green',
  ordered: 'blue',
  dismissed: 'grey',
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Label
      className={`status-badge status-${status}`}
      color={statusColors[status] || 'grey'}
      id={`status-${status}`}
    >
      {status}
    </Label>
  );
}
