"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Phone, ShieldCheck, Loader2, Mail, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP } from "@/components/ui/input-otp";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuthStore } from "@/stores/auth-store";
import { authApi } from "@/lib/api/client";

type AuthMethod = "otp" | "password" | "google";
type Step = "phone" | "otp";

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  google_denied: "You cancelled the Google sign-in. Try again or use phone OTP.",
  google_auth_failed: "Google authentication failed. Please try again.",
  google_server_error: "A server error occurred during Google sign-in. Please try again.",
  google_missing_tokens: "Incomplete Google sign-in. Please try again.",
  google_completion_failed: "Could not complete Google sign-in. Please try again.",
  google_invalid_callback: "Invalid Google callback. Please try again.",
};

export default function LoginPage() {
  const router = useRouter();
  const { loginWithOtp, loginWithPassword, isLoading, error, clearError } = useAuthStore();

  const [authMethod, setAuthMethod] = useState<AuthMethod>("otp");
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [googleErrorMessage, setGoogleErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const errorCode = params.get("error");
    if (errorCode) {
      setGoogleErrorMessage(
        GOOGLE_ERROR_MESSAGES[errorCode] ?? "Google sign-in failed. Please try again."
      );
    }
  }, []);

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  useEffect(() => {
    if (isAuthenticated) router.push("/dashboard");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => setResendCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const handleSendOtp = async () => {
    setPhoneError(null);
    clearError();
    const digits = phone.replace(/\D/g, "");
    let normalized = digits;
    if (normalized.startsWith("91") && normalized.length === 12) normalized = normalized.slice(2);
    if (normalized.length !== 10 || !/^[6-9]/.test(normalized)) {
      setPhoneError("Please enter a valid 10-digit Indian mobile number");
      return;
    }
    try {
      const response = await authApi.sendOtp(normalized, "login");
      setPhone(normalized);
      setStep("otp");
      setResendCooldown(response.cooldown_seconds);
    } catch (err) {
      setPhoneError(err instanceof Error ? err.message : "Failed to send OTP");
    }
  };

  // FIX: accepts otpValue directly — avoids reading stale React state
  // when called immediately from onChange on a 6-digit entry.
  const handleVerifyOtp = async (otpValue?: string) => {
    const code = otpValue ?? otp;
    if (code.length !== 6) return;
    clearError();
    try {
      await loginWithOtp(phone, code);
      router.push("/dashboard");
    } catch {
      // error surfaced from store
    }
  };

  const handleResendOtp = async () => {
    if (resendCooldown > 0) return;
    try {
      const response = await authApi.sendOtp(phone, "login");
      setResendCooldown(response.cooldown_seconds);
    } catch {
      // ignore
    }
  };

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    clearError();
    if (!email.trim() || !password) {
      setPasswordError("Please enter both email/phone and password");
      return;
    }
    try {
      await loginWithPassword(email, password);
      router.push("/dashboard");
    } catch {
      // error surfaced from store
    }
  };

  const handleGoogleLogin = () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    window.location.href = `${apiUrl}/api/v1/auth/google`;
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 py-12">
      <div className="mb-8">
        <Link href="/" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary">
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>
      </div>

      {googleErrorMessage && (
        <div className="mb-4 w-full max-w-md rounded-md border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">{googleErrorMessage}</p>
        </div>
      )}

      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-lg bg-primary">
            <ShieldCheck className="h-6 w-6 text-white" />
          </div>
          <CardTitle className="text-2xl">Welcome back</CardTitle>
          <CardDescription>
            {authMethod === "otp" && (step === "phone"
              ? "Enter your phone number to receive a login OTP"
              : `Enter the 6-digit code sent to +91 ${phone}`)}
            {authMethod === "password" && "Sign in with your email and password"}
            {authMethod === "google" && "Sign in with your Google account"}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* ── OTP: Phone input ── */}
          {authMethod === "otp" && step === "phone" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="phone">Phone Number</Label>
                <div className="relative">
                  <Phone className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="phone" type="tel" inputMode="numeric" placeholder="9876543210"
                    value={phone} onChange={(e) => setPhone(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSendOtp()}
                    className="pl-10" maxLength={13} />
                </div>
                {phoneError && <p className="text-sm text-red-600">{phoneError}</p>}
              </div>

              <Button onClick={handleSendOtp} className="w-full" disabled={isLoading}>
                {isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Sending OTP...</> : "Send OTP"}
              </Button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-white px-2 text-slate-500">Or continue with</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Button type="button" variant="secondary" onClick={() => setAuthMethod("password")} className="w-full">
                  <Mail className="mr-2 h-4 w-4" /> Email
                </Button>
                <Button type="button" variant="secondary" onClick={handleGoogleLogin} className="w-full">
                  <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                  </svg>
                  Google
                </Button>
              </div>

              <div className="text-center text-sm text-slate-600">
                Don&apos;t have an account?{" "}
                <Link href="/signup" className="font-medium text-primary hover:underline">Sign up</Link>
              </div>
            </>
          )}

          {/* ── OTP: Verify ── */}
          {authMethod === "otp" && step === "otp" && (
            <>
              <div className="space-y-3">
                <Label>Enter 6-digit code</Label>
                {/* FIX: removed onComplete (not in InputOTP API).
                    Completion detected in onChange by checking val.length === 6. */}
                <div className="flex justify-center">
                  <InputOTP
                    length={6}
                    value={otp}
                    onChange={(val) => {
                      setOtp(val);
                      if (val.length === 6) handleVerifyOtp(val);
                    }}
                  />
                </div>
                <p className="text-center text-xs text-slate-500">
                  Check your terminal/logs for the OTP in development mode
                </p>
              </div>

              {error && <p className="text-sm text-red-600 text-center">{error}</p>}

              <Button onClick={() => handleVerifyOtp()} className="w-full"
                disabled={otp.length !== 6 || isLoading}>
                {isLoading
                  ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Verifying...</>
                  : "Verify & Log In"}
              </Button>

              <div className="flex items-center justify-between text-sm text-slate-600">
                <button type="button" onClick={() => { setStep("phone"); setOtp(""); setPhoneError(null); clearError(); }}
                  className="hover:text-primary">
                  Change number
                </button>
                <button type="button" onClick={handleResendOtp} disabled={resendCooldown > 0}
                  className="hover:text-primary disabled:opacity-50 disabled:cursor-not-allowed">
                  {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend OTP"}
                </button>
              </div>
            </>
          )}

          {/* ── Password Login ── */}
          {authMethod === "password" && (
            <form onSubmit={handlePasswordLogin} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email or Phone</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="email" type="text" autoComplete="username"
                    placeholder="you@example.com or 9876543210"
                    value={email} onChange={(e) => setEmail(e.target.value)} className="pl-10" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="password" type="password" autoComplete="current-password" placeholder="••••••••"
                    value={password} onChange={(e) => setPassword(e.target.value)} className="pl-10" />
                </div>
                {passwordError && <p className="text-sm text-red-600">{passwordError}</p>}
              </div>

              {error && <p className="text-sm text-red-600 text-center">{error}</p>}

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Logging in...</> : "Log In"}
              </Button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-white px-2 text-slate-500">Or continue with</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Button type="button" variant="secondary"
                  onClick={() => { setAuthMethod("otp"); setStep("phone"); }} className="w-full">
                  <Phone className="mr-2 h-4 w-4" /> OTP
                </Button>
                <Button type="button" variant="secondary" onClick={handleGoogleLogin} className="w-full">
                  <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                  </svg>
                  Google
                </Button>
              </div>
            </form>
          )}

          {/* ── Google Login ── */}
          {authMethod === "google" && (
            <div className="space-y-4">
              <Button onClick={handleGoogleLogin} className="w-full" size="lg">
                <svg className="mr-2 h-5 w-5" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
                Continue with Google
              </Button>
              <div className="grid grid-cols-2 gap-3">
                <Button type="button" variant="secondary"
                  onClick={() => { setAuthMethod("otp"); setStep("phone"); }} className="w-full">
                  <Phone className="mr-2 h-4 w-4" /> OTP
                </Button>
                <Button type="button" variant="secondary" onClick={() => setAuthMethod("password")} className="w-full">
                  <Mail className="mr-2 h-4 w-4" /> Email
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="mt-6 max-w-md text-center text-xs text-slate-500">
        By logging in, you agree to KrishiSetu&apos;s{" "}
        <Link href="/terms" className="underline hover:text-primary">Terms of Service</Link>{" "}
        and{" "}
        <Link href="/privacy" className="underline hover:text-primary">Privacy Policy</Link>.
      </p>
    </div>
  );
}