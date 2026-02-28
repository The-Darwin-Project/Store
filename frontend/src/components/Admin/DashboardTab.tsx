import { useState, useCallback } from 'react';
import { Card, CardBody, CardTitle } from '@patternfly/react-core';
import { dashboard as dashboardApi } from '../../api/client';
import type { DashboardData } from '../../types';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export function DashboardTab({ log }: Props) {
  const [data, setData] = useState<DashboardData | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      const d = await dashboardApi.get();
      setData(d);
    } catch (error) {
      log(`Failed to load dashboard: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  usePolling(loadDashboard, 30000);

  return (
    <div id="dashboard">
      <Card isCompact className="ds-panel">
        <CardTitle>Total Revenue</CardTitle>
        <CardBody>
          <div id="dashboard-revenue" style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--pf-t--global--color--status--success--default)' }}>
            ${data ? (Number(data.total_revenue) || 0).toFixed(2) : '0.00'}
          </div>
        </CardBody>
      </Card>

      <Card isCompact className="ds-panel" style={{ marginTop: '1rem' }}>
        <CardTitle>Orders by Status</CardTitle>
        <CardBody>
          <div id="dashboard-orders-status">
            {data?.orders_by_status && Object.keys(data.orders_by_status).length > 0 ? (
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                {Object.entries(data.orders_by_status).map(([status, count]) => (
                  <div key={status} style={{
                    padding: '0.5rem 1rem',
                    background: 'var(--pf-t--global--background--color--secondary--default)',
                    borderRadius: '8px',
                  }}>
                    <div style={{ textTransform: 'capitalize', fontWeight: 600 }}>{status}</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{count}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="ds-empty-state">No orders yet.</div>
            )}
          </div>
        </CardBody>
      </Card>

      <Card isCompact className="ds-panel" style={{ marginTop: '1rem' }}>
        <CardTitle>Top 5 Products by Sales</CardTitle>
        <CardBody>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Rank</th><th>Product</th><th>Units Sold</th></tr>
            </thead>
            <tbody id="dashboard-top-products">
              {data?.top_products?.length > 0 ? (
                data.top_products.map((p, i) => (
                  <tr key={i}><td>{i + 1}</td><td>{p.name}</td><td>{p.units_sold}</td></tr>
                ))
              ) : (
                <tr><td colSpan={3} className="ds-empty-state">No sales data yet.</td></tr>
              )}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <Card isCompact className="ds-panel" style={{ marginTop: '1rem' }}>
        <CardTitle>Low Stock Alerts</CardTitle>
        <CardBody>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Product</th><th>Stock</th><th>Reorder At</th><th>Supplier</th><th>Contact</th></tr>
            </thead>
            <tbody id="dashboard-low-stock">
              {data?.low_stock?.length > 0 ? (
                data.low_stock.map((item, i) => (
                  <tr key={i}>
                    <td>{item.product_name}</td>
                    <td>{item.stock}</td>
                    <td>{item.reorder_threshold}</td>
                    <td>{item.supplier_name || '-'}</td>
                    <td>{item.supplier_email || '-'}</td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={5} className="ds-empty-state">No low-stock items.</td></tr>
              )}
            </tbody>
          </table>
        </CardBody>
      </Card>
    </div>
  );
}
