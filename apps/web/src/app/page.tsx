import Link from "next/link";
import {
  Sprout,
  Satellite,
  CloudRain,
  ShieldCheck,
  Stethoscope,
  Store,
  FileText,
  Mic,
  ArrowRight,
  Leaf,
  Droplets,
  TrendingUp,
  Users,
  CheckCircle2,
} from "lucide-react";

const HERO_STATS = [
  { label: "Crop Diseases Identified", value: "38+", icon: Stethoscope },
  { label: "Languages Supported", value: "10", icon: Mic },
  { label: "Weekly NDVI Refresh", value: "7 days", icon: Satellite },
  { label: "Verified via Aadhaar", value: "e-KYC", icon: ShieldCheck },
];

const CAPABILITIES = [
  {
    icon: Stethoscope,
    title: "Crop Disease Identification",
    description:
      "AI-powered diagnosis from a single leaf photo. YOLOv8 model fine-tuned on PlantVillage, PlantDoc, and a custom Indian crop disease dataset — 92%+ top-1 accuracy in seconds.",
    features: [
      "Real-time inference via ONNX Runtime",
      "Treatment recommendations linked to marketplace",
      "Officer review workflow for low-confidence cases",
    ],
  },
  {
    icon: CloudRain,
    title: "Soil Health & Weather Intelligence",
    description:
      "IMD-anchored weather data with 7-day forecasts and extreme-weather alerts. Soil Health Card integration and ISRIC SoilGrids auto-population for every registered plot.",
    features: [
      "Hourly weather sync from IMD",
      "Plot-specific interpolation",
      "Voice advisories in farmer's preferred language",
    ],
  },
  {
    icon: Satellite,
    title: "Satellite NDVI Monitoring",
    description:
      "Weekly vegetation health monitoring using free Sentinel-2 imagery. Plot-level NDVI maps with color-scale legend, time-series trends, and anomaly detection.",
    features: [
      "Sentinel-2 L2A at 10m resolution",
      "Cloud-masked compositing",
      "Automatic NDVI drop alerts",
    ],
  },
  {
    icon: ShieldCheck,
    title: "Insurance & PMFBY",
    description:
      "End-to-end crop insurance lifecycle — from product discovery and enrollment through claim filing with auto-attached NDVI evidence, disease reports, and weather events.",
    features: [
      "PMFBY portal API integration",
      "Pre-filled claim forms from verified profile",
      "Insurer dashboard with integrated evidence view",
    ],
  },
  {
    icon: Store,
    title: "Agricultural Marketplace",
    description:
      "Verified suppliers, transparent pricing, quality certification display, and integrated UPI payments with escrow. Order tracking from placement to delivery.",
    features: [
      "Supplier license verification",
      "UPI + Razorpay payments with escrow",
      "Real-time order state machine",
    ],
  },
  {
    icon: FileText,
    title: "Government Schemes Discovery",
    description:
      "Comprehensive catalog of PM-Kisan, KCC, PMFBY, Soil Health Card, and state schemes. Eligibility engine matches farmers to schemes based on verified profile.",
    features: [
      "YAML-based eligibility rules engine",
      "Auto-filled applications from profile",
      "Status tracking with daily govt portal sync",
    ],
  },
];

const IMPACT_STATS = [
  {
    value: "146M+",
    label: "Indian farmer households served by sector",
    icon: Users,
  },
  {
    value: "92%+",
    label: "Top-1 accuracy on crop disease classification",
    icon: TrendingUp,
  },
  {
    value: "10",
    label: "Languages with voice query and response",
    icon: Mic,
  },
  {
    value: "<15s",
    label: "End-to-end disease diagnosis on 4G network",
    icon: Stethoscope,
  },
];

const SOLUTIONS = [
  {
    title: "Precision Farming",
    description:
      "Plot-level NDVI maps, soil test history, and crop calendars enable data-driven decisions on irrigation, fertilizer, and harvest timing.",
    icon: Leaf,
  },
  {
    title: "Crop Monitoring",
    description:
      "Weekly satellite imagery and anomaly detection alert farmers to vegetation stress before it becomes visible to the naked eye.",
    icon: Satellite,
  },
  {
    title: "Risk Mitigation",
    description:
      "Insurance enrollment, claim filing with auto-evidence, and real-time weather advisories reduce crop-loss-driven income volatility.",
    icon: ShieldCheck,
  },
  {
    title: "Input Procurement",
    description:
      "Verified marketplace with quality certification eliminates counterfeit seeds, adulterated fertilizers, and price opacity.",
    icon: Store,
  },
  {
    title: "Scheme Access",
    description:
      "Eligibility-matched scheme catalog with auto-filled applications dramatically reduces the bureaucratic overhead of accessing government benefits.",
    icon: FileText,
  },
  {
    title: "Accessibility",
    description:
      "Voice-first interface in 10 languages makes the platform usable by farmers who cannot read or who prefer their native language.",
    icon: Mic,
  },
];

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Header />
      <Hero />
      <Stats />
      <Capabilities />
      <Solutions />
      <Impact />
      <CTA />
      <Footer />
    </main>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-200 bg-white/80 backdrop-blur-md">
      <div className="container-page flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <Sprout className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-bold text-slate-900">KrishiSetu</span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          <Link
            href="#capabilities"
            className="text-sm font-medium text-slate-700 hover:text-primary"
          >
            Capabilities
          </Link>
          <Link
            href="#solutions"
            className="text-sm font-medium text-slate-700 hover:text-primary"
          >
            Solutions
          </Link>
          <Link
            href="#impact"
            className="text-sm font-medium text-slate-700 hover:text-primary"
          >
            Impact
          </Link>
          <Link
            href="/about"
            className="text-sm font-medium text-slate-700 hover:text-primary"
          >
            About
          </Link>
        </nav>

        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="btn-ghost hidden text-sm sm:inline-flex"
          >
            Log In
          </Link>
          <Link href="/signup" className="btn-primary text-sm">
            Sign Up
          </Link>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-slate-900">
      {/* Background image — aerial farm view (matches reference UI hero) */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{
          backgroundImage:
            "url('https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=1920&q=80')",
        }}
      />
      <div className="absolute inset-0 bg-hero-overlay" />

      <div className="container-page relative flex min-h-[600px] flex-col justify-center py-20">
        <div className="max-w-3xl">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-primary/20 px-4 py-1.5 text-sm font-medium text-primary-100 backdrop-blur-sm">
            <Leaf className="h-4 w-4" />
            <span>One-stop platform for Indian agriculture</span>
          </div>

          <h1 className="text-balance text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl lg:text-6xl">
            Revolutionizing Agriculture Through Innovation
          </h1>

          <p className="mt-6 max-w-2xl text-balance text-lg text-slate-200 sm:text-xl">
            KrishiSetu unifies crop disease identification, soil and weather
            intelligence, satellite NDVI monitoring, crop insurance, marketplace,
            and government schemes — under one verified identity, in 10
            languages, for every Indian farmer.
          </p>

          <div className="mt-8 flex flex-col gap-4 sm:flex-row">
            <Link href="/signup" className="btn-primary btn-lg">
              Get Started
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link
              href="#capabilities"
              className="btn-secondary btn-lg border-white/20 bg-white/10 text-white backdrop-blur-sm hover:bg-white/20"
            >
              Explore Solutions
            </Link>
          </div>

          <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {HERO_STATS.map((stat) => (
              <div
                key={stat.label}
                className="rounded-lg border border-white/10 bg-white/5 p-4 backdrop-blur-sm"
              >
                <stat.icon className="h-6 w-6 text-primary-200" />
                <div className="mt-2 text-2xl font-bold text-white">
                  {stat.value}
                </div>
                <div className="text-xs text-slate-300">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Stats() {
  return (
    <section className="border-b border-slate-200 bg-white py-16">
      <div className="container-page">
        <div className="grid grid-cols-2 gap-8 lg:grid-cols-4">
          <StatCard
            icon={TrendingUp}
            value="50%"
            label="Increase in crop yield with timely advisories"
          />
          <StatCard
            icon={Droplets}
            value="45%"
            label="Reduction in water usage with precision irrigation"
          />
          <StatCard
            icon={Leaf}
            value="92%+"
            label="Top-1 accuracy on crop disease classification"
          />
          <StatCard
            icon={Users}
            value="146M+"
            label="Indian farmer households in the addressable sector"
          />
        </div>
      </div>
    </section>
  );
}

function StatCard({
  icon: Icon,
  value,
  label,
}: {
  icon: typeof Leaf;
  value: string;
  label: string;
}) {
  return (
    <div className="text-center">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-50">
        <Icon className="h-6 w-6 text-primary" />
      </div>
      <div className="text-3xl font-bold text-slate-900 sm:text-4xl">{value}</div>
      <p className="mt-1 text-sm text-slate-600">{label}</p>
    </div>
  );
}

function Capabilities() {
  return (
    <section id="capabilities" className="py-20 lg:py-28">
      <div className="container-page">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="section-heading">
            Eight Capabilities. One Platform.
          </h2>
          <p className="section-subheading">
            KrishiSetu consolidates the fragmented agricultural services ecosystem
            into a single, AI-powered, government-grade platform — anchored on
            Aadhaar-verified identity.
          </p>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((capability) => (
            <div
              key={capability.title}
              className="card group p-6 hover:border-primary/30"
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary-50 transition-colors group-hover:bg-primary-100">
                <capability.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-xl font-bold text-slate-900">
                {capability.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                {capability.description}
              </p>
              <ul className="mt-4 space-y-2">
                {capability.features.map((feature) => (
                  <li
                    key={feature}
                    className="flex items-start gap-2 text-sm text-slate-700"
                  >
                    <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Solutions() {
  return (
    <section id="solutions" className="bg-section-dark py-20 lg:py-28">
      <div className="container-page">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="section-heading text-white">
            Solutions for Every Stakeholder
          </h2>
          <p className="section-subheading text-slate-300">
            From smallholder farmers to agricultural officers, suppliers, and
            insurers — KrishiSetu serves the entire agricultural value chain with
            role-specific workflows and data access.
          </p>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {SOLUTIONS.map((solution) => (
            <div
              key={solution.title}
              className="group rounded-lg border border-white/10 bg-white/5 p-6 backdrop-blur-sm transition-all hover:border-primary/30 hover:bg-white/10"
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/20">
                <solution.icon className="h-6 w-6 text-primary-200" />
              </div>
              <h3 className="text-xl font-bold text-white">
                {solution.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-300">
                {solution.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Impact() {
  return (
    <section id="impact" className="bg-section-dark py-20 lg:py-28">
      <div className="container-page">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <h2 className="section-heading text-white">
              Changing the Game in Farming
            </h2>
            <p className="mt-6 text-lg text-slate-300">
              The platform addresses six well-defined problem categories that
              map directly to its eight functional modules — eliminating the
              fragmentation tax that Indian farmers currently pay in time, money,
              and missed opportunities.
            </p>
            <p className="mt-4 text-lg text-slate-300">
              Built on a Python-first, government-grade technology stack with
              Aadhaar-verified identity, role-based access control, and
              end-to-end audit logging — engineered for millions of users from
              day one.
            </p>
            <div className="mt-8">
              <Link
                href="/signup"
                className="btn-primary btn-lg inline-flex"
              >
                Join KrishiSetu
                <ArrowRight className="h-5 w-5" />
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {IMPACT_STATS.map((stat) => (
              <div
                key={stat.label}
                className="rounded-lg border border-white/10 bg-white/5 p-6 backdrop-blur-sm"
              >
                <stat.icon className="h-8 w-8 text-primary-200" />
                <div className="mt-3 text-3xl font-bold text-white sm:text-4xl">
                  {stat.value}
                </div>
                <p className="mt-1 text-sm text-slate-300">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="bg-white py-20 lg:py-28">
      <div className="container-page">
        <div className="mx-auto max-w-4xl rounded-2xl bg-gradient-to-br from-primary-50 to-primary-100 p-8 text-center lg:p-16">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Ready to Transform Your Farming?
          </h2>
          <p className="mt-4 text-lg text-slate-700">
            Sign up with your phone number, verify via Aadhaar e-KYC, and access
            every capability in one place — in your language, on your device.
          </p>
          <div className="mt-8 flex flex-col justify-center gap-4 sm:flex-row">
            <Link href="/signup" className="btn-primary btn-lg">
              Create Free Account
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link href="/about" className="btn-secondary btn-lg">
              Learn More
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-section-dark py-16 text-slate-400">
      <div className="container-page">
        <div className="grid gap-12 lg:grid-cols-4">
          <div className="lg:col-span-1">
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
                <Sprout className="h-5 w-5 text-white" />
              </div>
              <span className="text-lg font-bold text-white">KrishiSetu</span>
            </Link>
            <p className="mt-4 text-sm">
              कृषि-सेतु — Bridge to Agriculture. One-stop AI-powered platform
              for Indian farmers.
            </p>
          </div>

          <FooterColumn
            title="Platform"
            links={[
              { label: "Crop Disease ID", href: "/features/disease" },
              { label: "Soil & Weather", href: "/features/soil-weather" },
              { label: "Satellite NDVI", href: "/features/ndvi" },
              { label: "Insurance", href: "/features/insurance" },
              { label: "Marketplace", href: "/features/marketplace" },
              { label: "Schemes", href: "/features/schemes" },
            ]}
          />

          <FooterColumn
            title="Resources"
            links={[
              { label: "Documentation", href: "/docs" },
              { label: "API Reference", href: "/docs/api" },
              { label: "Privacy Policy", href: "/privacy" },
              { label: "Terms of Service", href: "/terms" },
              { label: "Security", href: "/security" },
            ]}
          />

          <FooterColumn
            title="Company"
            links={[
              { label: "About", href: "/about" },
              { label: "Contact", href: "/contact" },
              { label: "Careers", href: "/careers" },
              { label: "Press", href: "/press" },
            ]}
          />
        </div>

        <div className="mt-12 border-t border-white/10 pt-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <p className="text-sm">
              © {new Date().getFullYear()} KrishiSetu. All rights reserved.
            </p>
            <p className="text-xs">
              Made in India for Indian agriculture.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({
  title,
  links,
}: {
  title: string;
  links: { label: string; href: string }[];
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <ul className="mt-4 space-y-3">
        {links.map((link) => (
          <li key={link.label}>
            <Link
              href={link.href}
              className="text-sm text-slate-400 transition-colors hover:text-primary-200"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
