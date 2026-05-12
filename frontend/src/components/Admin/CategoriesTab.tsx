import { useState, useCallback } from 'react';
import {
  Button, Form, FormGroup, TextInput, TextArea,
  Modal, ModalVariant, ModalHeader, ModalBody, ModalFooter,
} from '@patternfly/react-core';
import { categories as categoriesApi } from '../../api/client';
import type { Category } from '../../types';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function CategoriesTab({ log, searchQuery }: Props) {
  const [categoryList, setCategoryList] = useState<Category[]>([]);
  const [editCategory, setEditCategory] = useState<Category | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null);
  const [addName, setAddName] = useState('');
  const [addDescription, setAddDescription] = useState('');
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');

  const loadCategories = useCallback(async () => {
    try {
      const data = await categoriesApi.list();
      setCategoryList(data || []);
    } catch (error) {
      log(`Failed to load categories: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  usePolling(loadCategories, 30000);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addName.trim()) return;
    try {
      const cat = await categoriesApi.create({
        name: addName.trim(),
        description: addDescription.trim() || null,
      });
      log(`Category created: ${cat.name}`, 'success');
      setAddName('');
      setAddDescription('');
      loadCategories();
    } catch (error) {
      log(`Failed to create category: ${(error as Error).message}`, 'error');
    }
  };

  const openEdit = (c: Category) => {
    setEditCategory(c);
    setEditName(c.name);
    setEditDescription(c.description || '');
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editCategory || !editName.trim()) return;
    try {
      await categoriesApi.update(editCategory.id, {
        name: editName.trim(),
        description: editDescription.trim() || null,
      });
      log(`Updated category: ${editName.trim()}`, 'success');
      setEditCategory(null);
      loadCategories();
    } catch (error) {
      log(`Failed to update category: ${(error as Error).message}`, 'error');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await categoriesApi.delete(deleteTarget.id);
      log(`Deleted category: ${deleteTarget.name}`, 'success');
      setDeleteTarget(null);
      loadCategories();
    } catch (error) {
      log(`Failed to delete category: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? categoryList.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : categoryList;

  return (
    <div id="categories">
      <div className="ds-panel">
        <h2>Add Category</h2>
        <Form onSubmit={handleAdd} id="add-category-form">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <FormGroup label="Name" fieldId="cat-name" isRequired style={{ flex: '1 1 200px' }}>
              <TextInput id="cat-name" value={addName} onChange={(_e, v) => setAddName(v)} isRequired placeholder="Category name" />
            </FormGroup>
            <FormGroup label="Description" fieldId="cat-desc" style={{ flex: '2 1 300px' }}>
              <TextInput id="cat-desc" value={addDescription} onChange={(_e, v) => setAddDescription(v)} placeholder="Optional description" />
            </FormGroup>
            <Button type="submit" variant="primary">Add Category</Button>
          </div>
        </Form>
      </div>

      <div className="ds-panel" style={{ marginTop: '1rem' }}>
        <h2>Categories</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Name</th><th>Description</th><th>Products</th><th>Actions</th></tr>
            </thead>
            <tbody id="category-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={4} className="ds-empty-state">No categories yet.</td></tr>
              ) : filtered.map(c => (
                <tr key={c.id} data-id={c.id}>
                  <td>{c.name}</td>
                  <td className="ds-desc-cell" title={c.description || ''}>{c.description || ''}</td>
                  <td>{c.product_count}</td>
                  <td className="actions">
                    <Button variant="secondary" size="sm" onClick={() => openEdit(c)}>Edit</Button>{' '}
                    <Button variant="danger" size="sm" onClick={() => setDeleteTarget(c)}>Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Modal variant={ModalVariant.medium} isOpen={!!editCategory} onClose={() => setEditCategory(null)} aria-label="Edit category">
        <ModalHeader title="Edit Category" />
        <ModalBody>
          <Form onSubmit={handleEdit} id="edit-category-form">
            <FormGroup label="Name" fieldId="edit-cat-name" isRequired>
              <TextInput id="edit-cat-name" value={editName} onChange={(_e, v) => setEditName(v)} isRequired />
            </FormGroup>
            <FormGroup label="Description" fieldId="edit-cat-desc">
              <TextArea id="edit-cat-desc" value={editDescription} onChange={(_e, v) => setEditDescription(v)} rows={3} />
            </FormGroup>
          </Form>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setEditCategory(null)}>Cancel</Button>
          <Button variant="primary" onClick={(e) => handleEdit(e as unknown as React.FormEvent)}>Save</Button>
        </ModalFooter>
      </Modal>

      <Modal variant={ModalVariant.small} isOpen={!!deleteTarget} onClose={() => setDeleteTarget(null)} aria-label="Confirm deletion">
        <ModalHeader title="Confirm Deletion" />
        <ModalBody>
          Are you sure you want to delete category <strong id="delete-category-name">{deleteTarget?.name}</strong>?
          {deleteTarget && deleteTarget.product_count > 0 && (
            <p style={{ marginTop: '0.5rem', color: 'var(--pf-t--global--color--status--warning--default)' }}>
              This category has {deleteTarget.product_count} product(s). They will become uncategorized.
            </p>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button variant="danger" onClick={handleDelete} id="confirm-delete-category-btn">Delete</Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
