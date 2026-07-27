import { apiFetch } from "./client";
import type { Product, Order, OrderListResponse, MarketplaceStats } from "./types";

export const marketplaceApi = {
  async listProducts(limit = 20, offset = 0): Promise<{ products: Product[]; total: number }> {
    return apiFetch(`/marketplace/products`, { query: { limit, offset } });
  },
  async createOrder(items: { product_id: string; quantity: number }[]): Promise<Order> {
    return apiFetch(`/marketplace/orders`, { method: "POST", body: JSON.stringify({ items }) });
  },
  async listOrders(limit = 20, offset = 0): Promise<OrderListResponse> {
    return apiFetch(`/marketplace/orders`, { query: { limit, offset } });
  },
};