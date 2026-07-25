"use client";

import { useState, useEffect } from "react";
import {
  CreditCard,
  Smartphone,
  Loader2,
  CheckCircle2,
  XCircle,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatINR } from "@/lib/utils";

interface PaymentCheckoutProps {
  paymentType: "marketplace_order" | "insurance_premium";
  referenceId: string;
  referenceType: string;
  amount: number;
  description?: string;
  onSuccess: (paymentId: string) => void;
  onFailure: (error: string) => void;
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
  const [step, setStep] = useState<"idle" | "checkout" | "processing" | "success" | "failed">("idle");
  const [paymentData, setPaymentData] = useState<CreatePaymentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

  async function startPayment() {
    setIsLoading(true);
    setError(null);

    try {
      // Step 1: Create payment on backend
      const response = await fetch(`${API_BASE}/payments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("krishisetu.access_token")}`,
        },
        body: JSON.stringify({
          payment_type: paymentType,
          reference_id: referenceId,
          reference_type: referenceType,
          amount,
          description,
        }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err?.error?.message || "Failed to create payment");
      }

      const data: CreatePaymentResponse = await response.json();
      setPaymentData(data);
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

    setStep("processing");

    // Load Razorpay checkout script
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;

    script.onload = () => {
      const options = {
        key: paymentData.razorpay_key,
        amount: Math.round(amount * 100), // Convert to paise
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
            setStep("checkout");
            setError("Payment cancelled");
          },
        },
      };

      const rzp = new (window as any).Razorpay(options);
      rzp.on("payment.failed", function (resp: any) {
        setStep("failed");
        setError(resp.error?.description || "Payment failed");
        onFailure(resp.error?.description || "Payment failed");
      });
      rzp.open();
    };

    script.onerror = () => {
      setStep("failed");
      setError("Failed to load payment gateway");
      onFailure("Failed to load payment gateway");
    };

    document.body.appendChild(script);
  }

  async function openUPI() {
    if (!paymentData?.upi_intent_url) return;

    // Open UPI app via deep link
    window.location.href = paymentData.upi_intent_url;

    // Show processing state (user will come back to verify)
    setStep("processing");
  }

  async function verifyPayment(response: Record<string, string>) {
    if (!paymentData) return;

    try {
      const verifyResponse = await fetch(`${API_BASE}/payments/${paymentData.payment_id}/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("krishisetu.access_token")}`,
        },
        body: JSON.stringify({
          payment_id: paymentData.payment_id,
          provider_payment_id: response.razorpay_payment_id,
          provider_order_id: response.razorpay_order_id,
          provider_signature: response.razorpay_signature,
        }),
      });

      if (!verifyResponse.ok) {
        const err = await verifyResponse.json().catch(() => ({}));
        throw new Error(err?.error?.message || "Payment verification failed");
      }

      setStep("success");
      onSuccess(paymentData.payment_id);
    } catch (err) {
      setStep("failed");
      const msg = err instanceof Error ? err.message : "Verification failed";
      setError(msg);
      onFailure(msg);
    }
  }

  if (step === "success") {
    return (
      <Card className="border-green-200 bg-green-50">
        <CardContent className="p-6 text-center">
          <CheckCircle2 className="mx-auto h-12 w-12 text-green-600" />
          <p className="mt-3 text-lg font-bold text-slate-900">Payment Successful!</p>
          <p className="mt-1 text-sm text-slate-600">
            Payment of {formatINR(amount)} completed successfully.
          </p>
          {paymentData && (
            <p className="mt-2 text-xs text-slate-400">
              Payment No: {paymentData.payment_number}
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
              setStep("idle");
              setError(null);
              setPaymentData(null);
            }}
          >
            Try Again
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
