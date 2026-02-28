import { useState, useCallback } from 'react';
import {
  Button, Form, FormGroup, TextInput,
} from '@patternfly/react-core';
import { customers as customersApi, orders as ordersApi } from '../../api/client';
import type { Customer, Order } from '../../types';
import { StatusBadge } from '../shared/StatusBadge';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function CustomersTab({ log, searchQuery }: Props) {
  const [customerList, setCustomerList] = useState<Customer[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [customerOrders, setCustomerOrders] = useState<Order[]>([]);

  // Add form
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [phone, setPhone] = useState('');
  const [street, setStreet] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [zip, setZip] = useState('');
  const [country, setCountry] = useState('');

  const loadCustomers = useCallback(async () => {
    try {
      const data = await customersApi.list();
      setCustomerList(data || []);
    } catch (error) {
      log(`Failed to load customers: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  usePolling(loadCustomers, 30000);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !email.trim()) return;
    try {
      const cust = await customersApi.create({
        name: name.trim(), email: email.trim(),
        company: company.trim() || null, phone: phone.trim() || null,
        address: (street || city || state || zip || country) ? { street, city, state, zip, country } : null,
      });
      log(`Created customer: ${cust.name}`, 'success');
      setName(''); setEmail(''); setCompany(''); setPhone('');
      setStreet(''); setCity(''); setState(''); setZip(''); setCountry('');
      loadCustomers();
    } catch (error) {
      log(`Failed to create customer: ${(error as Error).message}`, 'error');
    }
  };

  const selectCustomer = async (c: Customer) => {
    setSelectedCustomer(c);
    try {
      const ords = await customersApi.listOrders(c.id);
      setCustomerOrders(ords || []);
    } catch { setCustomerOrders([]); }
  };

  const deleteCustomer = async (c: Customer) => {
    try {
      await customersApi.delete(c.id);
      log(`Deleted customer: ${c.name}`, 'success');
      if (selectedCustomer?.id === c.id) { setSelectedCustomer(null); setCustomerOrders([]); }
      loadCustomers();
    } catch (error) {
      log(`Failed to delete customer: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? customerList.filter(c =>
        c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.email.toLowerCase().includes(searchQuery.toLowerCase()))
    : customerList;

  return (
    <div id="customers">
      <div className="ds-panel">
        <h2>Add Customer</h2>
        <Form onSubmit={handleAdd} id="add-customer-form">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <FormGroup label="Name" fieldId="cust-name" isRequired style={{ flex: '1 1 150px' }}>
              <TextInput id="cust-name" value={name} onChange={(_e, v) => setName(v)} isRequired placeholder="Customer name" />
            </FormGroup>
            <FormGroup label="Email" fieldId="cust-email" isRequired style={{ flex: '1 1 150px' }}>
              <TextInput id="cust-email" value={email} onChange={(_e, v) => setEmail(v)} isRequired placeholder="customer@example.com" type="email" />
            </FormGroup>
            <FormGroup label="Company" fieldId="cust-company" style={{ flex: '1 1 150px' }}>
              <TextInput id="cust-company" value={company} onChange={(_e, v) => setCompany(v)} placeholder="Company name" />
            </FormGroup>
            <FormGroup label="Phone" fieldId="cust-phone" style={{ flex: '1 1 120px' }}>
              <TextInput id="cust-phone" value={phone} onChange={(_e, v) => setPhone(v)} placeholder="Phone number" />
            </FormGroup>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
            <FormGroup label="Street" fieldId="cust-street" style={{ flex: '2 1 200px' }}>
              <TextInput id="cust-street" value={street} onChange={(_e, v) => setStreet(v)} placeholder="Street address" />
            </FormGroup>
            <FormGroup label="City" fieldId="cust-city" style={{ flex: '1 1 100px' }}>
              <TextInput id="cust-city" value={city} onChange={(_e, v) => setCity(v)} placeholder="City" />
            </FormGroup>
            <FormGroup label="State" fieldId="cust-state" style={{ flex: '1 1 80px' }}>
              <TextInput id="cust-state" value={state} onChange={(_e, v) => setState(v)} placeholder="State" />
            </FormGroup>
            <FormGroup label="Zip" fieldId="cust-zip" style={{ flex: '0 1 80px' }}>
              <TextInput id="cust-zip" value={zip} onChange={(_e, v) => setZip(v)} placeholder="Zip" />
            </FormGroup>
            <FormGroup label="Country" fieldId="cust-country" style={{ flex: '1 1 100px' }}>
              <TextInput id="cust-country" value={country} onChange={(_e, v) => setCountry(v)} placeholder="Country" />
            </FormGroup>
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <Button type="submit" variant="primary">Add Customer</Button>
            </div>
          </div>
        </Form>
      </div>

      <div className="ds-panel" style={{ marginTop: '1rem' }}>
        <h2>Customer List</h2>
        <div id="customer-list">
          {filtered.length === 0 ? (
            <div className="ds-empty-state">No customers yet.</div>
          ) : (
            filtered.map(c => (
              <div key={c.id} className="ds-customer-card customer-list-item" style={{
                padding: '0.75rem', marginBottom: '0.5rem',
                background: selectedCustomer?.id === c.id ? 'var(--pf-t--global--background--color--secondary--default)' : 'transparent',
                borderRadius: '8px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }} onClick={() => selectCustomer(c)}>
                <div>
                  <strong>{c.name}</strong> &mdash; {c.email}
                  {c.company && <span> ({c.company})</span>}
                </div>
                <Button variant="danger" size="sm" onClick={(e) => { e.stopPropagation(); deleteCustomer(c); }}>Delete</Button>
              </div>
            ))
          )}
        </div>
      </div>

      {selectedCustomer && (
        <>
          <div className="ds-panel" style={{ marginTop: '1rem' }} id="customer-detail-panel">
            <h2 id="customer-detail-title">Customer Details</h2>
            <div id="customer-detail-content">
              <p><strong>Name:</strong> {selectedCustomer.name}</p>
              <p><strong>Email:</strong> {selectedCustomer.email}</p>
              {selectedCustomer.company && <p><strong>Company:</strong> {selectedCustomer.company}</p>}
              {selectedCustomer.phone && <p><strong>Phone:</strong> {selectedCustomer.phone}</p>}
              {selectedCustomer.address && (
                <p><strong>Address:</strong> {[
                  selectedCustomer.address.street, selectedCustomer.address.city,
                  selectedCustomer.address.state, selectedCustomer.address.zip,
                  selectedCustomer.address.country
                ].filter(Boolean).join(', ')}</p>
              )}
            </div>
          </div>

          <div className="ds-panel" style={{ marginTop: '1rem' }} id="customer-orders-panel">
            <h2 id="customer-orders-title">Customer Orders</h2>
            <div className="ds-table-container">
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr><th>Date</th><th>Order ID</th><th>Total</th><th>Status</th></tr>
                </thead>
                <tbody id="customer-orders-table">
                  {customerOrders.length === 0 ? (
                    <tr><td colSpan={4} className="ds-empty-state">No orders for this customer.</td></tr>
                  ) : customerOrders.map(o => (
                    <tr key={o.id}>
                      <td>{new Date(o.created_at).toLocaleDateString()}</td>
                      <td>{o.id.substring(0, 8)}...</td>
                      <td className="price">${o.total.toFixed(2)}</td>
                      <td><StatusBadge status={o.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
