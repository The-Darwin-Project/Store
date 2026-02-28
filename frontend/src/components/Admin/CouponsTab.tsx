import { useState, useCallback } from 'react';
import {
  Button, Form, FormGroup, TextInput, FormSelect, FormSelectOption,
} from '@patternfly/react-core';
import { coupons as couponsApi } from '../../api/client';
import type { Coupon } from '../../types';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function CouponsTab({ log, searchQuery }: Props) {
  const [couponList, setCouponList] = useState<Coupon[]>([]);
  const [code, setCode] = useState('');
  const [type, setType] = useState('percentage');
  const [value, setValue] = useState('');
  const [minOrder, setMinOrder] = useState('0');
  const [maxUses, setMaxUses] = useState('0');
  const [expiresAt, setExpiresAt] = useState('');

  const loadCoupons = useCallback(async () => {
    try {
      const data = await couponsApi.list();
      setCouponList(data || []);
    } catch (error) {
      log(`Failed to load coupons: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  usePolling(loadCoupons, 30000);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim() || !value) return;
    try {
      const coupon = await couponsApi.create({
        code: code.trim().toUpperCase(),
        discount_type: type as 'percentage' | 'fixed',
        discount_value: parseFloat(value),
        min_order_amount: parseFloat(minOrder) || 0,
        max_uses: parseInt(maxUses) || 0,
        expires_at: expiresAt || null,
      });
      log(`Coupon created: ${coupon.code}`, 'success');
      setCode(''); setValue(''); setMinOrder('0'); setMaxUses('0'); setExpiresAt('');
      loadCoupons();
    } catch (error) {
      log(`Failed to create coupon: ${(error as Error).message}`, 'error');
    }
  };

  const toggleActive = async (coupon: Coupon) => {
    try {
      await couponsApi.update(coupon.id, { is_active: !coupon.is_active });
      log(`Coupon ${coupon.code} ${coupon.is_active ? 'deactivated' : 'activated'}`, 'success');
      loadCoupons();
    } catch (error) {
      log(`Failed to update coupon: ${(error as Error).message}`, 'error');
    }
  };

  const deleteCoupon = async (coupon: Coupon) => {
    try {
      await couponsApi.delete(coupon.id);
      log(`Deleted coupon: ${coupon.code}`, 'success');
      loadCoupons();
    } catch (error) {
      log(`Failed to delete coupon: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? couponList.filter(c => c.code.toLowerCase().includes(searchQuery.toLowerCase()))
    : couponList;

  return (
    <div id="coupons">
      <div className="ds-panel">
        <h2>Create Coupon</h2>
        <Form onSubmit={handleAdd} id="add-coupon-form">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <FormGroup label="Code" fieldId="coupon-code" isRequired style={{ flex: '1 1 150px' }}>
              <TextInput id="coupon-code" value={code} onChange={(_e, v) => setCode(v)} isRequired
                placeholder="e.g. SUMMER20" style={{ textTransform: 'uppercase' }} />
            </FormGroup>
            <FormGroup label="Type" fieldId="coupon-type" style={{ flex: '0 1 150px' }}>
              <FormSelect id="coupon-type" value={type} onChange={(_e, v) => setType(v)}>
                <FormSelectOption value="percentage" label="Percentage (%)" />
                <FormSelectOption value="fixed" label="Fixed ($)" />
              </FormSelect>
            </FormGroup>
            <FormGroup label="Value" fieldId="coupon-value" isRequired style={{ flex: '0 1 100px' }}>
              <TextInput id="coupon-value" type="number" value={value} onChange={(_e, v) => setValue(v)} isRequired placeholder="10" />
            </FormGroup>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem', alignItems: 'flex-end' }}>
            <FormGroup label="Min Order ($)" fieldId="coupon-min-order" style={{ flex: '0 1 120px' }}>
              <TextInput id="coupon-min-order" type="number" value={minOrder} onChange={(_e, v) => setMinOrder(v)} />
            </FormGroup>
            <FormGroup label="Max Uses" fieldId="coupon-max-uses" style={{ flex: '0 1 100px' }}>
              <TextInput id="coupon-max-uses" type="number" value={maxUses} onChange={(_e, v) => setMaxUses(v)} placeholder="0 = unlimited" />
            </FormGroup>
            <FormGroup label="Expires At" fieldId="coupon-expires" style={{ flex: '0 1 200px' }}>
              <input type="datetime-local" id="coupon-expires" value={expiresAt}
                onChange={e => setExpiresAt(e.target.value)} className="pf-v6-c-form-control" />
            </FormGroup>
            <Button type="submit" variant="primary">Create Coupon</Button>
          </div>
        </Form>
      </div>

      <div className="ds-panel" style={{ marginTop: '1rem' }}>
        <h2>Coupon List</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Code</th><th>Type</th><th>Value</th><th>Min Order</th><th>Uses</th><th>Expires</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody id="coupons-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={8} className="ds-empty-state">No coupons yet.</td></tr>
              ) : filtered.map(c => (
                <tr key={c.id}>
                  <td>{c.code}</td>
                  <td>{c.discount_type === 'percentage' ? '%' : '$'}</td>
                  <td>{c.discount_value}</td>
                  <td>${c.min_order_amount.toFixed(2)}</td>
                  <td>{c.current_uses}/{c.max_uses || '\u221E'}</td>
                  <td>{c.expires_at ? new Date(c.expires_at).toLocaleDateString() : 'Never'}</td>
                  <td>{c.is_active ? '\u2705 Active' : '\u274C Inactive'}</td>
                  <td className="actions">
                    <Button variant="secondary" size="sm" onClick={() => toggleActive(c)}>
                      {c.is_active ? 'Deactivate' : 'Activate'}
                    </Button>{' '}
                    <Button variant="danger" size="sm" onClick={() => deleteCoupon(c)}>Delete</Button>
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
