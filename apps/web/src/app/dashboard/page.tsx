"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Sprout,
  Stethoscope,
  Satellite,
  CloudRain,
  ShieldCheck,
  Store,
  FileText,
  LogOut,
  Loader2,
  MapPin,
  Calendar,
  TrendingUp,
  Shield,
  ShieldAlert,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LanguageSelector } from "@/components/language-selector";
import { VoiceAssistant } from "@/components/voice/voice-assistant";
import { ConsentBanner } from "@/components/consent/consent-banner";

const QUICK_ACTIONS = [
  {
    icon: MapPin,
    title: "Register a Plot",
    description: "Draw your plot boundary on the map and register it for monitoring",
    href: "/dashboard/plots/register",
    color: "bg-primary-50 text-primary",
    available: true,
  },
  {
    icon: Stethoscope,
    title: "Identify Crop Disease",
    description: "Upload a photo of an affected plant for AI-powered diagnosis",
    href: "/dashboard/disease",
    color: "bg-primary-50 text-primary",
    available: true,
  },
  {
    icon: CloudRain,
    title: "Weather & Alerts",
    description: "Check current conditions, 7-day forecast, and extreme weather alerts",
    href: "/dashboard/weather",
    color: "bg-blue-50 text-blue-600",
    available: true,
  },
  {
    icon: Satellite,
    title: "NDVI Monitoring",
    description: "View satellite-based vegetation health maps and anomaly alerts for your plots",
    href: "/dashboard/ndvi",
    color: "bg-emerald-50 text-emerald-600",
    available: true,
  },
  {
    icon: ShieldCheck,
    title: "Crop Insurance",
    description: "Browse PMFBY policies and file claims with auto-evidence",
    href: "/dashboard/insurance",
    color: "bg-amber-50 text-amber-600",
    available: true,
  },
  {
    icon: Store,
    title: "Marketplace",
    description: "Order seeds, fertilizers, and machinery from verified suppliers",
    href: "/dashboard/marketplace",
    color: "bg-purple-50 text-purple-600",
    available: true,
  },
  {
    icon: FileText,
    title: "Govt Schemes",
    description: "Discover schemes you are eligible for and apply in one click",
    href: "/dashboard/schemes",
    color: "bg-pink-50 text-pink-600",
    available: true,
  },
  {
    icon: Shield,
    title: "Privacy & Data Rights",
    description: "Manage consent, file DSRs, request erasure, or raise grievances (DPDP)",
    href: "/dashboard/privacy",
    color: "bg-slate-100 text-slate-700",
    available: true,
  },
];

const ADMIN_ACTIONS = [
  {
    icon: ShieldAlert,
    title: "Audit Logs",
    description: "Search security audit trail — logins, PII access, consent, payments",
    href: "/dashboard/admin/audit",
    color: "bg-red-50 text-red-600",
    available: true,
  },
];

const STATS = [
  { label: "Registered Plots", value: "0", icon: MapPin },
  { label: "Disease Reports", value: "0", icon: Stethoscope },
  { label: "Active Policies", value: "0", icon: ShieldCheck },
  { label: "Pending Orders", value: "0", icon: TrendingUp },
];

export default function DashboardPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading, logout, hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  if (isLoading || !isAuthenticated || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
              <Sprout className="h-5 w-5 text-white" />
            </div>
            <span className="text-lg font-bold text-slate-900">KrishiSetu</span>
          </Link>

          <div className="flex items-center gap-4">
            <div className="hidden sm:block">
              <p className="text-sm font-medium text-slate-900">{user.full_name}</p>
              <p className="text-xs text-slate-500">{user.phone}</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 text-primary-700 font-semibold">
              {user.full_name.charAt(0).toUpperCase()}
            </div>
            <LanguageSelector compact />
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Welcome banner */}
        <div className="mb-8 rounded-lg bg-gradient-to-br from-primary-50 to-primary-100 p-6">
          <h1 className="text-2xl font-bold text-slate-900">
            Welcome back, {user.full_name.split(" ")[0]}
          </h1>
          <p className="mt-1 text-slate-700">
            Here&apos;s an overview of your farm dashboard. Start by registering
            your plots to unlock NDVI monitoring and weather advisories.
          </p>
          {!user.aadhaar_verified && (
            <div className="mt-4 flex items-center gap-3 rounded-md bg-white/60 p-3">
              <ShieldCheck className="h-5 w-5 text-amber-600" />
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-900">
                  Complete Aadhaar verification
                </p>
                <p className="text-xs text-slate-600">
                  Required for scheme applications and insurance enrollment
                </p>
              </div>
              <Button size="sm" variant="outline">
                Verify now
              </Button>
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {STATS.map((stat) => (
            <Link
              key={stat.label}
              href={stat.label === "Registered Plots" ? "/dashboard/plots" : "#"}
            >
              <Card className="transition-all hover:shadow-md hover:border-primary/30">
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary-50">
                      <stat.icon className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-slate-900">{stat.value}</p>
                      <p className="text-xs text-slate-600">{stat.label}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>

        {/* Quick actions */}
        <h2 className="mb-4 text-xl font-bold text-slate-900">Quick Actions</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {QUICK_ACTIONS.map((action) => (
            <Card
              key={action.title}
              className={
                action.available
                  ? "cursor-pointer transition-all hover:shadow-md hover:border-primary/30"
                  : "opacity-60"
              }
            >
              {action.available ? (
                <Link href={action.href}>
                  <CardHeader>
                    <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${action.color}`}>
                      <action.icon className="h-5 w-5" />
                    </div>
                    <CardTitle className="text-base">{action.title}</CardTitle>
                    <CardDescription>{action.description}</CardDescription>
                  </CardHeader>
                </Link>
              ) : (
                <CardHeader>
                  <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${action.color}`}>
                    <action.icon className="h-5 w-5" />
                  </div>
                  <CardTitle className="text-base flex items-center gap-2">
                    {action.title}
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                      Soon
                    </span>
                  </CardTitle>
                  <CardDescription>{action.description}</CardDescription>
                </CardHeader>
              )}
            </Card>
          ))}
        </div>

        {/* Admin actions (admin role only) */}
        {user.role === "admin" && (
          <>
            <h2 className="mb-4 mt-8 text-xl font-bold text-slate-900">Admin Tools</h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {ADMIN_ACTIONS.map((action) => (
                <Card key={action.title} className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30">
                  <Link href={action.href}>
                    <CardHeader>
                      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${action.color}`}>
                        <action.icon className="h-5 w-5" />
                      </div>
                      <CardTitle className="text-base">{action.title}</CardTitle>
                      <CardDescription>{action.description}</CardDescription>
                    </CardHeader>
                  </Link>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Recent activity placeholder */}
        <h2 className="mb-4 mt-8 text-xl font-bold text-slate-900">Recent Activity</h2>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Calendar className="h-10 w-10 text-slate-300" />
            <p className="mt-3 text-sm text-slate-500">No activity yet</p>
            <p className="mt-1 text-xs text-slate-400">
              Your disease reports, scheme applications, and orders will appear here.
            </p>
          </CardContent>
        </Card>

        {/* Voice Assistant */}
        <div className="mt-8">
          <VoiceAssistant />
        </div>
      </main>

      {/* Phase F: consent banner — shows if user has ungranted consents */}
      <ConsentBanner />
    </div>
  );
}
