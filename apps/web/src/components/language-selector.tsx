"use client";

import { useState, useRef, useEffect } from "react";
import { Globe, Check, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { locales, localeNames, type Locale } from "@/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { authApi } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface LanguageSelectorProps {
  className?: string;
  compact?: boolean;
}

/**
 * Language selector dropdown.
 *
 * Shows the current locale's native name. On selection:
 * 1. Updates the UI immediately (via context)
 * 2. Saves preference to user profile via API
 * 3. Sets NEXT_LOCALE cookie
 */
export function LanguageSelector({ className, compact = false }: LanguageSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentLocale, setCurrentLocale] = useState<Locale>("en");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { user, refreshUser } = useAuthStore();

  // Initialize from user profile
  useEffect(() => {
    if (user?.preferred_language) {
      const lang = user.preferred_language as Locale;
      if (locales.includes(lang)) {
        setCurrentLocale(lang);
      }
    } else {
      // Try cookie
      const cookie = document.cookie
        .split("; ")
        .find((row) => row.startsWith("NEXT_LOCALE="))
        ?.split("=")[1];
      if (cookie && locales.includes(cookie as Locale)) {
        setCurrentLocale(cookie as Locale);
      }
    }
  }, [user]);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function handleSelect(locale: Locale) {
    setCurrentLocale(locale);
    setIsOpen(false);

    // Set cookie
    document.cookie = `NEXT_LOCALE=${locale};path=/;max-age=31536000;samesite=lax`;

    // Save to user profile if authenticated
    if (user) {
      try {
        await authApi.updateMe({ preferred_language: locale });
        await refreshUser();
      } catch {
        // Silent fail — UI already updated
      }
    }

    // Reload page to apply translations
    window.location.reload();
  }

  const currentName = localeNames[currentLocale];

  return (
    <div ref={dropdownRef} className={cn("relative", className)}>
      <Button
        variant="ghost"
        size={compact ? "sm" : "default"}
        onClick={() => setIsOpen(!isOpen)}
        className="gap-2"
      >
        <Globe className="h-4 w-4" />
        {!compact && <span>{currentName.native}</span>}
        <ChevronDown className="h-3 w-3" />
      </Button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-1 z-50 w-56 rounded-md border border-slate-200 bg-white shadow-lg">
          <div className="p-2">
            <p className="px-2 py-1 text-xs font-semibold uppercase text-slate-400">
              Select Language / भाषा चुनें
            </p>
            {locales.map((locale) => {
              const name = localeNames[locale];
              const isSelected = locale === currentLocale;
              return (
                <button
                  key={locale}
                  onClick={() => handleSelect(locale)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-md px-2 py-2 text-sm transition-colors",
                    isSelected
                      ? "bg-primary-50 text-primary"
                      : "text-slate-700 hover:bg-slate-50"
                  )}
                >
                  <div className="flex flex-col items-start">
                    <span className="font-medium">{name.native}</span>
                    <span className="text-xs text-slate-400">{name.english}</span>
                  </div>
                  {isSelected && <Check className="h-4 w-4" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
