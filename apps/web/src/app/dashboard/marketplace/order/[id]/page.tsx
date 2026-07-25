"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Package,
  Loader2,
  Sprout,
  Truck,
  CheckCircle2,
  Clock,
  XCircle,
  MapPin,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { marketplaceApi, type Order } from "@/lib/api/marketplace";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatINR, formatDateTime } from "@/lib/utils";

const ORDER_STATUS_BADGE: Record<string, { label: string; color: string; icon: typeof Clock }> = {
  placed: { label: "Placed", color: "bg-blue-50 text-blue-700", icon: Clock },
  confirmed: { label: "Confirmed", color: "bg-blue-50 text-blue-700", icon: CheckCircle2 },
  packed: { label: "Packed", color: "bg-indigo-50 text-indigo-700", icon: Package },
  shipped: { label: "Shipped", color: "bg-purple-50 text-purple-700", icon: Truck },
  out_for_delivery: { label: "Out for Delivery", color: "bg-amber-50 text-amber-700", icon: Truck },
  delivered: { label: "Delivered", color: "bg-green-50 text-green-700", icon: CheckCircle2 },
  completed: { label: "Completed", color: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
  cancelled: { label: "Cancelled", color: "bg-red-50 text-red-700", icon: XCircle },
  returned: { label: "Returned", color: "bg-orange-50 text-orange-700", icon: XCircle },
};

export default function OrderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const orderId = params?.id as string;
  const [order, setOrder] = useState<Order | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || !orderId) return;
    loadOrder();
  }, [isAuthenticated, orderId]);

  async function loadOrder() {
    try {
      const data = await marketplaceApi.getOrder(orderId);
      setOrder(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load order");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCancel() {
    if (!order) return;
    if (!confirm("Are you sure you want to cancel this order?")) return;
    try {
      const updated = await marketplaceApi.cancelOrder(order.id);
      setOrder(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel order");
    }
  }

  if (authLoading || !isAuthenticated || isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <p className="text-sm font-medium text-slate-900">Order not found</p>
            <p className="mt-1 text-xs text-slate-500">{error}</p>
            <Link href="/dashboard/marketplace">
              <Button className="mt-4">Back to Marketplace</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  const badge = ORDER_STATUS_BADGE[order.status] || { label: order.status, color: "bg-slate-100 text-slate-700", icon: Clock };
  const BadgeIcon = badge.icon;
  const canCancel = ["placed", "confirmed", "packed"].includes(order.status);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/marketplace" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to marketplace
          </Link>
          <h1 className="text-lg font-bold text-slate-900">Order Detail</h1>
          <div className="w-24" />
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Status banner */}
        <div className={`mb-6 flex items-center gap-3 rounded-md border p-4 ${badge.color}`}>
          <BadgeIcon className="h-6 w-6 flex-shrink-0" />
          <div className="flex-1">
            <p className="font-semibold">{badge.label}</p>
            <p className="text-sm opacity-80">
              Order {order.order_number} · Placed {order.placed_at ? formatDateTime(order.placed_at) : formatDateTime(order.created_at)}
            </p>
          </div>
          {canCancel && (
            <Button variant="ghost" size="sm" onClick={handleCancel}>
              Cancel Order
            </Button>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left: Items */}
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Order Items ({order.items.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {order.items.map((item) => (
                    <div key={item.id} className="flex items-start gap-3 rounded-md border border-slate-200 p-3">
                      <div className="h-16 w-16 flex-shrink-0 rounded-md bg-slate-100 flex items-center justify-center">
                        {item.product_image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={item.product_image_url} alt={item.product_name} className="h-full w-full rounded-md object-cover" />
                        ) : (
                          <Package className="h-6 w-6 text-slate-300" />
                        )}
                      </div>
                      <div className="flex-1">
                        <h4 className="font-medium text-slate-900 text-sm">{item.product_name}</h4>
                        <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
                          <span>Qty: {item.quantity}</span>
                          <span>Price: {formatINR(item.unit_price)}</span>
                          <span className="font-semibold text-slate-700">Total: {formatINR(item.total_price)}</span>
                        </div>
                        <div className="mt-1">
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 capitalize">
                            {item.fulfillment_status}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right: Summary */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Order Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Subtotal</span>
                  <span className="font-medium text-slate-900">{formatINR(order.subtotal)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Shipping</span>
                  <span className="font-medium text-slate-900">
                    {order.shipping_cost === 0 ? "FREE" : formatINR(order.shipping_cost)}
                  </span>
                </div>
                <div className="border-t border-slate-100 pt-2 flex justify-between">
                  <span className="font-semibold text-slate-900">Total</span>
                  <span className="text-xl font-bold text-primary">{formatINR(order.total_amount)}</span>
                </div>
                <div className="pt-2 text-xs text-slate-500">
                  Payment: <span className="font-medium capitalize">{order.payment_status}</span>
                </div>
              </CardContent>
            </Card>

            {/* Shipping address */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <MapPin className="h-5 w-5 text-primary" />
                  Shipping Address
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-1">
                <p className="font-medium text-slate-900">{order.shipping_name}</p>
                <p className="text-slate-600">{order.shipping_phone}</p>
                <p className="text-slate-600">{order.shipping_address_line1}</p>
                {order.shipping_address_line2 && <p className="text-slate-600">{order.shipping_address_line2}</p>}
                {order.shipping_village && <p className="text-slate-600">{order.shipping_village}</p>}
                <p className="text-slate-600">{order.shipping_district}, {order.shipping_state} - {order.shipping_pincode}</p>
              </CardContent>
            </Card>

            {/* Timeline */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Status Timeline</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <TimelineItem label="Order Placed" date={order.placed_at || order.created_at} done={true} />
                  <TimelineItem label="Confirmed" date={null} done={["confirmed", "packed", "shipped", "out_for_delivery", "delivered", "completed"].includes(order.status)} />
                  <TimelineItem label="Shipped" date={null} done={["shipped", "out_for_delivery", "delivered", "completed"].includes(order.status)} />
                  <TimelineItem label="Delivered" date={order.delivered_at} done={["delivered", "completed"].includes(order.status)} />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

function TimelineItem({ label, date, done }: { label: string; date: string | null; done: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`flex h-6 w-6 items-center justify-center rounded-full ${done ? "bg-green-100 text-green-600" : "bg-slate-100 text-slate-400"}`}>
        {done ? <CheckCircle2 className="h-4 w-4" /> : <Clock className="h-3 w-3" />}
      </div>
      <div>
        <p className={`text-sm font-medium ${done ? "text-slate-900" : "text-slate-400"}`}>{label}</p>
        {date && <p className="text-xs text-slate-500">{formatDateTime(date)}</p>}
      </div>
    </div>
  );
}
