"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Plus,
  Loader2,
  Camera,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Stethoscope,
  Sprout,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { diseaseApi } from "@/lib/api/disease";
import type { DiseaseReportListResponse, DiseaseReportStats } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDate, formatDateTime } from "@/lib/utils";

const STATUS_BADGE = {
  pending: { label: "Pending", color: "bg-slate-100 text-slate-700", icon: Clock },
  processing: { label: "Analyzing", color: "bg-blue-50 text-blue-700", icon: Loader2 },
  completed: { label: "Completed", color: "bg-green-50 text-green-700", icon: CheckCircle2 },
  failed: { label: "Failed", color: "bg-red-50 text-red-700", icon: XCircle },
  officer_review: { label: "Under Review", color: "bg-amber-50 text-amber-700", icon: AlertCircle },
  reviewed: { label: "Reviewed", color: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
} as const;

export default function DiseaseListPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [reports, setReports] = useState<DiseaseReportListResponse | null>(null);
  const [stats, setStats] = useState<DiseaseReportStats | null>(null);
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
      const [reportsResp, statsResp] = await Promise.all([
        diseaseApi.listMyReports(1, 20),
        diseaseApi.getStats(),
      ]);
      setReports(reportsResp);
      setStats(statsResp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reports");
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
            <h1 className="text-2xl font-bold text-slate-900">Disease Reports</h1>
            <p className="text-sm text-slate-600">
              AI-powered diagnosis of crop diseases from photos
            </p>
          </div>
          <Button onClick={() => router.push("/dashboard/disease/upload")}>
            <Plus className="h-4 w-4" />
            New Report
          </Button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              icon={Stethoscope}
              label="Total Reports"
              value={String(stats.total_reports)}
              color="bg-primary-50 text-primary"
            />
            <StatCard
              icon={CheckCircle2}
              label="Completed"
              value={String(stats.completed)}
              color="bg-green-50 text-green-600"
            />
            <StatCard
              icon={Clock}
              label="Pending"
              value={String(stats.pending)}
              color="bg-blue-50 text-blue-600"
            />
            <StatCard
              icon={AlertCircle}
              label="Needs Review"
              value={String(stats.needs_review)}
              color="bg-amber-50 text-amber-600"
            />
          </div>
        )}

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

        {/* Reports */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : !reports || reports.reports.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Camera className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">
                No disease reports yet
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Upload a photo of an affected plant to get an instant AI-powered diagnosis.
              </p>
              <Button
                onClick={() => router.push("/dashboard/disease/upload")}
                className="mt-4"
              >
                <Camera className="h-4 w-4" />
                Upload your first photo
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {reports.reports.map((report) => {
              const badge = STATUS_BADGE[report.status];
              const Icon = badge.icon;
              return (
                <Card
                  key={report.id}
                  className="cursor-pointer overflow-hidden transition-all hover:shadow-md hover:border-primary/30"
                  onClick={() => router.push(`/dashboard/disease/${report.id}`)}
                >
                  {/* Image preview */}
                  <div className="relative h-40 bg-slate-100">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={report.image_url}
                      alt="Disease report"
                      className="h-full w-full object-cover"
                    />
                    <div className={`absolute top-2 right-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${badge.color}`}>
                      <Icon className={`h-3 w-3 ${report.status === "processing" ? "animate-spin" : ""}`} />
                      {badge.label}
                    </div>
                  </div>

                  <CardContent className="p-4">
                    {report.prediction ? (
                      <>
                        <div className="flex items-start justify-between">
                          <div>
                            <h3 className="font-semibold text-slate-900">
                              {report.prediction.disease?.name_en || report.prediction.disease_slug}
                            </h3>
                            <p className="text-xs text-slate-500 capitalize">
                              {report.prediction.disease?.disease_type || "Unknown type"}
                            </p>
                          </div>
                          <span className={`text-sm font-bold ${report.prediction.is_reliable ? "text-green-600" : "text-amber-600"}`}>
                            {(report.prediction.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                      </>
                    ) : (
                      <div>
                        <h3 className="font-semibold text-slate-900">
                          {report.status === "failed" ? "Analysis failed" : "Analyzing..."}
                        </h3>
                        <p className="mt-1 text-xs text-slate-500">
                          {report.failure_reason || (report.status === "pending" || report.status === "processing"
                            ? "Result will appear here when ready"
                            : "Awaiting officer review")}
                        </p>
                      </div>
                    )}
                    <div className="mt-3 border-t border-slate-100 pt-2 text-xs text-slate-400">
                      {formatDateTime(report.created_at)}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
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
  color,
}: {
  icon: typeof Camera;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-md ${color}`}>
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">{value}</p>
            <p className="text-xs text-slate-600">{label}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
