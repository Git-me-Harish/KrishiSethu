"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Camera, Upload, Loader2, Sprout, X, CheckCircle2,
  AlertCircle, Image as ImageIcon,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { diseaseApi } from "@/lib/api/disease";
import { plotApi } from "@/lib/api/plots";
import type { PlotListResponse } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";

type UploadStep = "select" | "preview" | "uploading" | "submitted" | "error";

export default function DiseaseUploadPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<UploadStep>("select");
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [plotId, setPlotId] = useState<string>("");
  const [farmerNotes, setFarmerNotes] = useState("");
  const [plots, setPlots] = useState<PlotListResponse | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) router.push("/login");
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated) loadPlots();
  }, [isAuthenticated]);

  async function loadPlots() {
    try {
      const data = await plotApi.listMyPlots(1, 100);
      setPlots(data);
    } catch { /* non-critical — plot selection is optional */ }
  }

  const handleFileSelect = useCallback((file: File) => {
    if (!file.type.match(/^image\/(jpeg|png|webp)$/)) {
      setError("Please select a JPEG, PNG, or WebP image.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("Image must be under 10 MB.");
      return;
    }
    setError(null);
    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
    setStep("preview");
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  }, [handleFileSelect]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  const resetSelection = () => {
    setSelectedFile(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setStep("select");
  };

  async function handleSubmit() {
    if (!selectedFile) return;
    setStep("uploading");
    setUploadProgress(10);
    setError(null);
    try {
      // Step 1: Get pre-signed upload URL
      const contentType = selectedFile.type as "image/jpeg" | "image/png" | "image/webp";
      setUploadProgress(30);
      const imageKey = await diseaseApi.uploadImage(selectedFile, contentType);
      setUploadProgress(70);

      // Step 2: Submit the report
      const report = await diseaseApi.submitReport({
        image_key: imageKey,
        image_content_type: contentType,
        plot_id: plotId || undefined,
        farmer_notes: farmerNotes || undefined,
      });
      setUploadProgress(100);
      setStep("submitted");

      // Redirect to the report detail page after a brief delay
      setTimeout(() => {
        router.push(`/dashboard/disease/${report.id}`);
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
      setStep("error");
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
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/disease" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to reports
          </Link>
          <h1 className="text-lg font-bold text-slate-900">New Disease Report</h1>
          <div className="w-24" />
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <Card className="mb-6 border-red-200">
            <CardContent className="flex items-center gap-3 p-4">
              <AlertCircle className="h-5 w-5 flex-shrink-0 text-red-500" />
              <p className="flex-1 text-sm text-red-600">{error}</p>
              <Button variant="ghost" size="sm" onClick={() => { setError(null); setStep("preview"); }}>
                <X className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        )}

        {step === "select" && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Camera className="h-5 w-5 text-primary" />
                Upload a Photo
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                className="flex flex-col items-center justify-center cursor-pointer rounded-lg border-2 border-dashed border-slate-300 p-12 transition-colors hover:border-primary hover:bg-primary/5"
              >
                <ImageIcon className="h-12 w-12 text-slate-400" />
                <p className="mt-3 text-sm font-medium text-slate-900">
                  Click to select or drag & drop
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  JPEG, PNG, or WebP — max 10 MB
                </p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={handleFileInput}
                className="hidden"
              />
            </CardContent>
          </Card>
        )}

        {step === "preview" && previewUrl && (
          <Card>
            <CardHeader>
              <CardTitle>Review & Submit</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={previewUrl} alt="Preview" className="w-full rounded-lg" />
                <Button
                  variant="destructive"
                  size="sm"
                  className="absolute top-2 right-2"
                  onClick={resetSelection}
                >
                  <X className="h-4 w-4" />
                  Remove
                </Button>
              </div>

              {plots && plots.plots.length > 0 && (
                <div>
                  <Label htmlFor="plot">Link to plot (optional)</Label>
                  <select
                    id="plot"
                    value={plotId}
                    onChange={(e) => setPlotId(e.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="">— None —</option>
                    {plots.plots.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.nickname || `Survey ${p.survey_number}`} — {p.village}, {p.district}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <Label htmlFor="notes">Notes (optional)</Label>
                <textarea
                  id="notes"
                  value={farmerNotes}
                  onChange={(e) => setFarmerNotes(e.target.value)}
                  placeholder="Describe the symptoms you observed..."
                  rows={3}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  maxLength={2000}
                />
              </div>

              <Button onClick={handleSubmit} className="w-full" size="lg">
                <Upload className="h-4 w-4" />
                Submit for AI Diagnosis
              </Button>
            </CardContent>
          </Card>
        )}

        {step === "uploading" && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Loader2 className="h-12 w-12 animate-spin text-primary" />
              <p className="mt-4 text-sm font-medium text-slate-900">
                {uploadProgress < 30 ? "Preparing upload..." :
                 uploadProgress < 70 ? "Uploading image..." :
                 uploadProgress < 100 ? "Submitting for analysis..." :
                 "Almost done..."}
              </p>
              <div className="mt-3 h-2 w-48 overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {step === "submitted" && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <CheckCircle2 className="h-12 w-12 text-green-500" />
              <p className="mt-4 text-sm font-medium text-slate-900">
                Report submitted successfully!
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Redirecting to your report...
              </p>
            </CardContent>
          </Card>
        )}

        {step === "error" && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <AlertCircle className="h-12 w-12 text-red-500" />
              <p className="mt-4 text-sm font-medium text-slate-900">
                Something went wrong
              </p>
              <Button onClick={() => setStep("preview")} className="mt-4">
                Try Again
              </Button>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}