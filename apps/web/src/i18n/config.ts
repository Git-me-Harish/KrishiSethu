/**
 * i18n configuration for KrishiSetu.
 *
 * Supports 10 Indian languages:
 * - English (en) — default
 * - Hindi (hi)
 * - Marathi (mr)
 * - Tamil (ta)
 * - Telugu (te)
 * - Bengali (bn)
 * - Kannada (kn)
 * - Gujarati (gu)
 * - Punjabi (pa)
 * - Malayalam (ml)
 *
 * Locale is determined by:
 * 1. User's preferred_language setting (from API)
 * 2. Browser Accept-Language header
 * 3. Cookie (NEXT_LOCALE)
 * 4. Default: English
 */

export const locales = ["en", "hi", "mr", "ta", "te", "bn", "kn", "gu", "pa", "ml"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

export const localeNames: Record<Locale, { english: string; native: string }> = {
  en: { english: "English", native: "English" },
  hi: { english: "Hindi", native: "हिन्दी" },
  mr: { english: "Marathi", native: "मराठी" },
  ta: { english: "Tamil", native: "தமிழ்" },
  te: { english: "Telugu", native: "తెలుగు" },
  bn: { english: "Bengali", native: "বাংলা" },
  kn: { english: "Kannada", native: "ಕನ್ನಡ" },
  gu: { english: "Gujarati", native: "ગુજરાતી" },
  pa: { english: "Punjabi", native: "ਪੰਜਾਬੀ" },
  ml: { english: "Malayalam", native: "മലയാളം" },
};

export function isLocale(value: string): value is Locale {
  return locales.includes(value as Locale);
}

export function getLocaleName(locale: string): { english: string; native: string } {
  if (isLocale(locale)) {
    return localeNames[locale];
  }
  return localeNames.en;
}
