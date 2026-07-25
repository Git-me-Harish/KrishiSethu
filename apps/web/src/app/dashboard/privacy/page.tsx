"use client";

/**
 * Privacy & Data Rights Center.
 *
 * Aggregates all DPDP Act 2023 rights in one page:
 * - Consent management (grant / withdraw per purpose)
 * - Data Subject Requests (access, correction, portability)
 * - Account erasure (permanent deletion)
 * - Grievance redressal (file complaints)
 *
 * The page is organized into four cards, each linking to a detailed sub-page
 * or containing an inline form. Design follows the KrishiSetu dashboard
 * pattern: cards on a soft gray background, primary actions in green.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Shield,
  Eye,
  Download,
  Trash2,
  MessageSquareWarning,
  Check,
  X,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { consentApi, privacyApi } from "@/lib/api/client";
import type {
  ConsentPurpose,
  ConsentStatusResponse,
  DataSubjectRequest,
  DSRType,
  Grievance,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn, formatDate } from "@/lib/utils";

const PURPOSE_LABELS: Record<ConsentPurpose, string> = {
  identity_verification: "Identity Verification",
  disease_diagnosis: "Disease Diagnosis",
  weather_advisory: "Weather Advisory",
  ndvi_monitoring: "NDVI Monitoring",
  insurance_processing: "Insurance Processing",
  marketplace_transactions: "Marketplace Transactions",
  scheme_matching: "Scheme Matching",
  voice_processing: "Voice Processing",
  communication: "SMS & Notifications",
  research_anonymized: "Anonymized Research",
  service_improvement: "Service Improvement",
};

export default function PrivacyPage() {
  const { user } = useAuthStore();
  const [consent, setConsent] = useState<ConsentStatusResponse | null>(null);
  const [dsrs, setDsrs] = useState<DataSubjectRequest[]>([]);
  const [grievances, setGrievances] = useState<Grievance[]>([]);
  const [loading, setLoading] = useState(true);

  // DSR filing form state
  const [dsrType, setDsrType] = useState<DSRType>("access");
  const [dsrDescription, setDsrDescription] = useState("");
  const [filingDsr, setFilingDsr] = useState(false);

  // Grievance form state
  const [grievanceCategory, setGrievanceCategory] = useState("data_quality");
  const [grievanceSubject, setGrievanceSubject] = useState("");
  const [grievanceDescription, setGrievanceDescription] = useState("");
  const [filingGrievance, setFilingGrievance] = useState(false);

  // Erasure state
  const [showErasureConfirm, setShowErasureConfirm] = useState(false);
  const [erasurePhrase, setErasurePhrase] = useState("");
  const [erasing, setErasing] = useState(false);

  useEffect(() => {
    void loadAll();
  }, []);

  async function loadAll() {
    try {
      const [c, d, g] = await Promise.all([
        consentApi.getStatus().catch(() => null),
        privacyApi.listDsrs().catch(() => []),
        privacyApi.listGrievances().catch(() => []),
      ]);
      setConsent(c);
      setDsrs(d);
      setGrievances(g);
    } finally {
      setLoading(false);
    }
  }

  async function toggleConsent(purpose: ConsentPurpose, currentlyGranted: boolean) {
    try {
      if (currentlyGranted) {
        await consentApi.withdraw([purpose], "User withdrew from privacy center");
      } else {
        await consentApi.grant([purpose]);
      }
      const updated = await consentApi.getStatus();
      setConsent(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update consent");
    }
  }

  async function fileDsr() {
    setFilingDsr(true);
    try {
      await privacyApi.fileDsr({
        request_type: dsrType,
        description: dsrDescription || undefined,
      });
      setDsrDescription("");
      const updated = await privacyApi.listDsrs();
      setDsrs(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to file request");
    } finally {
      setFilingDsr(false);
    }
  }

  async function fileGrievance() {
    if (!grievanceSubject.trim() || !grievanceDescription.trim()) {
      alert("Please fill in subject and description");
      return;
    }
    setFilingGrievance(true);
    try {
      await privacyApi.fileGrievance({
        category: grievanceCategory,
        subject: grievanceSubject,
        description: grievanceDescription,
      });
      setGrievanceSubject("");
      setGrievanceDescription("");
      const updated = await privacyApi.listGrievances();
      setGrievances(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to file grievance");
    } finally {
      setFilingGrievance(false);
    }
  }

  async function confirmErasure() {
    if (erasurePhrase !== "DELETE MY ACCOUNT") {
      alert('Please type exactly "DELETE MY ACCOUNT" to confirm');
      return;
    }
    setErasing(true);
    try {
      await privacyApi.confirmErasure();
      // User is now logged out
      window.location.href = "/";
    } catch (err) {
      alert(err instanceof Error ? err.message : "Erasure failed");
      setErasing(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-pulse text-gray-500">Loading privacy center…</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-primary-50 p-2.5">
          <Shield className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Privacy & Data Rights</h1>
          <p className="text-sm text-gray-600">
            Manage your data under the Digital Personal Data Protection Act 2023
          </p>
        </div>
      </div>

      {/* Consent management */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Check className="h-5 w-5 text-primary" />
            Consent Management
          </CardTitle>
          <CardDescription>
            Control which purposes we can process your data for. You can revoke
            consent at any time — features that depend on a withdrawn consent
            will be disabled until you re-grant.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!consent ? (
            <p className="text-sm text-gray-500">Unable to load consent state.</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(PURPOSE_LABELS).map(([purpose, label]) => {
                const p = purpose as ConsentPurpose;
                const isGranted = consent.granted.includes(p);
                const isRequired = p === "identity_verification";
                return (
                  <div
                    key={purpose}
                    className="flex items-center justify-between p-3 rounded-lg border border-gray-200"
                  >
                    <div className="flex-1">
                      <div className="font-medium text-gray-900 text-sm">
                        {label}
                        {isRequired && (
                          <span className="ml-2 text-[10px] uppercase tracking-wide bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                            Required
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => !isRequired && toggleConsent(p, isGranted)}
                      disabled={isRequired}
                      className={cn(
                        "relative inline-flex h-6 w-11 items-center rounded-full transition",
                        isGranted ? "bg-primary" : "bg-gray-200",
                        isRequired && "opacity-60 cursor-not-allowed",
                      )}
                    >
                      <span
                        className={cn(
                          "inline-block h-4 w-4 transform rounded-full bg-white transition",
                          isGranted ? "translate-x-6" : "translate-x-1",
                        )}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Data Subject Requests */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Download className="h-5 w-5 text-primary" />
            Data Subject Requests
          </CardTitle>
          <CardDescription>
            Exercise your rights: access your data, request corrections, export
            your data, or restrict processing. SLA: 15-30 days depending on type.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-3">
            <select
              value={dsrType}
              onChange={(e) => setDsrType(e.target.value as DSRType)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="access">Access my data</option>
              <option value="correction">Request correction</option>
              <option value="portability">Export (portability)</option>
              <option value="restriction">Restrict processing</option>
            </select>
            <div className="flex gap-2">
              <input
                type="text"
                value={dsrDescription}
                onChange={(e) => setDsrDescription(e.target.value)}
                placeholder="Optional: describe what you need"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <Button onClick={fileDsr} disabled={filingDsr}>
                {filingDsr ? "Filing..." : "File request"}
              </Button>
            </div>
          </div>

          {dsrs.length > 0 && (
            <div className="border-t pt-4">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Your requests</h4>
              <div className="space-y-2">
                {dsrs.map((dsr) => (
                  <div
                    key={dsr.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-gray-50 text-sm"
                  >
                    <div>
                      <span className="font-medium capitalize">{dsr.request_type}</span>
                      <span className="text-gray-500 ml-2">— filed {formatDate(dsr.submitted_at)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <DsrStatusBadge status={dsr.status} />
                      <span className="text-xs text-gray-500">
                        due {formatDate(dsr.due_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Grievances */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquareWarning className="h-5 w-5 text-primary" />
            Grievance Redressal
          </CardTitle>
          <CardDescription>
            File a complaint under DPDP Section 13. We must acknowledge within
            24 hours and resolve within 30 days. If unresolved, you can escalate
            to the Data Protection Board of India.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-3">
            <select
              value={grievanceCategory}
              onChange={(e) => setGrievanceCategory(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="unauthorized_access">Unauthorized data access</option>
              <option value="consent_violation">Consent violation</option>
              <option value="data_quality">Incorrect data</option>
              <option value="excessive_collection">Excessive data collection</option>
              <option value="retention_violation">Data retained too long</option>
              <option value="other">Other</option>
            </select>
            <input
              type="text"
              value={grievanceSubject}
              onChange={(e) => setGrievanceSubject(e.target.value)}
              placeholder="Brief subject (max 200 chars)"
              maxLength={200}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <textarea
            value={grievanceDescription}
            onChange={(e) => setGrievanceDescription(e.target.value)}
            placeholder="Describe your grievance in detail (max 5000 chars)"
            maxLength={5000}
            rows={4}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary resize-y"
          />
          <div className="flex justify-end">
            <Button onClick={fileGrievance} disabled={filingGrievance}>
              {filingGrievance ? "Filing..." : "File grievance"}
            </Button>
          </div>

          {grievances.length > 0 && (
            <div className="border-t pt-4">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Your grievances</h4>
              <div className="space-y-2">
                {grievances.map((g) => (
                  <div
                    key={g.id}
                    className="p-3 rounded-lg bg-gray-50 text-sm"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-xs text-gray-600">{g.grievance_number}</span>
                      <GrievanceStatusBadge status={g.status} />
                    </div>
                    <div className="font-medium text-gray-900">{g.subject}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      Filed {formatDate(g.filed_at)} • Due {formatDate(g.due_at)}
                    </div>
                    {g.resolution && (
                      <div className="mt-2 p-2 bg-white rounded text-xs text-gray-700">
                        <strong>Resolution:</strong> {g.resolution}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Erasure */}
      <Card className="border-red-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-red-700">
            <Trash2 className="h-5 w-5" />
            Delete My Account
          </CardTitle>
          <CardDescription>
            Permanently delete your account and all personal data. This action
            cannot be undone. Payment records will be anonymized (kept for tax
            compliance). Audit logs will be anonymized (kept for security).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!showErasureConfirm ? (
            <Button
              variant="outline"
              className="text-red-700 border-red-300 hover:bg-red-50"
              onClick={() => setShowErasureConfirm(true)}
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              I want to delete my account
            </Button>
          ) : (
            <div className="space-y-3 p-4 bg-red-50 rounded-lg">
              <div className="flex items-start gap-2 text-red-800">
                <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                <div className="text-sm">
                  <strong>This is permanent.</strong> Type{" "}
                  <code className="bg-white px-1.5 py-0.5 rounded text-xs">
                    DELETE MY ACCOUNT
                  </code>{" "}
                  to confirm.
                </div>
              </div>
              <input
                type="text"
                value={erasurePhrase}
                onChange={(e) => setErasurePhrase(e.target.value)}
                placeholder="DELETE MY ACCOUNT"
                className="w-full px-3 py-2 border border-red-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
              />
              <div className="flex gap-2 justify-end">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowErasureConfirm(false);
                    setErasurePhrase("");
                  }}
                  disabled={erasing}
                >
                  Cancel
                </Button>
                <Button
                  className="bg-red-600 hover:bg-red-700"
                  onClick={confirmErasure}
                  disabled={erasing || erasurePhrase !== "DELETE MY ACCOUNT"}
                >
                  {erasing ? "Deleting..." : "Permanently delete"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Footer link to detailed privacy notice */}
      <div className="text-center text-sm text-gray-500">
        Questions? Read our{" "}
        <Link href="/privacy-notice" className="text-primary hover:underline">
          Privacy Notice
        </Link>{" "}
        or contact our Grievance Officer at{" "}
        <a
          href="mailto:grievance@krishisetu.in"
          className="text-primary hover:underline"
        >
          grievance@krishisetu.in
        </a>
        .
      </div>
    </div>
  );
}

function DsrStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    submitted: "bg-gray-100 text-gray-700",
    acknowledged: "bg-blue-100 text-blue-700",
    in_review: "bg-amber-100 text-amber-700",
    processing: "bg-amber-100 text-amber-700",
    awaiting_verification: "bg-amber-100 text-amber-700",
    completed: "bg-green-100 text-green-700",
    rejected: "bg-red-100 text-red-700",
    withdrawn: "bg-gray-100 text-gray-700",
  };
  return (
    <span
      className={cn(
        "text-[10px] uppercase tracking-wide px-2 py-0.5 rounded",
        colors[status] ?? "bg-gray-100 text-gray-700",
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function GrievanceStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    filed: "bg-gray-100 text-gray-700",
    acknowledged: "bg-blue-100 text-blue-700",
    in_review: "bg-amber-100 text-amber-700",
    resolved: "bg-green-100 text-green-700",
    escalated: "bg-red-100 text-red-700",
    rejected: "bg-red-100 text-red-700",
  };
  return (
    <span
      className={cn(
        "text-[10px] uppercase tracking-wide px-2 py-0.5 rounded",
        colors[status] ?? "bg-gray-100 text-gray-700",
      )}
    >
      {status}
    </span>
  );
}
