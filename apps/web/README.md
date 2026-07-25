# KrishiSetu Web

Next.js 14 frontend for the KrishiSetu agricultural platform.

## Local Development

### With Docker Compose (recommended)

From the repository root:

```bash
docker compose -f infra/docker-compose.yml up -d web
```

The web app will be available at http://localhost:3000.

### Without Docker

```bash
# Install dependencies
pnpm install

# Copy env
cp .env.example .env

# Run dev server
pnpm dev
```

## Tech Stack

- **Next.js 14** (App Router, React Server Components)
- **TypeScript** (strict mode)
- **Tailwind CSS** (custom design tokens matching reference UI)
- **shadcn/ui + Radix UI** (accessible components)
- **lucide-react** (line icons — no emojis in production UI)
- **next-intl** (10-language i18n)
- **TanStack Query** (server state)
- **Zustand** (client UI state)
- **react-hook-form + zod** (forms & validation)

## Design System

The design language is derived from the reference UI:

| Token | Value | Usage |
|-------|-------|-------|
| Primary | `#4CAF50` (green) | CTAs, active states, NDVI healthy |
| Primary Dark | `#1E293B` (slate) | Headers, footers, dark sections |
| Background | `#F8FAFC` (off-white) | Page background |
| Card | `#FFFFFF` (white) | Cards, panels |
| Foreground | `#111827` (near-black) | Primary text |
| Muted | `#6C757D` (gray) | Secondary text |
| NDVI High | `#4CAF50` (green) | Healthy vegetation |
| NDVI Medium | `#FFEB3B` (yellow) | Moderate health |
| NDVI Low | `#FF9800` (orange) | Stressed vegetation |

## Code Quality

```bash
# Lint
pnpm lint

# Type check
pnpm typecheck

# Tests
pnpm test

# Format
pnpm format
```
