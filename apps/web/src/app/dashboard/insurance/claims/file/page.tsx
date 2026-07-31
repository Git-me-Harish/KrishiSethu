"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  Loader2,
  Sprout,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Camera,
  CloudRain,
  Satellite,
  Stethoscope,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { insuranceApi } from "@/lib/api/insurance";
import type { InsuranceClaim, InsurancePolicy } from "@/lib/api/types";
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

const CLAIM_TYPES = [
  { value: "localized_risk", label: "Localized Risk (individual farm loss — hail, pest, etc.)" },
  { value: "widespread_risk", label: "Widespread Risk (district-level yield shortfall)" },
  { value: "preventive_sowing", label: "Preventive Sowing (germination failure)" },
  { value: "mid_season_adversity", label: "Mid-Season Adversity (drought/flood mid-season)" },
  { value: "post_harvest", label: "Post-Harvest Loss (during storage/transport)" },
];

const EVIDENCE_ICONS = {
  ndvi_drop: Satellite,
  disease_report: Stethoscope,
  weather_alert: CloudRain,
  officer_inspection: ShieldCheck,
  photo_evidence: Camera,
  yield_data: FileText,
  bank_document: FileText,
} as const;

export default function FileClaimPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const policyId = params?.id as string;

  const [policy, setPolicy] = useState<InsurancePolicy | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [claimType, setClaimType] = useState("localized_risk");
  const [lossDate, setLossDate] = useState(new Date().toISOString().slice(0, 10));
  const [lossDescription, setLossDescription] = useState("");
  const [estimatedLossPct, setEstimatedLossPct] = useState("");
  const [bankAccount, setBankAccount] = useState("");
  const [bankIfsc, setBankIfsc] = useState("");

  const [claim, setClaim] = useState<InsuranceClaim | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || !policyId) return;
    loadPolicy();
  }, [isAuthenticated, policyId]);

  async function loadPolicy() {
    try {
      const policyData = await insuranceApi.getPolicy(policyId);
      setPolicy(policyData);
      if (policyData.bank_account_number) setBankAccount(policyData.bank_account_number);
      if (policyData.bank_ifsc) setBankIfsc(policyData.bank_ifsc);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load policy");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCreateClaim() {
    if (!policy) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const created = await insuranceApi.createClaim({
        policy_id: policy.id,
        claim_type: claimType,
        loss_date: lossDate,
        loss_description: lossDescription,
        estimated_loss_pct: parseFloat(estimatedLossPct),
      });
      setClaim(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create claim");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSubmitClaim() {
    if (!claim) return;
    if (!bankAccount || !bankIfsc) {
      setError("Bank account and IFSC are required to submit the claim");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const submitted = await insuranceApi.submitClaim(claim.id, bankAccount, bankIfsc);
      setClaim(submitted);
      setTimeout(() => {
        router.push(`/dashboard/insurance/claims/${submitted.id}`);
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit claim");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (isLoading) {
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
          <Link
            href={policy ? `/dashboard/insurance/policies/${policy.id}` : "/dashboard/insurance"}
            className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to policy
          </Link>
          <h1 className="text-lg font-bold text-slate-900">File Insurance Claim</h1>
          <div className="w-24" />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <Card className="mb-6 border-red-200">
            <CardContent className="p-4">
              <p className="text-sm text-red-600">{error}</p>
            </CardContent>
          </Card>
        )}

        {policy && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-base">Policy Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs text-slate-500">Policy Number</p>
                  <p className="font-mono font-medium text-slate-900">{policy.policy_number}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Crop</p>
                  <p className="font-medium text-slate-900">{policy.product?.crop_name || "Unknown"}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Sum Insured</p>
                  <p className="font-semibold text-slate-900">{formatINR(policy.sum_insured)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Coverage Period</p>
                  <p className="font-medium text-slate-700 text-xs">
                    {formatDate(policy.coverage_start_date)} — {formatDate(policy.coverage_end_date)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {!claim && policy && (
          <Card>
            <CardHeader>
              <CardTitle>Claim Details</CardTitle>
              <CardDescription>
                Describe the crop loss you experienced. The platform will automatically
                attach evidence from NDVI monitoring, disease reports, and weather alerts.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="claim_type">Claim Type *</Label>
                <select
                  id="claim_type"
                  value={claimType}
                  onChange={(e) => setClaimType(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  {CLAIM_TYPES.map((ct) => (
                    <option key={ct.value} value={ct.value}>
                      {ct.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="loss_date">Date of Loss *</Label>
                <Input
                  id="loss_date"
                  type="date"
                  value={lossDate}
                  onChange={(e) => setLossDate(e.target.value)}
                  min={policy.coverage_start_date}
                  max={policy.coverage_end_date}
                />
                <p className="text-xs text-slate-500">Must be within the coverage period</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="loss_desc">Loss Description *</Label>
                <textarea
                  id="loss_desc"
                  value={lossDescription}
                  onChange={(e) => setLossDescription(e.target.value)}
                  placeholder="Describe what happened, when you noticed the loss, what percentage of the crop was affected, and any contributing factors (weather, disease, pests, etc.)"
                  className="flex min-h-[120px] w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                  maxLength={5000}
                />
                <p className="text-xs text-slate-500">
                  {lossDescription.length}/5000 characters (minimum 20)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="loss_pct">Estimated Loss Percentage *</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="loss_pct"
                    type="number"
                    min="0"
                    max="100"
                    step="1"
                    placeholder="e.g., 50"
                    value={estimatedLossPct}
                    onChange={(e) => setEstimatedLossPct(e.target.value)}
                    className="w-32"
                  />
                  <span className="text-sm text-slate-500">% of crop lost</span>
                </div>
                {estimatedLossPct && policy && (
                  <p className="text-xs text-slate-600">
                    Estimated claim amount:{" "}
                    <strong className="text-primary">
                      {formatINR(
                        Number(policy.sum_insured) * (parseFloat(estimatedLossPct || "0") / 100),
                      )}
                    </strong>
                  </p>
                )}
              </div>

              <Button
                onClick={handleCreateClaim}
                disabled={isSubmitting || !lossDescription || lossDescription.length < 20 || !estimatedLossPct}
                className="w-full"
              >
                {isSubmitting ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Creating draft & auto-attaching evidence...</>
                ) : (
                  <>Create Draft Claim</>
                )}
              </Button>
            </CardContent>
          </Card>
        )}

        {claim && (
          <div className="space-y-6">
            <Card className="border-green-200 bg-green-50">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                  <div>
                    <p className="font-semibold text-slate-900">
                      Draft claim created: {claim.claim_number}
                    </p>
                    <p className="text-sm text-slate-600">
                      The platform has auto-attached {claim.evidence.length} evidence item(s).
                      Review below and submit when ready.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertCircle className="h-5 w-5 text-primary" />
                  Auto-Attached Evidence
                </CardTitle>
                <CardDescription>
                  Automatically compiled from your plot&apos;s NDVI monitoring, disease reports, and weather alerts
                </CardDescription>
              </CardHeader>
              <CardContent>
                {claim.evidence.length === 0 ? (
                  <div className="text-center py-8">
                    <AlertCircle className="mx-auto h-10 w-10 text-slate-300" />
                    <p className="mt-2 text-sm text-slate-500">
                      No auto-evidence found for this plot in the 30 days before the loss date.
                    </p>
                    <p className="text-xs text-slate-400">
                      You can still submit the claim — the insurer will review based on your description.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {claim.evidence.map((ev) => {
                      const Icon = EVIDENCE_ICONS[ev.evidence_type as keyof typeof EVIDENCE_ICONS] || FileText;
                      return (
                        <div
                          key={ev.id}
                          className={`rounded-md border p-3 ${
                            ev.is_auto_attached ? "border-primary/20 bg-primary/5" : "border-slate-200"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`flex h-8 w-8 items-center justify-center rounded-md ${
                              ev.is_auto_attached ? "bg-primary-100 text-primary" : "bg-slate-100 text-slate-600"
                            }`}>
                              <Icon className="h-4 w-4" />
                            </div>
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <h4 className="text-sm font-semibold text-slate-900">{ev.title}</h4>
                                {ev.is_auto_attached && (
                                  <span className="rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary">
                                    Auto
                                  </span>
                                )}
                              </div>
                              <p className="mt-1 text-xs text-slate-600">{ev.description}</p>
                              <p className="mt-1 text-xs text-slate-400">
                                {formatDateTime(ev.evidence_date)} · Source: {ev.source_module}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Bank Details for Payout</CardTitle>
                <CardDescription>
                  Required for claim disbursement via DBT (Direct Benefit Transfer)
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="bank_account">Bank Account Number *</Label>
                  <Input
                    id="bank_account"
                    placeholder="e.g., 12345678901"
                    value={bankAccount}
                    onChange={(e) => setBankAccount(e.target.value)}
                    maxLength={30}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bank_ifsc">Bank IFSC Code *</Label>
                  <Input
                    id="bank_ifsc"
                    placeholder="e.g., SBIN0001234"
                    value={bankIfsc}
                    onChange={(e) => setBankIfsc(e.target.value)}
                    maxLength={15}
                  />
                </div>
              </CardContent>
            </Card>

            <div className="flex gap-3">
              <Button
                variant="ghost"
                onClick={() => {
                  setClaim(null);
                  setError(null);
                }}
              >
                Edit Details
              </Button>
              <Button
                onClick={handleSubmitClaim}
                disabled={isSubmitting || !bankAccount || !bankIfsc}
                className="flex-1"
              >
                {isSubmitting ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Submitting...</>
                ) : (
                  <>Submit Claim for Review</>
                )}
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
