import { useState, useCallback } from 'react';
import { Button, Pagination } from '@patternfly/react-core';
import { orders as ordersApi, invoices as invoicesApi } from '../../api/client';
import type { Order, Invoice } from '../../types';
import { StatusBadge } from '../shared/StatusBadge';
import { InvoiceModal } from '../shared/InvoiceModal';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
  onReviewProduct?: (productId: string) => void;
}

export function OrdersTab({ log, searchQuery, onReviewProduct }: Props) {
  const [orderList, setOrderList] = useState<Order[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [invoiceModal, setInvoiceModal] = useState<Invoice | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const LIMIT = 20;

  const loadOrders = useCallback(async () => {
    try {
      const data = await ordersApi.list(page, LIMIT);
      setOrderList(data.items || []);
      setTotal(data.total);
    } catch (error) {
      log(`Failed to load orders: ${(error as Error).message}`, 'error');
    }
  }, [log, page]);

  usePolling(loadOrders, 30000);

  const viewInvoice = async (orderId: string) => {
    try {
      const invList = await invoicesApi.list(orderId);
      if (invList && invList.length > 0) {
        setInvoiceModal(invList[0]);
      } else {
        log('No invoice found for this order', 'info');
      }
    } catch (error) {
      log(`Failed to load invoice: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? orderList.filter(o =>
        o.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        o.status.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : orderList;

  return (
    <div id="orders">
      <div className="ds-panel">
        <h2>My Orders</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th></th>
                <th>Date</th>
                <th>Order ID</th>
                <th>Total</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody id="orders-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={5} className="ds-empty-state">No orders yet.</td></tr>
              ) : (
                filtered.map(order => (
                  <>
                    <tr key={order.id} className="order-row" style={{ cursor: 'pointer' }}
                        onClick={() => setExpandedId(expandedId === order.id ? null : order.id)}>
                      <td>{expandedId === order.id ? '\u25BC' : '\u25B6'}</td>
                      <td>{new Date(order.created_at).toLocaleDateString()}</td>
                      <td>{order.id.substring(0, 8)}...</td>
                      <td className="price">${(Number(order.total) || 0).toFixed(2)}</td>
                      <td><StatusBadge status={order.status} /></td>
                    </tr>
                    {expandedId === order.id && (
                      <tr key={`${order.id}-detail`}>
                        <td colSpan={5}>
                          <div style={{ padding: '1rem', background: 'var(--pf-t--global--background--color--secondary--default)', borderRadius: '4px' }}>
                            <h4>Items:</h4>
                            <ul>
                              {order.items.map((item, i) => (
                                <li key={i}>
                                  {item.product_name} x{item.quantity} @ ${(Number(item.unit_price) || 0).toFixed(2)} = ${((Number(item.unit_price) || 0) * (item.quantity || 0)).toFixed(2)}
                                </li>
                              ))}
                            </ul>
                            {order.coupon_code && (
                              <div style={{ marginTop: '0.5rem' }}>
                                Coupon: {order.coupon_code} (Discount: -${(order.discount_amount || 0).toFixed(2)})
                              </div>
                            )}
                            {order.status === 'delivered' && (
                              <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
                                <Button variant="secondary" size="sm"
                                  onClick={(e) => { e.stopPropagation(); viewInvoice(order.id); }}>
                                  View Invoice
                                </Button>
                                {onReviewProduct && (
                                  <Button variant="secondary" size="sm" className="review-products-btn"
                                    onClick={(e) => { e.stopPropagation(); onReviewProduct(order.items[0]?.product_id); }}>
                                    Review Products
                                  </Button>
                                )}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))
              )}
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

      <InvoiceModal invoice={invoiceModal} isOpen={!!invoiceModal} onClose={() => setInvoiceModal(null)} />
    </div>
  );
}
