import { useState, useEffect } from 'react';
import {
  Page, PageSection, PageSectionVariants,
  Title, TextInput, Tabs, Tab, TabTitleText,
  Button, Flex, FlexItem, Badge,
} from '@patternfly/react-core';
import { useNavigate } from 'react-router-dom';
import { DashboardTab } from '../components/Admin/DashboardTab';
import { InventoryTab } from '../components/Admin/InventoryTab';
import { AdminOrdersTab } from '../components/Admin/AdminOrdersTab';
import { CustomersTab } from '../components/Admin/CustomersTab';
import { SuppliersTab } from '../components/Admin/SuppliersTab';
import { AlertsTab } from '../components/Admin/AlertsTab';
import { CouponsTab } from '../components/Admin/CouponsTab';
import { CampaignsTab } from '../components/Admin/CampaignsTab';
import { InvoicesTab } from '../components/Admin/InvoicesTab';
import { SettingsTab } from '../components/Admin/SettingsTab';
import { ActivityLog } from '../components/shared/ActivityLog';
import { useActivityLog } from '../hooks/useActivityLog';
import { auth } from '../api/client';
import { alerts as alertsApi } from '../api/client';

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [searchQuery, setSearchQuery] = useState('');
  const [alertCount, setAlertCount] = useState(0);
  const { entries, log } = useActivityLog();
  const navigate = useNavigate();

  useEffect(() => {
    const loadAlertCount = async () => {
      try {
        const data = await alertsApi.list('active');
        setAlertCount(data?.length || 0);
      } catch { /* ignore */ }
    };
    loadAlertCount();
    const interval = setInterval(loadAlertCount, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = async () => {
    try {
      await auth.logout();
      log('Logged out', 'info');
    } catch { /* ignore */ }
    navigate('/');
  };

  const placeholders: Record<string, string> = {
    dashboard: 'Search...',
    inventory: 'Search products...',
    orders: 'Search orders...',
    customers: 'Search customers...',
    suppliers: 'Search suppliers...',
    alerts: 'Search alerts...',
    coupons: 'Search coupons...',
    campaigns: 'Search campaigns...',
    invoices: 'Search invoices...',
    settings: 'Search...',
  };

  return (
    <Page>
      <PageSection variant={PageSectionVariants.secondary}>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Title headingLevel="h1" size="2xl">Darwin Store Admin</Title>
            <p className="ds-subtitle">Back Office Management</p>
          </FlexItem>
          <FlexItem>
            <Button variant="secondary" onClick={handleLogout} className="admin-logout-btn">Logout</Button>
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
          <Tab eventKey="dashboard" title={<TabTitleText>Dashboard</TabTitleText>} id="dashboard-tab">
            <PageSection><DashboardTab log={log} /></PageSection>
          </Tab>
          <Tab eventKey="inventory" title={<TabTitleText>Inventory</TabTitleText>} id="inventory-tab">
            <PageSection><InventoryTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="orders" title={<TabTitleText>Orders</TabTitleText>} id="orders-tab">
            <PageSection><AdminOrdersTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="customers" title={<TabTitleText>Customers</TabTitleText>} id="customers-tab">
            <PageSection><CustomersTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="suppliers" title={<TabTitleText>Suppliers</TabTitleText>} id="suppliers-tab">
            <PageSection><SuppliersTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="alerts" title={
            <TabTitleText>
              Alerts {alertCount > 0 && <Badge id="alerts-badge">{alertCount}</Badge>}
            </TabTitleText>
          } id="alerts-tab">
            <PageSection><AlertsTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="coupons" title={<TabTitleText>Coupons</TabTitleText>} id="coupons-tab">
            <PageSection><CouponsTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="campaigns" title={<TabTitleText>Campaigns</TabTitleText>} id="campaigns-tab">
            <PageSection><CampaignsTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="invoices" title={<TabTitleText>Invoices</TabTitleText>} id="invoices-tab">
            <PageSection><InvoicesTab log={log} searchQuery={searchQuery} /></PageSection>
          </Tab>
          <Tab eventKey="settings" title={<TabTitleText>Settings</TabTitleText>} id="settings-tab">
            <PageSection><SettingsTab log={log} /></PageSection>
          </Tab>
        </Tabs>
      </PageSection>

      <PageSection variant={PageSectionVariants.secondary}>
        <ActivityLog entries={entries} />
      </PageSection>
    </Page>
  );
}
