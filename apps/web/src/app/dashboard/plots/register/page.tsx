"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  MapPin,
  Sprout,
  FileText,
  CheckCircle2,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { plotApi } from "@/lib/api/plots";
import type { GeoJSONPolygon } from "@/lib/api/types";
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

// Load the boundary editor dynamically (Leaflet needs window)
const PlotBoundaryEditor = dynamic(
  () =>
    import("@/components/maps/plot-boundary-editor").then(
      (mod) => mod.PlotBoundaryEditor,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[400px] items-center justify-center rounded-md border border-slate-200 bg-slate-50">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    ),
  },
);

const STEPS = [
  { id: 1, title: "Locate Plot", icon: MapPin, description: "Draw the boundary on the map" },
  { id: 2, title: "Land Details", icon: FileText, description: "Survey number, village, district" },
  { id: 3, title: "Additional Info", icon: Sprout, description: "Irrigation, ownership, nickname" },
  { id: 4, title: "Review & Submit", icon: CheckCircle2, description: "Confirm and register" },
] as const;

const IRRIGATION_OPTIONS = [
  { value: "", label: "Select irrigation source" },
  { value: "canal", label: "Canal" },
  { value: "borewell", label: "Borewell" },
  { value: "river", label: "River" },
  { value: "rainfed", label: "Rainfed (no irrigation)" },
  { value: "drip", label: "Drip irrigation" },
  { value: "sprinkler", label: "Sprinkler" },
  { value: "tank", label: "Tank / Pond" },
  { value: "other", label: "Other" },
];

const OWNERSHIP_OPTIONS = [
  { value: "owned", label: "Owned" },
  { value: "leased", label: "Leased" },
  { value: "shared", label: "Shared (joint ownership)" },
];

export default function RegisterPlotPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [step, setStep] = useState(1);
  const [boundary, setBoundary] = useState<GeoJSONPolygon | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [surveyNumber, setSurveyNumber] = useState("");
  const [village, setVillage] = useState("");
  const [district, setDistrict] = useState("");
  const [state, setState] = useState("");
  const [pincode, setPincode] = useState("");
  const [irrigationSource, setIrrigationSource] = useState("");
  const [ownershipType, setOwnershipType] = useState<"owned" | "leased" | "shared">("owned");
  const [lessorName, setLessorName] = useState("");
  const [leaseStartDate, setLeaseStartDate] = useState("");
  const [leaseEndDate, setLeaseEndDate] = useState("");
  const [nickname, setNickname] = useState("");

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  if (authLoading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const canProceedStep1 = boundary !== null;
  const canProceedStep2 = surveyNumber.trim() && village.trim() && district.trim() && state.trim();
  const canProceedStep3 =
    ownershipType !== "leased" ||
    (lessorName.trim() && leaseStartDate && leaseEndDate);

  const validatePincode = (p: string) => p === "" || /^[1-9][0-9]{5}$/.test(p);

  async function handleSubmit() {
    if (!boundary) {
      setError("Please draw the plot boundary first");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const plot = await plotApi.createPlot({
        survey_number: surveyNumber.trim(),
        village: village.trim(),
        district: district.trim(),
        state: state.trim(),
        pincode: pincode || undefined,
        boundary,
        irrigation_source: irrigationSource || undefined,
        ownership_type: ownershipType,
        lessor_name: ownershipType === "leased" ? lessorName.trim() : undefined,
        lease_start_date: ownershipType === "leased" ? leaseStartDate : undefined,
        lease_end_date: ownershipType === "leased" ? leaseEndDate : undefined,
        nickname: nickname.trim() || undefined,
      });
      // Redirect to the new plot's detail page
      router.push(`/dashboard/plots/${plot.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to register plot";
      setError(message);
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/plots" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to plots
          </Link>
          <h1 className="text-lg font-bold text-slate-900">Register New Plot</h1>
          <div className="w-20" />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Stepper */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            {STEPS.map((s, idx) => {
              const Icon = s.icon;
              const isActive = step === s.id;
              const isComplete = step > s.id;
              return (
                <div key={s.id} className="flex flex-1 items-center">
                  <div className="flex flex-col items-center">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors ${
                        isActive
                          ? "border-primary bg-primary text-white"
                          : isComplete
                            ? "border-primary bg-primary-50 text-primary"
                            : "border-slate-200 bg-white text-slate-400"
                      }`}
                    >
                      {isComplete ? (
                        <Check className="h-5 w-5" />
                      ) : (
                        <Icon className="h-5 w-5" />
                      )}
                    </div>
                    <p className={`mt-1 text-xs font-medium ${isActive || isComplete ? "text-slate-900" : "text-slate-400"}`}>
                      {s.title}
                    </p>
                  </div>
                  {idx < STEPS.length - 1 && (
                    <div
                      className={`mx-2 h-0.5 flex-1 ${
                        step > s.id ? "bg-primary" : "bg-slate-200"
                      }`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Step content */}
        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle>Draw your plot boundary</CardTitle>
              <CardDescription>
                Locate your plot on the map and draw its boundary by clicking
                points. The area will be computed automatically.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PlotBoundaryEditor onBoundaryChange={setBoundary} />
              <div className="mt-6 flex justify-end">
                <Button
                  onClick={() => setStep(2)}
                  disabled={!canProceedStep1}
                >
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle>Land details</CardTitle>
              <CardDescription>
                Enter the official land record identifiers for your plot. These
                will be used by the agricultural officer to verify ownership.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="survey_number">Survey Number *</Label>
                <Input
                  id="survey_number"
                  placeholder="e.g., 142/3 or RS No. 87"
                  value={surveyNumber}
                  onChange={(e) => setSurveyNumber(e.target.value)}
                  maxLength={100}
                />
                <p className="text-xs text-slate-500">
                  Found on your land records (Bhulekh / Patta)
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="village">Village *</Label>
                  <Input
                    id="village"
                    placeholder="e.g., Khanapur"
                    value={village}
                    onChange={(e) => setVillage(e.target.value)}
                    maxLength={255}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pincode">Pincode</Label>
                  <Input
                    id="pincode"
                    placeholder="6-digit pincode"
                    value={pincode}
                    onChange={(e) => setPincode(e.target.value)}
                    maxLength={6}
                  />
                  {!validatePincode(pincode) && (
                    <p className="text-xs text-red-600">Invalid pincode format</p>
                  )}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="district">District *</Label>
                  <Input
                    id="district"
                    placeholder="e.g., Pune"
                    value={district}
                    onChange={(e) => setDistrict(e.target.value)}
                    maxLength={100}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="state">State *</Label>
                  <Input
                    id="state"
                    placeholder="e.g., Maharashtra"
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    maxLength={100}
                  />
                </div>
              </div>

              <div className="flex justify-between">
                <Button variant="ghost" onClick={() => setStep(1)}>
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
                <Button
                  onClick={() => setStep(3)}
                  disabled={!canProceedStep2 || !validatePincode(pincode)}
                >
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle>Additional information</CardTitle>
              <CardDescription>
                Optional but helpful details. These can be changed later.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="nickname">Plot nickname</Label>
                <Input
                  id="nickname"
                  placeholder="e.g., Back field near well"
                  value={nickname}
                  onChange={(e) => setNickname(e.target.value)}
                  maxLength={100}
                />
                <p className="text-xs text-slate-500">
                  A friendly name to identify this plot
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="irrigation">Irrigation source</Label>
                <select
                  id="irrigation"
                  value={irrigationSource}
                  onChange={(e) => setIrrigationSource(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  {IRRIGATION_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label>Ownership type</Label>
                <div className="grid gap-2 sm:grid-cols-3">
                  {OWNERSHIP_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setOwnershipType(opt.value as "owned" | "leased" | "shared")}
                      className={`rounded-md border-2 px-3 py-2 text-sm font-medium transition-colors ${
                        ownershipType === opt.value
                          ? "border-primary bg-primary-50 text-primary"
                          : "border-slate-200 text-slate-700 hover:border-slate-300"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {ownershipType === "leased" && (
                <div className="space-y-4 rounded-md bg-amber-50 p-4">
                  <p className="text-sm font-medium text-amber-900">
                    Lease details (required)
                  </p>
                  <div className="space-y-2">
                    <Label htmlFor="lessor">Lessor (landlord) name</Label>
                    <Input
                      id="lessor"
                      placeholder="e.g., Suresh Patil"
                      value={lessorName}
                      onChange={(e) => setLessorName(e.target.value)}
                      maxLength={255}
                    />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="lease_start">Lease start date</Label>
                      <Input
                        id="lease_start"
                        type="date"
                        value={leaseStartDate}
                        onChange={(e) => setLeaseStartDate(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="lease_end">Lease end date</Label>
                      <Input
                        id="lease_end"
                        type="date"
                        value={leaseEndDate}
                        onChange={(e) => setLeaseEndDate(e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              )}

              <div className="flex justify-between">
                <Button variant="ghost" onClick={() => setStep(2)}>
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
                <Button
                  onClick={() => setStep(4)}
                  disabled={!canProceedStep3}
                >
                  Review
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle>Review & submit</CardTitle>
              <CardDescription>
                Please verify all details before submitting. The plot will be
                sent for verification by your agricultural officer.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ReviewRow label="Survey Number" value={surveyNumber} />
              <ReviewRow label="Location" value={`${village}, ${district}, ${state}`} />
              {pincode && <ReviewRow label="Pincode" value={pincode} />}
              {nickname && <ReviewRow label="Nickname" value={nickname} />}
              {irrigationSource && (
                <ReviewRow
                  label="Irrigation"
                  value={IRRIGATION_OPTIONS.find((o) => o.value === irrigationSource)?.label || irrigationSource}
                />
              )}
              <ReviewRow
                label="Ownership"
                value={OWNERSHIP_OPTIONS.find((o) => o.value === ownershipType)?.label || ownershipType}
              />
              {ownershipType === "leased" && (
                <>
                  <ReviewRow label="Lessor" value={lessorName} />
                  <ReviewRow label="Lease period" value={`${leaseStartDate} to ${leaseEndDate}`} />
                </>
              )}
              <ReviewRow label="Boundary" value="Drawn (see map)" />

              {error && (
                <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <div className="flex justify-between border-t border-slate-100 pt-4">
                <Button variant="ghost" onClick={() => setStep(3)} disabled={isSubmitting}>
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
                <Button onClick={handleSubmit} disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Registering...
                    </>
                  ) : (
                    <>
                      <Check className="h-4 w-4" />
                      Register Plot
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between border-b border-slate-100 pb-2">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="ml-4 text-right text-sm font-medium text-slate-900">{value}</span>
    </div>
  );
}
