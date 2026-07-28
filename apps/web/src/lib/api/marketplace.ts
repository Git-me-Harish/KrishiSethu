/**
 * Marketplace API client.
 *
 * Mirrors the backend REST surface under /api/v1/marketplace/* and
 * /api/v1/supplier/* — see apps/api/krishisetu/domains/marketplace/routes.py.
 *
 * Method names match the call-sites in:
 * - app/dashboard/marketplace/page.tsx           (listProducts, getStats, listMyOrders)
 * - app/dashboard/marketplace/order/[id]/page.tsx (getOrder, cancelOrder)
 */

import { apiFetch } from "./client";
import type {
  MarketplaceStatsResponse,
  OrderCreateRequest,
  OrderListResponse,
  OrderResponse,
  OrderStatus,
  ProductCategoryListResponse,
  ProductListResponse,
  ProductResponse,
} from "./types";

export const marketplaceApi = {
  // Public product catalog (no auth required)
  async listProducts(params?: {
    category?: string;
    search?: string;
    state?: string;
    disease?: string;
    in_stock?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<ProductListResponse> {
    return apiFetch<ProductListResponse>("/marketplace/products", {
      query: params,
    });
  },

  async getProduct(productId: string): Promise<ProductResponse> {
    return apiFetch<ProductResponse>(`/marketplace/products/${productId}`);
  },

  async getProductsForDisease(diseaseSlug: string): Promise<ProductResponse[]> {
    return apiFetch<ProductResponse[]>(
      `/marketplace/diseases/${diseaseSlug}/products`,
    );
  },

  async listCategories(): Promise<ProductCategoryListResponse> {
    return apiFetch<ProductCategoryListResponse>("/marketplace/categories");
  },

  // Farmer orders (require auth)
  async getStats(): Promise<MarketplaceStatsResponse> {
    return apiFetch<MarketplaceStatsResponse>("/marketplace/stats");
  },

  async listMyOrders(params?: {
    status?: OrderStatus;
    page?: number;
    page_size?: number;
  }): Promise<OrderListResponse> {
    return apiFetch<OrderListResponse>("/marketplace/orders", { query: params });
  },

  async getOrder(orderId: string): Promise<OrderResponse> {
    return apiFetch<OrderResponse>(`/marketplace/orders/${orderId}`);
  },

  async createOrder(payload: OrderCreateRequest): Promise<OrderResponse> {
    return apiFetch<OrderResponse>("/marketplace/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async cancelOrder(orderId: string, reason?: string): Promise<OrderResponse> {
    return apiFetch<OrderResponse>(`/marketplace/orders/${orderId}/cancel`, {
      method: "POST",
      query: { reason },
    });
  },
};

// Supplier-facing API (supplier role only)
export const supplierApi = {
  async createProduct(payload: {
    category_id: string;
    name: string;
    name_hi?: string;
    description: string;
    brand?: string;
    price: string;
    mrp?: string;
    unit?: string;
    min_order_qty?: number;
    stock_quantity?: number;
    low_stock_threshold?: number;
    image_url?: string;
    certifications?: string[];
    active_ingredient?: string;
    concentration?: string;
    linked_disease_slug?: string;
    suitable_crops?: string[];
  }): Promise<ProductResponse> {
    return apiFetch<ProductResponse>("/supplier/products", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async listOrders(params?: {
    status?: OrderStatus;
    page?: number;
    page_size?: number;
  }): Promise<OrderListResponse> {
    return apiFetch<OrderListResponse>("/supplier/orders", { query: params });
  },

  async updateOrderStatus(
    orderId: string,
    payload: {
      status: "confirm" | "pack" | "ship" | "deliver" | "cancel";
      tracking_number?: string;
      carrier?: string;
    },
  ): Promise<OrderResponse> {
    return apiFetch<OrderResponse>(`/supplier/orders/${orderId}/status`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
};
