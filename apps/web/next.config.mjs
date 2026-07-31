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
      { protocol: "http", hostname: "localhost", port: 9000 },
      { protocol: "http", hostname: "minio", port: 9000 },
      // In production, add your S3 / CDN hostname here, e.g.:
      // { protocol: "https", hostname: "krishisetu.s3.ap-south-1.amazonaws.com" },
    ],
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
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
