"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Phone, User, Loader2, ShieldCheck, Mail, Lock, Info } from "lucide-react";
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
type Step = "details" | "otp";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिन्दी (Hindi)" },
  { code: "mr", label: "मराठी (Marathi)" },
  { code: "ta", label: "தமிழ் (Tamil)" },
  { code: "te", label: "తెలుగు (Telugu)" },
  { code: "bn", label: "বাংলা (Bengali)" },
  { code: "kn", label: "ಕನ್ನಡ (Kannada)" },
  { code: "gu", label: "ગુજરાતી (Gujarati)" },
  { code: "pa", label: "ਪੰਜਾਬੀ (Punjabi)" },
  { code: "ml", label: "മലയാളം (Malayalam)" },
];

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  google_denied: "You cancelled the Google sign-in. Try again or use phone OTP.",
  google_auth_failed: "Google authentication failed. Please try again.",
  google_server_error: "A server error occurred during Google sign-in. Please try again.",
  google_missing_tokens: "Incomplete Google sign-in. Please try again.",
  google_completion_failed: "Could not complete Google sign-in. Please try again.",
};

export default function SignupPage() {
  const router = useRouter();
  const { loginWithOtp, isLoading, error, clearError } = useAuthStore();

  const [authMethod, setAuthMethod] = useState<AuthMethod>("otp");
  const [step, setStep] = useState<Step>("details");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [language, setLanguage] = useState("en");
  const [formError, setFormError] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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

  const validateOtpDetails = (): boolean => {
    if (!fullName.trim() || fullName.trim().length < 2) {
      setFormError("Please enter your full name (at least 2 characters)");
      return false;
    }
    const digits = phone.replace(/\D/g, "");
    let normalized = digits;
    if (normalized.startsWith("91") && normalized.length === 12) normalized = normalized.slice(2);
    if (normalized.length !== 10 || !/^[6-9]/.test(normalized)) {
      setFormError("Please enter a valid 10-digit Indian mobile number");
      return false;
    }
    setFormError(null);
    setPhone(normalized);
    return true;
  };

  const validatePasswordDetails = (): boolean => {
    if (!fullName.trim() || fullName.trim().length < 2) {
      setPasswordError("Please enter your full name (at least 2 characters)");
      return false;
    }
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setPasswordError("Please enter a valid email address");
      return false;
    }
    if (!password || password.length < 8) {
      setPasswordError("Password must be at least 8 characters");
      return false;
    }
    if (password !== confirmPassword) {
      setPasswordError("Passwords do not match");
      return false;
    }
    setPasswordError(null);
    return true;
  };

  const handleSendOtp = async () => {
    if (!validateOtpDetails()) return;
    clearError();
    try {
      const response = await authApi.sendOtp(phone, "signup");
      setStep("otp");
      setResendCooldown(response.cooldown_seconds);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to send OTP");
    }
  };

  // FIX: accepts otpValue directly because React state updates are async —
  // when onChange fires with a full 6-digit value, `otp` state hasn't updated yet.
  const handleVerifyOtp = async (otpValue?: string) => {
    const code = otpValue ?? otp;
    if (code.length !== 6) return;
    clearError();
    try {
      await loginWithOtp(phone, code, fullName);
      router.push("/dashboard");
    } catch {
      // error surfaced from store
    }
  };

  const handleResendOtp = async () => {
    if (resendCooldown > 0) return;
    try {
      const response = await authApi.sendOtp(phone, "signup");
      setResendCooldown(response.cooldown_seconds);
    } catch {
      // ignore
    }
  };

  const handlePasswordSignup = (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setPasswordError(null);
    if (!validatePasswordDetails()) return;
    setPasswordError(
      "Email/password accounts are set up by system administrators. " +
      "To register, please use phone OTP. " +
      "If you received credentials from an admin, use the Login page."
    );
  };

  const handleGoogleSignup = () => {
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
            <User className="h-6 w-6 text-white" />
          </div>
          <CardTitle className="text-2xl">Create your account</CardTitle>
          <CardDescription>
            {authMethod === "otp" && (step === "details"
              ? "Sign up with your phone number — OTP verification required"
              : `Enter the 6-digit code sent to +91 ${phone}`)}
            {authMethod === "password" && "Sign up with your email and password"}
            {authMethod === "google" && "Sign up with your Google account"}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* ── OTP Step 1: Details ── */}
          {authMethod === "otp" && step === "details" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="fullName">Full Name</Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="fullName" type="text" placeholder="Ramesh Kumar" value={fullName}
                    onChange={(e) => setFullName(e.target.value)} className="pl-10" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="phone">Phone Number</Label>
                <div className="relative">
                  <Phone className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="phone" type="tel" inputMode="numeric" placeholder="9876543210"
                    value={phone} onChange={(e) => setPhone(e.target.value)} className="pl-10" maxLength={13} />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="language">Preferred Language</Label>
                <select id="language" value={language} onChange={(e) => setLanguage(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  {LANGUAGES.map((lang) => (
                    <option key={lang.code} value={lang.code}>{lang.label}</option>
                  ))}
                </select>
              </div>

              {formError && <p className="text-sm text-red-600">{formError}</p>}

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
                <Button type="button" variant="secondary" onClick={handleGoogleSignup} className="w-full">
                  <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                  </svg>
                  Google
                </Button>
              </div>

              <div className="text-center text-sm text-slate-600">
                Already have an account?{" "}
                <Link href="/login" className="font-medium text-primary hover:underline">Log in</Link>
              </div>
            </>
          )}

          {/* ── OTP Step 2: Verify ── */}
          {authMethod === "otp" && step === "otp" && (
            <>
              <div className="space-y-3">
                <Label>Enter 6-digit code</Label>
                {/* FIX: removed onComplete prop (not in InputOTP API).
                    Instead detect completion inside onChange — otpValue is
                    passed directly to avoid reading stale React state. */}
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
                  ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating account...</>
                  : "Verify & Create Account"}
              </Button>

              <div className="flex items-center justify-between text-sm text-slate-600">
                <button type="button" onClick={() => { setStep("details"); setOtp(""); setFormError(null); clearError(); }}
                  className="hover:text-primary">
                  Change details
                </button>
                <button type="button" onClick={handleResendOtp} disabled={resendCooldown > 0}
                  className="hover:text-primary disabled:opacity-50 disabled:cursor-not-allowed">
                  {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend OTP"}
                </button>
              </div>
            </>
          )}

          {/* ── Password Signup ── */}
          {authMethod === "password" && (
            <form onSubmit={handlePasswordSignup} className="space-y-4">
              <div className="flex gap-2 rounded-md border border-blue-200 bg-blue-50 p-3">
                <Info className="h-4 w-4 shrink-0 text-blue-600 mt-0.5" />
                <p className="text-xs text-blue-700">
                  Email/password accounts are for administrators and officers provisioned by the platform.
                  Farmers should sign up using phone OTP.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="fullName">Full Name</Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="fullName" type="text" placeholder="Ramesh Kumar" value={fullName}
                    onChange={(e) => setFullName(e.target.value)} className="pl-10" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="email" type="email" autoComplete="email" placeholder="you@example.com"
                    value={email} onChange={(e) => setEmail(e.target.value)} className="pl-10" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="password" type="password" autoComplete="new-password" placeholder="••••••••"
                    value={password} onChange={(e) => setPassword(e.target.value)} className="pl-10" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input id="confirmPassword" type="password" autoComplete="new-password" placeholder="••••••••"
                    value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="pl-10" />
                </div>
                {passwordError && <p className="text-sm text-red-600">{passwordError}</p>}
              </div>

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating...</> : "Create Account"}
              </Button>

              <div className="grid grid-cols-2 gap-3">
                <Button type="button" variant="secondary"
                  onClick={() => { setAuthMethod("otp"); setStep("details"); }} className="w-full">
                  <Phone className="mr-2 h-4 w-4" /> OTP
                </Button>
                <Button type="button" variant="secondary" onClick={handleGoogleSignup} className="w-full">
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

          {/* ── Google Signup ── */}
          {authMethod === "google" && (
            <div className="space-y-4">
              <Button onClick={handleGoogleSignup} className="w-full" size="lg">
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
                  onClick={() => { setAuthMethod("otp"); setStep("details"); }} className="w-full">
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

      <div className="mt-6 flex max-w-md items-center justify-center gap-2 text-xs text-slate-500">
        <ShieldCheck className="h-4 w-4" />
        <span>Your data is encrypted and never shared with third parties.</span>
      </div>
    </div>
  );
}