import { useState, useCallback } from 'react';
import { Button, Form, FormGroup, TextInput } from '@patternfly/react-core';
import { suppliers as suppliersApi } from '../../api/client';
import type { Supplier, Product } from '../../types';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function SuppliersTab({ log, searchQuery }: Props) {
  const [supplierList, setSupplierList] = useState<Supplier[]>([]);
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  const [supplierProducts, setSupplierProducts] = useState<Product[]>([]);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');

  const loadSuppliers = useCallback(async () => {
    try {
      const data = await suppliersApi.list();
      setSupplierList(data || []);
    } catch (error) {
      log(`Failed to load suppliers: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  usePolling(loadSuppliers, 30000);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const supp = await suppliersApi.create({
        name: name.trim(),
        contact_email: email.trim() || null,
        phone: phone.trim() || null,
      });
      log(`Supplier created: ${supp.name}`, 'success');
      setName(''); setEmail(''); setPhone('');
      loadSuppliers();
    } catch (error) {
      log(`Failed to create supplier: ${(error as Error).message}`, 'error');
    }
  };

  const selectSupplier = async (s: Supplier) => {
    setSelectedSupplier(s);
    try {
      const prods = await suppliersApi.listProducts(s.id);
      setSupplierProducts(prods || []);
    } catch { setSupplierProducts([]); }
  };

  const deleteSupplier = async (s: Supplier) => {
    try {
      await suppliersApi.delete(s.id);
      log(`Deleted supplier: ${s.name}`, 'success');
      if (selectedSupplier?.id === s.id) { setSelectedSupplier(null); setSupplierProducts([]); }
      loadSuppliers();
    } catch (error) {
      log(`Failed to delete supplier: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? supplierList.filter(s => s.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : supplierList;

  return (
    <div id="suppliers">
      <div className="ds-panel">
        <h2>Add Supplier</h2>
        <Form onSubmit={handleAdd} id="add-supplier-form">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <FormGroup label="Name" fieldId="supp-name" isRequired style={{ flex: '1 1 150px' }}>
              <TextInput id="supp-name" value={name} onChange={(_e, v) => setName(v)} isRequired placeholder="Supplier name" />
            </FormGroup>
            <FormGroup label="Contact Email" fieldId="supp-email" style={{ flex: '1 1 150px' }}>
              <TextInput id="supp-email" value={email} onChange={(_e, v) => setEmail(v)} placeholder="contact@supplier.com" type="email" />
            </FormGroup>
            <FormGroup label="Phone" fieldId="supp-phone" style={{ flex: '1 1 120px' }}>
              <TextInput id="supp-phone" value={phone} onChange={(_e, v) => setPhone(v)} placeholder="Phone number" />
            </FormGroup>
            <Button type="submit" variant="primary">Add Supplier</Button>
          </div>
        </Form>
      </div>

      <div className="ds-panel" style={{ marginTop: '1rem' }}>
        <h2>Supplier List</h2>
        <div id="supplier-list">
          {filtered.length === 0 ? (
            <div className="ds-empty-state">No suppliers yet.</div>
          ) : filtered.map(s => (
            <div key={s.id} className="ds-supplier-card" style={{
              padding: '0.75rem', marginBottom: '0.5rem',
              background: selectedSupplier?.id === s.id ? 'var(--pf-t--global--background--color--secondary--default)' : 'transparent',
              borderRadius: '8px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }} onClick={() => selectSupplier(s)}>
              <div>
                <strong>{s.name}</strong>
                {s.contact_email && <span> &mdash; {s.contact_email}</span>}
                {s.phone && <span> | {s.phone}</span>}
              </div>
              <Button variant="danger" size="sm" onClick={(e) => { e.stopPropagation(); deleteSupplier(s); }}>Delete</Button>
            </div>
          ))}
        </div>
      </div>

      {selectedSupplier && (
        <div className="ds-panel" style={{ marginTop: '1rem' }} id="supplier-products-panel">
          <h2 id="supplier-products-title">Supplier Products</h2>
          <div className="ds-table-container">
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr><th>Product</th><th>SKU</th><th>Price</th><th>Stock</th></tr>
              </thead>
              <tbody id="supplier-products-table">
                {supplierProducts.length === 0 ? (
                  <tr><td colSpan={4} className="ds-empty-state">No products from this supplier.</td></tr>
                ) : supplierProducts.map(p => (
                  <tr key={p.id}>
                    <td>{p.name}</td><td>{p.sku}</td>
                    <td className="price">${(Number(p.price) || 0).toFixed(2)}</td><td>{p.stock}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
