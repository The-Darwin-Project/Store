import { useState, useEffect } from 'react';
import {
  Modal, ModalVariant, ModalHeader, ModalBody, ModalFooter,
  Button, TextInput, TextArea, Form, FormGroup,
  NumberInput,
} from '@patternfly/react-core';
import { StarIcon } from '@patternfly/react-icons';
import { reviews as reviewsApi } from '../../api/client';
import type { Product, Review, AverageRating } from '../../types';

interface Props {
  product: Product | null;
  isOpen: boolean;
  onClose: () => void;
  onAddToCart: (product: { id: string; name: string; price: number }, qty: number) => void;
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export function ProductDetailModal({ product, isOpen, onClose, onAddToCart, log }: Props) {
  const [reviewsList, setReviewsList] = useState<Review[]>([]);
  const [avgRating, setAvgRating] = useState<AverageRating | null>(null);
  const [reviewerName, setReviewerName] = useState('');
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState('');
  const [qty, setQty] = useState(1);

  useEffect(() => {
    if (product && isOpen) {
      loadReviews(product.id);
      setQty(1);
    }
  }, [product, isOpen]);

  const loadReviews = async (productId: string) => {
    try {
      const [revs, avg] = await Promise.all([
        reviewsApi.list(productId),
        reviewsApi.getAverage(productId),
      ]);
      setReviewsList(revs || []);
      setAvgRating(avg);
    } catch { /* ignore */ }
  };

  const submitReview = async () => {
    if (!product || !reviewerName.trim()) return;
    try {
      await reviewsApi.create(product.id, {
        reviewer_name: reviewerName.trim(),
        rating: reviewRating,
        comment: reviewComment.trim() || null,
      });
      log(`Review submitted for ${product.name}`, 'success');
      setReviewerName('');
      setReviewRating(5);
      setReviewComment('');
      loadReviews(product.id);
    } catch (error) {
      log(`Failed to submit review: ${(error as Error).message}`, 'error');
    }
  };

  const renderStars = (rating: number) => {
    const stars = [];
    for (let i = 1; i <= 5; i++) {
      stars.push(
        <StarIcon
          key={i}
          style={{ color: i <= rating ? '#fbbf24' : '#555', cursor: 'default' }}
        />
      );
    }
    return stars;
  };

  if (!product) return null;

  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen={isOpen}
      onClose={onClose}
      aria-label="Product detail"
      id="product-detail-modal"
    >
      <ModalHeader title={product.name} />
      <ModalBody id="product-detail-content">
        <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1.5rem' }}>
          {product.image_data && (
            <img src={product.image_data} alt={product.name}
              style={{ maxWidth: '200px', maxHeight: '200px', objectFit: 'cover', borderRadius: '8px' }} />
          )}
          <div>
            <div className="price" style={{ fontSize: '1.5rem', fontWeight: 700 }}>${product.price.toFixed(2)}</div>
            <div style={{ margin: '0.5rem 0' }}>SKU: {product.sku}</div>
            <div>Stock: {product.stock}</div>
            {product.description && <p style={{ marginTop: '0.5rem' }}>{product.description}</p>}
            {avgRating && (avgRating.review_count ?? 0) > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                {renderStars(Math.round(avgRating.average_rating ?? 0))}
                <span style={{ marginLeft: '0.5rem' }}>
                  {(avgRating.average_rating ?? 0).toFixed(1)} ({avgRating.review_count} review{avgRating.review_count !== 1 ? 's' : ''})
                </span>
              </div>
            )}
            {product.stock > 0 && (
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <NumberInput value={qty} min={1} max={product.stock}
                  onChange={(e) => setQty(parseInt((e.target as HTMLInputElement).value) || 1)}
                  onMinus={() => setQty(q => Math.max(1, q - 1))}
                  onPlus={() => setQty(q => Math.min(product.stock, q + 1))}
                  widthChars={3} />
                <Button variant="primary" onClick={() => {
                  onAddToCart({ id: product.id, name: product.name, price: product.price }, qty);
                  log(`Added ${qty}x ${product.name} to cart`, 'success');
                }}>Add to Cart</Button>
              </div>
            )}
          </div>
        </div>

        <h3 style={{ marginBottom: '1rem' }}>Reviews</h3>
        {reviewsList.length === 0 ? (
          <div className="ds-empty-state">No reviews yet. Be the first!</div>
        ) : (
          <div style={{ marginBottom: '1.5rem' }}>
            {reviewsList.map(r => (
              <div key={r.id} style={{
                padding: '0.75rem', marginBottom: '0.5rem',
                background: 'var(--pf-t--global--background--color--secondary--default)',
                borderRadius: '8px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <strong>{r.reviewer_name}</strong>
                  <span style={{ color: '#fbbf24' }}>{renderStars(r.rating)}</span>
                </div>
                {r.comment && <p style={{ marginTop: '0.25rem' }}>{r.comment}</p>}
                <div style={{ fontSize: '0.8rem', color: 'var(--pf-t--global--text--color--subtle)' }}>
                  {new Date(r.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}

        <h4 style={{ marginBottom: '0.5rem' }}>Write a Review</h4>
        <Form onSubmit={e => { e.preventDefault(); submitReview(); }}>
          <FormGroup label="Your Name" fieldId="review-customer" isRequired>
            <TextInput id="review-customer" value={reviewerName}
              onChange={(_e, val) => setReviewerName(val)} isRequired />
          </FormGroup>
          <FormGroup label="Rating" fieldId="review-rating">
            <div id="star-picker">
              {[1, 2, 3, 4, 5].map(i => (
                <StarIcon key={i}
                  style={{ cursor: 'pointer', color: i <= reviewRating ? '#fbbf24' : '#555', fontSize: '1.5rem' }}
                  onClick={() => setReviewRating(i)} />
              ))}
            </div>
          </FormGroup>
          <FormGroup label="Comment" fieldId="review-comment">
            <TextArea id="review-comment" value={reviewComment}
              onChange={(_e, val) => setReviewComment(val)} rows={2} />
          </FormGroup>
          <Button type="submit" variant="primary" isDisabled={!reviewerName.trim()}>Submit Review</Button>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>Close</Button>
      </ModalFooter>
    </Modal>
  );
}
