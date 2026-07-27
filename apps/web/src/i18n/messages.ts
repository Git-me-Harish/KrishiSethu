/**
 * Unified i18n message loader.
 *
 * Dynamically imports the correct message file based on locale.
 * All 10 locales are now fully translated:
 * - English (en) — default
 * - Hindi (hi) — Devanagari
 * - Marathi (mr) — Devanagari
 * - Tamil (ta) — Tamil script
 * - Telugu (te) — Telugu script
 * - Bengali (bn) — Bengali script
 * - Kannada (kn) — Kannada script
 * - Gujarati (gu) — Gujarati script
 * - Punjabi (pa) — Gurmukhi script
 * - Malayalam (ml) — Malayalam script
 *
 * Each locale file exports a complete `messages` object with all keys translated.
 * The `loadMessages()` function dynamically imports the correct file.
 */

import type { Locale } from "./config";
import { messages as enMessages, type Messages } from "./messages/en";

// Lazy-loaded locale messages
const localeLoaders: Record<Locale, () => Promise<{ messages: Messages }>> = {
  en: async () => ({ messages: enMessages }),
  hi: async () => {
    const { messages } = await import("./messages/hi");
    return { messages: mergeMessages(enMessages, messages) };
  },
  mr: async () => {
    const { messages } = await import("./messages/mr");
    return { messages: mergeMessages(enMessages, messages) };
  },
  ta: async () => {
    const { messages } = await import("./messages/ta");
    return { messages: mergeMessages(enMessages, messages) };
  },
  te: async () => {
    const { messages } = await import("./messages/te");
    return { messages: mergeMessages(enMessages, messages) };
  },
  bn: async () => {
    const { messages } = await import("./messages/bn");
    return { messages: mergeMessages(enMessages, messages) };
  },
  kn: async () => {
    const { messages } = await import("./messages/kn");
    return { messages: mergeMessages(enMessages, messages) };
  },
  gu: async () => {
    const { messages } = await import("./messages/gu");
    return { messages: mergeMessages(enMessages, messages) };
  },
  pa: async () => {
    const { messages } = await import("./messages/pa");
    return { messages: mergeMessages(enMessages, messages) };
  },
  ml: async () => {
    const { messages } = await import("./messages/ml");
    return { messages: mergeMessages(enMessages, messages) };
  },
};

/**
 * Deep merge two message objects, using `fallback` for missing keys.
 */
function mergeMessagesLoose(
  fallback: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...fallback };
  for (const key in override) {
    const fallbackValue = fallback[key];
    const overrideValue = override[key];
    if (
      typeof fallbackValue === "object" &&
      fallbackValue !== null &&
      typeof overrideValue === "object" &&
      overrideValue !== null &&
      !Array.isArray(fallbackValue)
    ) {
      result[key] = mergeMessagesLoose(
        fallbackValue as Record<string, unknown>,
        overrideValue as Record<string, unknown>,
      );
    } else if (overrideValue !== undefined) {
      result[key] = overrideValue;
    }
  }
  return result;
}

function mergeMessages<T extends Record<string, unknown>>(fallback: T, override: Partial<T>): T {
  return mergeMessagesLoose(fallback, override as Record<string, unknown>) as T;
}

/**
 * Get messages for a locale (synchronous — returns English immediately).
 *
 * For async loading with translations, use `loadMessages()`.
 */
export function getMessages(locale: Locale): Messages {
  return enMessages;
}

/**
 * Async message loader for dynamic imports.
 * Loads the full translation for the requested locale.
 */
export async function loadMessages(locale: Locale): Promise<Messages> {
  const loader = localeLoaders[locale] || localeLoaders.en;
  const { messages } = await loader();
  return messages;
}

export type { Messages };
