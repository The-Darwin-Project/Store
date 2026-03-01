import { useState, useCallback } from 'react';
import {
  Button, FormSelect, FormSelectOption,
  Modal, ModalVariant, ModalHeader, ModalBody, ModalFooter,
  Pagination,
} from '@patternfly/react-core';
import { orders as ordersApi, invoices as invoicesApi, customers as customersApi } from '../../api/client';
import type { Order, Invoice, Customer } from '../../types';
import { StatusBadge } from '../shared/StatusBadge';
import { InvoiceModal } from '../shared/InvoiceModal';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

const STATUS_TRANSITIONS: Record<string, string[]> = {
  pending: ['processing', 'cancelled'],
  processing: ['shipped', 'cancelled'],
  shipped: ['delivered', 'cancelled'],
  delivered: ['returned'],
  cancelled: [],
  returned: [],
};

export function AdminOrdersTab({ log, searchQuery }: Props) {
  const [orderList, setOrderList] = useState<Order[]>([]);
  const [unassignedOrders, setUnassignedOrders] = useState<Order[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [invoiceModal, setInvoiceModal] = useState<Invoice | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Order | null>(null);
  const [attachTarget, setAttachTarget] = useState<Order | null>(null);
  const [customersList, setCustomersList] = useState<Customer[]>([]);
  const [attachCustomerId, setAttachCustomerId] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const LIMIT = 20;

  const loadData = useCallback(async () => {
    try {
      const [ords, unassigned] = await Promise.all([
        ordersApi.list(page, LIMIT),
        ordersApi.listUnassigned(),
      ]);
      setOrderList(ords.items || []);
      setTotal(ords.total);
      setUnassignedOrders(unassigned || []);
    } catch (error) {
      log(`Failed to load orders: ${(error as Error).message}`, 'error');
    }
  }, [log, page]);

  usePolling(loadData, 30000);

  const updateStatus = async (orderId: string, newStatus: string) => {
    try {
      const order = await ordersApi.updateStatus(orderId, newStatus as Order['status']);
      log(`Order ${orderId.substring(0, 8)}... status changed to "${order.status}"`, 'success');
      loadData();
    } catch (error) {
      log(`Failed to update order status: ${(error as Error).message}`, 'error');
    }
  };

  const generateInvoice = async (orderId: string) => {
    try {
      const inv = await ordersApi.generateInvoice(orderId);
      log(`Invoice generated: ${inv.invoice_number}`, 'success');
      setInvoiceModal(inv);
    } catch (error) {
      log(`Failed to generate invoice: ${(error as Error).message}`, 'error');
    }
  };

  const viewInvoice = async (orderId: string) => {
    try {
      const invList = await invoicesApi.list(orderId);
      if (invList && invList.length > 0) setInvoiceModal(invList[0]);
    } catch (error) {
      log(`Failed to load invoice: ${(error as Error).message}`, 'error');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await ordersApi.delete(deleteTarget.id);
      log(`Deleted order: ${deleteTarget.id.substring(0, 8)}...`, 'success');
      setDeleteTarget(null);
      loadData();
    } catch (error) {
      log(`Failed to delete order: ${(error as Error).message}`, 'error');
    }
  };

  const openAttach = async (order: Order) => {
    setAttachTarget(order);
    setAttachCustomerId('');
    try {
      const custs = await customersApi.list();
      setCustomersList(custs || []);
    } catch { /* ignore */ }
  };

  const confirmAttach = async () => {
    if (!attachTarget || !attachCustomerId) return;
    try {
      await ordersApi.attachToCustomer(attachTarget.id, attachCustomerId);
      log(`Order attached to customer`, 'success');
      setAttachTarget(null);
      loadData();
    } catch (error) {
      log(`Failed to attach order: ${(error as Error).message}`, 'error');
    }
  };

  const renderOrderRow = (order: Order, showActions = true) => {
    const nextStatuses = STATUS_TRANSITIONS[order.status] || [];
    return (
      <>
        <tr key={order.id} style={{ cursor: 'pointer' }}
            onClick={() => setExpandedId(expandedId === order.id ? null : order.id)}>
          <td>{expandedId === order.id ? '\u25BC' : '\u25B6'}</td>
          <td>{new Date(order.created_at).toLocaleDateString()}</td>
          <td>{order.id.substring(0, 8)}...</td>
          <td className="price">${(Number(order.total) || 0).toFixed(2)}</td>
          <td><StatusBadge status={order.status} /></td>
          {showActions && (
            <td className="actions" onClick={e => e.stopPropagation()}>
              {nextStatuses.map(s => (
                <Button key={s} variant="secondary" size="sm" onClick={() => updateStatus(order.id, s)}
                  style={{ marginRight: '0.25rem', textTransform: 'capitalize' }}>{s}</Button>
              ))}
              {order.status === 'delivered' && (
                <Button variant="secondary" size="sm" onClick={() => generateInvoice(order.id)}>Invoice</Button>
              )}
              <Button variant="danger" size="sm" onClick={() => setDeleteTarget(order)}>Delete</Button>
            </td>
          )}
        </tr>
        {expandedId === order.id && (
          <tr key={`${order.id}-exp`}>
            <td colSpan={showActions ? 6 : 5}>
              <div style={{ padding: '1rem', background: 'var(--pf-t--global--background--color--secondary--default)', borderRadius: '4px' }}>
                <h4>Items:</h4>
                <ul>
                  {order.items.map((item, i) => (
                    <li key={i}>{item.product_name} x{item.quantity} @ ${(Number(item.unit_price) || 0).toFixed(2)}</li>
                  ))}
                </ul>
                {order.coupon_code && <div>Coupon: {order.coupon_code} (-${(order.discount_amount || 0).toFixed(2)})</div>}
              </div>
            </td>
          </tr>
        )}
      </>
    );
  };

  const filtered = searchQuery
    ? orderList.filter(o => o.id.toLowerCase().includes(searchQuery.toLowerCase()) || o.status.includes(searchQuery.toLowerCase()))
    : orderList;

  return (
    <div id="orders">
      <div className="ds-panel">
        <h2>Order History</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th></th><th>Date</th><th>Order ID</th><th>Total</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody id="orders-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={6} className="ds-empty-state">No orders yet.</td></tr>
              ) : filtered.map(o => renderOrderRow(o))}
            </tbody>
          </table>
        </div>
        {total > 0 && (
          <Pagination
            itemCount={total}
            perPage={LIMIT}
            page={page}
            onSetPage={(_e, p) => setPage(p)}
            isCompact
          />
        )}
      </div>

      <div className="ds-panel" style={{ marginTop: '1.5rem' }}>
        <h2>Unassigned Orders (Legacy)</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th></th><th>Date</th><th>Order ID</th><th>Total</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody id="unassigned-orders-table">
              {unassignedOrders.length === 0 ? (
                <tr><td colSpan={6} className="ds-empty-state">No unassigned orders.</td></tr>
              ) : unassignedOrders.map(o => (
                <>
                  {renderOrderRow(o, false)}
                  <tr key={`${o.id}-attach`}>
                    <td colSpan={6}>
                      <Button variant="secondary" size="sm" onClick={() => openAttach(o)}>Attach to Customer</Button>
                    </td>
                  </tr>
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <InvoiceModal invoice={invoiceModal} isOpen={!!invoiceModal} onClose={() => setInvoiceModal(null)} />

      {/* Delete Order Modal */}
      <Modal variant={ModalVariant.small} isOpen={!!deleteTarget} onClose={() => setDeleteTarget(null)} aria-label="Delete order">
        <ModalHeader title="Confirm Deletion" />
        <ModalBody>
          Are you sure you want to permanently delete order <strong id="delete-order-id">{deleteTarget?.id.substring(0, 8)}...</strong>?
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button variant="danger" onClick={handleDelete} id="confirm-delete-order-btn">Delete</Button>
        </ModalFooter>
      </Modal>

      {/* Attach Order Modal */}
      <Modal variant={ModalVariant.small} isOpen={!!attachTarget} onClose={() => setAttachTarget(null)} aria-label="Attach order">
        <ModalHeader title="Attach Order to Customer" />
        <ModalBody>
          <FormSelect id="attach-customer-select" value={attachCustomerId} onChange={(_e, v) => setAttachCustomerId(v)}>
            <FormSelectOption value="" label="-- Select --" />
            {customersList.map(c => <FormSelectOption key={c.id} value={c.id} label={`${c.name} (${c.email})`} />)}
          </FormSelect>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setAttachTarget(null)}>Cancel</Button>
          <Button variant="primary" onClick={confirmAttach}>Attach</Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
