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
  Camera,
  CloudRain,
  Satellite,
  Stethoscope,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { insuranceApi } from "@/lib/api/insurance";
import type { InsuranceClaim } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatINR, formatDate, formatDateTime } from "@/lib/utils";

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

const EVIDENCE_ICONS = {
  ndvi_drop: Satellite,
  disease_report: Stethoscope,
  weather_alert: CloudRain,
  officer_inspection: ShieldCheck,
  photo_evidence: Camera,
  yield_data: FileText,
  bank_document: FileText,
} as const;

export default function ClaimDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const claimId = params?.id as string;

  const [claim, setClaim] = useState<InsuranceClaim | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || !claimId) return;
    loadClaim();
  }, [isAuthenticated, claimId]);

  async function loadClaim() {
    try {
      const claimData = await insuranceApi.getClaim(claimId);
      setClaim(claimData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load claim");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleWithdraw() {
    if (!claim) return;
    if (!confirm("Are you sure you want to withdraw this claim? This cannot be undone.")) return;
    try {
      const updated = await insuranceApi.withdrawClaim(claim.id);
      setClaim(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to withdraw claim");
    }
  }

  if (authLoading || !isAuthenticated || isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error && !claim) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <p className="text-sm font-medium text-slate-900">Claim not found</p>
            <p className="mt-1 text-xs text-slate-500">{error}</p>
            <Link href="/dashboard/insurance">
              <Button className="mt-4">Back to Insurance</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!claim) return null;

  const badge = CLAIM_STATUS_BADGE[claim.status as keyof typeof CLAIM_STATUS_BADGE];
  const BadgeIcon = badge.icon;
  const canWithdraw = !["approved", "payout_disbursed", "withdrawn"].includes(claim.status);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/insurance" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to insurance
          </Link>
          <h1 className="text-lg font-bold text-slate-900">Claim Detail</h1>
          <div className="w-24" />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Status banner */}
        <div className={`mb-6 flex items-center gap-3 rounded-md border p-4 ${badge.color}`}>
          <BadgeIcon className="h-6 w-6 flex-shrink-0" />
          <div className="flex-1">
            <p className="font-semibold">{badge.label}</p>
            <p className="text-sm opacity-80">
              Claim {claim.claim_number}
              {claim.submitted_at && ` · Submitted ${formatDateTime(claim.submitted_at)}`}
            </p>
          </div>
          {canWithdraw && (
            <Button variant="ghost" size="sm" onClick={handleWithdraw}>
              Withdraw
            </Button>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left: Claim details + evidence */}
          <div className="space-y-6 lg:col-span-2">
            {/* Claim info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Claim Information</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <InfoRow label="Claim Number" value={claim.claim_number} mono />
                  <InfoRow
                    label="Claim Type"
                    value={claim.claim_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  />
                  <InfoRow label="Date of Loss" value={formatDate(claim.loss_date)} />
                  <InfoRow label="Estimated Loss" value={`${claim.estimated_loss_pct}%`} />
                  <InfoRow label="Claimed Amount" value={formatINR(claim.claimed_amount)} />
                  {claim.approved_amount !== null && (
                    <InfoRow
                      label="Approved Amount"
                      value={formatINR(claim.approved_amount)}
                      highlight
                    />
                  )}
                  {claim.payout_transaction_id && (
                    <InfoRow label="Payout Ref" value={claim.payout_transaction_id} mono />
                  )}
                  {claim.payout_date && (
                    <InfoRow label="Payout Date" value={formatDateTime(claim.payout_date)} />
                  )}
                </div>

                <div className="mt-4">
                  <p className="text-xs text-slate-500">Loss Description</p>
                  <p className="mt-1 text-sm text-slate-700 whitespace-pre-wrap">
                    {claim.loss_description}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Evidence */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldCheck className="h-5 w-5 text-primary" />
                  Evidence ({claim.evidence.length})
                </CardTitle>
                <CardDescription>
                  Auto-attached from platform modules + manually uploaded
                </CardDescription>
              </CardHeader>
              <CardContent>
                {claim.evidence.length === 0 ? (
                  <div className="text-center py-6">
                    <AlertCircle className="mx-auto h-8 w-8 text-slate-300" />
                    <p className="mt-2 text-sm text-slate-500">No evidence attached</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {claim.evidence.map((ev) => {
                      const Icon = EVIDENCE_ICONS[ev.evidence_type as keyof typeof EVIDENCE_ICONS] || FileText;
                      return (
                        <div
                          key={ev.id}
                          className={`rounded-md border p-4 ${
                            ev.is_auto_attached ? "border-primary/20 bg-primary/5" : "border-slate-200"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`flex h-10 w-10 items-center justify-center rounded-md ${
                              ev.is_auto_attached ? "bg-primary-100 text-primary" : "bg-slate-100 text-slate-600"
                            }`}>
                              <Icon className="h-5 w-5" />
                            </div>
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <h4 className="font-semibold text-slate-900">{ev.title}</h4>
                                {ev.is_auto_attached ? (
                                  <span className="rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary">
                                    Auto-Attached
                                  </span>
                                ) : (
                                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                                    Manual
                                  </span>
                                )}
                              </div>
                              <p className="mt-1 text-sm text-slate-600">{ev.description}</p>
                              <p className="mt-1 text-xs text-slate-400">
                                {formatDateTime(ev.evidence_date)} · Source: {ev.source_module}
                              </p>

                              {/* Snapshot data */}
                              {ev.snapshot_data && Object.keys(ev.snapshot_data).length > 0 && (
                                <div className="mt-2 rounded bg-slate-50 p-2">
                                  <p className="text-xs font-medium text-slate-500 mb-1">Snapshot:</p>
                                  <pre className="text-xs text-slate-600 overflow-x-auto">
                                    {JSON.stringify(ev.snapshot_data, null, 2)}
                                  </pre>
                                </div>
                              )}

                              {/* File download */}
                              {ev.file_download_url && (
                                <a
                                  href={ev.file_download_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                                >
                                  <Camera className="h-3 w-3" />
                                  View attachment
                                </a>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Review info */}
            {(claim.review_notes || claim.rejection_reason) && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Insurer Review</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {claim.reviewed_at && (
                    <InfoRow label="Reviewed On" value={formatDateTime(claim.reviewed_at)} />
                  )}
                  {claim.review_notes && (
                    <div>
                      <p className="text-xs text-slate-500">Review Notes</p>
                      <p className="mt-1 text-sm text-slate-700">{claim.review_notes}</p>
                    </div>
                  )}
                  {claim.rejection_reason && (
                    <div className="rounded-md bg-red-50 p-3">
                      <p className="text-xs font-medium text-red-900">Rejection Reason</p>
                      <p className="mt-1 text-sm text-red-700">{claim.rejection_reason}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right: Summary sidebar */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Claim Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="rounded-md bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Claimed Amount</p>
                  <p className="text-2xl font-bold text-slate-900">
                    {formatINR(claim.claimed_amount)}
                  </p>
                </div>
                {claim.approved_amount !== null && (
                  <div className="rounded-md bg-green-50 p-3">
                    <p className="text-xs text-green-700">Approved Amount</p>
                    <p className="text-2xl font-bold text-green-900">
                      {formatINR(claim.approved_amount)}
                    </p>
                  </div>
                )}
                <div className="space-y-2 text-sm">
                  <InfoRow
                    label="Evidence Count"
                    value={String(claim.evidence.length)}
                  />
                  <InfoRow
                    label="Auto-Attached"
                    value={String(claim.evidence.filter((e) => e.is_auto_attached).length)}
                  />
                  <InfoRow
                    label="Created"
                    value={formatDateTime(claim.created_at)}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Policy link */}
            {claim.policy && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Policy</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <InfoRow label="Policy Number" value={claim.policy.policy_number} mono />
                  {claim.policy.sum_insured && (
                    <InfoRow label="Sum Insured" value={formatINR(claim.policy.sum_insured)} />
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full mt-2"
                    onClick={() => router.push(`/dashboard/insurance/policies/${claim.policy_id}`)}
                  >
                    View Policy
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Status timeline */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Status Timeline</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <TimelineItem
                    label="Created"
                    date={claim.created_at}
                    done={true}
                  />
                  <TimelineItem
                    label="Submitted"
                    date={claim.submitted_at}
                    done={!!claim.submitted_at}
                  />
                  <TimelineItem
                    label="Under Review"
                    date={claim.reviewed_at}
                    done={["under_review", "evidence_requested", "approved", "rejected", "payout_disbursed"].includes(claim.status)}
                  />
                  <TimelineItem
                    label={claim.status === "approved" || claim.status === "payout_disbursed" ? "Approved" : "Resolved"}
                    date={claim.payout_date || claim.reviewed_at}
                    done={["approved", "rejected", "payout_disbursed"].includes(claim.status)}
                  />
                </div>
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
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`font-medium ${highlight ? "text-green-700" : "text-slate-900"} ${mono ? "font-mono text-xs" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function TimelineItem({
  label,
  date,
  done,
}: {
  label: string;
  date: string | null;
  done: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className={`flex h-6 w-6 items-center justify-center rounded-full ${
        done ? "bg-green-100 text-green-600" : "bg-slate-100 text-slate-400"
      }`}>
        {done ? <CheckCircle2 className="h-4 w-4" /> : <Clock className="h-3 w-3" />}
      </div>
      <div className="flex-1">
        <p className={`text-sm font-medium ${done ? "text-slate-900" : "text-slate-400"}`}>
          {label}
        </p>
        {date && (
          <p className="text-xs text-slate-500">{formatDateTime(date)}</p>
        )}
      </div>
    </div>
  );
}
