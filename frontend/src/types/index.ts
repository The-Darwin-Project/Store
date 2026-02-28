export interface Product {
  id: string;
  name: string;
  sku: string;
  price: number;
  stock: number;
  image_data?: string | null;
  description?: string | null;
  reorder_threshold?: number;
  supplier_id?: string | null;
  created_at?: string;
}

export interface ProductCreate {
  name: string;
  sku: string;
  price: number;
  stock: number;
  image_data?: string | null;
  description?: string | null;
  reorder_threshold?: number;
  supplier_id?: string | null;
}

export interface Order {
  id: string;
  customer_id?: string | null;
  items: OrderItem[];
  total: number;
  status: OrderStatus;
  created_at: string;
  coupon_code?: string | null;
  discount_amount?: number;
}

export interface OrderItem {
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: number;
}

export type OrderStatus =
  | 'pending'
  | 'processing'
  | 'shipped'
  | 'delivered'
  | 'cancelled'
  | 'returned';

export interface OrderCreate {
  customer_id?: string | null;
  items: { product_id: string; quantity: number }[];
  coupon_code?: string | null;
}

export interface Customer {
  id: string;
  name: string;
  email: string;
  company?: string | null;
  phone?: string | null;
  address?: Address | null;
  created_at?: string;
}

export interface Address {
  street?: string;
  city?: string;
  state?: string;
  zip?: string;
  country?: string;
}

export interface CustomerCreate {
  name: string;
  email: string;
  company?: string | null;
  phone?: string | null;
  address?: Address | null;
}

export interface Supplier {
  id: string;
  name: string;
  contact_email?: string | null;
  phone?: string | null;
  created_at?: string;
}

export interface SupplierCreate {
  name: string;
  contact_email?: string | null;
  phone?: string | null;
}

export interface Alert {
  id: string;
  product_id: string;
  product_name: string;
  current_stock: number;
  reorder_threshold: number;
  supplier_id?: string | null;
  supplier_name?: string | null;
  supplier_email?: string | null;
  status: 'active' | 'ordered' | 'dismissed';
  created_at: string;
}

export interface Coupon {
  id: string;
  code: string;
  discount_type: 'percentage' | 'fixed';
  discount_value: number;
  min_order_amount: number;
  max_uses: number;
  current_uses: number;
  expires_at?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CouponCreate {
  code: string;
  discount_type: 'percentage' | 'fixed';
  discount_value: number;
  min_order_amount?: number;
  max_uses?: number;
  expires_at?: string | null;
}

export interface CouponValidationResult {
  valid: boolean;
  coupon?: Coupon;
  discount_amount?: number;
  message?: string;
}

export interface InvoiceLineItem {
  product_name: string;
  sku: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

export interface CustomerSnapshot {
  name: string;
  email: string;
  company?: string | null;
  phone?: string | null;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  order_id: string;
  customer_snapshot: CustomerSnapshot;
  line_items: InvoiceLineItem[];
  subtotal: number;
  discount_amount: number;
  grand_total: number;
  coupon_code?: string | null;
  created_at: string;
}

export interface Campaign {
  id: string;
  title: string;
  type: 'banner' | 'discount_promo' | 'product_spotlight';
  content?: string | null;
  image_url?: string | null;
  link_url?: string | null;
  coupon_code?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  start_date: string;
  end_date: string;
  is_active: boolean;
  priority: number;
  created_at: string;
}

export interface CampaignCreate {
  title: string;
  type: 'banner' | 'discount_promo' | 'product_spotlight';
  content?: string | null;
  image_url?: string | null;
  link_url?: string | null;
  coupon_code?: string | null;
  product_id?: string | null;
  start_date: string;
  end_date: string;
  is_active?: boolean;
  priority?: number;
}

export interface Review {
  id: string;
  product_id: string;
  reviewer_name: string;
  rating: number;
  comment?: string | null;
  created_at: string;
}

export interface ReviewCreate {
  reviewer_name: string;
  rating: number;
  comment?: string | null;
}

export interface AverageRating {
  product_id: string;
  average_rating: number;
  review_count: number;
}

export interface DashboardData {
  total_revenue: number;
  orders_by_status: Record<string, number>;
  top_products: { name: string; units_sold: number }[];
  low_stock: {
    product_name: string;
    stock: number;
    reorder_threshold: number;
    supplier_name?: string;
    supplier_email?: string;
  }[];
}

export interface CartItem {
  product_id: string;
  product_name: string;
  price: number;
  quantity: number;
}

export interface LogEntry {
  time: string;
  message: string;
  type: 'info' | 'success' | 'error';
}
