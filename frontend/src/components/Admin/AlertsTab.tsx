import { useState, useCallback } from 'react';
import { Button, FormSelect, FormSelectOption } from '@patternfly/react-core';
import { alerts as alertsApi } from '../../api/client';
import type { Alert } from '../../types';
import { StatusBadge } from '../shared/StatusBadge';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function AlertsTab({ log, searchQuery }: Props) {
  const [alertList, setAlertList] = useState<Alert[]>([]);
  const [filter, setFilter] = useState('active');

  const loadAlerts = useCallback(async () => {
    try {
      const data = await alertsApi.list(filter || undefined);
      setAlertList(data || []);
    } catch (error) {
      log(`Failed to load alerts: ${(error as Error).message}`, 'error');
    }
  }, [log, filter]);

  usePolling(loadAlerts, 30000);

  const updateStatus = async (id: string, status: string) => {
    try {
      await alertsApi.updateStatus(id, status);
      log(`Alert status updated to ${status}`, 'success');
      loadAlerts();
    } catch (error) {
      log(`Failed to update alert: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? alertList.filter(a => a.product_name.toLowerCase().includes(searchQuery.toLowerCase()))
    : alertList;

  return (
    <div id="alerts">
      <div className="ds-panel">
        <h2>Restock Alerts</h2>
        <div style={{ marginBottom: '1rem' }}>
          <FormSelect id="alerts-filter" value={filter}
            onChange={(_e, v) => setFilter(v)} style={{ maxWidth: '200px' }}>
            <FormSelectOption value="" label="All Alerts" />
            <FormSelectOption value="active" label="Active" />
            <FormSelectOption value="ordered" label="Ordered" />
            <FormSelectOption value="dismissed" label="Dismissed" />
          </FormSelect>
        </div>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Product</th><th>Stock</th><th>Threshold</th><th>Supplier</th><th>Status</th><th>Created</th><th>Actions</th></tr>
            </thead>
            <tbody id="alerts-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={7} className="ds-empty-state">No alerts.</td></tr>
              ) : filtered.map(a => (
                <tr key={a.id}>
                  <td>{a.product_name}</td>
                  <td>{a.current_stock}</td>
                  <td>{a.reorder_threshold}</td>
                  <td>{a.supplier_name || '-'}</td>
                  <td><StatusBadge status={a.status} /></td>
                  <td>{new Date(a.created_at).toLocaleDateString()}</td>
                  <td className="actions">
                    {a.status === 'active' && (
                      <>
                        <Button variant="secondary" size="sm" onClick={() => updateStatus(a.id, 'ordered')}>Mark Ordered</Button>{' '}
                        <Button variant="secondary" size="sm" onClick={() => updateStatus(a.id, 'dismissed')}>Dismiss</Button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
