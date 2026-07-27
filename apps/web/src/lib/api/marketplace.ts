import { apiFetch } from "./client";

/**
 * Marketplace domain types — mirrors krishisetu/domains/marketplace/schemas.py.
 * Exported from this module (not lib/api/types.ts) because that's where the
 * dashboard pages already import them from.
 */

export interface Product {
  id: string;
  supplier_id: string;
  category_id: string;
  name: string;
  name_hi: string | null;
  slug: string;
  description: string;
  brand: string | null;
  price: number;
  mrp: number | null;
  unit: string;
  min_order_qty: number;
  stock_quantity: number;
  is_in_stock: boolean;
  image_url: string | null;
  certifications: string[] | null;
  active_ingredient: string | null;
  concentration: string | null;
  linked_disease_slug: string | null;
  suitable_crops: string[] | null;
  rating: number;
  total_reviews: number;
  discount_pct: number;
  supplier_name: string | null;
  category_name: string | null;
}

export interface ProductListResponse {
  products: Product[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface OrderItem {
  id: string;
  product_id: string;
  product_name: string;
  product_image_url: string | null;
  unit_price: number;
  quantity: number;
  total_price: number;
  fulfillment_status: string;
}

export interface Order {
  id: string;
  order_number: string;
  farmer_id: string;
  status: string;
  payment_status: string;
  subtotal: number;
  shipping_cost: number;
  total_amount: number;
  shipping_name: string;
  shipping_phone: string;
  shipping_address_line1: string;
  shipping_address_line2: string | null;
  shipping_village: string | null;
  shipping_district: string;
  shipping_state: string;
  shipping_pincode: string;
  placed_at: string | null;
  delivered_at: string | null;
  created_at: string;
  items: OrderItem[];
}

export interface OrderListResponse {
  orders: Order[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface MarketplaceStats {
  total_products: number;
  total_orders: number;
  pending_orders: number;
  completed_orders: number;
  total_spent: number;
}

export const marketplaceApi = {
  async listProducts(params: {
    category?: string;
    search?: string;
    state?: string;
    disease?: string;
    in_stock?: boolean;
    page?: number;
    page_size?: number;
  } = {}): Promise<ProductListResponse> {
    return apiFetch(`/marketplace/products`, { query: params });
  },
  async getProduct(id: string): Promise<Product> {
    return apiFetch(`/marketplace/products/${id}`);
  },
  async listMyOrders(page = 1, pageSize = 20): Promise<OrderListResponse> {
    return apiFetch(`/marketplace/orders`, { query: { page, page_size: pageSize } });
  },
  async getOrder(id: string): Promise<Order> {
    return apiFetch(`/marketplace/orders/${id}`);
  },
  async cancelOrder(id: string, reason?: string): Promise<Order> {
    return apiFetch(`/marketplace/orders/${id}/cancel`, {
      method: "POST",
      query: { reason },
    });
  },
  async createOrder(payload: {
    items: { product_id: string; quantity: number }[];
    shipping_name: string;
    shipping_phone: string;
    shipping_address_line1: string;
    shipping_address_line2?: string;
    shipping_village?: string;
    shipping_district: string;
    shipping_state: string;
    shipping_pincode: string;
    payment_method?: string;
  }): Promise<Order> {
    return apiFetch(`/marketplace/orders`, { method: "POST", body: JSON.stringify(payload) });
  },
  async getStats(): Promise<MarketplaceStats> {
    return apiFetch(`/marketplace/stats`);
  },
};
