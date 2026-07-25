"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Plus,
  MapPin,
  Loader2,
  CheckCircle2,
  Clock,
  XCircle,
  TrendingUp,
  Sprout,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { plotApi } from "@/lib/api/plots";
import type { PlotListResponse, PlotStatsResponse, PlotListItem } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatINR, formatDate } from "@/lib/utils";

const VERIFICATION_BADGE = {
  pending: { label: "Pending", color: "bg-amber-50 text-amber-700", icon: Clock },
  verified: { label: "Verified", color: "bg-green-50 text-green-700", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "bg-red-50 text-red-700", icon: XCircle },
  resubmission_requested: { label: "Resubmit", color: "bg-orange-50 text-orange-700", icon: Clock },
} as const;

export default function PlotsListPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [plots, setPlots] = useState<PlotListItem[]>([]);
  const [stats, setStats] = useState<PlotStatsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadData();
  }, [isAuthenticated, page]);

  async function loadData() {
    setIsLoading(true);
    setError(null);
    try {
      const [plotsResponse, statsResponse] = await Promise.all([
        plotApi.listMyPlots(page),
        plotApi.getPlotStats(),
      ]);
      setPlots(plotsResponse.plots);
      setStats(statsResponse);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load plots";
      setError(message);
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
            <h1 className="text-2xl font-bold text-slate-900">My Plots</h1>
            <p className="text-sm text-slate-600">
              Manage your registered farm plots and crop cycles
            </p>
          </div>
          <Button onClick={() => router.push("/dashboard/plots/register")}>
            <Plus className="h-4 w-4" />
            Register Plot
          </Button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              icon={MapPin}
              label="Total Plots"
              value={String(stats.total_plots)}
              color="bg-primary-50 text-primary"
            />
            <StatCard
              icon={TrendingUp}
              label="Total Area"
              value={`${stats.total_area_ha.toFixed(2)} ha`}
              color="bg-blue-50 text-blue-600"
            />
            <StatCard
              icon={CheckCircle2}
              label="Verified"
              value={String(stats.verified_plots)}
              color="bg-green-50 text-green-600"
            />
            <StatCard
              icon={Clock}
              label="Pending"
              value={String(stats.pending_verification)}
              color="bg-amber-50 text-amber-600"
            />
          </div>
        )}

        {/* Error */}
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

        {/* Plots list */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : plots.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <MapPin className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">
                No plots registered yet
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Register your first plot to unlock NDVI monitoring, weather advisories, and insurance.
              </p>
              <Button
                onClick={() => router.push("/dashboard/plots/register")}
                className="mt-4"
              >
                <Plus className="h-4 w-4" />
                Register your first plot
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {plots.map((plot) => {
              const badge = VERIFICATION_BADGE[plot.verification_status];
              const Icon = badge.icon;
              return (
                <Card
                  key={plot.id}
                  className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30"
                  onClick={() => router.push(`/dashboard/plots/${plot.id}`)}
                >
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <CardTitle className="text-base">
                          {plot.nickname || `Plot ${plot.survey_number}`}
                        </CardTitle>
                        <CardDescription className="mt-1">
                          {plot.village}, {plot.district}
                        </CardDescription>
                      </div>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${badge.color}`}
                      >
                        <Icon className="h-3 w-3" />
                        {badge.label}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-slate-500">Area</span>
                      <span className="font-medium text-slate-900">
                        {Number(plot.area_ha).toFixed(2)} ha
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-slate-500">Survey No.</span>
                      <span className="font-mono text-xs text-slate-700">
                        {plot.survey_number}
                      </span>
                    </div>
                    {plot.current_crop && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Current crop</span>
                        <span className="inline-flex items-center gap-1 font-medium text-slate-900">
                          <Sprout className="h-3 w-3 text-primary" />
                          {plot.current_crop}
                        </span>
                      </div>
                    )}
                    <div className="border-t border-slate-100 pt-2 text-xs text-slate-400">
                      Registered {formatDate(plot.created_at)}
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
  icon: typeof MapPin;
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
