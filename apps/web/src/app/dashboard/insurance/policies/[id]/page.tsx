"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ShieldCheck,
  Loader2,
  Sprout,
  FileText,
  CheckCircle2,
  CreditCard,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { insuranceApi } from "@/lib/api/insurance";
import type { InsurancePolicy, ClaimListResponse } from "@/lib/api/types";
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
import { formatINR, formatDate, formatDateTime } from "@/lib/utils";

const POLICY_STATUS_BADGE = {
  pending: { label: "Pending Payment", color: "bg-amber-50 text-amber-700" },
  active: { label: "Active", color: "bg-green-50 text-green-700" },
  expired: { label: "Expired", color: "bg-slate-100 text-slate-600" },
  cancelled: { label: "Cancelled", color: "bg-red-50 text-red-700" },
} as const;

const CLAIM_STATUS_BADGE = {
  draft: { label: "Draft", color: "bg-slate-100 text-slate-700" },
  submitted: { label: "Submitted", color: "bg-blue-50 text-blue-700" },
  under_review: { label: "Under Review", color: "bg-blue-50 text-blue-700" },
  evidence_requested: { label: "Evidence Requested", color: "bg-amber-50 text-amber-700" },
  approved: { label: "Approved", color: "bg-green-50 text-green-700" },
  rejected: { label: "Rejected", color: "bg-red-50 text-red-700" },
  payout_disbursed: { label: "Payout Disbursed", color: "bg-emerald-50 text-emerald-700" },
  withdrawn: { label: "Withdrawn", color: "bg-slate-100 text-slate-500" },
} as const;

export default function PolicyDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const policyId = params?.id as string;

  const [policy, setPolicy] = useState<InsurancePolicy | null>(null);
  const [claims, setClaims] = useState<ClaimListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Payment state
  const [paymentRef, setPaymentRef] = useState("");
  const [isPaying, setIsPaying] = useState(false);
  const [paySuccess, setPaySuccess] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || !policyId) return;
    loadData();
  }, [isAuthenticated, policyId]);

  async function loadData() {
    try {
      const [policyData, claimsData] = await Promise.all([
        insuranceApi.getPolicy(policyId),
        insuranceApi.listClaims(),
      ]);
      setPolicy(policyData);
      // Filter claims for this policy
      const policyClaims = {
        ...claimsData,
        claims: claimsData.claims.filter((c) => c.policy_id === policyId),
        total: claimsData.claims.filter((c) => c.policy_id === policyId).length,
      };
      setClaims(policyClaims);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load policy");
    } finally {
      setIsLoading(false);
    }
  }

  async function handlePayPremium() {
    if (!policy || !paymentRef) return;
    setIsPaying(true);
    setError(null);
    try {
      const updated = await insuranceApi.payPremium(policy.id, paymentRef);
      setPolicy(updated);
      setPaySuccess(true);
      setPaymentRef("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to process payment");
    } finally {
      setIsPaying(false);
    }
  }

  if (authLoading || !isAuthenticated || isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error && !policy) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <p className="text-sm font-medium text-slate-900">Policy not found</p>
            <p className="mt-1 text-xs text-slate-500">{error}</p>
            <Link href="/dashboard/insurance">
              <Button className="mt-4">Back to Insurance</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!policy) return null;

  const badge = POLICY_STATUS_BADGE[policy.status as keyof typeof POLICY_STATUS_BADGE];

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/insurance" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to insurance
          </Link>
          <h1 className="text-lg font-bold text-slate-900">Policy Detail</h1>
          <div className="w-24" />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <Card className="mb-6 border-red-200">
            <CardContent className="p-4">
              <p className="text-sm text-red-600">{error}</p>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left: Policy details */}
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <ShieldCheck className="h-5 w-5 text-primary" />
                      {policy.product?.crop_name || "Insurance Policy"}
                    </CardTitle>
                    <CardDescription>
                      {policy.product?.season?.charAt(0).toUpperCase() + policy.product?.season?.slice(1)} {policy.product?.season_year} · {policy.product?.state}
                    </CardDescription>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-sm font-medium ${badge.color}`}>
                    {badge.label}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <InfoRow label="Policy Number" value={policy.policy_number} mono />
                  <InfoRow label="Insurer" value={policy.product?.insurer_name || "N/A"} />
                  <InfoRow label="Crop" value={policy.product?.crop_name || "N/A"} />
                  <InfoRow label="Season" value={`${policy.product?.season || ""} ${policy.product?.season_year || ""}`} />
                  <InfoRow label="Sum Insured" value={formatINR(policy.sum_insured)} />
                  <InfoRow label="Area Insured" value={`${Number(policy.area_insured_ha).toFixed(4)} ha`} />
                  <InfoRow label="Premium Amount" value={formatINR(policy.premium_amount)} />
                  <InfoRow label="Premium Rate" value={`${(Number(policy.premium_rate) * 100).toFixed(1)}%`} />
                  <InfoRow label="Coverage Start" value={formatDate(policy.coverage_start_date)} />
                  <InfoRow label="Coverage End" value={formatDate(policy.coverage_end_date)} />
                  <InfoRow label="Enrolled On" value={formatDateTime(policy.created_at)} />
                  <InfoRow
                    label="Premium Paid"
                    value={policy.premium_paid ? formatDateTime(policy.premium_paid_at || "") : "Not paid"}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Claims on this policy */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <FileText className="h-5 w-5 text-primary" />
                    Claims ({claims?.total || 0})
                  </CardTitle>
                  {policy.status === "active" && (
                    <Button
                      size="sm"
                      onClick={() => router.push(`/dashboard/insurance/claims/file?policy=${policy.id}`)}
                    >
                      <FileText className="h-4 w-4" />
                      File New Claim
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {!claims || claims.claims.length === 0 ? (
                  <div className="text-center py-6">
                    <FileText className="mx-auto h-8 w-8 text-slate-300" />
                    <p className="mt-2 text-sm text-slate-500">No claims filed on this policy</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {claims.claims.map((claim) => {
                      const cBadge = CLAIM_STATUS_BADGE[claim.status as keyof typeof CLAIM_STATUS_BADGE];
                      return (
                        <div
                          key={claim.id}
                          className="flex items-center justify-between rounded-md border border-slate-200 p-3 hover:border-primary/30 cursor-pointer"
                          onClick={() => router.push(`/dashboard/insurance/claims/${claim.id}`)}
                        >
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-sm font-medium text-slate-900">
                                {claim.claim_number}
                              </span>
                              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cBadge.color}`}>
                                {cBadge.label}
                              </span>
                            </div>
                            <p className="text-xs text-slate-500 capitalize mt-1">
                              {claim.claim_type.replace(/_/g, " ")} · Loss: {formatDate(claim.loss_date)}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold text-slate-900">
                              {formatINR(claim.claimed_amount)}
                            </p>
                            <p className="text-xs text-slate-500">claimed</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Right: Payment */}
          <div className="space-y-6">
            {policy.status === "pending" && !paySuccess && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <CreditCard className="h-5 w-5 text-primary" />
                    Pay Premium
                  </CardTitle>
                  <CardDescription>
                    Pay the premium to activate your policy
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-md bg-primary-50 p-4 text-center">
                    <p className="text-xs text-slate-500">Premium Due</p>
                    <p className="text-3xl font-bold text-primary">
                      {formatINR(policy.premium_amount)}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="payment_ref">Payment Reference</Label>
                    <Input
                      id="payment_ref"
                      placeholder="Enter UPI/transaction ID"
                      value={paymentRef}
                      onChange={(e) => setPaymentRef(e.target.value)}
                    />
                    <p className="text-xs text-slate-500">
                      In production, this would integrate with UPI/Razorpay payment gateway.
                      For now, enter any reference to simulate payment.
                    </p>
                  </div>

                  <Button
                    onClick={handlePayPremium}
                    disabled={isPaying || !paymentRef}
                    className="w-full"
                  >
                    {isPaying ? (
                      <><Loader2 className="h-4 w-4 animate-spin" /> Processing...</>
                    ) : (
                      <>Pay {formatINR(policy.premium_amount)}</>
                    )}
                  </Button>
                </CardContent>
              </Card>
            )}

            {paySuccess && (
              <Card className="border-green-200 bg-green-50">
                <CardContent className="p-6 text-center">
                  <CheckCircle2 className="mx-auto h-12 w-12 text-green-600" />
                  <p className="mt-3 text-lg font-bold text-slate-900">Premium Paid!</p>
                  <p className="mt-1 text-sm text-slate-600">
                    Your policy is now active. You can file claims for crop losses.
                  </p>
                </CardContent>
              </Card>
            )}

            {policy.status === "active" && (
              <Card className="border-green-200 bg-green-50">
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    <CheckCircle2 className="h-8 w-8 text-green-600" />
                    <div>
                      <p className="font-semibold text-green-900">Policy Active</p>
                      <p className="text-xs text-green-700">
                        Coverage until {formatDate(policy.coverage_end_date)}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Bank details */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Bank Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <InfoRow
                  label="Account No."
                  value={policy.bank_account_number || "Not provided"}
                />
                <InfoRow
                  label="IFSC"
                  value={policy.bank_ifsc || "Not provided"}
                />
                <p className="text-xs text-slate-500 mt-2">
                  Bank details are required for claim payout via DBT.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

function InfoRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`font-medium text-slate-900 ${mono ? "font-mono text-xs" : ""}`}>
        {value}
      </p>
    </div>
  );
}
