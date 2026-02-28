import { useState, useEffect } from 'react';
import {
  Button, TextInput, Form, FormGroup, FormSelect, FormSelectOption,
  Modal, ModalVariant, ModalHeader, ModalBody, ModalFooter,
} from '@patternfly/react-core';
import { customers as customersApi, orders as ordersApi, coupons as couponsApi } from '../../api/client';
import type { CartItem, Customer, CouponValidationResult, Order } from '../../types';

interface Props {
  items: CartItem[];
  total: number;
  onUpdateQuantity: (productId: string, qty: number) => void;
  onRemoveItem: (productId: string) => void;
  onClear: () => void;
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export function CartTab({ items, total, onUpdateQuantity, onRemoveItem, onClear, log }: Props) {
  const [customersList, setCustomersList] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [newCustName, setNewCustName] = useState('');
  const [newCustEmail, setNewCustEmail] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const [couponResult, setCouponResult] = useState<CouponValidationResult | null>(null);
  const [orderSuccess, setOrderSuccess] = useState<Order | null>(null);

  useEffect(() => {
    loadCustomers();
  }, []);

  const loadCustomers = async () => {
    try {
      const data = await customersApi.list();
      setCustomersList(data || []);
    } catch { /* ignore */ }
  };

  const applyCoupon = async () => {
    if (!couponCode.trim()) return;
    try {
      const result = await couponsApi.validate(couponCode.trim().toUpperCase(), total);
      setCouponResult(result);
      if (result.valid) {
        log(`Coupon applied: ${couponCode.toUpperCase()} (-$${result.discount_amount?.toFixed(2)})`, 'success');
      } else {
        log(`Coupon invalid: ${result.message}`, 'error');
      }
    } catch (error) {
      log(`Failed to validate coupon: ${(error as Error).message}`, 'error');
    }
  };

  const removeCoupon = () => {
    setCouponCode('');
    setCouponResult(null);
    log('Coupon removed', 'info');
  };

  const createInlineCustomer = async () => {
    if (!newCustName.trim() || !newCustEmail.trim()) return;
    try {
      const cust = await customersApi.create({ name: newCustName.trim(), email: newCustEmail.trim() });
      log(`Customer created: ${cust.name}`, 'success');
      setSelectedCustomerId(cust.id);
      setShowNewCustomer(false);
      setNewCustName('');
      setNewCustEmail('');
      loadCustomers();
    } catch (error) {
      log(`Failed to create customer: ${(error as Error).message}`, 'error');
    }
  };

  const checkout = async () => {
    if (items.length === 0) return;
    try {
      const order = await ordersApi.create({
        customer_id: selectedCustomerId || null,
        items: items.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
        coupon_code: couponResult?.valid ? couponCode.toUpperCase() : null,
      });
      log(`Order placed: ${order.id.substring(0, 8)}... Total: $${order.total.toFixed(2)}`, 'success');
      setOrderSuccess(order);
      onClear();
      setCouponCode('');
      setCouponResult(null);
    } catch (error) {
      log(`Checkout failed: ${(error as Error).message}`, 'error');
    }
  };

  const discountAmount = couponResult?.valid ? (couponResult.discount_amount || 0) : 0;
  const finalTotal = total - discountAmount;

  return (
    <div id="cart">
      <div className="ds-panel">
        <h2>Shopping Cart</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th>Product</th>
                <th>Price</th>
                <th>Quantity</th>
                <th>Subtotal</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="cart-table">
              {items.length === 0 ? (
                <tr><td colSpan={5} className="ds-empty-state">Your cart is empty.</td></tr>
              ) : (
                items.map(item => (
                  <tr key={item.product_id}>
                    <td>{item.product_name}</td>
                    <td className="price">${item.price.toFixed(2)}</td>
                    <td>
                      <input
                        type="number"
                        min={1}
                        value={item.quantity}
                        onChange={e => onUpdateQuantity(item.product_id, parseInt(e.target.value) || 1)}
                        style={{ width: '60px' }}
                      />
                    </td>
                    <td className="price">${(item.price * item.quantity).toFixed(2)}</td>
                    <td>
                      <Button variant="danger" size="sm" onClick={() => onRemoveItem(item.product_id)}>Remove</Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {items.length > 0 && (
          <>
            <div id="coupon-section" style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
                <FormGroup label="Discount Code" fieldId="coupon-input" style={{ flex: 1 }}>
                  <TextInput
                    id="coupon-input"
                    value={couponCode}
                    onChange={(_e, val) => setCouponCode(val)}
                    placeholder="Enter coupon code"
                    style={{ textTransform: 'uppercase' }}
                  />
                </FormGroup>
                <Button variant="secondary" onClick={applyCoupon}>Apply</Button>
                {couponResult?.valid && (
                  <Button variant="secondary" onClick={removeCoupon} id="remove-coupon-btn">Clear</Button>
                )}
              </div>
              {couponResult && (
                <div id="coupon-result" style={{ marginTop: '0.5rem', color: couponResult.valid
                  ? 'var(--pf-t--global--color--status--success--default)'
                  : 'var(--pf-t--global--color--status--danger--default)' }}>
                  {couponResult.valid
                    ? `Discount: -$${couponResult.discount_amount?.toFixed(2)}`
                    : couponResult.message}
                </div>
              )}
            </div>

            <div id="cart-total" style={{ textAlign: 'right', marginTop: '1rem', fontSize: '1.25rem', fontWeight: 700 }}>
              {discountAmount > 0 && (
                <div style={{ fontSize: '0.9rem', fontWeight: 400 }}>
                  Subtotal: ${total.toFixed(2)} | Discount: -${discountAmount.toFixed(2)}
                </div>
              )}
              Total: ${finalTotal.toFixed(2)}
            </div>

            <div id="checkout-section" style={{ marginTop: '1.5rem' }}>
              <div className="ds-panel" style={{ marginBottom: '1rem' }}>
                <h3>Select Customer</h3>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
                  <FormGroup label="Customer" fieldId="checkout-customer" style={{ flex: 1 }}>
                    <FormSelect
                      id="checkout-customer"
                      value={selectedCustomerId}
                      onChange={(_e, val) => setSelectedCustomerId(val)}
                    >
                      <FormSelectOption value="" label="-- Select a customer --" />
                      {customersList.map(c => (
                        <FormSelectOption key={c.id} value={c.id} label={`${c.name} (${c.email})`} />
                      ))}
                    </FormSelect>
                  </FormGroup>
                  <Button variant="secondary" onClick={() => setShowNewCustomer(!showNewCustomer)}>
                    New Customer
                  </Button>
                </div>
                {showNewCustomer && (
                  <div id="inline-new-customer" style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
                    <FormGroup label="Name" fieldId="new-cust-name" style={{ flex: 1 }}>
                      <TextInput id="new-cust-name" value={newCustName}
                        onChange={(_e, val) => setNewCustName(val)} placeholder="Customer name" />
                    </FormGroup>
                    <FormGroup label="Email" fieldId="new-cust-email" style={{ flex: 1 }}>
                      <TextInput id="new-cust-email" value={newCustEmail}
                        onChange={(_e, val) => setNewCustEmail(val)} placeholder="customer@example.com" type="email" />
                    </FormGroup>
                    <Button variant="primary" onClick={createInlineCustomer}>Create</Button>
                  </div>
                )}
              </div>
              <div style={{ textAlign: 'right' }}>
                <Button variant="primary" onClick={checkout} id="checkout-btn" size="lg">Checkout</Button>
              </div>
            </div>
          </>
        )}
      </div>

      <Modal
        variant={ModalVariant.small}
        isOpen={!!orderSuccess}
        onClose={() => setOrderSuccess(null)}
        aria-label="Order success"
        id="order-success-modal"
      >
        <ModalHeader title="Order Confirmed" />
        <ModalBody>
          <p style={{ color: 'var(--pf-t--global--color--status--success--default)', marginBottom: '1rem' }}>
            Your order has been placed successfully!
          </p>
          {orderSuccess && (
            <div id="order-details" style={{ fontSize: '0.9rem' }}>
              <div>Order ID: {orderSuccess.id.substring(0, 8)}...</div>
              <div>Total: ${orderSuccess.total.toFixed(2)}</div>
              <div>Items: {orderSuccess.items.length}</div>
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" onClick={() => setOrderSuccess(null)}>Continue Shopping</Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
