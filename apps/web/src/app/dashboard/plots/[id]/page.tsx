"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import {
  ArrowLeft,
  Loader2,
  MapPin,
  Calendar,
  CheckCircle2,
  Clock,
  XCircle,
  Sprout,
  Droplets,
  Plus,
  Pencil,
  Trash2,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { plotApi } from "@/lib/api/plots";
import type {
  CropCycleResponse,
  CropResponse,
  PlotResponse,
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

const PlotMap = dynamic(
  () => import("@/components/maps/plot-map").then((mod) => mod.PlotMap),
  { ssr: false },
);

const VERIFICATION_BADGE = {
  pending: { label: "Pending verification", color: "bg-amber-50 text-amber-700 border-amber-200", icon: Clock },
  verified: { label: "Verified", color: "bg-green-50 text-green-700 border-green-200", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "bg-red-50 text-red-700 border-red-200", icon: XCircle },
  resubmission_requested: { label: "Resubmission requested", color: "bg-orange-50 text-orange-700 border-orange-200", icon: Clock },
} as const;

const STATUS_COLORS = {
  planned: "bg-slate-100 text-slate-700",
  sown: "bg-blue-50 text-blue-700",
  growing: "bg-green-50 text-green-700",
  harvested: "bg-amber-50 text-amber-700",
  failed: "bg-red-50 text-red-700",
} as const;

export default function PlotDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const plotId = params?.id as string;

  const [plot, setPlot] = useState<PlotResponse | null>(null);
  const [cropCycles, setCropCycles] = useState<CropCycleResponse[]>([]);
  const [crops, setCrops] = useState<CropResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddCrop, setShowAddCrop] = useState(false);

  // New crop cycle form state
  const [selectedCropId, setSelectedCropId] = useState("");
  const [selectedSeason, setSelectedSeason] = useState<"kharif" | "rabi" | "zaid">("kharif");
  const [selectedYear, setSelectedYear] = useState(String(new Date().getFullYear()));
  const [sowingDate, setSowingDate] = useState("");
  const [cropArea, setCropArea] = useState("");

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || !plotId) return;
    loadPlot();
    loadCrops();
  }, [isAuthenticated, plotId]);

  async function loadPlot() {
    setIsLoading(true);
    setError(null);
    try {
      const [plotData, cycles] = await Promise.all([
        plotApi.getPlot(plotId),
        plotApi.listCropCycles(plotId),
      ]);
      setPlot(plotData);
      setCropCycles(cycles);
      setCropArea(Number(plotData.area_ha).toFixed(4));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load plot";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function loadCrops() {
    try {
      const response = await plotApi.listCrops();
      setCrops(response.crops);
    } catch {
      // Crops list is non-critical
    }
  }

  async function handleAddCropCycle() {
    if (!selectedCropId) return;
    try {
      await plotApi.createCropCycle(plotId, {
        crop_id: selectedCropId,
        season: selectedSeason,
        season_year: parseInt(selectedYear, 10),
        sowing_date: sowingDate || undefined,
        area_ha: parseFloat(cropArea),
      });
      // Reload cycles
      const cycles = await plotApi.listCropCycles(plotId);
      setCropCycles(cycles);
      setShowAddCrop(false);
      // Reset form
      setSelectedCropId("");
      setSowingDate("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to add crop cycle";
      setError(message);
    }
  }

  async function handleUpdateCycleStatus(
    cycleId: string,
    status: "sown" | "growing" | "harvested" | "failed",
  ) {
    try {
      await plotApi.updateCropCycle(cycleId, { status });
      const cycles = await plotApi.listCropCycles(plotId);
      setCropCycles(cycles);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update status";
      setError(message);
    }
  }

  async function handleDeletePlot() {
    if (!confirm("Are you sure you want to delete this plot? This cannot be undone.")) return;
    try {
      await plotApi.deletePlot(plotId);
      router.push("/dashboard/plots");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete plot";
      setError(message);
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

  if (error && !plot) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <XCircle className="mx-auto h-12 w-12 text-red-500" />
            <p className="mt-3 text-sm font-medium text-slate-900">Plot not found</p>
            <p className="mt-1 text-xs text-slate-500">{error}</p>
            <Link href="/dashboard/plots">
              <Button className="mt-4">Back to plots</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!plot) return null;

  const badge = VERIFICATION_BADGE[plot.verification_status];
  const BadgeIcon = badge.icon;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/plots" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to plots
          </Link>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm">
              <Pencil className="h-4 w-4" />
              Edit
            </Button>
            {plot.verification_status !== "verified" && (
              <Button variant="ghost" size="sm" onClick={handleDeletePlot}>
                <Trash2 className="h-4 w-4" />
                Delete
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Title */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900">
            {plot.nickname || `Plot ${plot.survey_number}`}
          </h1>
          <p className="text-sm text-slate-600">
            {plot.village}, {plot.district}, {plot.state}
            {plot.pincode && ` - ${plot.pincode}`}
          </p>
        </div>

        {/* Verification banner */}
        <div className={`mb-6 flex items-center gap-3 rounded-md border p-4 ${badge.color}`}>
          <BadgeIcon className="h-5 w-5 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium">{badge.label}</p>
            {plot.verification_notes && (
              <p className="mt-1 text-xs opacity-80">{plot.verification_notes}</p>
            )}
          </div>
          {plot.verified_at && (
            <span className="text-xs opacity-70">
              {formatDate(plot.verified_at)}
            </span>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left column: Map + details */}
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <MapPin className="h-5 w-5 text-primary" />
                  Plot Boundary
                </CardTitle>
                <CardDescription>
                  Area: {Number(plot.area_ha).toFixed(4)} hectares ({(Number(plot.area_ha) * 2.471).toFixed(2)} acres)
                </CardDescription>
              </CardHeader>
              <CardContent>
                {plot.boundary && (
                  <PlotMap
                    boundary={plot.boundary}
                    centroid={plot.centroid}
                    height="400px"
                  />
                )}
              </CardContent>
            </Card>

            {/* Crop cycles */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-lg">
                      <Sprout className="h-5 w-5 text-primary" />
                      Crop History
                    </CardTitle>
                    <CardDescription>
                      Crops grown on this plot over time
                    </CardDescription>
                  </div>
                  <Button size="sm" onClick={() => setShowAddCrop(!showAddCrop)}>
                    <Plus className="h-4 w-4" />
                    Add Crop
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {/* Add crop form */}
                {showAddCrop && (
                  <div className="mb-4 rounded-md bg-slate-50 p-4">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-2 sm:col-span-2">
                        <Label htmlFor="crop">Crop</Label>
                        <select
                          id="crop"
                          value={selectedCropId}
                          onChange={(e) => setSelectedCropId(e.target.value)}
                          className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm"
                        >
                          <option value="">Select a crop</option>
                          {crops.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name_en} {c.name_hi ? `(${c.name_hi})` : ""} — {c.crop_category}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="season">Season</Label>
                        <select
                          id="season"
                          value={selectedSeason}
                          onChange={(e) => setSelectedSeason(e.target.value as "kharif" | "rabi" | "zaid")}
                          className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm"
                        >
                          <option value="kharif">Kharif (Jun-Oct)</option>
                          <option value="rabi">Rabi (Nov-Mar)</option>
                          <option value="zaid">Zaid (Apr-Jun)</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="year">Year</Label>
                        <Input
                          id="year"
                          type="number"
                          value={selectedYear}
                          onChange={(e) => setSelectedYear(e.target.value)}
                          min={2000}
                          max={2100}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="sowing">Sowing date (optional)</Label>
                        <Input
                          id="sowing"
                          type="date"
                          value={sowingDate}
                          onChange={(e) => setSowingDate(e.target.value)}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="crop_area">Area under crop (ha)</Label>
                        <Input
                          id="crop_area"
                          type="number"
                          step="0.0001"
                          value={cropArea}
                          onChange={(e) => setCropArea(e.target.value)}
                          max={Number(plot.area_ha)}
                        />
                      </div>
                    </div>
                    <div className="mt-3 flex justify-end gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setShowAddCrop(false)}>
                        Cancel
                      </Button>
                      <Button size="sm" onClick={handleAddCropCycle} disabled={!selectedCropId}>
                        Add Crop Cycle
                      </Button>
                    </div>
                  </div>
                )}

                {/* Crop cycles list */}
                {cropCycles.length === 0 ? (
                  <div className="flex flex-col items-center py-8 text-center">
                    <Sprout className="h-10 w-10 text-slate-300" />
                    <p className="mt-2 text-sm text-slate-500">No crops registered yet</p>
                    <p className="text-xs text-slate-400">
                      Add a crop to track its growth and link to disease reports
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {cropCycles.map((cycle) => (
                      <div
                        key={cycle.id}
                        className="rounded-md border border-slate-200 p-4"
                      >
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="font-semibold text-slate-900">
                                {cycle.crop_name || "Unknown crop"}
                              </h4>
                              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[cycle.status]}`}>
                                {cycle.status}
                              </span>
                            </div>
                            <p className="text-xs text-slate-500">
                              {cycle.season.charAt(0).toUpperCase() + cycle.season.slice(1)} {cycle.season_year}
                              {" - "}
                              {cycle.area_ha} ha
                            </p>
                          </div>
                          <div className="flex gap-1">
                            {cycle.status === "planned" && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleUpdateCycleStatus(cycle.id, "sown")}
                              >
                                Mark sown
                              </Button>
                            )}
                            {cycle.status === "sown" && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleUpdateCycleStatus(cycle.id, "growing")}
                              >
                                Mark growing
                              </Button>
                            )}
                            {cycle.status === "growing" && (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleUpdateCycleStatus(cycle.id, "harvested")}
                                >
                                  Harvested
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleUpdateCycleStatus(cycle.id, "failed")}
                                >
                                  Failed
                                </Button>
                              </>
                            )}
                          </div>
                        </div>
                        {(cycle.sowing_date || cycle.expected_harvest_date || cycle.actual_harvest_date) && (
                          <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-600">
                            {cycle.sowing_date && (
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                Sown: {formatDate(cycle.sowing_date)}
                              </span>
                            )}
                            {cycle.expected_harvest_date && (
                              <span>Expected harvest: {formatDate(cycle.expected_harvest_date)}</span>
                            )}
                            {cycle.actual_harvest_date && (
                              <span>Harvested: {formatDate(cycle.actual_harvest_date)}</span>
                            )}
                          </div>
                        )}
                        {cycle.notes && (
                          <p className="mt-2 text-xs text-slate-600">{cycle.notes}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Right column: Quick info */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Plot Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <InfoRow label="Survey Number" value={plot.survey_number} mono />
                <InfoRow label="Village" value={plot.village} />
                <InfoRow label="District" value={plot.district} />
                <InfoRow label="State" value={plot.state} />
                {plot.pincode && <InfoRow label="Pincode" value={plot.pincode} />}
                <InfoRow
                  label="Area"
                  value={`${Number(plot.area_ha).toFixed(4)} ha (${(Number(plot.area_ha) * 2.471).toFixed(2)} acres)`}
                />
                <InfoRow
                  label="Ownership"
                  value={plot.ownership_type.charAt(0).toUpperCase() + plot.ownership_type.slice(1)}
                />
                {plot.irrigation_source && (
                  <InfoRow
                    label="Irrigation"
                    value={
                      <span className="flex items-center gap-1">
                        <Droplets className="h-3 w-3 text-blue-500" />
                        {plot.irrigation_source}
                      </span>
                    }
                  />
                )}
              </CardContent>
            </Card>

            {/* Soil info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Soil Information</CardTitle>
                <CardDescription>Auto-detected from ISRIC SoilGrids</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {plot.soil_type ? (
                  <InfoRow label="Soil Type" value={plot.soil_type} />
                ) : (
                  <p className="text-xs text-slate-500">
                    Soil type will be auto-populated from ISRIC SoilGrids.
                    May take a few minutes after registration.
                  </p>
                )}
                {plot.soil_ph && (
                  <InfoRow label="pH" value={String(plot.soil_ph)} />
                )}
              </CardContent>
            </Card>

            {/* Important dates */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Important Dates</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <InfoRow label="Registered" value={formatDate(plot.created_at)} />
                {plot.verified_at && (
                  <InfoRow label="Verified" value={formatDate(plot.verified_at)} />
                )}
                <InfoRow label="Last Updated" value={formatDate(plot.updated_at)} />
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
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between">
      <span className="text-slate-500">{label}</span>
      <span
        className={`ml-4 text-right font-medium text-slate-900 ${mono ? "font-mono text-xs" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
