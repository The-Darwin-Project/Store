import { useState, useEffect, useCallback } from 'react';
import {
  Button, Form, FormGroup, TextInput, TextArea, FormSelect, FormSelectOption,
  Modal, ModalVariant, ModalHeader, ModalBody, ModalFooter,
  Pagination,
} from '@patternfly/react-core';
import { products as productsApi, suppliers as suppliersApi } from '../../api/client';
import type { Product, Supplier, ProductCreate } from '../../types';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function InventoryTab({ log, searchQuery }: Props) {
  const [productList, setProductList] = useState<Product[]>([]);
  const [supplierList, setSupplierList] = useState<Supplier[]>([]);
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Product | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const LIMIT = 20;

  // Add form state
  const [addName, setAddName] = useState('');
  const [addSku, setAddSku] = useState('');
  const [addPrice, setAddPrice] = useState('0');
  const [addStock, setAddStock] = useState('0');
  const [addReorder, setAddReorder] = useState('10');
  const [addSupplier, setAddSupplier] = useState('');
  const [addDescription, setAddDescription] = useState('');
  const [addImage, setAddImage] = useState<string | null>(null);

  // Edit form state
  const [editName, setEditName] = useState('');
  const [editSku, setEditSku] = useState('');
  const [editPrice, setEditPrice] = useState('0');
  const [editStock, setEditStock] = useState('0');
  const [editReorder, setEditReorder] = useState('10');
  const [editSupplier, setEditSupplier] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editImage, setEditImage] = useState<string | null>(null);

  const loadProducts = useCallback(async () => {
    try {
      const data = await productsApi.list(page, LIMIT);
      setProductList(data.items || []);
      setTotal(data.total);
    } catch (error) {
      log(`Failed to load products: ${(error as Error).message}`, 'error');
    }
  }, [log, page]);

  const loadSuppliers = useCallback(async () => {
    try {
      const data = await suppliersApi.list();
      setSupplierList(data || []);
    } catch { /* ignore */ }
  }, []);

  usePolling(() => { loadProducts(); loadSuppliers(); }, 30000);

  const readFileAsDataUrl = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addName.trim() || !addSku.trim()) {
      log('Product name and SKU are required', 'error');
      return;
    }
    try {
      const data: ProductCreate = {
        name: addName.trim(),
        sku: addSku.trim(),
        price: parseFloat(addPrice) || 0,
        stock: parseInt(addStock) || 0,
        reorder_threshold: parseInt(addReorder) || 0,
        supplier_id: addSupplier || null,
        description: addDescription.trim() || null,
        image_data: addImage,
      };
      const product = await productsApi.create(data);
      log(`Created product: ${product.name}`, 'success');
      setAddName(''); setAddSku(''); setAddPrice('0'); setAddStock('0');
      setAddReorder('10'); setAddSupplier(''); setAddDescription(''); setAddImage(null);
      loadProducts();
    } catch (error) {
      log(`Failed to create product: ${(error as Error).message}`, 'error');
    }
  };

  const openEdit = (p: Product) => {
    setEditProduct(p);
    setEditName(p.name);
    setEditSku(p.sku);
    setEditPrice(String(p.price));
    setEditStock(String(p.stock));
    setEditReorder(String(p.reorder_threshold ?? 10));
    setEditSupplier(p.supplier_id || '');
    setEditDescription(p.description || '');
    setEditImage(null);
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editProduct || !editName.trim() || !editSku.trim()) return;
    try {
      const data: ProductCreate = {
        name: editName.trim(),
        sku: editSku.trim(),
        price: parseFloat(editPrice) || 0,
        stock: parseInt(editStock) || 0,
        reorder_threshold: parseInt(editReorder) || 0,
        supplier_id: editSupplier || null,
        description: editDescription.trim() || null,
        image_data: editImage,
      };
      const product = await productsApi.update(editProduct.id, data);
      log(`Updated product: ${product.name}`, 'success');
      setEditProduct(null);
      loadProducts();
    } catch (error) {
      log(`Failed to update product: ${(error as Error).message}`, 'error');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await productsApi.delete(deleteTarget.id);
      log(`Deleted product: ${deleteTarget.name}`, 'success');
      setDeleteTarget(null);
      loadProducts();
    } catch (error) {
      log(`Failed to delete product: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? productList.filter(p =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.sku.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : productList;

  return (
    <div id="inventory">
      <div className="ds-panel">
        <h2>Add Product</h2>
        <Form onSubmit={handleAdd} id="add-form">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <FormGroup label="Name" fieldId="add-name" isRequired style={{ flex: '2 1 150px' }}>
              <TextInput id="add-name" value={addName} onChange={(_e, v) => setAddName(v)} isRequired placeholder="Product name" />
            </FormGroup>
            <FormGroup label="SKU" fieldId="add-sku" isRequired style={{ flex: '1 1 100px' }}>
              <TextInput id="add-sku" value={addSku} onChange={(_e, v) => setAddSku(v)} isRequired placeholder="Product SKU" />
            </FormGroup>
            <FormGroup label="Price ($)" fieldId="add-price" style={{ flex: '0 1 100px' }}>
              <TextInput id="add-price" type="number" value={addPrice} onChange={(_e, v) => setAddPrice(v)} />
            </FormGroup>
            <FormGroup label="Stock" fieldId="add-stock" style={{ flex: '0 1 80px' }}>
              <TextInput id="add-stock" type="number" value={addStock} onChange={(_e, v) => setAddStock(v)} />
            </FormGroup>
            <FormGroup label="Reorder At" fieldId="add-reorder" style={{ flex: '0 1 80px' }}>
              <TextInput id="add-reorder" type="number" value={addReorder} onChange={(_e, v) => setAddReorder(v)} />
            </FormGroup>
            <FormGroup label="Supplier" fieldId="add-supplier" style={{ flex: '1 1 150px' }}>
              <FormSelect id="add-supplier" value={addSupplier} onChange={(_e, v) => setAddSupplier(v)}>
                <FormSelectOption value="" label="-- No supplier --" />
                {supplierList.map(s => <FormSelectOption key={s.id} value={s.id} label={s.name} />)}
              </FormSelect>
            </FormGroup>
            <FormGroup label="Image" fieldId="add-image" style={{ flex: '0 1 150px' }}>
              <input type="file" id="add-image" accept="image/*" onChange={async (e) => {
                const file = e.target.files?.[0];
                if (file) {
                  if (file.size > 1024 * 1024) { log('Image must be under 1MB', 'error'); return; }
                  setAddImage(await readFileAsDataUrl(file));
                }
              }} />
            </FormGroup>
          </div>
          <FormGroup label="Description" fieldId="add-description" style={{ marginTop: '0.5rem' }}>
            <TextArea id="add-description" value={addDescription} onChange={(_e, v) => setAddDescription(v)} rows={2} placeholder="Product description (optional)" />
          </FormGroup>
          <Button type="submit" variant="primary" style={{ marginTop: '0.5rem' }}>Add Product</Button>
        </Form>
      </div>

      <div className="ds-panel" style={{ marginTop: '1rem' }}>
        <h2>Product Inventory</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Image</th><th>Name</th><th>SKU</th><th>Price</th><th>Stock</th><th>Supplier</th><th>Description</th><th>Actions</th></tr>
            </thead>
            <tbody id="product-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={8} className="ds-empty-state">No products yet. Add one above!</td></tr>
              ) : (
                filtered.map(p => {
                  const supplier = supplierList.find(s => s.id === p.supplier_id);
                  const stockClass = p.stock === 0 ? 'stock-out' : p.stock < 10 ? 'stock-low' : '';
                  return (
                    <tr key={p.id} data-id={p.id}>
                      <td>
                        {p.image_data
                          ? <img src={p.image_data} alt={p.name} width="50" height="50" style={{ objectFit: 'cover' }} />
                          : <div style={{ width: 50, height: 50, background: 'var(--ds-bg-card)', display: 'inline-block' }} />}
                      </td>
                      <td>{p.name}</td>
                      <td>{p.sku}</td>
                      <td className="price">${(Number(p.price) || 0).toFixed(2)}</td>
                      <td className={`stock ${stockClass}`}>{p.stock}</td>
                      <td>{supplier ? supplier.name : '-'}</td>
                      <td className="ds-desc-cell" title={p.description || ''}>{p.description || ''}</td>
                      <td className="actions">
                        <Button variant="secondary" size="sm" onClick={() => openEdit(p)}>Edit</Button>{' '}
                        <Button variant="danger" size="sm" onClick={() => setDeleteTarget(p)}>Delete</Button>
                      </td>
                    </tr>
                  );
                })
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

      {/* Edit Modal */}
      <Modal variant={ModalVariant.medium} isOpen={!!editProduct} onClose={() => setEditProduct(null)} aria-label="Edit product">
        <ModalHeader title="Edit Product" />
        <ModalBody>
          <Form onSubmit={handleEdit} id="edit-form">
            <FormGroup label="Name" fieldId="edit-name" isRequired>
              <TextInput id="edit-name" value={editName} onChange={(_e, v) => setEditName(v)} isRequired />
            </FormGroup>
            <FormGroup label="SKU" fieldId="edit-sku" isRequired>
              <TextInput id="edit-sku" value={editSku} onChange={(_e, v) => setEditSku(v)} isRequired />
            </FormGroup>
            <FormGroup label="Price ($)" fieldId="edit-price">
              <TextInput id="edit-price" type="number" value={editPrice} onChange={(_e, v) => setEditPrice(v)} />
            </FormGroup>
            <FormGroup label="Stock" fieldId="edit-stock">
              <TextInput id="edit-stock" type="number" value={editStock} onChange={(_e, v) => setEditStock(v)} />
            </FormGroup>
            <FormGroup label="Reorder At" fieldId="edit-reorder">
              <TextInput id="edit-reorder" type="number" value={editReorder} onChange={(_e, v) => setEditReorder(v)} />
            </FormGroup>
            <FormGroup label="Supplier" fieldId="edit-supplier">
              <FormSelect id="edit-supplier" value={editSupplier} onChange={(_e, v) => setEditSupplier(v)}>
                <FormSelectOption value="" label="-- No supplier --" />
                {supplierList.map(s => <FormSelectOption key={s.id} value={s.id} label={s.name} />)}
              </FormSelect>
            </FormGroup>
            <FormGroup label="Replace Image" fieldId="edit-image">
              <input type="file" id="edit-image" accept="image/*" onChange={async (e) => {
                const file = e.target.files?.[0];
                if (file) {
                  if (file.size > 1024 * 1024) { log('Image must be under 1MB', 'error'); return; }
                  setEditImage(await readFileAsDataUrl(file));
                }
              }} />
            </FormGroup>
            <FormGroup label="Description" fieldId="edit-description">
              <TextArea id="edit-description" value={editDescription} onChange={(_e, v) => setEditDescription(v)} rows={3} />
            </FormGroup>
          </Form>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setEditProduct(null)}>Cancel</Button>
          <Button variant="primary" onClick={(e) => handleEdit(e as unknown as React.FormEvent)}>Save</Button>
        </ModalFooter>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal variant={ModalVariant.small} isOpen={!!deleteTarget} onClose={() => setDeleteTarget(null)} aria-label="Confirm deletion">
        <ModalHeader title="Confirm Deletion" />
        <ModalBody>
          Are you sure you want to delete product <strong id="delete-product-name">{deleteTarget?.name}</strong>?
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button variant="danger" onClick={handleDelete} id="confirm-delete-btn">Delete</Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
