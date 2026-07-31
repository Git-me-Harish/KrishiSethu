"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import {
  ArrowLeft,
  Loader2,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Sprout,
  ThumbsUp,
  ThumbsDown,
  ShieldCheck,
  FlaskConical,
  Beaker,
  Leaf,
  Sun,
  FileText,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { diseaseApi } from "@/lib/api/disease";
import type { DiseaseReport } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDateTime } from "@/lib/utils";

const STATUS_BADGE = {
  pending: { label: "Pending analysis", color: "bg-slate-100 text-slate-700", icon: Clock },
  processing: { label: "Analyzing", color: "bg-blue-50 text-blue-700", icon: Loader2 },
  completed: { label: "Diagnosis complete", color: "bg-green-50 text-green-700", icon: CheckCircle2 },
  failed: { label: "Analysis failed", color: "bg-red-50 text-red-700", icon: XCircle },
  officer_review: { label: "Under officer review", color: "bg-amber-50 text-amber-700", icon: AlertCircle },
  reviewed: { label: "Officer reviewed", color: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
} as const;

const TREATMENT_ICONS = {
  organic: Leaf,
  chemical: FlaskConical,
  biological: Beaker,
  cultural: Sun,
  preventive: ShieldCheck,
} as const;

export default function DiseaseReportDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const reportId = params?.id as string;

  const [report, setReport] = useState<DiseaseReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedbackGiven, setFeedbackGiven] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || !reportId) return;
    loadReport();
  }, [isAuthenticated, reportId]);

  // Poll for updates if report is pending or processing
  useEffect(() => {
    if (!report || !["pending", "processing"].includes(report.status)) return;
    const interval = setInterval(loadReport, 3000);
    return () => clearInterval(interval);
  }, [report?.status]);

  async function loadReport() {
    try {
      const data = await diseaseApi.getReport(reportId);
      setReport(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleFeedback(type: "correct" | "incorrect") {
    if (!report) return;
    try {
      await diseaseApi.submitFeedback(report.id, { feedback_type: type });
      setFeedbackGiven(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit feedback");
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

  if (error && !report) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <XCircle className="mx-auto h-12 w-12 text-red-500" />
            <p className="mt-3 text-sm font-medium text-slate-900">Report not found</p>
            <p className="mt-1 text-xs text-slate-500">{error}</p>
            <Link href="/dashboard/disease">
              <Button className="mt-4">Back to reports</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!report) return null;

  const badge = STATUS_BADGE[report.status];
  const BadgeIcon = badge.icon;
  const prediction = report.prediction;
  const disease = prediction?.disease;
  const isProcessing = ["pending", "processing"].includes(report.status);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard/disease" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to reports
          </Link>
          <h1 className="text-lg font-bold text-slate-900">Disease Report</h1>
          <div className="w-24" />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left: Image */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Submitted Photo</CardTitle>
            </CardHeader>
            <CardContent>
              <Image
                src={report.image_url}
                alt="Disease report"
                width={800}
                height={600}
                className="w-full rounded-md"
                unoptimized
              />
              <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                <Clock className="h-3 w-3" />
                Submitted {formatDateTime(report.created_at)}
              </div>
              {report.farmer_notes && (
                <div className="mt-3 rounded-md bg-slate-50 p-3">
                  <p className="text-xs font-medium text-slate-700">Your notes:</p>
                  <p className="mt-1 text-sm text-slate-600">{report.farmer_notes}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Right: Result */}
          <div className="space-y-6">
            {/* Status banner */}
            <div className={`flex items-center gap-3 rounded-md border p-4 ${badge.color}`}>
              <BadgeIcon className={`h-5 w-5 flex-shrink-0 ${report.status === "processing" ? "animate-spin" : ""}`} />
              <div className="flex-1">
                <p className="text-sm font-medium">{badge.label}</p>
                {isProcessing && (
                  <p className="text-xs opacity-80">
                    AI is analyzing your photo. This usually takes 5-15 seconds.
                  </p>
                )}
                {report.status === "failed" && report.failure_reason && (
                  <p className="text-xs opacity-80">{report.failure_reason}</p>
                )}
                {report.status === "officer_review" && (
                  <p className="text-xs opacity-80">
                    Confidence was below threshold. An agricultural officer will review and provide a manual diagnosis.
                  </p>
                )}
              </div>
            </div>

            {/* Prediction */}
            {prediction && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span className="text-lg">AI Diagnosis</span>
                    <span className={`text-2xl font-bold ${prediction.is_reliable ? "text-green-600" : "text-amber-600"}`}>
                      {(prediction.confidence * 100).toFixed(1)}%
                    </span>
                  </CardTitle>
                  <CardDescription>
                    Model: {prediction.model_name} {prediction.model_version} ·
                    Inference: {prediction.inference_time_ms}ms
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {disease ? (
                    <div className="space-y-3">
                      <div>
                        <h3 className="text-xl font-bold text-slate-900">{disease.name_en}</h3>
                        {disease.name_hi && (
                          <p className="text-sm text-slate-600">{disease.name_hi}</p>
                        )}
                        {disease.scientific_name && (
                          <p className="text-sm italic text-slate-500">{disease.scientific_name}</p>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium capitalize text-slate-700">
                          {disease.disease_type}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${SEVERITY_COLORS[disease.default_severity]}`}>
                          {disease.default_severity} severity
                        </span>
                        {disease.affected_crops.map((crop) => (
                          <span key={crop} className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary">
                            {crop}
                          </span>
                        ))}
                      </div>

                      {/* Symptoms */}
                      <div>
                        <h4 className="text-sm font-semibold text-slate-900">Symptoms</h4>
                        <p className="mt-1 text-sm text-slate-600">{disease.symptoms}</p>
                      </div>

                      {/* Cause */}
                      <div>
                        <h4 className="text-sm font-semibold text-slate-900">Cause</h4>
                        <p className="mt-1 text-sm text-slate-600">{disease.cause}</p>
                      </div>

                      {disease.favorable_conditions && (
                        <div>
                          <h4 className="text-sm font-semibold text-slate-900">Favorable Conditions</h4>
                          <p className="mt-1 text-sm text-slate-600">{disease.favorable_conditions}</p>
                        </div>
                      )}

                      {disease.prevention_measures && (
                        <div>
                          <h4 className="text-sm font-semibold text-slate-900">Prevention</h4>
                          <p className="mt-1 text-sm text-slate-600">{disease.prevention_measures}</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <h3 className="text-xl font-bold text-slate-900 capitalize">
                        {prediction.disease_slug.replace(/_/g, " ")}
                      </h3>
                      <p className="mt-1 text-sm text-slate-500">
                        Disease not in catalog. Consult an agricultural officer for details.
                      </p>
                    </div>
                  )}

                  {/* Other predictions */}
                  {prediction.all_predictions.length > 1 && (
                    <div className="mt-4 border-t border-slate-100 pt-3">
                      <h4 className="text-xs font-semibold uppercase text-slate-500">
                        Other possibilities
                      </h4>
                      <div className="mt-2 space-y-1">
                        {prediction.all_predictions.slice(1, 5).map((p) => (
                          <div key={p.disease_slug} className="flex items-center justify-between text-xs">
                            <span className="capitalize text-slate-700">
                              {p.disease_slug.replace(/_/g, " ")}
                            </span>
                            <span className="font-medium text-slate-500">
                              {(p.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Feedback */}
                  {report.status === "completed" && !feedbackGiven && (
                    <div className="mt-4 border-t border-slate-100 pt-3">
                      <h4 className="text-sm font-semibold text-slate-900">
                        Was this diagnosis correct?
                      </h4>
                      <p className="text-xs text-slate-500">
                        Your feedback helps improve the AI model.
                      </p>
                      <div className="mt-2 flex gap-2">
                        <Button size="sm" variant="outline" onClick={() => handleFeedback("correct")}>
                          <ThumbsUp className="h-4 w-4" />
                          Correct
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => handleFeedback("incorrect")}>
                          <ThumbsDown className="h-4 w-4" />
                          Incorrect
                        </Button>
                      </div>
                    </div>
                  )}
                  {feedbackGiven && (
                    <div className="mt-4 rounded-md bg-green-50 p-3 text-sm text-green-700">
                      <CheckCircle2 className="inline h-4 w-4 mr-1" />
                      Thanks for your feedback!
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Officer diagnosis */}
            {report.officer_diagnosis && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <ShieldCheck className="h-5 w-5 text-primary" />
                    Officer Diagnosis
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-700">{report.officer_diagnosis}</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>

        {/* Treatments */}
        {prediction?.treatments && prediction.treatments.length > 0 && (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FileText className="h-5 w-5 text-primary" />
                Treatment Recommendations
              </CardTitle>
              <CardDescription>
                Sourced from ICAR and agricultural university extension publications
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2">
                {prediction.treatments.map((treatment) => {
                  const Icon = TREATMENT_ICONS[treatment.treatment_type] || FlaskConical;
                  return (
                    <div
                      key={treatment.id}
                      className={`rounded-md border p-4 ${
                        treatment.is_primary
                          ? "border-primary/30 bg-primary/5"
                          : "border-slate-200"
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2">
                          <div className={`flex h-8 w-8 items-center justify-center rounded-md ${
                            treatment.is_primary ? "bg-primary-100 text-primary" : "bg-slate-100 text-slate-600"
                          }`}>
                            <Icon className="h-4 w-4" />
                          </div>
                          <div>
                            <span className="text-xs font-medium uppercase text-slate-500">
                              {treatment.treatment_type}
                            </span>
                            {treatment.is_primary && (
                              <span className="ml-2 rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary">
                                Primary
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <p className="mt-2 text-sm font-medium text-slate-900">
                        {treatment.description}
                      </p>
                      {treatment.dosage && (
                        <p className="mt-1 text-sm text-slate-600">
                          <span className="font-medium">Dosage:</span> {treatment.dosage}
                        </p>
                      )}
                      {treatment.application_method && (
                        <p className="mt-1 text-sm text-slate-600">
                          <span className="font-medium">How:</span> {treatment.application_method}
                        </p>
                      )}
                      {treatment.timing && (
                        <p className="mt-1 text-sm text-slate-600">
                          <span className="font-medium">When:</span> {treatment.timing}
                        </p>
                      )}
                      {treatment.precautions && (
                        <div className="mt-2 rounded bg-amber-50 p-2">
                          <p className="text-xs text-amber-800">
                            <span className="font-medium">Caution:</span> {treatment.precautions}
                          </p>
                        </div>
                      )}
                      {treatment.source && (
                        <p className="mt-2 text-xs italic text-slate-400">
                          Source: {treatment.source}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

const SEVERITY_COLORS = {
  low: "bg-blue-50 text-blue-700",
  moderate: "bg-amber-50 text-amber-700",
  high: "bg-orange-50 text-orange-700",
  critical: "bg-red-50 text-red-700",
} as const;
