"use client";

import { useState, useEffect, useRef } from "react";
import {
  CreditCard,
  Smartphone,
  Loader2,
  CheckCircle2,
  XCircle,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiFetch } from "@/lib/api/client";
import { formatINR } from "@/lib/utils";

/**
 * The backend rejects a reference_type that doesn't match the payment_type,
 * so the two travel as a discriminated union rather than a free-form string.
 * Only client-initiated types exist here — insurance_payout and refund are
 * platform-initiated and are refused at create.
 */
type PaymentTarget =
  | {
      paymentType: "marketplace_order";
      referenceType: "order" | "marketplace_order";
    }
  | {
      paymentType: "insurance_premium";
      referenceType: "insurance_policy" | "policy";
    };

type PaymentCheckoutProps = PaymentTarget & {
  referenceId: string;
  /** Display only — the server derives the charged amount from reference_id. */
  amount: number;
  description?: string;
  onSuccess: (paymentId: string) => void;
  onFailure: (error: string) => void;
};

/**
 * Every value of the backend's PaymentStatus enum (payment/models.py:53-76).
 * Kept exhaustive on purpose: the classifier below switches over all nine, so
 * adding a status server-side without updating this list is a type error here
 * rather than a silent fall-through at runtime.
 */
type PaymentStatus =
  | "created"
  | "pending"
  | "authorized"
  | "captured"
  | "failed"
  | "refunded"
  | "partially_refunded"
  | "released"
  | "cancelled";

type StatusVerdict = "success" | "refunded" | "failure" | "in_flight";

/**
 * Non-escrow payments auto-release on capture, so insurance premiums settle on
 * "released" and marketplace orders on "captured" — both mean paid.
 *
 * "refunded" / "partially_refunded" are deliberately NOT success. They are
 * reachable here because a captured payment can be refunded later, and showing
 * "Payment Successful" for money that has gone back is the worst outcome this
 * component can produce.
 */
/**
 * Runtime no-op. Its only job is to fail the build: in the default branch
 * below `known` narrows to `never` only while every PaymentStatus value has a
 * case. Add a status to the union without classifying it and this stops
 * compiling, which is the point — a new status must be an explicit decision,
 * not a silent fall-through.
 */
function assertAllStatusesHandled(_exhaustive: never): void {}

function classifyPaymentStatus(status: string): StatusVerdict {
  const known = status as PaymentStatus;

  switch (known) {
    case "captured":
    case "released":
      return "success";
    case "refunded":
    case "partially_refunded":
      return "refunded";
    case "failed":
    case "cancelled":
      return "failure";
    case "created":
    case "pending":
    case "authorized":
      return "in_flight";
    default:
      // Compile-time: every PaymentStatus is handled above, so `known` is
      // `never` here. Runtime: a status the server invented after this shipped
      // must never be read as success — treat it as still settling and let the
      // attempt budget end the poll in the honest "unresolved" state.
      assertAllStatusesHandled(known);
      return "in_flight";
  }
}

/** sessionStorage key that survives the UPI deep-link round trip. */
const PENDING_PAYMENT_KEY = "krishisetu_pending_payment";
const POLL_INTERVAL_MS = 3000;
const POLL_MAX_ATTEMPTS = 20; // ~60s, then stop and say so rather than guess.

/** Only the fields this component reads off PaymentResponse. */
interface PaymentStatusResponse {
  id: string;
  status: string;
  payment_number: string;
  amount: number;
  amount_refunded: number;
}

/**
 * What was actually collected. Never render `amount` on its own: a partially
 * refunded payment still carries its original amount, so showing that figure
 * overstates what the user paid.
 */
function netCollected(payment: PaymentStatusResponse): number {
  return payment.amount - payment.amount_refunded;
}

interface CreatePaymentResponse {
  payment_id: string;
  payment_number: string;
  amount: number;
  status: string;
  provider: string;
  provider_order_id: string;
  razorpay_key: string;
  checkout_options: Record<string, unknown>;
  upi_intent_url: string;
}

export function PaymentCheckout({
  paymentType,
  referenceId,
  referenceType,
  amount,
  description,
  onSuccess,
  onFailure,
}: PaymentCheckoutProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [step, setStep] = useState<
    "idle" | "checkout" | "processing" | "verifying" | "success" | "failed" | "unresolved"
  >("idle");
  const [paymentData, setPaymentData] = useState<CreatePaymentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** Payment being polled — outlives paymentData across a UPI round trip. */
  const [trackedPaymentId, setTrackedPaymentId] = useState<string | null>(null);
  /**
   * The server's own record, once polling has seen it. On the UPI resume path
   * paymentData is null (the page reloaded), so this is the only source for
   * the payment number and the real collected amount.
   */
  const [settledPayment, setSettledPayment] = useState<PaymentStatusResponse | null>(null);
  /**
   * Identifies the currently-valid poll run. A shared abort boolean is not
   * enough: under StrictMode the effect runs mount → cleanup → mount, and the
   * second mount would reset the flag and revive the orphaned first loop,
   * leaving two pollers hitting the API. Bumping this invalidates any run that
   * isn't the latest.
   */
  const pollRunRef = useRef(0);

  // --- pending-payment handoff -------------------------------------------
  // The UPI button navigates away from the page entirely, so component state
  // is gone when the user returns. The payment id is parked in sessionStorage
  // so the remount can pick the payment back up and ask the server how it went.

  function rememberPendingPayment(paymentId: string) {
    setTrackedPaymentId(paymentId);
    if (typeof window === "undefined") return;
    window.sessionStorage.setItem(
      PENDING_PAYMENT_KEY,
      JSON.stringify({ payment_id: paymentId, reference_id: referenceId }),
    );
  }

  function forgetPendingPayment() {
    if (typeof window === "undefined") return;
    window.sessionStorage.removeItem(PENDING_PAYMENT_KEY);
  }

  function readPendingPayment(): string | null {
    if (typeof window === "undefined") return null;
    const raw = window.sessionStorage.getItem(PENDING_PAYMENT_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as {
        payment_id?: string;
        reference_id?: string;
      };
      // Only resume a payment belonging to the thing we're currently checking
      // out — a stale key from another order must not settle this one.
      if (parsed.reference_id !== referenceId) return null;
      return parsed.payment_id ?? null;
    } catch {
      return null;
    }
  }

  // --- status polling -----------------------------------------------------

  function settle(
    verdict: Exclude<StatusVerdict, "in_flight">,
    paymentId: string,
    payment: PaymentStatusResponse,
  ) {
    forgetPendingPayment();

    if (verdict === "success") {
      setStep("success");
      onSuccess(paymentId);
      return;
    }

    let msg: string;
    if (verdict === "refunded") {
      // Quote the real figures — a refunded payment still carries its original
      // amount, so "your payment of <amount>" would misstate what was kept.
      msg =
        payment.status === "partially_refunded"
          ? `This payment was partially refunded — ${formatINR(payment.amount_refunded)} of ${formatINR(payment.amount)} was returned, so it is not being treated as paid.`
          : `This payment was refunded — ${formatINR(payment.amount_refunded)} was returned, so it is not being treated as paid.`;
    } else {
      msg = "Payment failed";
    }

    setStep("failed");
    setError(msg);
    onFailure(msg);
  }

  /**
   * Ask the server what actually happened, rather than trusting a single
   * in-page callback. Bounded: stops on any terminal status, on unmount, or
   * after POLL_MAX_ATTEMPTS — never spins indefinitely against the API.
   */
  async function pollUntilSettled(paymentId: string) {
    setTrackedPaymentId(paymentId);
    // Claim this run; any earlier loop still in flight is now stale and exits.
    const runId = ++pollRunRef.current;

    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
      if (pollRunRef.current !== runId) return;

      try {
        const payment = await apiFetch<PaymentStatusResponse>(`/payments/${paymentId}`);
        if (pollRunRef.current !== runId) return;

        const verdict = classifyPaymentStatus(payment.status);
        if (verdict !== "in_flight") {
          // Record the server's version before settling — the UI reads amounts
          // and the payment number off this, not off the display props.
          setSettledPayment(payment);
          settle(verdict, paymentId, payment);
          return;
        }
      } catch {
        // Transient — a network blip or an in-flight token refresh. The payment
        // may still be settling server-side, so keep asking rather than
        // declaring a failure we haven't confirmed.
      }

      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }

    if (pollRunRef.current !== runId) return;
    // Budget exhausted with no terminal status. Say exactly that — do not
    // guess in either direction while money may have moved.
    setStep("unresolved");
  }

  // Resume an interrupted payment (the UPI deep-link return path).
  useEffect(() => {
    const resumeId = readPendingPayment();
    if (resumeId) {
      setStep("verifying");
      void pollUntilSettled(resumeId);
    }

    return () => {
      // Invalidate whatever run is in flight; it exits at its next checkpoint.
      pollRunRef.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referenceId]);

  async function startPayment() {
    setIsLoading(true);
    setError(null);

    try {
      // Step 1: Create payment on backend.
      // The amount is NEVER sent from the client — the server derives it from
      // reference_id. The `amount` prop is display-only.
      const data = await apiFetch<CreatePaymentResponse>("/payments", {
        method: "POST",
        body: JSON.stringify({
          payment_type: paymentType,
          reference_id: referenceId,
          reference_type: referenceType,
          description,
        }),
      });

      setPaymentData(data);
      setTrackedPaymentId(data.payment_id);
      setStep("checkout");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Payment creation failed";
      setError(msg);
      onFailure(msg);
    } finally {
      setIsLoading(false);
    }
  }

  async function openRazorpayCheckout() {
    if (!paymentData) return;

    // From here the user is on a payment surface — if the tab reloads before
    // the callback fires, the remount must be able to resume this payment.
    rememberPendingPayment(paymentData.payment_id);
    setStep("processing");

    // Load Razorpay checkout script
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;

    script.onload = () => {
      const options = {
        key: paymentData.razorpay_key,
        amount: Math.round(paymentData.amount * 100), // Server-derived ₹ → paise
        currency: "INR",
        name: "KrishiSetu",
        description: description || `Payment ${paymentData.payment_number}`,
        order_id: paymentData.provider_order_id,
        theme: { color: "#4CAF50" },
        method: { upi: true, card: true, netbanking: true, wallet: true },
        handler: async function (response: Record<string, string>) {
          // Payment successful — verify on backend
          await verifyPayment(response);
        },
        modal: {
          ondismiss: function () {
            // Closed without paying — drop the handoff so a later remount
            // doesn't sit and poll a payment that was never attempted.
            forgetPendingPayment();
            setStep("checkout");
            setError("Payment cancelled");
          },
        },
      };

      const rzp = new (window as any).Razorpay(options);
      rzp.on("payment.failed", function (resp: any) {
        forgetPendingPayment();
        setStep("failed");
        setError(resp.error?.description || "Payment failed");
        onFailure(resp.error?.description || "Payment failed");
      });
      rzp.open();
    };

    script.onerror = () => {
      // Gateway never loaded, so no money moved.
      forgetPendingPayment();
      setStep("failed");
      setError("Failed to load payment gateway");
      onFailure("Failed to load payment gateway");
    };

    document.body.appendChild(script);
  }

  async function openUPI() {
    if (!paymentData?.upi_intent_url) return;

    // This navigates away from the page entirely, so there is no callback to
    // come back to — the payment id is parked first and the remount effect
    // resumes by polling the server for the real outcome.
    rememberPendingPayment(paymentData.payment_id);

    // Open UPI app via deep link
    window.location.href = paymentData.upi_intent_url;

    // Also poll from here: on desktop, or with no UPI app installed, the deep
    // link never navigates and the remount effect would never run — without
    // this the user sits on a spinner forever.
    setStep("verifying");
    void pollUntilSettled(paymentData.payment_id);
  }

  async function verifyPayment(response: Record<string, string>) {
    if (!paymentData) return;

    try {
      // Razorpay has already captured the money at this point — this call must
      // go through apiFetch so an expired access token is refreshed and retried
      // instead of leaving the payment captured-but-unverified.
      await apiFetch(`/payments/${paymentData.payment_id}/verify`, {
        method: "POST",
        body: JSON.stringify({
          payment_id: paymentData.payment_id,
          provider_payment_id: response.razorpay_payment_id,
          provider_order_id: response.razorpay_order_id,
          provider_signature: response.razorpay_signature,
        }),
      });

      forgetPendingPayment();
      setStep("success");
      onSuccess(paymentData.payment_id);
    } catch {
      // A failed verify is NOT a failed payment. Razorpay may already have
      // captured, and the webhook reconciles capture server-side, so the
      // payment record is the authority — not this one request. Fall back to
      // polling it instead of telling the user their payment failed.
      setStep("verifying");
      void pollUntilSettled(paymentData.payment_id);
    }
  }

  if (step === "success") {
    return (
      <Card className="border-green-200 bg-green-50">
        <CardContent className="p-6 text-center">
          <CheckCircle2 className="mx-auto h-12 w-12 text-green-600" />
          <p className="mt-3 text-lg font-bold text-slate-900">Payment Successful!</p>
          <p className="mt-1 text-sm text-slate-600">
            Payment of{" "}
            {formatINR(
              // Prefer what the server says was collected. `amount` is the
              // display prop and is only a fallback when neither the create
              // response nor a poll result is available.
              settledPayment
                ? netCollected(settledPayment)
                : (paymentData?.amount ?? amount),
            )}{" "}
            completed successfully.
          </p>
          {(settledPayment ?? paymentData) && (
            <p className="mt-2 text-xs text-slate-400">
              Payment No: {(settledPayment ?? paymentData)!.payment_number}
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  if (step === "failed") {
    return (
      <Card className="border-red-200 bg-red-50">
        <CardContent className="p-6 text-center">
          <XCircle className="mx-auto h-12 w-12 text-red-600" />
          <p className="mt-3 text-lg font-bold text-slate-900">Payment Failed</p>
          <p className="mt-1 text-sm text-red-700">{error}</p>
          <Button
            className="mt-4"
            variant="outline"
            onClick={() => {
              forgetPendingPayment();
              setStep("idle");
              setError(null);
              setPaymentData(null);
              setTrackedPaymentId(null);
              setSettledPayment(null);
            }}
          >
            Try Again
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (step === "verifying") {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <Loader2 className="mx-auto h-12 w-12 animate-spin text-primary" />
          <p className="mt-3 text-lg font-bold text-slate-900">Confirming your payment…</p>
          <p className="mt-1 text-sm text-slate-600">
            We&apos;re checking with the bank. This can take up to a minute —
            please don&apos;t close this page or pay again.
          </p>
        </CardContent>
      </Card>
    );
  }

  // Polling ran out of attempts without the payment reaching a terminal state.
  // Money may or may not have moved, so this deliberately claims neither —
  // "Try Again" is not offered here because retrying could double-charge.
  if (step === "unresolved") {
    return (
      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="p-6 text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-amber-600" />
          <p className="mt-3 text-lg font-bold text-slate-900">
            We couldn&apos;t confirm your payment
          </p>
          <p className="mt-1 text-sm text-slate-700">
            Your payment is still being processed. If money has left your
            account it will be recorded automatically — please do not pay again.
          </p>
          {(settledPayment ?? paymentData) && (
            <p className="mt-2 text-xs text-slate-500">
              Payment No: {(settledPayment ?? paymentData)!.payment_number}
            </p>
          )}
          <Button
            className="mt-4"
            variant="outline"
            onClick={() => {
              if (!trackedPaymentId) return;
              setStep("verifying");
              void pollUntilSettled(trackedPaymentId);
            }}
          >
            Check again
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (step === "processing") {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <Loader2 className="mx-auto h-12 w-12 animate-spin text-primary" />
          <p className="mt-3 text-lg font-bold text-slate-900">Processing Payment...</p>
          <p className="mt-1 text-sm text-slate-600">
            Please wait while we process your payment. Do not close this page.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (step === "checkout" && paymentData) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Choose Payment Method</CardTitle>
          <CardDescription>
            Pay {formatINR(amount)} via your preferred method
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            className="w-full h-14"
            onClick={openRazorpayCheckout}
          >
            <CreditCard className="h-5 w-5" />
            Pay with Razorpay (UPI / Card / NetBanking)
          </Button>

          {paymentData.upi_intent_url && (
            <Button
              variant="secondary"
              className="w-full h-14"
              onClick={openUPI}
            >
              <Smartphone className="h-5 w-5" />
              Pay via UPI App (Direct)
            </Button>
          )}

          <div className="flex items-center justify-center gap-1 text-xs text-slate-400 pt-2">
            <ShieldCheck className="h-3 w-3" />
            <span>Secured by Razorpay · 256-bit SSL</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Initial state
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CreditCard className="h-5 w-5 text-primary" />
          Payment Required
        </CardTitle>
        <CardDescription>
          {description || `Complete payment to proceed`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md bg-slate-50 p-4 text-center">
          <p className="text-xs text-slate-500">Amount to Pay</p>
          <p className="text-3xl font-bold text-primary">{formatINR(amount)}</p>
        </div>

        <Button
          className="w-full h-12"
          onClick={startPayment}
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Initializing Payment...
            </>
          ) : (
            <>
              <CreditCard className="h-4 w-4" />
              Pay Now
            </>
          )}
        </Button>

        {error && <p className="text-sm text-red-600 text-center">{error}</p>}

        <div className="flex items-center justify-center gap-1 text-xs text-slate-400">
          <ShieldCheck className="h-3 w-3" />
          <span>Secured by Razorpay · 256-bit SSL</span>
        </div>
      </CardContent>
    </Card>
  );
}
