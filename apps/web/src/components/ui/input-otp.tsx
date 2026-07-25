"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type InputOTPProps = React.InputHTMLAttributes<HTMLInputElement> & {
  length?: number;
  value?: string;
  onChange?: (value: string) => void;
};

const InputOTP = React.forwardRef<HTMLInputElement, InputOTPProps>(
  ({ className, length = 6, value = "", onChange, ...props }, ref) => {
    const inputsRef = React.useRef<(HTMLInputElement | null)[]>([]);

    const focusInput = (idx: number) => {
      const next = Math.max(0, Math.min(idx, length - 1));
      inputsRef.current[next]?.focus();
    };

    const handleKeyDown = (e: React.KeyboardEvent, idx: number) => {
      if (e.key === "Backspace") {
        e.preventDefault();
        const newValue = value.split("");
        if (newValue[idx]) {
          newValue[idx] = "";
          onChange?.(newValue.join(""));
        } else if (idx > 0) {
          newValue[idx - 1] = "";
          onChange?.(newValue.join(""));
          focusInput(idx - 1);
        }
      } else if (e.key === "ArrowLeft") {
        focusInput(idx - 1);
      } else if (e.key === "ArrowRight") {
        focusInput(idx + 1);
      }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>, idx: number) => {
      const digit = e.target.value.replace(/\D/g, "").slice(-1);
      const newValue = value.split("");
      while (newValue.length < length) newValue.push("");
      newValue[idx] = digit;
      onChange?.(newValue.join(""));
      if (digit && idx < length - 1) {
        focusInput(idx + 1);
      }
    };

    const handlePaste = (e: React.ClipboardEvent) => {
      e.preventDefault();
      const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
      onChange?.(pasted);
      focusInput(Math.min(pasted.length, length - 1));
    };

    return (
      <div className={cn("flex gap-2", className)} onPaste={handlePaste}>
        {Array.from({ length }).map((_, idx) => (
          <input
            key={idx}
            ref={(el) => {
              inputsRef.current[idx] = el;
            }}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={1}
            value={value[idx] || ""}
            onChange={(e) => handleChange(e, idx)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-md border border-slate-200 bg-white text-center text-lg font-semibold text-slate-900 transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:border-primary",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
            {...props}
          />
        ))}
      </div>
    );
  },
);
InputOTP.displayName = "InputOTP";

export { InputOTP };
