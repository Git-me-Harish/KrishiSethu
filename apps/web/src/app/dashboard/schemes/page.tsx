"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  Loader2,
  Sprout,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
  Award,
  ExternalLink,
  Phone,
  MapPin,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { schemesApi, type GovtScheme, type SchemeApplication, type SchemeStats } from "@/lib/api/schemes";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatINR, formatDateTime } from "@/lib/utils";

const CATEGORY_LABELS: Record<string, string> = {
  income_support: "Income Support",
  crop_insurance: "Crop Insurance",
  credit: "Credit / Loan",
  input_subsidy: "Input Subsidy",
  equipment_subsidy: "Equipment Subsidy",
  irrigation: "Irrigation",
  soil_health: "Soil Health",
  market_support: "Market Support",
  pension: "Pension",
  other: "Other",
};

const STATUS_BADGE: Record<string, { label: string; color: string; icon: typeof Clock }> = {
  draft: { label: "Draft", color: "bg-slate-100 text-slate-700", icon: FileText },
  submitted: { label: "Submitted", color: "bg-blue-50 text-blue-700", icon: Clock },
  under_review: { label: "Under Review", color: "bg-blue-50 text-blue-700", icon: Clock },
  approved: { label: "Approved", color: "bg-green-50 text-green-700", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "bg-red-50 text-red-700", icon: XCircle },
  resubmission_requested: { label: "Resubmit", color: "bg-amber-50 text-amber-700", icon: Clock },
  withdrawn: { label: "Withdrawn", color: "bg-slate-100 text-slate-500", icon: XCircle },
  benefit_disbursed: { label: "Benefit Disbursed", color: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
};

export default function SchemesPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [schemes, setSchemes] = useState<GovtScheme[]>([]);
  const [stats, setStats] = useState<SchemeStats | null>(null);
  const [applications, setApplications] = useState<SchemeApplication[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all"); // all, eligible, applied

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
      const [schemesResp, statsResp, appsResp] = await Promise.all([
        schemesApi.listSchemes(),
        schemesApi.getStats(),
        schemesApi.listMyApplications(),
      ]);
      setSchemes(schemesResp.schemes);
      setStats(statsResp);
      setApplications(appsResp.applications);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load schemes");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleApply(schemeId: string) {
    try {
      const app = await schemesApi.createApplication(schemeId);
      // Reload to update has_applied status
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create application");
    }
  }

  const filteredSchemes = schemes.filter((s) => {
    if (filter === "eligible") return s.is_eligible === true && !s.has_applied;
    if (filter === "applied") return s.has_applied;
    return true;
  });

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
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
              <Sprout className="h-5 w-5 text-white" />
            </div>
            <span className="text-lg font-bold text-slate-900">KrishiSetu</span>
          </Link>
          <Button variant="ghost" size="sm" onClick={async () => { await useAuthStore.getState().logout(); router.push("/"); }}>
            Logout
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6">
          <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Link>
        </div>

        <div className="mb-8">
          <h1 className="text-2xl font-bold text-slate-900">Government Schemes</h1>
          <p className="text-sm text-slate-600">
            Discover schemes you are eligible for and apply in one click
          </p>
        </div>

        {/* Stats */}
        {stats && (
          <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard icon={Award} label="Available Schemes" value={String(stats.total_schemes_available)} color="bg-primary-50 text-primary" />
            <StatCard icon={CheckCircle2} label="Eligible Schemes" value={String(stats.eligible_schemes)} color="bg-green-50 text-green-600" />
            <StatCard icon={Clock} label="Pending Applications" value={String(stats.pending_applications)} color="bg-amber-50 text-amber-600" />
            <StatCard icon={TrendingUp} label="Approved" value={String(stats.approved_applications)} color="bg-emerald-50 text-emerald-600" />
          </div>
        )}

        {/* Filter */}
        <div className="mb-6 flex gap-2">
          {[
            { key: "all", label: "All Schemes" },
            { key: "eligible", label: "Eligible for Me" },
            { key: "applied", label: "Applied" },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                filter === f.key
                  ? "bg-primary text-white"
                  : "bg-white text-slate-700 border border-slate-200 hover:border-primary/30"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* My Applications */}
        {applications.length > 0 && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileText className="h-5 w-5 text-primary" />
                My Applications ({applications.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {applications.slice(0, 5).map((app) => {
                  const badge = STATUS_BADGE[app.status] || { label: app.status, color: "bg-slate-100 text-slate-700", icon: Clock };
                  const Icon = badge.icon;
                  return (
                    <div key={app.id} className="flex items-center justify-between rounded-md border border-slate-200 p-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-slate-900 text-sm">{app.scheme_name || "Unknown scheme"}</span>
                          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${badge.color}`}>
                            <Icon className="h-3 w-3" />
                            {badge.label}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">{app.application_number} · {formatDateTime(app.created_at)}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Schemes */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : filteredSchemes.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Award className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">No schemes found</p>
              <p className="mt-1 text-xs text-slate-500">
                {filter === "eligible" ? "You may not be eligible for any schemes. Complete your profile to unlock more." : "Check back later for new schemes."}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredSchemes.map((scheme) => (
              <SchemeCard key={scheme.id} scheme={scheme} onApply={() => handleApply(scheme.id)} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: { icon: typeof Award; label: string; value: string; color: string }) {
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

function SchemeCard({ scheme, onApply }: { scheme: GovtScheme; onApply: () => void }) {
  const eligible = scheme.is_eligible;
  const applied = scheme.has_applied;

  return (
    <Card className={`transition-all hover:shadow-md ${scheme.is_featured ? "border-primary/30" : ""}`}>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <CardTitle className="text-base">{scheme.name}</CardTitle>
            {scheme.name_hi && <p className="text-sm text-slate-500 mt-0.5">{scheme.name_hi}</p>}
            <CardDescription className="mt-1">
              {CATEGORY_LABELS[scheme.category] || scheme.category} · {scheme.level === "central" ? "Central Govt" : scheme.level === "state" ? "State Govt" : "Central + State"}
            </CardDescription>
          </div>
          {eligible !== null && (
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
              eligible ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-500"
            }`}>
              {eligible ? "Eligible" : "Not Eligible"}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-slate-600 line-clamp-2">{scheme.short_description}</p>

        {/* Benefit */}
        {scheme.benefit_description && (
          <div className="rounded-md bg-primary-5 p-2">
            <p className="text-xs font-medium text-primary">Benefit</p>
            <p className="text-sm text-slate-700">{scheme.benefit_description}</p>
          </div>
        )}

        {/* Eligibility reasons (if not eligible) */}
        {eligible === false && scheme.eligibility_reasons && scheme.eligibility_reasons.length > 0 && (
          <div className="rounded-md bg-amber-50 p-2">
            <p className="text-xs font-medium text-amber-800">Not eligible because:</p>
            <ul className="mt-1 space-y-0.5">
              {scheme.eligibility_reasons.map((reason, i) => (
                <li key={i} className="text-xs text-amber-700">• {reason}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Application status (if applied) */}
        {applied && scheme.application_status && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">Application:</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[scheme.application_status]?.color || "bg-slate-100 text-slate-700"}`}>
              {STATUS_BADGE[scheme.application_status]?.label || scheme.application_status}
            </span>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          {!applied && (
            <Button
              size="sm"
              className="flex-1"
              onClick={onApply}
              disabled={eligible === false}
            >
              {eligible === false ? "Not Eligible" : "Apply Now"}
            </Button>
          )}
          {applied && (
            <Button size="sm" variant="secondary" className="flex-1" disabled>
              Applied
            </Button>
          )}
          {scheme.source_url && (
            <a href={scheme.source_url} target="_blank" rel="noopener noreferrer">
              <Button size="sm" variant="ghost">
                <ExternalLink className="h-4 w-4" />
              </Button>
            </a>
          )}
        </div>

        {/* Helpline */}
        {scheme.helpline_number && (
          <div className="flex items-center gap-1 text-xs text-slate-400">
            <Phone className="h-3 w-3" />
            Helpline: {scheme.helpline_number}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
