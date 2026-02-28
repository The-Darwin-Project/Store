import { useState, useEffect, useCallback } from 'react';
import {
  Button, Form, FormGroup, TextInput, TextArea, FormSelect, FormSelectOption,
  Checkbox,
} from '@patternfly/react-core';
import { campaigns as campaignsApi, products as productsApi } from '../../api/client';
import type { Campaign, Product } from '../../types';
import { usePolling } from '../../hooks/usePolling';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function CampaignsTab({ log, searchQuery }: Props) {
  const [campaignList, setCampaignList] = useState<Campaign[]>([]);
  const [productList, setProductList] = useState<Product[]>([]);
  const [title, setTitle] = useState('');
  const [campaignType, setCampaignType] = useState('banner');
  const [content, setContent] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const [productId, setProductId] = useState('');
  const [priority, setPriority] = useState('0');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isActive, setIsActive] = useState(true);

  const loadCampaigns = useCallback(async () => {
    try {
      const data = await campaignsApi.list();
      setCampaignList(data || []);
    } catch (error) {
      log(`Failed to load campaigns: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  useEffect(() => {
    productsApi.list().then(p => setProductList(p || [])).catch(() => {});
  }, []);

  usePolling(loadCampaigns, 30000);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !startDate || !endDate) return;
    try {
      const campaign = await campaignsApi.create({
        title: title.trim(),
        campaign_type: campaignType as Campaign['campaign_type'],
        content: content.trim() || null,
        image_url: imageUrl.trim() || null,
        link_url: linkUrl.trim() || null,
        coupon_code: couponCode.trim().toUpperCase() || null,
        product_id: productId || null,
        start_date: startDate,
        end_date: endDate,
        is_active: isActive,
        priority: parseInt(priority) || 0,
      });
      log(`Campaign created: ${campaign.title}`, 'success');
      setTitle(''); setContent(''); setImageUrl(''); setLinkUrl('');
      setCouponCode(''); setProductId(''); setPriority('0');
      setStartDate(''); setEndDate(''); setIsActive(true);
      loadCampaigns();
    } catch (error) {
      log(`Failed to create campaign: ${(error as Error).message}`, 'error');
    }
  };

  const toggleActive = async (c: Campaign) => {
    try {
      await campaignsApi.update(c.id, { is_active: !c.is_active });
      log(`Campaign ${c.title} ${c.is_active ? 'deactivated' : 'activated'}`, 'success');
      loadCampaigns();
    } catch (error) {
      log(`Failed to update campaign: ${(error as Error).message}`, 'error');
    }
  };

  const deleteCampaign = async (c: Campaign) => {
    try {
      await campaignsApi.delete(c.id);
      log(`Deleted campaign: ${c.title}`, 'success');
      loadCampaigns();
    } catch (error) {
      log(`Failed to delete campaign: ${(error as Error).message}`, 'error');
    }
  };

  const filtered = searchQuery
    ? campaignList.filter(c => c.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : campaignList;

  return (
    <div id="campaigns">
      <div className="ds-panel">
        <h2>Create Campaign</h2>
        <Form onSubmit={handleAdd} id="add-campaign-form">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <FormGroup label="Title" fieldId="campaign-title" isRequired style={{ flex: '2 1 200px' }}>
              <TextInput id="campaign-title" value={title} onChange={(_e, v) => setTitle(v)} isRequired placeholder="Campaign title" />
            </FormGroup>
            <FormGroup label="Type" fieldId="campaign-type" style={{ flex: '0 1 180px' }}>
              <FormSelect id="campaign-type" value={campaignType} onChange={(_e, v) => setCampaignType(v)}>
                <FormSelectOption value="banner" label="Banner" />
                <FormSelectOption value="discount_promo" label="Discount Promo" />
                <FormSelectOption value="product_spotlight" label="Product Spotlight" />
              </FormSelect>
            </FormGroup>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
            <FormGroup label="Content" fieldId="campaign-content" style={{ flex: '2 1 200px' }}>
              <TextArea id="campaign-content" value={content} onChange={(_e, v) => setContent(v)} rows={2} />
            </FormGroup>
            <FormGroup label="Image URL" fieldId="campaign-image-url" style={{ flex: '1 1 150px' }}>
              <TextInput id="campaign-image-url" value={imageUrl} onChange={(_e, v) => setImageUrl(v)} placeholder="https://..." />
            </FormGroup>
            <FormGroup label="Link URL" fieldId="campaign-link-url" style={{ flex: '1 1 150px' }}>
              <TextInput id="campaign-link-url" value={linkUrl} onChange={(_e, v) => setLinkUrl(v)} placeholder="https://..." />
            </FormGroup>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem', alignItems: 'flex-end' }}>
            <FormGroup label="Coupon Code" fieldId="campaign-coupon-code" style={{ flex: '0 1 150px' }}>
              <TextInput id="campaign-coupon-code" value={couponCode} onChange={(_e, v) => setCouponCode(v)}
                placeholder="e.g. SUMMER20" style={{ textTransform: 'uppercase' }} />
            </FormGroup>
            {campaignType === 'product_spotlight' && (
              <FormGroup label="Product" fieldId="campaign-product-id" style={{ flex: '1 1 150px' }} id="campaign-product-group">
                <FormSelect id="campaign-product-id" value={productId} onChange={(_e, v) => setProductId(v)}>
                  <FormSelectOption value="" label="-- Select product --" />
                  {productList.map(p => <FormSelectOption key={p.id} value={p.id} label={p.name} />)}
                </FormSelect>
              </FormGroup>
            )}
            <FormGroup label="Priority" fieldId="campaign-priority" style={{ flex: '0 1 80px' }}>
              <TextInput id="campaign-priority" type="number" value={priority} onChange={(_e, v) => setPriority(v)} />
            </FormGroup>
            <FormGroup label="Start Date" fieldId="campaign-start-date" isRequired style={{ flex: '0 1 200px' }}>
              <input type="datetime-local" id="campaign-start-date" value={startDate} required
                onChange={e => setStartDate(e.target.value)} className="pf-v6-c-form-control" />
            </FormGroup>
            <FormGroup label="End Date" fieldId="campaign-end-date" isRequired style={{ flex: '0 1 200px' }}>
              <input type="datetime-local" id="campaign-end-date" value={endDate} required
                onChange={e => setEndDate(e.target.value)} className="pf-v6-c-form-control" />
            </FormGroup>
            <Checkbox id="campaign-is-active" label="Active" isChecked={isActive}
              onChange={(_e, checked) => setIsActive(checked)} />
            <Button type="submit" variant="primary">Create Campaign</Button>
          </div>
        </Form>
      </div>

      <div className="ds-panel" style={{ marginTop: '1rem' }}>
        <h2>Campaign List</h2>
        <div className="ds-table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Title</th><th>Type</th><th>Dates</th><th>Coupon</th><th>Status</th><th>Priority</th><th>Actions</th></tr>
            </thead>
            <tbody id="campaigns-table">
              {filtered.length === 0 ? (
                <tr><td colSpan={7} className="ds-empty-state">No campaigns yet.</td></tr>
              ) : filtered.map(c => (
                <tr key={c.id}>
                  <td>{c.title}</td>
                  <td>{c.campaign_type.replace('_', ' ')}</td>
                  <td>{new Date(c.start_date).toLocaleDateString()} - {new Date(c.end_date).toLocaleDateString()}</td>
                  <td>{c.coupon_code || '-'}</td>
                  <td>{c.is_active ? '\u2705 Active' : '\u274C Inactive'}</td>
                  <td>{c.priority}</td>
                  <td className="actions">
                    <Button variant="secondary" size="sm" onClick={() => toggleActive(c)}>
                      {c.is_active ? 'Deactivate' : 'Activate'}
                    </Button>{' '}
                    <Button variant="danger" size="sm" onClick={() => deleteCampaign(c)}>Delete</Button>
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
