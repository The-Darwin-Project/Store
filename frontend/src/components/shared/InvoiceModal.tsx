import { Modal, ModalVariant, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
import type { Invoice } from '../../types';

interface Props {
  invoice: Invoice | null;
  isOpen: boolean;
  onClose: () => void;
}

export function InvoiceModal({ invoice, isOpen, onClose }: Props) {
  if (!invoice) return null;

  const handlePrint = () => {
    window.print();
  };

  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen={isOpen}
      onClose={onClose}
      aria-label="Invoice"
    >
      <ModalHeader title={`Invoice #${invoice.invoice_number}`} />
      <ModalBody>
        <div id="invoice-content">
          <div style={{ marginBottom: '1rem' }}>
            <strong>Date:</strong> {new Date(invoice.created_at).toLocaleDateString()}
          </div>
          {invoice.customer_snapshot?.name && (
            <div style={{ marginBottom: '1rem' }}>
              <strong>Customer:</strong> {invoice.customer_snapshot.name}
              {invoice.customer_snapshot.email && ` (${invoice.customer_snapshot.email})`}
            </div>
          )}
          <div style={{ marginBottom: '0.5rem' }}>
            <strong>Order:</strong> {invoice.order_id.substring(0, 8)}...
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '0.5rem', borderBottom: '1px solid var(--pf-t--global--border--color--default)' }}>Product</th>
                <th style={{ textAlign: 'right', padding: '0.5rem', borderBottom: '1px solid var(--pf-t--global--border--color--default)' }}>Qty</th>
                <th style={{ textAlign: 'right', padding: '0.5rem', borderBottom: '1px solid var(--pf-t--global--border--color--default)' }}>Price</th>
                <th style={{ textAlign: 'right', padding: '0.5rem', borderBottom: '1px solid var(--pf-t--global--border--color--default)' }}>Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {(invoice.line_items || []).map((item, i) => (
                <tr key={i}>
                  <td style={{ padding: '0.5rem' }}>{item.product_name}</td>
                  <td style={{ textAlign: 'right', padding: '0.5rem' }}>{item.quantity}</td>
                  <td style={{ textAlign: 'right', padding: '0.5rem' }}>${(Number(item.unit_price) || 0).toFixed(2)}</td>
                  <td style={{ textAlign: 'right', padding: '0.5rem' }}>${(Number(item.line_total) || 0).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: '1rem', textAlign: 'right' }}>
            <div>Subtotal: ${(Number(invoice.subtotal) || 0).toFixed(2)}</div>
            {invoice.discount_amount > 0 && (
              <div style={{ color: 'var(--pf-t--global--color--status--success--default)' }}>
                Discount{invoice.coupon_code ? ` (${invoice.coupon_code})` : ''}: -${(Number(invoice.discount_amount) || 0).toFixed(2)}
              </div>
            )}
            <div style={{ fontWeight: 700, fontSize: '1.25rem', marginTop: '0.5rem' }}>
              Total: ${(Number(invoice.grand_total) || 0).toFixed(2)}
            </div>
          </div>
        </div>
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" onClick={handlePrint}>Print</Button>
      </ModalFooter>
    </Modal>
  );
}
