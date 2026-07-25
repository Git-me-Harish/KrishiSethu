import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/auth-provider";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://krishisetu.in"),
  title: {
    default: "KrishiSetu — One-Stop AI-Powered Agricultural Platform",
    template: "%s | KrishiSetu",
  },
  description:
    "Production-grade digital platform serving Indian farmers. Crop disease identification, soil health, weather intelligence, satellite NDVI monitoring, crop insurance, marketplace, and government scheme discovery — unified under one verified identity.",
  keywords: [
    "Indian agriculture",
    "crop disease identification",
    "PMFBY",
    "PM-Kisan",
    "soil health card",
    "NDVI",
    "satellite imagery",
    "farmer portal",
    "agricultural marketplace",
    "Aadhaar e-KYC",
  ],
  authors: [{ name: "KrishiSetu" }],
  openGraph: {
    type: "website",
    locale: "en_IN",
    title: "KrishiSetu — One-Stop AI-Powered Agricultural Platform",
    description:
      "Unified digital platform for Indian agriculture. Identity, diagnostics, agronomy, monitoring, insurance, commerce, schemes, and accessibility — under one verified identity.",
    siteName: "KrishiSetu",
  },
  twitter: {
    card: "summary_large_image",
    title: "KrishiSetu",
    description:
      "One-Stop AI-Powered Agricultural Platform for India",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
