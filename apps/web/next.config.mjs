const isDev = process.env.NODE_ENV !== "production";

/**
 * Origins the browser is allowed to talk to, derived from the same env vars the
 * app reads at runtime so the CSP never drifts from the actual API host.
 */
const apiOrigins = [
  process.env.NEXT_PUBLIC_API_URL,
  process.env.NEXT_PUBLIC_API_BASE_URL,
]
  .filter(Boolean)
  .map((u) => {
    try {
      return new URL(u).origin;
    } catch {
      return null;
    }
  })
  .filter((o, i, a) => o && a.indexOf(o) === i);

// Same default client.ts falls back to, so the CSP matches where the app
// actually sends requests. Only in dev — never widen a production policy.
if (apiOrigins.length === 0 && isDev) {
  apiOrigins.push("http://localhost:8000");
}

const cspReportUri = `${apiOrigins[0] ?? "http://localhost:8000"}/api/v1/security/csp-report`;

/**
 * Content-Security-Policy.
 *
 * script-src carries 'unsafe-inline' deliberately. Next's App Router emits
 * inline bootstrap and RSC flight-data <script> tags on every page; the only
 * way to drop 'unsafe-inline' is per-request nonces, which require a
 * middleware/proxy that rewrites this header. Until that exists, removing
 * 'unsafe-inline' would make every page fail to hydrate. Everything else is
 * allowlisted to an exact host — no wildcard script sources.
 *
 * Third-party origins in use:
 * - checkout.razorpay.com  — checkout.js, injected by payment-checkout.tsx
 * - api.razorpay.com       — the checkout iframe + its form POST target
 * - lumberjack.razorpay.com— Razorpay's telemetry beacon (checkout hangs on
 *                            some flows if this is blocked)
 * - unpkg.com              — Leaflet default marker icons (images only)
 * - *.tile.openstreetmap.org, server.arcgisonline.com — map tiles
 * - images.unsplash.com, sentinel-cdn.s3.amazonaws.com — matches images.remotePatterns
 */
const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self' https://api.razorpay.com",
  `script-src 'self' 'unsafe-inline' https://checkout.razorpay.com${isDev ? " 'unsafe-eval'" : ""}`,
  // Razorpay's widget and Leaflet both write inline style attributes.
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://images.unsplash.com https://sentinel-cdn.s3.amazonaws.com https://unpkg.com https://*.tile.openstreetmap.org https://server.arcgisonline.com https://*.razorpay.com",
  "font-src 'self' data: https://checkout.razorpay.com",
  `connect-src 'self' ${apiOrigins.join(" ")} https://api.razorpay.com https://lumberjack.razorpay.com${isDev ? " ws: wss:" : ""}`,
  "frame-src 'self' https://api.razorpay.com https://checkout.razorpay.com",
  // Voice assistant plays back recorded + API-returned audio.
  `media-src 'self' blob: data: ${apiOrigins.join(" ")}`,
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
  // The API already exposes a collector (main.py:156). Reporting is how we
  // catch anything this hand-built allowlist missed.
  `report-uri ${cspReportUri}`,
  "report-to csp-endpoint",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // Required for production Dockerfile (standalone server)
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
      { protocol: "https", hostname: "sentinel-cdn.s3.amazonaws.com" },
    ],
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          {
            key: "Reporting-Endpoints",
            value: `csp-endpoint="${cspReportUri}"`,
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "geolocation=(self), microphone=(self), camera=(self)",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
