import type {
  Product, ProductCreate, Order, OrderCreate, OrderStatus,
  Customer, CustomerCreate, Supplier, SupplierCreate,
  Alert, Coupon, CouponCreate, CouponValidationResult,
  Invoice, Campaign, CampaignCreate, Review, ReviewCreate,
  AverageRating, DashboardData, PaginatedResponse,
} from '../types';

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(endpoint: string, method = 'GET', body?: unknown): Promise<T> {
  const options: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  if (body) options.body = JSON.stringify(body);

  const response = await fetch(endpoint, options);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(error.detail || 'Request failed', response.status);
  }

  if (response.status === 204) return null as T;
  return response.json();
}

// Products
export const products = {
  list: (page = 1, limit = 20) =>
    request<PaginatedResponse<Product>>(`/products?page=${page}&limit=${limit}`),
  get: (id: string) => request<Product>(`/products/${id}`),
  create: (data: ProductCreate) => request<Product>('/products', 'POST', data),
  update: (id: string, data: ProductCreate) => request<Product>(`/products/${id}`, 'PUT', data),
  patch: (id: string, data: Partial<ProductCreate>) => request<Product>(`/products/${id}`, 'PATCH', data),
  delete: (id: string) => request<void>(`/products/${id}`, 'DELETE'),
};

// Orders
export const orders = {
  list: (page = 1, limit = 20) =>
    request<PaginatedResponse<Order>>(`/orders?page=${page}&limit=${limit}`),
  listUnassigned: () => request<Order[]>('/orders/unassigned'),
  create: (data: OrderCreate) => request<Order>('/orders', 'POST', data),
  delete: (id: string) => request<void>(`/orders/${id}`, 'DELETE'),
  updateStatus: (id: string, status: OrderStatus) =>
    request<Order>(`/orders/${id}/status`, 'PATCH', { status }),
  attachToCustomer: (orderId: string, customerId: string) =>
    request<Order>(`/orders/${orderId}/customer/${customerId}`, 'PUT'),
  generateInvoice: (orderId: string) =>
    request<Invoice>(`/orders/${orderId}/invoice`, 'POST'),
};

// Customers
export const customers = {
  list: () => request<Customer[]>('/customers'),
  get: (id: string) => request<Customer>(`/customers/${id}`),
  create: (data: CustomerCreate) => request<Customer>('/customers', 'POST', data),
  update: (id: string, data: Partial<CustomerCreate>) =>
    request<Customer>(`/customers/${id}`, 'PATCH', data),
  delete: (id: string) => request<void>(`/customers/${id}`, 'DELETE'),
  listOrders: (id: string) => request<Order[]>(`/customers/${id}/orders`),
  detachOrder: (customerId: string, orderId: string) =>
    request<void>(`/customers/${customerId}/orders/${orderId}`, 'DELETE'),
};

// Suppliers
export const suppliers = {
  list: () => request<Supplier[]>('/suppliers'),
  create: (data: SupplierCreate) => request<Supplier>('/suppliers', 'POST', data),
  delete: (id: string) => request<void>(`/suppliers/${id}`, 'DELETE'),
  listProducts: (id: string) => request<Product[]>(`/suppliers/${id}/products`),
};

// Dashboard
export const dashboard = {
  get: () => request<DashboardData>('/dashboard'),
};

// Alerts
export const alerts = {
  list: (status?: string) =>
    request<Alert[]>(status ? `/alerts?status=${status}` : '/alerts'),
  create: (data: { product_id: string }) => request<Alert>('/alerts', 'POST', data),
  updateStatus: (id: string, status: string) =>
    request<Alert>(`/alerts/${id}`, 'PATCH', { status }),
};

// Coupons
export const coupons = {
  list: () => request<Coupon[]>('/coupons'),
  get: (id: string) => request<Coupon>(`/coupons/${id}`),
  create: (data: CouponCreate) => request<Coupon>('/coupons', 'POST', data),
  update: (id: string, data: Partial<CouponCreate & { is_active: boolean }>) =>
    request<Coupon>(`/coupons/${id}`, 'PATCH', data),
  delete: (id: string) => request<void>(`/coupons/${id}`, 'DELETE'),
  validate: (code: string, cart_total: number) =>
    request<CouponValidationResult>('/coupons/validate', 'POST', { code, cart_total }),
};

// Invoices
export const invoices = {
  list: (orderId?: string) =>
    request<Invoice[]>(orderId ? `/invoices?order_id=${orderId}` : '/invoices'),
  get: (id: string) => request<Invoice>(`/invoices/${id}`),
};

// Reviews
export const reviews = {
  list: (productId: string) => request<Review[]>(`/products/${productId}/reviews`),
  create: (productId: string, data: ReviewCreate) =>
    request<Review>(`/products/${productId}/reviews`, 'POST', data),
  getAverage: (productId: string) =>
    request<AverageRating>(`/products/${productId}/average-rating`),
  getBatchAverages: async (productIds: string[]): Promise<AverageRating[]> => {
    const BATCH_SIZE = 50;
    if (productIds.length <= BATCH_SIZE) {
      return request<AverageRating[]>(
        `/products/average-ratings/batch?product_ids=${productIds.join(',')}`
      );
    }
    const results: AverageRating[] = [];
    for (let i = 0; i < productIds.length; i += BATCH_SIZE) {
      const chunk = productIds.slice(i, i + BATCH_SIZE);
      const batch = await request<AverageRating[]>(
        `/products/average-ratings/batch?product_ids=${chunk.join(',')}`
      );
      results.push(...batch);
    }
    return results;
  },
};

// Campaigns
export const campaigns = {
  list: () => request<Campaign[]>('/campaigns'),
  listActive: () => request<Campaign[]>('/campaigns/active'),
  get: (id: string) => request<Campaign>(`/campaigns/${id}`),
  create: (data: CampaignCreate) => request<Campaign>('/campaigns', 'POST', data),
  update: (id: string, data: Partial<CampaignCreate>) =>
    request<Campaign>(`/campaigns/${id}`, 'PATCH', data),
  delete: (id: string) => request<void>(`/campaigns/${id}`, 'DELETE'),
};

// Auth
export const auth = {
  login: (password: string) => request<{ message: string }>('/auth/login', 'POST', { password }),
  logout: () => request<{ message: string }>('/auth/logout', 'POST'),
  changePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>('/auth/change-password', 'POST', {
      current_password,
      new_password,
    }),
};

export { ApiError };
