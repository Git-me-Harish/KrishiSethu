import { FlatCompat } from "@eslint/eslintrc";
import { fileURLToPath } from "node:url";
import path from "node:path";

// `next lint` / eslint-config-next still ship as .eslintrc-style configs.
// ESLint 9 dropped the legacy config format (and the CLIEngine options next's
// own runner passes), so it needs to be loaded through FlatCompat instead of
// a bare ".eslintrc.json" — without this file `next lint` fails immediately
// with "Unknown options: useEslintrc, extensions" before checking a single
// file.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals"),
  {
    ignores: [".next/**", "node_modules/**", "coverage/**", "playwright-report/**"],
  },
  {
    rules: {
      // eslint-plugin-next@14.2.x's Pages-Router-era `_document.js` check
      // calls the removed `context.getAncestors()` API and crashes outright
      // under ESLint 9 (this app is App Router only and has no _document.js,
      // so the rule has nothing to check here anyway).
      "@next/next/no-duplicate-head": "off",
    },
  },
];

export default eslintConfig;
