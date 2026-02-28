import { useState } from 'react';
import {
  Page, PageSection, PageSectionVariants,
  Title, TextInput, Tabs, Tab, TabTitleText,
  Button, Flex, FlexItem,
} from '@patternfly/react-core';
import { ShoppingCartIcon } from '@patternfly/react-icons';
import { CatalogTab } from '../components/Storefront/CatalogTab';
import { CartTab } from '../components/Storefront/CartTab';
import { OrdersTab } from '../components/Storefront/OrdersTab';
import { ProductDetailModal } from '../components/Storefront/ProductDetailModal';
import { ActivityLog } from '../components/shared/ActivityLog';
import { useCart } from '../hooks/useCart';
import { useActivityLog } from '../hooks/useActivityLog';
import { LoginModal } from '../components/shared/LoginModal';
import { products as productsApi } from '../api/client';
import type { Product } from '../types';

export function StorefrontPage() {
  const [activeTab, setActiveTab] = useState<string>('catalog');
  const [searchQuery, setSearchQuery] = useState('');
  const [loginOpen, setLoginOpen] = useState(false);
  const [reviewProduct, setReviewProduct] = useState<Product | null>(null);
  const cart = useCart();
  const { entries, log } = useActivityLog();

  const handleReviewProduct = async (productId: string) => {
    try {
      const p = await productsApi.get(productId);
      setReviewProduct(p);
    } catch { /* ignore */ }
  };

  const placeholders: Record<string, string> = {
    catalog: 'Search products...',
    cart: 'Search cart...',
    orders: 'Search orders...',
  };

  return (
    <Page>
      <PageSection variant={PageSectionVariants.secondary}>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Title headingLevel="h1" size="2xl">Darwin Store</Title>
            <p className="ds-subtitle">Shop</p>
          </FlexItem>
          <FlexItem>
            <Flex gap={{ default: 'gapMd' }}>
              <FlexItem>
                <Button variant="secondary" onClick={() => setLoginOpen(true)} className="admin-login-btn">Admin</Button>
              </FlexItem>
              <FlexItem>
                <Button variant="plain" onClick={() => setActiveTab('cart')}
                  className="cart-icon-wrapper" aria-label="View Cart">
                  <ShoppingCartIcon />
                  <span className={`cart-badge${cart.count === 0 ? ' hidden' : ''}`} id="cart-badge">{cart.count}</span>
                </Button>
              </FlexItem>
            </Flex>
          </FlexItem>
        </Flex>
        <div style={{ marginTop: '1rem' }}>
          <TextInput
            id="global-search"
            type="text"
            placeholder={placeholders[activeTab] || 'Search...'}
            value={searchQuery}
            onChange={(_e, val) => setSearchQuery(val)}
            style={{ maxWidth: '500px' }}
          />
        </div>
      </PageSection>

      <PageSection variant={PageSectionVariants.default} padding={{ default: 'noPadding' }}>
        <Tabs
          activeKey={activeTab}
          onSelect={(_e, key) => { setActiveTab(String(key)); setSearchQuery(''); }}
          id="viewTabs"
        >
          <Tab eventKey="catalog" title={<TabTitleText>Catalog</TabTitleText>} id="catalog-tab">
            <PageSection>
              <CatalogTab onAddToCart={cart.addItem} log={log} searchQuery={searchQuery} />
            </PageSection>
          </Tab>
          <Tab eventKey="cart" title={<TabTitleText>Cart</TabTitleText>} id="cart-tab">
            <PageSection>
              <CartTab
                items={cart.items}
                total={cart.total}
                onUpdateQuantity={cart.updateQuantity}
                onRemoveItem={cart.removeItem}
                onClear={cart.clear}
                log={log}
              />
            </PageSection>
          </Tab>
          <Tab eventKey="orders" title={<TabTitleText>My Orders</TabTitleText>} id="orders-tab">
            <PageSection>
              <OrdersTab log={log} searchQuery={searchQuery} onReviewProduct={handleReviewProduct} />
            </PageSection>
          </Tab>
        </Tabs>
      </PageSection>

      <PageSection variant={PageSectionVariants.secondary}>
        <ActivityLog entries={entries} />
      </PageSection>

      <LoginModal isOpen={loginOpen} onClose={() => setLoginOpen(false)} log={log} />
      <ProductDetailModal
        product={reviewProduct}
        isOpen={!!reviewProduct}
        onClose={() => setReviewProduct(null)}
        onAddToCart={cart.addItem}
        log={log}
      />
    </Page>
  );
}
