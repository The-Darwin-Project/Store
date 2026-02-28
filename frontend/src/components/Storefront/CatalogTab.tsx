import { useState, useEffect, useCallback } from 'react';
import {
  Card, CardBody, CardTitle, CardFooter,
  Button, Gallery, GalleryItem,
  TextInput,
  NumberInput,
} from '@patternfly/react-core';
import { ShoppingCartIcon } from '@patternfly/react-icons';
import { products as productsApi, campaigns as campaignsApi, reviews as reviewsApi } from '../../api/client';
import type { Product, Campaign, AverageRating } from '../../types';
import { usePolling } from '../../hooks/usePolling';
import { ProductDetailModal } from './ProductDetailModal';

interface Props {
  onAddToCart: (product: { id: string; name: string; price: number }, qty: number) => void;
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
  searchQuery: string;
}

export function CatalogTab({ onAddToCart, log, searchQuery }: Props) {
  const [productList, setProductList] = useState<Product[]>([]);
  const [activeCampaigns, setActiveCampaigns] = useState<Campaign[]>([]);
  const [ratings, setRatings] = useState<Record<string, AverageRating>>({});
  const [addQty, setAddQty] = useState<Record<string, number>>({});
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

  const loadProducts = useCallback(async () => {
    try {
      const data = await productsApi.list();
      setProductList(data || []);
      if (data && data.length > 0) {
        const ids = data.map(p => p.id);
        try {
          const avgRatings = await reviewsApi.getBatchAverages(ids);
          const map: Record<string, AverageRating> = {};
          avgRatings.forEach(r => { map[r.product_id] = r; });
          setRatings(map);
        } catch { /* batch ratings may not be available */ }
      }
    } catch (error) {
      log(`Failed to load products: ${(error as Error).message}`, 'error');
    }
  }, [log]);

  const loadCampaigns = useCallback(async () => {
    try {
      const data = await campaignsApi.listActive();
      setActiveCampaigns(data || []);
    } catch { /* ignore campaign load errors */ }
  }, []);

  usePolling(() => { loadProducts(); loadCampaigns(); }, 30000);

  const filtered = searchQuery
    ? productList.filter(p =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (p.description || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
    : productList;

  const renderStars = (rating: number) => {
    const full = Math.floor(rating);
    const half = rating - full >= 0.5;
    let stars = '';
    for (let i = 0; i < full; i++) stars += '\u2605';
    if (half) stars += '\u2605';
    for (let i = full + (half ? 1 : 0); i < 5; i++) stars += '\u2606';
    return stars;
  };

  const banners = activeCampaigns.filter(c => c.campaign_type === 'banner');
  const promos = activeCampaigns.filter(c => c.campaign_type !== 'banner');

  return (
    <div id="catalog">
      {banners.length > 0 && (
        <div className="campaign-banners-container" id="campaign-banners">
          {banners.map(b => (
            <div key={b.id} className="ds-campaign-banner" style={{
              background: 'linear-gradient(135deg, var(--pf-t--global--color--brand--default), var(--pf-t--global--color--brand--hover))',
              padding: '1.5rem', borderRadius: '8px', marginBottom: '1rem', color: '#fff',
            }}>
              <h3>{b.title}</h3>
              {b.content && <p>{b.content}</p>}
              {b.coupon_code && <span className="ds-coupon-tag">Use code: {b.coupon_code}</span>}
            </div>
          ))}
        </div>
      )}

      {promos.length > 0 && (
        <div className="campaign-promos-container" id="campaign-promos">
          {promos.map(p => (
            <div key={p.id} className="ds-promo-card" style={{
              background: 'var(--pf-t--global--background--color--secondary--default)',
              padding: '1rem', borderRadius: '8px', marginBottom: '0.5rem',
            }}>
              <strong>{p.title}</strong>
              {p.content && <span> &mdash; {p.content}</span>}
              {p.coupon_code && <span className="ds-coupon-tag" style={{ marginLeft: '0.5rem' }}>Code: {p.coupon_code}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="catalog-grid" id="catalog-grid">
        {filtered.length === 0 ? (
          <div className="ds-empty-state" style={{ gridColumn: '1 / -1' }}>No products yet.</div>
        ) : (
          <Gallery hasGutter>
            {filtered.map(p => {
              const r = ratings[p.id];
              const qty = addQty[p.id] || 1;
              return (
                <GalleryItem key={p.id}>
                  <Card isCompact className="ds-product-card" id={`product-card-${p.id}`}>
                    <CardTitle>
                      <span
                        className="ds-product-name"
                        style={{ cursor: 'pointer' }}
                        onClick={() => setSelectedProduct(p)}
                      >
                        {p.name}
                      </span>
                    </CardTitle>
                    <CardBody>
                      {p.image_data && (
                        <div style={{ marginBottom: '0.5rem' }}>
                          <img
                            src={p.image_data}
                            alt={p.name}
                            style={{ maxWidth: '100%', maxHeight: '120px', objectFit: 'cover', borderRadius: '4px' }}
                          />
                        </div>
                      )}
                      <div className="price" style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                        ${p.price.toFixed(2)}
                      </div>
                      {p.stock === 0 ? (
                        <div style={{ color: 'var(--pf-t--global--color--status--danger--default)' }}>Out of stock</div>
                      ) : p.stock < 10 ? (
                        <div style={{ color: 'var(--pf-t--global--color--status--warning--default)' }}>Low stock ({p.stock})</div>
                      ) : (
                        <div style={{ color: 'var(--pf-t--global--color--status--success--default)' }}>In stock</div>
                      )}
                      {r && r.review_count > 0 && (
                        <div className="ds-rating" style={{ color: '#fbbf24' }}>
                          {renderStars(r.average_rating)} ({r.review_count})
                        </div>
                      )}
                    </CardBody>
                    <CardFooter>
                      {p.stock > 0 && (
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          <NumberInput
                            value={qty}
                            min={1}
                            max={p.stock}
                            onChange={(e) => {
                              const val = parseInt((e.target as HTMLInputElement).value) || 1;
                              setAddQty(prev => ({ ...prev, [p.id]: val }));
                            }}
                            onMinus={() => setAddQty(prev => ({ ...prev, [p.id]: Math.max(1, (prev[p.id] || 1) - 1) }))}
                            onPlus={() => setAddQty(prev => ({ ...prev, [p.id]: Math.min(p.stock, (prev[p.id] || 1) + 1) }))}
                            widthChars={3}
                          />
                          <Button
                            variant="primary"
                            icon={<ShoppingCartIcon />}
                            onClick={() => {
                              onAddToCart({ id: p.id, name: p.name, price: p.price }, qty);
                              log(`Added ${qty}x ${p.name} to cart`, 'success');
                              setAddQty(prev => ({ ...prev, [p.id]: 1 }));
                            }}
                            id={`add-to-cart-${p.id}`}
                          >
                            Add
                          </Button>
                        </div>
                      )}
                    </CardFooter>
                  </Card>
                </GalleryItem>
              );
            })}
          </Gallery>
        )}
      </div>

      <ProductDetailModal
        product={selectedProduct}
        isOpen={!!selectedProduct}
        onClose={() => setSelectedProduct(null)}
        onAddToCart={onAddToCart}
        log={log}
      />
    </div>
  );
}
