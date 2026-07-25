"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Search,
  Package,
  ShoppingCart,
  Loader2,
  Sprout,
  ShieldCheck,
  TrendingUp,
  Clock,
  CheckCircle2,
  Store,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { marketplaceApi, type Product, type MarketplaceStats, type OrderListResponse } from "@/lib/api/marketplace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatINR, formatDateTime } from "@/lib/utils";

const ORDER_STATUS_BADGE: Record<string, { label: string; color: string }> = {
  draft: { label: "Draft", color: "bg-slate-100 text-slate-700" },
  placed: { label: "Placed", color: "bg-blue-50 text-blue-700" },
  confirmed: { label: "Confirmed", color: "bg-blue-50 text-blue-700" },
  packed: { label: "Packed", color: "bg-indigo-50 text-indigo-700" },
  shipped: { label: "Shipped", color: "bg-purple-50 text-purple-700" },
  out_for_delivery: { label: "Out for Delivery", color: "bg-amber-50 text-amber-700" },
  delivered: { label: "Delivered", color: "bg-green-50 text-green-700" },
  completed: { label: "Completed", color: "bg-emerald-50 text-emerald-700" },
  cancelled: { label: "Cancelled", color: "bg-red-50 text-red-700" },
  returned: { label: "Returned", color: "bg-orange-50 text-orange-700" },
};

export default function MarketplacePage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [products, setProducts] = useState<Product[]>([]);
  const [stats, setStats] = useState<MarketplaceStats | null>(null);
  const [orders, setOrders] = useState<OrderListResponse | null>(null);
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadData();
  }, [isAuthenticated]);

  async function loadData() {
    setIsLoading(true);
    try {
      const [productsResp, statsResp, ordersResp] = await Promise.all([
        marketplaceApi.listProducts({ page: 1, page_size: 12 }),
        marketplaceApi.getStats(),
        marketplaceApi.listMyOrders(),
      ]);
      setProducts(productsResp.products);
      setStats(statsResp);
      setOrders(ordersResp);
    } catch (err) {
      // Stats and orders require auth — products are public
      try {
        const productsResp = await marketplaceApi.listProducts({ page: 1, page_size: 12 });
        setProducts(productsResp.products);
      } catch (e) {
        setError("Failed to load products");
      }
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSearch() {
    setIsLoading(true);
    try {
      const resp = await marketplaceApi.listProducts({ search, page: 1, page_size: 12 });
      setProducts(resp.products);
    } catch {
      setError("Search failed");
    } finally {
      setIsLoading(false);
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <Header />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6">
          <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Link>
        </div>

        <div className="mb-8">
          <h1 className="text-2xl font-bold text-slate-900">Agricultural Marketplace</h1>
          <p className="text-sm text-slate-600">
            Order seeds, fertilizers, pesticides, and machinery from verified suppliers
          </p>
        </div>

        {/* Stats */}
        {stats && (
          <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard icon={Package} label="Products Ordered" value={String(stats.total_products)} color="bg-primary-50 text-primary" />
            <StatCard icon={ShoppingCart} label="Total Orders" value={String(stats.total_orders)} color="bg-blue-50 text-blue-600" />
            <StatCard icon={Clock} label="Pending Orders" value={String(stats.pending_orders)} color="bg-amber-50 text-amber-600" />
            <StatCard icon={TrendingUp} label="Total Spent" value={formatINR(stats.total_spent)} color="bg-green-50 text-green-600" />
          </div>
        )}

        {/* Search */}
        <Card className="mb-6">
          <CardContent className="p-4">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  placeholder="Search for seeds, fertilizers, pesticides..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  className="pl-10"
                />
              </div>
              <Button onClick={handleSearch}>
                <Search className="h-4 w-4" />
                Search
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Recent orders */}
        {orders && orders.orders.length > 0 && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShoppingCart className="h-5 w-5 text-primary" />
                Recent Orders
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {orders.orders.slice(0, 3).map((order) => {
                  const badge = ORDER_STATUS_BADGE[order.status] || { label: order.status, color: "bg-slate-100 text-slate-700" };
                  return (
                    <div
                      key={order.id}
                      className="flex items-center justify-between rounded-md border border-slate-200 p-3 hover:border-primary/30 cursor-pointer"
                      onClick={() => router.push(`/dashboard/marketplace/order/${order.id}`)}
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-medium text-slate-900">{order.order_number}</span>
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.color}`}>{badge.label}</span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          {order.items.length} item(s) · {formatDateTime(order.created_at)}
                        </p>
                      </div>
                      <span className="font-semibold text-slate-900">{formatINR(order.total_amount)}</span>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Products grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : products.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Package className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">No products found</p>
              <p className="mt-1 text-xs text-slate-500">
                Try a different search term or check back later as suppliers list products.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {products.map((product) => (
              <ProductCard key={product.id} product={product} onClick={() => router.push(`/dashboard/marketplace/product/${product.id}`)} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function Header() {
  const { user, logout } = useAuthStore();
  const router = useRouter();
  const handleLogout = async () => {
    await logout();
    router.push("/");
  };
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <Sprout className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-bold text-slate-900">KrishiSetu</span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm font-medium text-slate-700 sm:block">{user?.full_name}</span>
          <Button variant="ghost" size="sm" onClick={handleLogout}>Logout</Button>
        </div>
      </div>
    </header>
  );
}

function StatCard({ icon: Icon, label, value, color }: { icon: typeof Package; label: string; value: string; color: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-md ${color}`}>
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xl font-bold text-slate-900">{value}</p>
            <p className="text-xs text-slate-600">{label}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ProductCard({ product, onClick }: { product: Product; onClick: () => void }) {
  return (
    <Card className="cursor-pointer overflow-hidden transition-all hover:shadow-md hover:border-primary/30" onClick={onClick}>
      <div className="h-40 bg-slate-100 flex items-center justify-center">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" />
        ) : (
          <Package className="h-12 w-12 text-slate-300" />
        )}
      </div>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-slate-900 text-sm line-clamp-2">{product.name}</h3>
          {product.discount_pct > 0 && (
            <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs font-bold text-red-600 whitespace-nowrap">
              {product.discount_pct}% OFF
            </span>
          )}
        </div>
        {product.brand && <p className="text-xs text-slate-500 mt-1">by {product.brand}</p>}
        {product.supplier_name && (
          <p className="text-xs text-slate-500 mt-0.5">Sold by {product.supplier_name}</p>
        )}
        <div className="mt-2 flex items-center gap-2">
          <span className="text-lg font-bold text-slate-900">{formatINR(product.price)}</span>
          {product.mrp && product.mrp > product.price && (
            <span className="text-xs text-slate-400 line-through">{formatINR(product.mrp)}</span>
          )}
          <span className="text-xs text-slate-500">/ {product.unit}</span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          {product.is_in_stock ? (
            <span className="inline-flex items-center gap-1 text-xs text-green-600">
              <CheckCircle2 className="h-3 w-3" /> In Stock ({product.stock_quantity})
            </span>
          ) : (
            <span className="text-xs text-red-600">Out of Stock</span>
          )}
        </div>
        {product.certifications && product.certifications.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {product.certifications.slice(0, 2).map((cert) => (
              <span key={cert} className="rounded bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary">
                <ShieldCheck className="inline h-3 w-3" /> {cert}
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
