"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ShieldCheck,
  Loader2,
  Sprout,
  Plus,
  CheckCircle2,
  MapPin,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { insuranceApi } from "@/lib/api/insurance";
import { plotApi } from "@/lib/api/plots";
import type {
  InsuranceProductListResponse,
  PlotListResponse,
  PremiumEstimate,
  InsurancePolicy,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatINR, formatDate } from "@/lib/utils";

export default function InsurancePoliciesPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [plots, setPlots] = useState<PlotListResponse | null>(null);
  const [selectedPlotId, setSelectedPlotId] = useState<string | null>(null);
  const [products, setProducts] = useState<InsuranceProductListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Enrollment state
  const [enrollingProductId, setEnrollingProductId] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<PremiumEstimate | null>(null);
  const [bankAccount, setBankAccount] = useState("");
  const [bankIfsc, setBankIfsc] = useState("");
  const [isEnrolling, setIsEnrolling] = useState(false);
  const [enrolledPolicy, setEnrolledPolicy] = useState<InsurancePolicy | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadPlots();
  }, [isAuthenticated]);

  async function loadPlots() {
    try {
      const plotsResp = await plotApi.listMyPlots(1, 100);
      setPlots(plotsResp);
      if (plotsResp.plots.length > 0) {
        setSelectedPlotId(plotsResp.plots[0].id);
      } else {
        setIsLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plots");
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedPlotId) return;
    loadProducts();
  }, [selectedPlotId]);

  async function loadProducts() {
    if (!selectedPlotId) return;
    setIsLoading(true);
    setError(null);
    try {
      const productsResp = await insuranceApi.getProductsForPlot(selectedPlotId);
      setProducts(productsResp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load products");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleEnrollClick(productId: string) {
    if (!selectedPlotId) return;
    setEnrollingProductId(productId);
    setEstimate(null);
    setEnrolledPolicy(null);
    try {
      const est = await insuranceApi.estimatePremium(productId, selectedPlotId);
      setEstimate(est);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to estimate premium");
    }
  }

  async function handleConfirmEnroll() {
    if (!enrollingProductId || !selectedPlotId || !estimate) return;
    setIsEnrolling(true);
    setError(null);
    try {
      const policy = await insuranceApi.enrollPolicy({
        product_id: enrollingProductId,
        plot_id: selectedPlotId,
        bank_account_number: bankAccount || undefined,
        bank_ifsc: bankIfsc || undefined,
      });
      setEnrolledPolicy(policy);
      setEnrollingProductId(null);
      setEstimate(null);
      setBankAccount("");
      setBankIfsc("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enroll");
    } finally {
      setIsEnrolling(false);
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
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/insurance" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to insurance
          </Link>
          <h1 className="text-lg font-bold text-slate-900">Available Policies</h1>
          <div className="w-24" />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Plot selector */}
        {plots && plots.plots.length > 0 && (
          <Card className="mb-6">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-center gap-3">
                <MapPin className="h-5 w-5 text-primary" />
                <select
                  value={selectedPlotId || ""}
                  onChange={(e) => setSelectedPlotId(e.target.value)}
                  className="flex h-10 flex-1 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  {plots.plots.map((plot) => (
                    <option key={plot.id} value={plot.id}>
                      {plot.nickname || `Plot ${plot.survey_number}`} — {plot.village}, {plot.district}, {plot.state}
                    </option>
                  ))}
                </select>
              </div>
            </CardContent>
          </Card>
        )}

        {plots && plots.plots.length === 0 && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <MapPin className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">No plots registered</p>
              <Button onClick={() => router.push("/dashboard/plots/register")} className="mt-4">
                Register a Plot
              </Button>
            </CardContent>
          </Card>
        )}

        {error && (
          <Card className="mb-6 border-red-200">
            <CardContent className="p-4">
              <p className="text-sm text-red-600">{error}</p>
            </CardContent>
          </Card>
        )}

        {/* Enrolled success */}
        {enrolledPolicy && (
          <Card className="mb-6 border-green-200 bg-green-50">
            <CardContent className="p-6 text-center">
              <CheckCircle2 className="mx-auto h-12 w-12 text-green-600" />
              <p className="mt-3 text-lg font-bold text-slate-900">Policy Enrolled!</p>
              <p className="mt-1 text-sm text-slate-600">
                Policy number: <strong>{enrolledPolicy.policy_number}</strong>
              </p>
              <p className="text-sm text-slate-600">
                Premium to pay: <strong>{formatINR(enrolledPolicy.premium_amount)}</strong>
              </p>
              <div className="mt-4 flex justify-center gap-3">
                <Button onClick={() => router.push(`/dashboard/insurance/policies/${enrolledPolicy.id}`)}>
                  View Policy & Pay Premium
                </Button>
                <Button variant="secondary" onClick={() => setEnrolledPolicy(null)}>
                  Continue Browsing
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Products */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : products && products.products.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {products.products.map((product) => (
              <Card key={product.id}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base">{product.crop_name}</CardTitle>
                      <CardDescription>
                        {product.season.charAt(0).toUpperCase() + product.season.slice(1)} {product.season_year} · {product.state}
                      </CardDescription>
                    </div>
                    <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary uppercase">
                      {product.product_type}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-slate-500">Sum Insured/ha</p>
                      <p className="font-semibold text-slate-900">{formatINR(product.sum_insured_per_ha)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Farmer Premium</p>
                      <p className="font-semibold text-slate-900">
                        {(product.farmer_premium_rate * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Coverage</p>
                      <p className="font-medium text-slate-700 text-xs">
                        {formatDate(product.coverage_start_date)} — {formatDate(product.coverage_end_date)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Insurer</p>
                      <p className="font-medium text-slate-700 text-xs">{product.insurer_name}</p>
                    </div>
                  </div>

                  {enrollingProductId === product.id && estimate ? (
                    <div className="rounded-md bg-slate-50 p-4 space-y-3">
                      <h4 className="text-sm font-semibold text-slate-900">Premium Estimate</h4>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div>
                          <p className="text-xs text-slate-500">Plot Area</p>
                          <p className="font-medium">{Number(estimate.area_ha).toFixed(4)} ha</p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-500">Sum Insured</p>
                          <p className="font-medium">{formatINR(estimate.sum_insured)}</p>
                        </div>
                        <div className="col-span-2 border-t border-slate-200 pt-2">
                          <p className="text-xs text-slate-500">Premium to Pay</p>
                          <p className="text-xl font-bold text-primary">
                            {formatINR(estimate.premium_amount)}
                          </p>
                          <p className="text-xs text-slate-500">
                            ({estimate.farmer_premium_rate_pct}% of sum insured)
                          </p>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="bank_account">Bank Account Number (for payout)</Label>
                        <Input
                          id="bank_account"
                          placeholder="e.g., 12345678901"
                          value={bankAccount}
                          onChange={(e) => setBankAccount(e.target.value)}
                          maxLength={30}
                        />
                        <Label htmlFor="bank_ifsc">Bank IFSC Code</Label>
                        <Input
                          id="bank_ifsc"
                          placeholder="e.g., SBIN0001234"
                          value={bankIfsc}
                          onChange={(e) => setBankIfsc(e.target.value)}
                          maxLength={15}
                        />
                        <p className="text-xs text-slate-500">
                          Bank details are required for claim payouts (DBT). You can also provide them later.
                        </p>
                      </div>

                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEnrollingProductId(null);
                            setEstimate(null);
                          }}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleConfirmEnroll}
                          disabled={isEnrolling}
                        >
                          {isEnrolling ? (
                            <><Loader2 className="h-4 w-4 animate-spin" /> Enrolling...</>
                          ) : (
                            <>Confirm Enrollment</>
                          )}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      onClick={() => handleEnrollClick(product.id)}
                    >
                      <Plus className="h-4 w-4" />
                      Enroll & Estimate Premium
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          !isLoading && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <ShieldCheck className="h-12 w-12 text-slate-300" />
                <p className="mt-3 text-sm font-medium text-slate-900">
                  No insurance products available
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  No PMFBY products found for the selected plot&apos;s state.
                  Try registering a plot in a different state.
                </p>
              </CardContent>
            </Card>
          )
        )}
      </main>
    </div>
  );
}
