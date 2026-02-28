import { useState, useCallback } from 'react';
import { Button } from '@patternfly/react-core';
import { invoices as invoicesApi } from '../../api/client';
import type { Invoice } from '../../types';
import { InvoiceModal } from '../shared/InvoiceModal';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function InvoicesTab({ log, searchQuery }: Props) {
  const [invoiceList, setInvoiceList] = useState<Invoice[]>([]);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  const loadInvoices = useCallback(async () => {
    try {
      const data = await invoicesApi.list();
      setInvoiceList(data || []);
    } catch (error) {
      log(`Failed to load invoices: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  usePolling(loadInvoices, 30000);

  const filtered = searchQuery
    ? invoiceList.filter(i =>
        String(i.invoice_number).toLowerCase().includes(searchQuery.toLowerCase()) ||
        (i.customer_snapshot?.name || '').toLowerCase().includes(searchQuery.toLowerCase()))
    : invoiceList;

  return (
    <div id="invoices">
      <div className="ds-panel">
        <h2>Invoice History</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Date</th><th>Invoice #</th><th>Customer</th><th>Order ID</th><th>Grand Total</th><th>Actions</th></tr>
            </thead>
            <tbody id="invoices-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={6} className="ds-empty-state">No invoices yet.</td></tr>
              ) : filtered.map(inv => (
                <tr key={inv.id}>
                  <td>{new Date(inv.created_at).toLocaleDateString()}</td>
                  <td>{inv.invoice_number}</td>
                  <td>{inv.customer_snapshot?.name || '-'}</td>
                  <td>{inv.order_id.substring(0, 8)}...</td>
                  <td className="price">${(Number(inv.grand_total) || 0).toFixed(2)}</td>
                  <td>
                    <Button variant="secondary" size="sm" onClick={() => setSelectedInvoice(inv)}>View</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <InvoiceModal invoice={selectedInvoice} isOpen={!!selectedInvoice} onClose={() => setSelectedInvoice(null)} />
    </div>
  );
}
