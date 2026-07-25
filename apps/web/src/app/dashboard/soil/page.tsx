"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Beaker,
  Plus,
  Loader2,
  Sprout,
  MapPin,
  FlaskConical,
  ShieldCheck,
  Info,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { soilApi } from "@/lib/api/soil-weather";
import { plotApi } from "@/lib/api/plots";
import type {
  PlotListResponse,
  SoilTest,
  SoilTestListResponse,
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
import { formatDate } from "@/lib/utils";

const SOURCE_BADGES = {
  shc_portal: { label: "Soil Health Card", color: "bg-green-50 text-green-700", icon: ShieldCheck },
  lab_manual: { label: "Lab Test", color: "bg-blue-50 text-blue-700", icon: FlaskConical },
  isric_auto: { label: "ISRIC Auto", color: "bg-amber-50 text-amber-700", icon: Beaker },
  officer_entered: { label: "Officer Verified", color: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
} as const;

export default function SoilHealthPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [plots, setPlots] = useState<PlotListResponse | null>(null);
  const [selectedPlotId, setSelectedPlotId] = useState<string | null>(null);
  const [tests, setTests] = useState<SoilTestListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);

  // New test form state
  const [testDate, setTestDate] = useState(new Date().toISOString().slice(0, 10));
  const [labName, setLabName] = useState("");
  const [nitrogenN, setNitrogenN] = useState("");
  const [phosphorusP, setPhosphorusP] = useState("");
  const [potassiumK, setPotassiumK] = useState("");
  const [ph, setPh] = useState("");
  const [ec, setEc] = useState("");
  const [organicCarbon, setOrganicCarbon] = useState("");
  const [notes, setNotes] = useState("");

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
    }
  }

  useEffect(() => {
    if (!selectedPlotId) return;
    loadTests();
  }, [selectedPlotId]);

  async function loadTests() {
    if (!selectedPlotId) return;
    setIsLoading(true);
    setError(null);
    try {
      const testsResp = await soilApi.listPlotTests(selectedPlotId);
      setTests(testsResp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load soil tests");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAddTest() {
    if (!selectedPlotId) return;
    setError(null);
    try {
      await soilApi.createPlotTest(selectedPlotId, {
        test_date: testDate,
        lab_name: labName || undefined,
        nitrogen_n: nitrogenN ? parseFloat(nitrogenN) : undefined,
        phosphorus_p: phosphorusP ? parseFloat(phosphorusP) : undefined,
        potassium_k: potassiumK ? parseFloat(potassiumK) : undefined,
        ph: ph ? parseFloat(ph) : undefined,
        electrical_conductivity: ec ? parseFloat(ec) : undefined,
        organic_carbon: organicCarbon ? parseFloat(organicCarbon) : undefined,
        notes: notes || undefined,
      });
      setShowAddForm(false);
      // Reset form
      setLabName("");
      setNitrogenN("");
      setPhosphorusP("");
      setPotassiumK("");
      setPh("");
      setEc("");
      setOrganicCarbon("");
      setNotes("");
      // Reload tests
      await loadTests();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add soil test");
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
            <h1 className="text-2xl font-bold text-slate-900">Soil Health</h1>
            <p className="text-sm text-slate-600">
              Soil test results, nutrient levels, and fertilizer recommendations
            </p>
          </div>
          {selectedPlotId && (
            <Button onClick={() => setShowAddForm(!showAddForm)}>
              <Plus className="h-4 w-4" />
              Add Soil Test
            </Button>
          )}
        </div>

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
                      {plot.nickname || `Plot ${plot.survey_number}`} — {plot.village}, {plot.district}
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
              <p className="mt-3 text-sm font-medium text-slate-900">
                No plots registered
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Register a plot to manage its soil test data.
              </p>
              <Button
                onClick={() => router.push("/dashboard/plots/register")}
                className="mt-4"
              >
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

        {/* Add test form */}
        {showAddForm && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-lg">Add Manual Soil Test</CardTitle>
              <CardDescription>
                Enter values from your soil testing lab report. Fertilizer
                recommendations are generated automatically.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="test_date">Test Date *</Label>
                  <Input
                    id="test_date"
                    type="date"
                    value={testDate}
                    onChange={(e) => setTestDate(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lab_name">Lab Name</Label>
                  <Input
                    id="lab_name"
                    placeholder="e.g., District Soil Testing Lab"
                    value={labName}
                    onChange={(e) => setLabName(e.target.value)}
                    maxLength={255}
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="n">Nitrogen (kg/ha)</Label>
                  <Input
                    id="n"
                    type="number"
                    step="0.01"
                    placeholder="e.g., 150"
                    value={nitrogenN}
                    onChange={(e) => setNitrogenN(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="p">Phosphorus (kg/ha)</Label>
                  <Input
                    id="p"
                    type="number"
                    step="0.01"
                    placeholder="e.g., 12.5"
                    value={phosphorusP}
                    onChange={(e) => setPhosphorusP(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="k">Potassium (kg/ha)</Label>
                  <Input
                    id="k"
                    type="number"
                    step="0.01"
                    placeholder="e.g., 110"
                    value={potassiumK}
                    onChange={(e) => setPotassiumK(e.target.value)}
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="ph">pH (0-14)</Label>
                  <Input
                    id="ph"
                    type="number"
                    step="0.01"
                    min="0"
                    max="14"
                    placeholder="e.g., 6.5"
                    value={ph}
                    onChange={(e) => setPh(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ec">EC (dS/m)</Label>
                  <Input
                    id="ec"
                    type="number"
                    step="0.001"
                    placeholder="e.g., 0.8"
                    value={ec}
                    onChange={(e) => setEc(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="oc">Organic Carbon (%)</Label>
                  <Input
                    id="oc"
                    type="number"
                    step="0.01"
                    placeholder="e.g., 0.65"
                    value={organicCarbon}
                    onChange={(e) => setOrganicCarbon(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="notes">Notes (optional)</Label>
                <textarea
                  id="notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Additional observations or context"
                  className="flex min-h-[80px] w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                  maxLength={2000}
                />
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setShowAddForm(false)}>
                  Cancel
                </Button>
                <Button onClick={handleAddTest} disabled={!testDate}>
                  Save Soil Test
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Soil tests list */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : tests && tests.tests.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Beaker className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">
                No soil tests yet
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Add a soil test result manually, or wait for ISRIC auto-population
                (happens within minutes of plot registration).
              </p>
            </CardContent>
          </Card>
        ) : (
          tests && (
            <div className="space-y-4">
              {tests.tests.map((test) => (
                <SoilTestCard key={test.id} test={test} />
              ))}
            </div>
          )
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

function SoilTestCard({ test }: { test: SoilTest }) {
  const source = SOURCE_BADGES[test.source];
  const SourceIcon = source.icon;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              Soil Test — {formatDate(test.test_date)}
            </CardTitle>
            <CardDescription>
              {test.lab_name || "No lab specified"}
            </CardDescription>
          </div>
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${source.color}`}>
            <SourceIcon className="h-3 w-3" />
            {source.label}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <NutrientValue
            label="Nitrogen"
            value={test.nitrogen_n}
            unit="kg/ha"
            levels={[
              { max: 150, label: "Low", color: "text-red-600" },
              { max: 280, label: "Medium", color: "text-amber-600" },
              { max: 1000, label: "High", color: "text-green-600" },
            ]}
          />
          <NutrientValue
            label="Phosphorus"
            value={test.phosphorus_p}
            unit="kg/ha"
            levels={[
              { max: 12, label: "Low", color: "text-red-600" },
              { max: 25, label: "Medium", color: "text-amber-600" },
              { max: 1000, label: "High", color: "text-green-600" },
            ]}
          />
          <NutrientValue
            label="Potassium"
            value={test.potassium_k}
            unit="kg/ha"
            levels={[
              { max: 110, label: "Low", color: "text-red-600" },
              { max: 280, label: "Medium", color: "text-amber-600" },
              { max: 1000, label: "High", color: "text-green-600" },
            ]}
          />
          <NutrientValue
            label="pH"
            value={test.ph}
            unit=""
            levels={[
              { max: 5.5, label: "Acidic", color: "text-amber-600" },
              { max: 7.5, label: "Optimal", color: "text-green-600" },
              { max: 14, label: "Alkaline", color: "text-amber-600" },
            ]}
          />
          <NutrientValue
            label="EC"
            value={test.electrical_conductivity}
            unit="dS/m"
            levels={[
              { max: 1, label: "Normal", color: "text-green-600" },
              { max: 2, label: "Marginal", color: "text-amber-600" },
              { max: 100, label: "Saline", color: "text-red-600" },
            ]}
          />
          <NutrientValue
            label="Organic Carbon"
            value={test.organic_carbon}
            unit="%"
            levels={[
              { max: 0.5, label: "Low", color: "text-red-600" },
              { max: 0.75, label: "Medium", color: "text-amber-600" },
              { max: 100, label: "High", color: "text-green-600" },
            ]}
          />
        </div>

        {/* Soil texture (if available) */}
        {(test.clay_pct !== null || test.soil_type) && (
          <div className="mt-4 flex flex-wrap gap-4 border-t border-slate-100 pt-3">
            {test.soil_type && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-slate-500">Soil Type:</span>
                <span className="font-medium text-slate-900">{test.soil_type}</span>
              </div>
            )}
            {test.soil_texture && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-slate-500">Texture:</span>
                <span className="font-medium text-slate-900">{test.soil_texture}</span>
              </div>
            )}
            {test.clay_pct !== null && test.sand_pct !== null && test.silt_pct !== null && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                Clay {Number(test.clay_pct).toFixed(0)}% / Sand {Number(test.sand_pct).toFixed(0)}% / Silt {Number(test.silt_pct).toFixed(0)}%
              </div>
            )}
          </div>
        )}

        {/* Fertilizer recommendation */}
        {test.fertilizer_recommendation && (
          <div className="mt-4 rounded-md bg-green-50 p-3">
            <p className="text-xs font-medium text-green-900 flex items-center gap-1">
              <ShieldCheck className="h-3 w-3" />
              Fertilizer Recommendation
            </p>
            <p className="mt-1 text-sm text-green-800">
              {test.fertilizer_recommendation}
            </p>
          </div>
        )}

        {/* Amendment recommendation */}
        {test.amendment_recommendation && (
          <div className="mt-2 rounded-md bg-amber-50 p-3">
            <p className="text-xs font-medium text-amber-900 flex items-center gap-1">
              <AlertCircle className="h-3 w-3" />
              Soil Amendment
            </p>
            <p className="mt-1 text-sm text-amber-800">
              {test.amendment_recommendation}
            </p>
          </div>
        )}

        {/* ISRIC disclaimer */}
        {test.source === "isric_auto" && (
          <div className="mt-3 flex items-start gap-2 rounded-md bg-blue-50 p-2 text-xs text-blue-800">
            <Info className="h-3 w-3 flex-shrink-0 mt-0.5" />
            <span>
              These values are auto-populated from ISRIC SoilGrids (global model at 250m resolution).
              They are approximations, not actual lab tests. For precise values, submit a soil sample to a testing lab.
            </span>
          </div>
        )}

        {test.notes && (
          <p className="mt-3 text-xs text-slate-500 italic">{test.notes}</p>
        )}
      </CardContent>
    </Card>
  );
}

function NutrientValue({
  label,
  value,
  unit,
  levels,
}: {
  label: string;
  value: number | null;
  unit: string;
  levels: { max: number; label: string; color: string }[];
}) {
  if (value === null || value === undefined) {
    return (
      <div className="rounded-md bg-slate-50 p-3 text-center">
        <p className="text-xs text-slate-500">{label}</p>
        <p className="mt-1 text-lg font-bold text-slate-400">—</p>
        <p className="text-xs text-slate-400">{unit || "Not tested"}</p>
      </div>
    );
  }

  // Find level
  const level = levels.find((l) => value <= l.max) || levels[levels.length - 1];

  return (
    <div className="rounded-md bg-slate-50 p-3 text-center">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${level.color}`}>
        {Number(value).toFixed(2)}
      </p>
      <p className="text-xs text-slate-400">
        {level.label} {unit}
      </p>
    </div>
  );
}
