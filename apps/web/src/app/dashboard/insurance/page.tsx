"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ShieldCheck,
  Plus,
  FileText,
  Loader2,
  Sprout,
  TrendingUp,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { insuranceApi } from "@/lib/api/insurance";
import type {
  InsuranceStats,
  PolicyListResponse,
  ClaimListResponse,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDate, formatDateTime, formatINR } from "@/lib/utils";

const POLICY_STATUS_BADGE = {
  pending: { label: "Pending Payment", color: "bg-amber-50 text-amber-700" },
  active: { label: "Active", color: "bg-green-50 text-green-700" },
  expired: { label: "Expired", color: "bg-slate-100 text-slate-600" },
  cancelled: { label: "Cancelled", color: "bg-red-50 text-red-700" },
} as const;

const CLAIM_STATUS_BADGE = {
  draft: { label: "Draft", color: "bg-slate-100 text-slate-700", icon: FileText },
  submitted: { label: "Submitted", color: "bg-blue-50 text-blue-700", icon: Clock },
  under_review: { label: "Under Review", color: "bg-blue-50 text-blue-700", icon: Clock },
  evidence_requested: { label: "Evidence Requested", color: "bg-amber-50 text-amber-700", icon: AlertCircle },
  approved: { label: "Approved", color: "bg-green-50 text-green-700", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "bg-red-50 text-red-700", icon: XCircle },
  payout_disbursed: { label: "Payout Disbursed", color: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
  withdrawn: { label: "Withdrawn", color: "bg-slate-100 text-slate-500", icon: XCircle },
} as const;

export default function InsurancePage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [stats, setStats] = useState<InsuranceStats | null>(null);
  const [policies, setPolicies] = useState<PolicyListResponse | null>(null);
  const [claims, setClaims] = useState<ClaimListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    setError(null);
    try {
      const [statsResp, policiesResp, claimsResp] = await Promise.all([
        insuranceApi.getStats(),
        insuranceApi.listPolicies(),
        insuranceApi.listClaims(),
      ]);
      setStats(statsResp);
      setPolicies(policiesResp);
      setClaims(claimsResp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load insurance data");
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
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Link>
        </div>

        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Crop Insurance</h1>
            <p className="text-sm text-slate-600">
              PMFBY policies, claims, and payouts — with auto-attached evidence
            </p>
          </div>
          <Button onClick={() => router.push("/dashboard/insurance/policies")}>
            <Plus className="h-4 w-4" />
            Browse Policies
          </Button>
        </div>

        {error && (
          <Card className="mb-6 border-red-200">
            <CardContent className="p-4">
              <p className="text-sm text-red-600">{error}</p>
              <Button variant="ghost" size="sm" onClick={loadData} className="mt-2">
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Stats */}
        {stats && (
          <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              icon={ShieldCheck}
              label="Active Policies"
              value={String(stats.active_policies)}
              sub={`${formatINR(stats.total_sum_insured)} coverage`}
              color="bg-primary-50 text-primary"
            />
            <StatCard
              icon={TrendingUp}
              label="Premium Paid"
              value={formatINR(stats.total_premium_paid)}
              sub={`${stats.total_policies} total policies`}
              color="bg-blue-50 text-blue-600"
            />
            <StatCard
              icon={Clock}
              label="Pending Claims"
              value={String(stats.pending_claims)}
              sub={`${stats.total_claims} total claims`}
              color="bg-amber-50 text-amber-600"
            />
            <StatCard
              icon={CheckCircle2}
              label="Approved Claims"
              value={String(stats.approved_claims)}
              sub={formatINR(stats.total_approved_amount) + " approved"}
              color="bg-green-50 text-green-600"
            />
          </div>
        )}

        {/* Active Policies */}
        <Card className="mb-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-primary" />
                  Your Policies
                </CardTitle>
                <CardDescription>Insurance policies you have enrolled in</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
              </div>
            ) : !policies || policies.policies.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-center">
                <ShieldCheck className="h-10 w-10 text-slate-300" />
                <p className="mt-2 text-sm text-slate-500">No policies yet</p>
                <Button
                  size="sm"
                  className="mt-3"
                  onClick={() => router.push("/dashboard/insurance/policies")}
                >
                  Browse Available Policies
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {policies.policies.slice(0, 5).map((policy) => {
                  const badge = POLICY_STATUS_BADGE[policy.status as keyof typeof POLICY_STATUS_BADGE];
                  return (
                    <div
                      key={policy.id}
                      className="flex items-center justify-between rounded-md border border-slate-200 p-4 hover:border-primary/30 cursor-pointer"
                      onClick={() => router.push(`/dashboard/insurance/policies/${policy.id}`)}
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-slate-900">
                            {policy.product?.crop_name || "Unknown crop"}
                          </h4>
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.color}`}>
                            {badge.label}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500">
                          {policy.policy_number} · {policy.product?.season?.charAt(0).toUpperCase() + policy.product?.season?.slice(1)} {policy.product?.season_year}
                        </p>
                        <div className="mt-1 flex gap-4 text-xs text-slate-600">
                          <span>Sum: <strong>{formatINR(policy.sum_insured)}</strong></span>
                          <span>Premium: <strong>{formatINR(policy.premium_amount)}</strong></span>
                          {policy.active_claims_count > 0 && (
                            <span className="text-amber-600 font-medium">
                              {policy.active_claims_count} active claim(s)
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {policies.policies.length > 5 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full"
                    onClick={() => router.push("/dashboard/insurance/policies")}
                  >
                    View all {policies.total} policies
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Claims */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Your Claims
            </CardTitle>
            <CardDescription>Insurance claims you have filed</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
              </div>
            ) : !claims || claims.claims.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-center">
                <FileText className="h-10 w-10 text-slate-300" />
                <p className="mt-2 text-sm text-slate-500">No claims filed yet</p>
                <p className="text-xs text-slate-400">
                  File a claim when you experience crop loss on an insured plot
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {claims.claims.slice(0, 5).map((claim) => {
                  const badge = CLAIM_STATUS_BADGE[claim.status as keyof typeof CLAIM_STATUS_BADGE];
                  const Icon = badge.icon;
                  return (
                    <div
                      key={claim.id}
                      className="flex items-center justify-between rounded-md border border-slate-200 p-4 hover:border-primary/30 cursor-pointer"
                      onClick={() => router.push(`/dashboard/insurance/claims/${claim.id}`)}
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-slate-900">
                            {claim.claim_number}
                          </h4>
                          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${badge.color}`}>
                            <Icon className="h-3 w-3" />
                            {badge.label}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 capitalize">
                          {claim.claim_type.replace(/_/g, " ")} · Loss: {formatDate(claim.loss_date)}
                        </p>
                        <div className="mt-1 flex gap-4 text-xs text-slate-600">
                          <span>Claimed: <strong>{formatINR(claim.claimed_amount)}</strong></span>
                          {claim.approved_amount && (
                            <span className="text-green-600">
                              Approved: <strong>{formatINR(claim.approved_amount)}</strong>
                            </span>
                          )}
                          <span>{claim.evidence.length} evidence items</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
                {claims.claims.length > 5 && (
                  <Button variant="ghost" size="sm" className="w-full">
                    View all {claims.total} claims
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
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
          <span className="hidden text-sm font-medium text-slate-700 sm:block">
            {user?.full_name}
          </span>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            Logout
          </Button>
        </div>
      </div>
    </header>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color,
}: {
  icon: typeof ShieldCheck;
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-md ${color}`}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xl font-bold text-slate-900 truncate">{value}</p>
            <p className="text-xs text-slate-600">{label}</p>
            <p className="text-xs text-slate-400 truncate">{sub}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
