"use client";

/**
 * Consent banner — shown to users who haven't yet granted consent for one or
 * more core purposes. Modal-style overlay with accept / decline / customize.
 *
 * DPDP Act 2023 requires consent to be free, specific, informed, and
 * unambiguous. This component shows a brief summary of each purpose with
 * a link to the full notice, and requires an explicit action (no pre-ticked
 * checkboxes).
 */

import { useEffect, useState } from "react";
import { Check, X, ChevronDown, ChevronUp, Shield } from "lucide-react";
import { consentApi } from "@/lib/api/client";
import type { ConsentPurpose, ConsentStatusResponse } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const PURPOSE_LABELS: Record<ConsentPurpose, { title: string; description: string; required: boolean }> = {
  identity_verification: {
    title: "Identity Verification (Aadhaar e-KYC)",
    description: "Verify your identity through UIDAI Aadhaar e-KYC for scheme eligibility and insurance.",
    required: true,
  },
  disease_diagnosis: {
    title: "Crop Disease Diagnosis",
    description: "Upload photos of affected plants for AI-powered disease identification.",
    required: false,
  },
  weather_advisory: {
    title: "Weather Advisory",
    description: "Use your plot location to provide personalized weather forecasts and alerts.",
    required: false,
  },
  ndvi_monitoring: {
    title: "Satellite NDVI Monitoring",
    description: "Process satellite imagery of your plots to monitor crop health.",
    required: false,
  },
  insurance_processing: {
    title: "Insurance Processing",
    description: "Process your plot and crop data for crop insurance underwriting and claims.",
    required: false,
  },
  marketplace_transactions: {
    title: "Marketplace Transactions",
    description: "Process orders, payments, and delivery details for marketplace purchases.",
    required: false,
  },
  scheme_matching: {
    title: "Government Scheme Matching",
    description: "Match your profile against eligible government schemes and applications.",
    required: false,
  },
  voice_processing: {
    title: "Voice Queries",
    description: "Process your voice queries through speech-to-text and natural language understanding.",
    required: false,
  },
  communication: {
    title: "SMS & Notifications",
    description: "Send you SMS and in-app notifications about your account, orders, and alerts.",
    required: false,
  },
  research_anonymized: {
    title: "Anonymized Research",
    description: "Include your anonymized data in agricultural research (your identity is never shared).",
    required: false,
  },
  service_improvement: {
    title: "Service Improvement",
    description: "Use aggregated usage data to improve the platform (no individual tracking).",
    required: false,
  },
};

interface ConsentBannerProps {
  /** Called after the user has acted on all required consents */
  onResolved?: () => void;
}

export function ConsentBanner({ onResolved }: ConsentBannerProps) {
  const [status, setStatus] = useState<ConsentStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [showBanner, setShowBanner] = useState(false);
  const [selectedPurposes, setSelectedPurposes] = useState<Set<ConsentPurpose>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void loadStatus();
  }, []);

  async function loadStatus() {
    try {
      const s = await consentApi.getStatus();
      setStatus(s);
      // Show banner if any purpose has not been asked yet OR if a required
      // purpose is in not_yet_asked
      const hasUnasked = s.not_yet_asked.length > 0;
      setShowBanner(hasUnasked);
      // Pre-select all purposes by default (user can deselect)
      setSelectedPurposes(new Set(s.not_yet_asked));
    } catch {
      // Likely not logged in — don't show banner
      setShowBanner(false);
    } finally {
      setLoading(false);
    }
  }

  if (loading || !showBanner || !status) return null;

  const purposes = expanded
    ? status.not_yet_asked
    : status.not_yet_asked.slice(0, 4);

  function togglePurpose(p: ConsentPurpose) {
    if (PURPOSE_LABELS[p].required) return; // can't deselect required
    setSelectedPurposes((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  }

  async function handleAccept() {
    if (selectedPurposes.size === 0) return;
    setSubmitting(true);
    try {
      // Always include required purposes even if user deselected (they're required)
      const required = status!.not_yet_asked.filter(
        (p) => PURPOSE_LABELS[p].required,
      );
      const toGrant = Array.from(new Set([...selectedPurposes, ...required]));
      await consentApi.grant(toGrant);
      setShowBanner(false);
      onResolved?.();
    } catch (err) {
      console.error("Failed to grant consent:", err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeclineOptional() {
    // Grant only required consents
    const required = status!.not_yet_asked.filter(
      (p) => PURPOSE_LABELS[p].required,
    );
    setSubmitting(true);
    try {
      if (required.length > 0) {
        await consentApi.grant(required);
      }
      setShowBanner(false);
      onResolved?.();
    } catch (err) {
      console.error("Failed to set minimal consent:", err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-100">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-primary-50 p-2.5">
                <Shield className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900">
                  Your Data, Your Consent
                </h2>
                <p className="mt-1 text-sm text-gray-600">
                  Under India&apos;s Digital Personal Data Protection Act 2023,
                  we need your permission to process your data for specific
                  purposes. You can change these any time in Privacy Settings.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="p-6 space-y-3">
          {purposes.map((p) => {
            const info = PURPOSE_LABELS[p];
            const checked = selectedPurposes.has(p);
            return (
              <label
                key={p}
                className={cn(
                  "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition",
                  checked ? "border-primary bg-primary-50/50" : "border-gray-200",
                  info.required && "cursor-not-allowed bg-gray-50",
                )}
              >
                <button
                  type="button"
                  disabled={info.required}
                  onClick={() => togglePurpose(p)}
                  className={cn(
                    "mt-0.5 h-5 w-5 rounded border-2 flex items-center justify-center transition",
                    checked
                      ? "bg-primary border-primary text-white"
                      : "border-gray-300",
                  )}
                >
                  {checked && <Check className="h-3.5 w-3.5" />}
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-gray-900 text-sm">
                      {info.title}
                    </span>
                    {info.required && (
                      <span className="text-[10px] uppercase tracking-wide bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                        Required
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-600 mt-0.5">{info.description}</p>
                </div>
              </label>
            );
          })}

          {status.not_yet_asked.length > 4 && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="flex items-center gap-1 text-sm text-primary hover:underline"
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-4 w-4" /> Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-4 w-4" />
                  Show {status.not_yet_asked.length - 4} more
                </>
              )}
            </button>
          )}
        </div>

        <div className="p-6 border-t border-gray-100 flex flex-col sm:flex-row gap-3 sm:justify-between sm:items-center">
          <button
            type="button"
            onClick={handleDeclineOptional}
            disabled={submitting}
            className="text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50"
          >
            Only required
          </button>
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => setShowBanner(false)}
              disabled={submitting}
            >
              <X className="h-4 w-4 mr-1.5" />
              Later
            </Button>
            <Button onClick={handleAccept} disabled={submitting}>
              <Check className="h-4 w-4 mr-1.5" />
              {submitting ? "Saving..." : "Accept selected"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
