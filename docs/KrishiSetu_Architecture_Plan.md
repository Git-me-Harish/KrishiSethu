# KrishiSetu — Production Architecture & Engineering Plan

> **Project Codename:** KrishiSetu (कृषि-सेतु, "Bridge to Agriculture")
> **Domain:** Indian Agriculture — One-Stop Digital Platform
> **Document Type:** Comprehensive Architecture & Engineering Plan
> **Target Audience:** Engineering Team, AI/ML Engineers, Systems Architects, Govt-of-India Reviewers
> **Version:** 1.0 — Planning Phase
> **Status:** Pre-Implementation Blueprint

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Vision, Mission & Guiding Principles](#2-vision-mission--guiding-principles)
3. [Indian Agricultural Context & Problem Landscape](#3-indian-agricultural-context--problem-landscape)
4. [Stakeholders, Personas & RBAC Matrix](#4-stakeholders-personas--rbac-matrix)
5. [Platform Capabilities Overview](#5-platform-capabilities-overview)
6. [High-Level System Architecture](#6-high-level-system-architecture)
7. [Technology Stack Decisions](#7-technology-stack-decisions)
8. [Repository & Project Structure](#8-repository--project-structure)
9. [Backend Architecture (FastAPI)](#9-backend-architecture-fastapi)
10. [Frontend Architecture (Next.js 14)](#10-frontend-architecture-nextjs-14)
11. [Data Model & PostgreSQL Schema](#11-data-model--postgresql-schema)
12. [API Design & Endpoint Catalog](#12-api-design--endpoint-catalog)
13. [ML Pipeline Architecture](#13-ml-pipeline-architecture)
14. [Module Deep-Dives](#14-module-deep-dives)
    - 14.1 [Identity, Auth & Aadhaar e-KYC](#141-identity-auth--aadhaar-e-kyc)
    - 14.2 [Farmer Profile & Land Records](#142-farmer-profile--land-records)
    - 14.3 [Crop Disease Identification](#143-crop-disease-identification)
    - 14.4 [Soil Health & Weather Intelligence](#144-soil-health--weather-intelligence)
    - 14.5 [Satellite NDVI & Farm Monitoring](#145-satellite-ndvi--farm-monitoring)
    - 14.6 [Insurance & PMFBY Integration](#146-insurance--pmfby-integration)
    - 14.7 [Agricultural Marketplace](#147-agricultural-marketplace)
    - 14.8 [Government Schemes Discovery](#148-government-schemes-discovery)
    - 14.9 [Multilingual & Voice Interface](#149-multilingual--voice-interface)
15. [Security Architecture](#15-security-architecture)
16. [Scalability & Performance Strategy](#16-scalability--performance-strategy)
17. [Observability](#17-observability)
18. [DevOps & CI/CD](#18-devops--cicd)
19. [Testing Strategy](#19-testing-strategy)
20. [Localization Strategy](#20-localization-strategy)
21. [12-Month Development Roadmap](#21-12-month-development-roadmap)
22. [Risk Assessment & Mitigations](#22-risk-assessment--mitigations)
23. [Recommendations & Future Work](#23-recommendations--future-work)
24. [Appendix: Glossary & References](#24-appendix-glossary--references)

---

## 1. Executive Summary

KrishiSetu is a production-grade, government-grade digital platform engineered to serve as a single, unified, AI-powered solution for Indian agriculture. The platform consolidates eight previously fragmented capabilities — identity verification, crop disease diagnostics, soil and weather intelligence, satellite-based farm monitoring, crop insurance, an agricultural marketplace, government scheme discovery, and a multilingual voice-driven interface — into one cohesive, scalable, secure system.

India's agricultural sector supports roughly 50% of the country's workforce and contributes approximately 18% to national GDP, yet farmers continue to operate within an information ecosystem characterized by deep fragmentation. A typical smallholder farmer must navigate separate portals for soil health cards, weather advisories, insurance enrollment, scheme eligibility, and input procurement, each with their own authentication, data formats, and uptime characteristics. The cognitive and logistical overhead of stitching these services together falls entirely on the farmer, who often lacks the digital literacy or bandwidth to do so effectively. KrishiSetu's central thesis is that this fragmentation, not the absence of individual solutions, is the primary bottleneck in Indian agricultural technology adoption.

The platform is engineered for the scale and rigor demanded by a Government-of-India deployment. The backend is built on **FastAPI** (Python 3.12, async, type-safe) backed by **PostgreSQL 16** as the system of record, **Redis 7** for caching and task brokering, and **Celery** for asynchronous machine-learning workloads. The frontend is **Next.js 14** (App Router, React Server Components, TypeScript, Tailwind CSS, shadcn/ui), providing server-side rendering for low-bandwidth rural users while preserving a modern, component-based, dashboard-rich experience. Machine learning models — YOLOv8 for crop disease detection, fine-tuned transformer models for vernacular query understanding, and remote-sensing pipelines for NDVI computation — are served through a dedicated inference layer with model versioning, A/B routing, and observability.

Security is treated as a first-class architectural concern. Aadhaar e-KYC serves as the foundational identity primitive, with all subsequent authorizations, scheme eligibility checks, and insurance workflows derived from a verified identity graph. Every endpoint is protected by JWT-based authentication, role-based access control (RBAC) with five distinct roles, per-route rate limiting, input validation via Pydantic schemas, structured audit logging, and encryption at rest and in transit. The system is designed to handle millions of users with horizontal scalability, database read replicas, partitioned tables, and CDN-cached static assets.

This document is the comprehensive engineering blueprint. It is intended to be sufficiently detailed that an engineering team can begin implementation immediately upon its approval, with no further architectural ambiguity. The plan covers system architecture, data models, API contracts, ML model selection per use case, security threat models, scalability mathematics, observability, DevOps, a phased twelve-month roadmap, and explicit risk mitigations.

---

## 2. Vision, Mission & Guiding Principles

### 2.1 Vision

To become the digital backbone of Indian agriculture — a single, trusted, AI-powered platform where every Indian farmer, regardless of landholding size, literacy level, language, or geographic location, can access every service needed to make informed decisions, mitigate risk, increase productivity, and improve livelihoods.

### 2.2 Mission

KrishiSetu's mission is to eliminate the fragmentation tax that Indian farmers currently pay in time, money, and missed opportunities. The platform achieves this by unifying eight critical capabilities — identity, diagnostics, agronomy, monitoring, insurance, commerce, schemes, and accessibility — under one verified identity, one consistent user experience, and one engineering system that meets government-grade reliability and security standards.

### 2.3 Guiding Principles

The following principles govern every architectural, technological, and product decision in KrishiSetu. They are not aspirational statements; they are engineering constraints.

**Principle 1 — Farmer-First, Always.** Every design choice is evaluated through the lens of a smallholder farmer in rural India operating on a low-end Android device with intermittent 2G/3G connectivity. If a feature degrades the experience for this user, it is rejected regardless of its technical elegance.

**Principle 2 — No Mock Data, Ever.** Every piece of data displayed to a user must originate from a verified source — a government API, an authenticated sensor feed, a real satellite imagery provider, a trained and validated ML model, or a verified user input. Mock data is treated as a defect, not a development shortcut. Where live data is unavailable in development, the system uses clearly-tagged fixture data loaded from versioned seed files, never inline mock values in application code.

**Principle 3 — Identity as the Foundation.** Aadhaar e-KYC verification is the gateway to every other capability. Schemes, insurance, marketplace, and diagnostic history are all bound to a verified identity graph. Anonymous or unverified access is permitted only for read-only public content (scheme listings, weather forecasts, mandi prices); any transactional or personalized capability requires authentication.

**Principle 4 — Engineer Like a Systems Architect, Not a Hackathon Builder.** This is a production system intended to serve millions. Every component must be horizontally scalable, observable, independently deployable, fault-tolerant, and documented. Quick fixes that compromise long-term maintainability are explicitly forbidden in code review.

**Principle 5 — Best Model for the Task, Not the Hype.** Model selection is use-case-driven. YOLOv8 is chosen for crop disease detection because of its real-time inference characteristics and proven performance on plant pathology datasets. Transformer-based NLP models are chosen for vernacular query understanding because of their ability to handle morphologically rich Indian languages. Every model choice in this document is justified by dataset compatibility, inference latency, fine-tuning feasibility, and production maturity — not by popularity.

**Principle 6 — Security by Construction, Not by Addition.** Authentication, authorization, input validation, rate limiting, encryption, and audit logging are built into the framework layer, not bolted on as middleware afterthoughts. Every API route declares its authentication requirement, required roles, and rate-limit policy at the route definition level.

**Principle 7 — Component-Based, Accessible UI.** The frontend is built entirely from composable, accessible, reusable components following the WAI-ARIA standards. No emojis in the production UI. No decorative graphics that don't communicate information. The aesthetic is professional, data-focused, and consistent with the visual language established in the reference UI (green primary, dark slate sections, white cards, NDVI color scales).

**Principle 8 — Verifiable Observability.** Every system action — every API call, every ML inference, every payment, every Aadhaar verification — is logged with structured fields, trace IDs, and user context. The platform can answer the question "what happened and why" for any user transaction in under 30 seconds.

**Principle 9 — Strict Tech Stack Adherence.** The technology stack specified in this document is the result of deliberate evaluation against the Government-of-India requirements. Substitutions are not permitted without formal architectural review and written approval. This discipline is essential for long-term maintainability and team onboarding.

**Principle 10 — Localized, Not Translated.** Multilingual support means more than string translation. Date formats, currency rendering, units (hectares vs acres, kilograms vs quintals), voice interfaces, and even iconography must respect regional conventions. The platform treats each of the ten supported languages as a first-class locale with dedicated content review.

---

## 3. Indian Agricultural Context & Problem Landscape

### 3.1 Scale and Significance

Indian agriculture operates at a scale that few other national sectors match. The country supports approximately 146 million farmer households, of which roughly 86% are small and marginal farmers holding less than two hectares of land. The sector employs nearly 152 million people directly and contributes approximately 18% to national GDP. India is the world's largest producer of milk, pulses, and jute, and the second-largest producer of rice, wheat, sugarcane, groundnut, vegetables, and fruit. Despite this scale, the average Indian farmer's income remains disproportionately low relative to the value they generate, and crop losses due to pest attacks, weather events, and market volatility affect roughly 20-30% of farmers in any given year.

The opportunity for a unified digital platform is therefore not incremental — it is structural. The fragmentation of agricultural services across dozens of central and state government portals, the absence of a unified identity layer that bridges those portals, the lack of localized and actionable advisory, and the deep asymmetry between what information is available and what reaches the farmer in a usable form — these are systemic problems that no single feature can solve.

### 3.2 The Fragmentation Tax

To understand why KrishiSetu is necessary, consider the journey of a smallholder farmer in Madhya Pradesh who wants to: (a) check if they are eligible for PM-Kisan installments, (b) determine why their wheat crop is showing yellowing leaves, (c) understand whether the upcoming monsoon forecast warrants early harvesting, (d) enroll in crop insurance under PMFBY, and (e) purchase a fungicide recommended for the detected disease. Today, this farmer must navigate at least five separate portals or physical offices, authenticate separately on each, re-enter the same identity and land-holding information multiple times, and reconcile conflicting advisory sources. The total time cost is measured in days; the cognitive cost is measured in frustration; the economic cost is measured in delayed decisions that compound into reduced yield.

KrishiSetu's value proposition is that this farmer should be able to complete all five tasks within a single authenticated session, with the platform orchestrating the underlying government APIs, ML inferences, weather data, and marketplace transactions on their behalf. The farmer provides their Aadhaar once, their land records once, a single photo of the affected crop, and the platform handles the rest.

### 3.3 Problem Categories Addressed

The platform addresses six well-defined problem categories that map directly to its eight functional modules:

**Information Asymmetry.** Farmers lack timely, accurate, localized information about weather, soil health, market prices, and scheme eligibility. KrishiSetu's Weather, Soil, and Schemes modules directly address this.

**Diagnostic Latency.** When a crop shows signs of disease, the time between symptom onset and corrective action is the single largest determinant of yield loss. Existing extension services cannot scale to 146 million farmers. The Crop Disease Identification module compresses this diagnostic window from days to seconds.

**Monitoring Blind Spots.** Farmers with multi-acre holdings cannot visually monitor every plot daily. The Satellite NDVI module provides weekly vegetation health updates at the plot level, with anomaly detection that flags declining areas for inspection.

**Risk Transfer Friction.** Crop insurance exists, but enrollment, premium payment, and claim filing are bureaucratic processes with high rejection rates due to documentation errors. The Insurance & PMFBY module simplifies the workflow and pre-populates forms from the verified identity graph.

**Input Procurement Inefficiency.** Counterfeit seeds, adulterated fertilizers, and price opacity in the agricultural input supply chain erode farmer margins. The Marketplace module connects verified suppliers with verified farmers, with quality certification visible at the point of purchase.

**Linguistic and Literacy Barriers.** Approximately 35% of Indian farmers are functionally illiterate, and the majority prefer to consume information in their native language. The Multilingual & Voice module makes the platform accessible to users who cannot read English or Hindi, with voice-based query and response in ten languages.

### 3.4 Why Now

Three converging trends make this the right moment for a platform like KrishiSetu:

First, the **India Stack** — Aadhaar, UPI, DigiLocker, UMANG, and the India Data Portal — has matured to the point where a unified identity-anchored platform can compose these primitives into a coherent farmer experience without building each underlying capability from scratch.

Second, **machine learning models** for plant pathology, vernacular NLP, and remote sensing have crossed the production-readiness threshold. YOLOv8 achieves over 95% top-5 accuracy on the PlantVillage dataset, multilingual transformer models like IndicBERT and MuRIL handle Indian languages with reasonable accuracy, and open satellite imagery from Sentinel-2 provides free, frequent, high-resolution coverage of Indian farmland.

Third, **smartphone penetration** in rural India has crossed 40% and is projected to reach 65% by 2027, with the majority of new devices supporting the modern web standards (Service Workers, WebRTC, Web Speech API) required for an offline-capable, voice-enabled Progressive Web App.

---

## 4. Stakeholders, Personas & RBAC Matrix

### 4.1 Primary Stakeholders

KrishiSetu serves five distinct user populations, each with different capabilities, data access rights, and workflow requirements. The platform's RBAC model is designed around these roles, and every API endpoint enforces role-based authorization at the route definition level.

| Role | Description | Estimated User Base | Primary Use Cases |
|------|-------------|---------------------|-------------------|
| **Farmer** | Individual cultivator (small, marginal, or large) | ~10M at scale | Disease ID, weather, NDVI, insurance, marketplace, schemes |
| **Agricultural Officer** | State/District agriculture dept official | ~50K | Farmer verification, scheme approvals, crop loss assessment |
| **Supplier** | Verified seed/fertilizer/machinery vendor | ~100K | Product catalog management, order fulfillment, inventory |
| **Insurer** | Insurance company representative (PMFBY empaneled) | ~5K | Policy issuance, claim review, payout authorization |
| **Admin** | Platform operator (KrishiSetu internal) | ~500 | User management, content moderation, system config, audit |

### 4.2 User Personas

#### Persona 1 — Ramesh, Smallholder Farmer (Marginal)

Ramesh is 47 years old, owns 1.2 hectares of land in Vidarbha, Maharashtra, where he cultivates cotton and soybean. He completed primary school but is more comfortable speaking Marathi than reading it. He owns a low-end Android smartphone with a 4G connection that drops frequently. His primary pain points are: unpredictable weather damaging his crops, recurring pest attacks that he cannot diagnose in time, and difficulty navigating government scheme paperwork. He has heard of PM-Kisan but has never successfully enrolled. He wants the platform to talk to him in Marathi, ideally by voice, and to tell him in plain language what to do next.

#### Persona 2 — Lakshmi, Medium-Holding Farmer (Progressive)

Lakshmi is 34 years old, holds a B.Sc. in Agriculture, and manages 8 hectares of paddy and pulses in Thanjavur, Tamil Nadu. She uses a mid-range smartphone with reliable 4G. She is tech-savvy, has used the eNAM portal, and actively seeks data-driven decision tools. Her pain points are: lack of plot-level vegetation health monitoring, opaque mandi price discovery, and difficulty comparing insurance products. She expects the platform to provide NDVI maps for her plots, real-time market prices for her crops, and an integrated view of all available insurance products with clear premium-vs-coverage tradeoffs.

#### Persona 3 — Suresh, Agricultural Officer

Suresh is 52 years old, works in the District Agriculture Office in Belagavi, Karnataka, and is responsible for verifying farmer identities, approving scheme applications, and conducting crop-loss assessments for insurance claims. He uses a desktop computer at the office and a tablet in the field. His pain points are: paper-based verification workflows that take weeks, difficulty cross-referencing farmer-declared land with official land records, and the inability to geographically visualize which farmers in his district have pending applications or recent disease reports. He needs the platform to provide a verification worklist, land-record integration, and a geographic dashboard of his district.

#### Persona 4 — Anjali, Supplier (Seed & Fertilizer Vendor)

Anjali is 38 years old and operates a licensed seed and fertilizer distribution business in Indore, Madhya Pradesh. She serves approximately 2,000 farmers in her region. Her pain points are: managing product catalog updates across multiple channels, tracking orders and deliveries manually, and difficulty demonstrating product authenticity to skeptical farmers. She needs the platform to provide a supplier dashboard for catalog management, order tracking, delivery confirmation, and quality certification display.

#### Persona 5 — Vikram, Insurer (PMFBY Empaneled)

Vikram is 41 years old and works for a public-sector insurance company handling PMFBY policies in Uttar Pradesh. His pain points are: incomplete claim documentation leading to rejection cycles, lack of access to verified satellite NDVI data to assess localized crop loss, and difficulty coordinating with agricultural officers for ground-truth verification. He needs the platform to provide claim review workflows, integrated NDVI evidence for insured plots, and a communication channel with agricultural officers.

### 4.3 RBAC Matrix

The following matrix defines which role can perform which action across the platform's functional capabilities. This matrix is enforced at the API layer through FastAPI dependency injection.

```mermaid
graph TD
    A[KrishiSetu RBAC Model] --> B[Farmer]
    A --> C[Agri-Officer]
    A --> D[Supplier]
    A --> E[Insurer]
    A --> F[Admin]

    B --> B1[Self Profile CRUD]
    B --> B2[Disease ID - Submit & View Own]
    B --> B3[Soil/Weather - View Own Plots]
    B --> B4[NDVI - View Own Plots]
    B --> B5[Insurance - Apply & View Own]
    B --> B6[Marketplace - Browse & Order]
    B --> B7[Schemes - Apply & Track]

    C --> C1[Farmer Verification Workflow]
    C --> C2[District-wide NDVI View]
    C --> C3[Scheme Approval/Rejection]
    C --> C4[Crop Loss Assessment]

    D --> D1[Catalog CRUD - Own Products]
    D --> D2[Order Fulfillment - Own Orders]
    D --> D3[Inventory Management]

    E --> E1[Policy Issuance]
    E --> E2[Claim Review Workflow]
    E --> E3[NDVI Evidence Access]

    F --> F1[User Management - All Roles]
    F --> F2[Content Moderation]
    F --> F3[System Configuration]
    F --> F4[Audit Log Access]
    F --> F5[ML Model Version Management]

    style A fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style B fill:#E6F4EA,stroke:#4CAF50
    style C fill:#FEF3C7,stroke:#D97706
    style D fill:#DBEAFE,stroke:#2563EB
    style E fill:#FCE7F3,stroke:#DB2777
    style F fill:#F3F4F6,stroke:#374151
```

The detailed permission matrix (resource × action × role) is maintained as a versioned configuration file in the repository and is enforced through a single `require_permissions` FastAPI dependency that every protected route declares. This ensures that permission changes propagate through code review rather than runtime database mutations, preserving auditability.

---

## 5. Platform Capabilities Overview

KrishiSetu delivers eight functional modules, each engineered as an independently deployable domain service with a well-defined API contract, data model, and ML pipeline where applicable. The modules share a common identity, profile, and notification infrastructure but otherwise maintain domain isolation to enable parallel development and independent scaling.

### 5.1 Module Catalog

| # | Module | Primary Capability | Key Technology | Data Sources |
|---|--------|-------------------|----------------|--------------|
| 1 | **Identity & Auth** | Aadhaar e-KYC, JWT sessions, RBAC | FastAPI, python-jose, OTP via SMS gateway | UIDAI, in-house user store |
| 2 | **Farmer Profile & Land Records** | Profile, plot registration, geo-boundaries | PostGIS, Leaflet, Bhulekh APIs (state) | User input, state land record portals |
| 3 | **Crop Disease Identification** | Photo-based disease diagnosis | YOLOv8 fine-tuned, PlantVillage+PlantDoc | User uploads, trained model |
| 4 | **Soil Health & Weather** | Soil test history, real-time weather, forecast | IMD API, OpenWeatherMap, SHC portal | IMD, OWM, state soil labs |
| 5 | **Satellite NDVI** | Plot-level vegetation health, weekly trend | Sentinel-2 via Copernicus, rasterio | ESA Sentinel-2, Landsat-8 |
| 6 | **Insurance & PMFBY** | Policy discovery, enrollment, claim filing | PMFBY workflow, integrated NDVI evidence | PMFBY portal, insurer APIs |
| 7 | **Agricultural Marketplace** | Inputs ordering, supplier catalog, delivery | Stripe-style order state machine, Geocoding | Supplier catalogs, logistics APIs |
| 8 | **Govt Schemes Discovery** | Eligibility-matched scheme catalog | Rules engine, scheme registry | PM-Kisan, KCC, SHC, state schemes |
| 9 | **Multilingual & Voice** | 10-language UI, voice query, TTS response | IndicBERT/MuRIL, Web Speech API, Azure TTS | In-house localization, speech models |

### 5.2 Capability Map

The following diagram shows how the eight functional modules relate to each other through shared infrastructure and data flows. The key insight is that **Identity** is the root capability — every other module depends on a verified identity, and every cross-module workflow (e.g., "this farmer's disease report should trigger an insurance claim") traverses the identity graph.

```mermaid
graph TB
    subgraph Foundational Layer
        ID[Identity & Auth<br/>Aadhaar e-KYC, JWT, RBAC]
        PR[Profile & Land Records<br/>Plot registration, geo-boundaries]
        NT[Notifications<br/>SMS, Push, Email, Voice]
    end

    subgraph Intelligence Layer
        DI[Crop Disease ID<br/>YOLOv8 inference]
        SW[Soil & Weather<br/>IMD + OWM integration]
        ND[Satellite NDVI<br/>Sentinel-2 pipeline]
    end

    subgraph Transactional Layer
        IN[Insurance & PMFBY<br/>Policy + Claims]
        MK[Marketplace<br/>Order + Delivery]
        SC[Govt Schemes<br/>Eligibility matching]
    end

    subgraph Accessibility Layer
        ML[Multilingual & Voice<br/>10 languages, TTS/STT]
    end

    ID --> PR
    ID --> NT
    PR --> DI
    PR --> SW
    PR --> ND
    PR --> IN
    PR --> MK
    PR --> SC
    DI --> IN
    ND --> IN
    SW --> SC
    ML -.-> ID
    ML -.-> DI
    ML -.-> MK
    ML -.-> SC

    style ID fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:3px
    style PR fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style NT fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style DI fill:#E6F4EA,stroke:#4CAF50,stroke-width:2px
    style SW fill:#E6F4EA,stroke:#4CAF50,stroke-width:2px
    style ND fill:#E6F4EA,stroke:#4CAF50,stroke-width:2px
    style IN fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style MK fill:#DBEAFE,stroke:#2563EB,stroke-width:2px
    style SC fill:#FCE7F3,stroke:#DB2777,stroke-width:2px
    style ML fill:#F3F4F6,stroke:#374151,stroke-width:2px,stroke-dasharray: 5 5
```

### 5.3 Cross-Module Workflows

The platform's power comes from cross-module orchestration. Three illustrative workflows demonstrate this:

**Workflow A — Disease-to-Claim.** A farmer uploads a photo of an affected crop. The Disease ID module identifies the disease with confidence >85%. The system automatically checks whether the affected plot has active PMFBY insurance, whether the detected disease is a covered peril, and whether the NDVI trend for that plot corroborates the loss. If all three conditions hold, the system pre-fills a claim form and notifies the farmer with a one-tap "Submit Claim" action. This compresses a multi-week bureaucratic process into minutes.

**Workflow B — Weather-to-Advisory.** The Soil & Weather module detects an imminent hailstorm forecast for a district. The system queries all registered plots in that district, identifies the crops currently in vulnerable growth stages based on sowing date and crop calendar, and dispatches localized voice advisories in the farmer's preferred language with actionable mitigation steps. The advisory is logged against the farmer's profile and used as evidence in any subsequent insurance claim.

**Workflow C — Schemes-to-Action.** A new state government scheme for drip irrigation subsidy is announced. The Schemes module's rules engine evaluates all registered farmers against the eligibility criteria (landholding size, crop type, district, prior scheme availed) and produces a ranked list of eligible farmers. Each farmer receives a targeted notification with the application link pre-populated from their verified profile, dramatically increasing conversion compared to broad untargeted announcements.

These workflows are not features bolted on after the modules are built — they are the reason the modules exist as a unified platform rather than separate apps. The architecture is explicitly designed to support these cross-module event-driven compositions through a shared event bus.

---

## 6. High-Level System Architecture

### 6.1 C4 Context Diagram

The Context diagram shows KrishiSetu as a single system in the center, with all external actors and systems it interacts with around it. This view establishes the system boundary and the external dependencies that the platform's architecture must accommodate.

```mermaid
graph TB
    subgraph External Users
        F[Farmer<br/>Mobile Web]
        AO[Agri Officer<br/>Desktop + Tablet]
        SP[Supplier<br/>Desktop Web]
        IN[Insurer<br/>Desktop Web]
        AD[Admin<br/>Desktop Web]
    end

    subgraph KrishiSetu Platform
        KS[KrishiSetu System]
    end

    subgraph Government Systems
        UID[UIDAI<br/>Aadhaar e-KYC]
        IMD[IMD<br/>Weather Services]
        PMK[PM-Kisan Portal]
        PMF[PMFBY Portal]
        SHC[Soil Health Card Portal]
        ENAM[eNAM Market]
        BHL[Bhulekh / Land Records<br/>State portals]
        DL[DigiLocker]
    end

    subgraph Third-Party Services
        OWM[OpenWeatherMap]
        SEN[Sentinel-2 / Copernicus]
        SMS[SMS Gateway<br/>MSG91 / Karix]
        PUSH[FCM Push Notifications]
        TTS[Azure / Google TTS]
        MAPS[Mapbox / OSM Tiles]
        LOG[Cloud Logging<br/>Loki / CloudWatch]
    end

    F -->|HTTPS| KS
    AO -->|HTTPS| KS
    SP -->|HTTPS| KS
    IN -->|HTTPS| KS
    AD -->|HTTPS| KS

    KS -->|Aadhaar OTP/Biometric API| UID
    KS -->|REST API| IMD
    KS -->|REST API| PMK
    KS -->|REST API| PMF
    KS -->|REST API| SHC
    KS -->|REST API| ENAM
    KS -->|REST API| BHL
    KS -->|OAuth| DL

    KS -->|REST API| OWM
    KS -->|REST API| SEN
    KS -->|SMS API| SMS
    KS -->|Firebase Admin SDK| PUSH
    KS -->|REST API| TTS
    KS -->|Raster Tiles| MAPS
    KS -->|Structured Logs| LOG

    style KS fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:3px
    style F fill:#E6F4EA,stroke:#4CAF50
    style AO fill:#FEF3C7,stroke:#D97706
    style SP fill:#DBEAFE,stroke:#2563EB
    style IN fill:#FCE7F3,stroke:#DB2777
    style AD fill:#F3F4F6,stroke:#374151
    style UID fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style IMD fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style PMK fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style PMF fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style SHC fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style ENAM fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style BHL.fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style DL.fill:#FEF3C7,stroke:#D97706,stroke-width:2px
```

### 6.2 C4 Container Diagram

The Container diagram decomposes the KrishiSetu system into its major deployable units. Each container is a separately runnable process with its own technology stack, communicating with other containers through well-defined protocols.

```mermaid
graph TB
    subgraph Client Tier
        WB[Next.js 14 Web App<br/>App Router, RSC, TypeScript<br/>Tailwind + shadcn/ui]
    end

    subgraph Edge Tier
        CDN[CDN<br/>Cloudflare / CloudFront<br/>Static assets, image cache]
        LB[Load Balancer<br/>NGINX / ALB<br/>TLS termination, rate limit]
    end

    subgraph Application Tier
        API[FastAPI Application<br/>Python 3.12, async<br/>UVloop, Gunicorn workers]
        WRK[Celery Workers<br/>Python 3.12<br/>ML inference, async tasks]
        BEAT[Celery Beat<br/>Scheduled jobs<br/>NDVI refresh, scheme sync]
    end

    subgraph ML Tier
        INF[ML Inference Service<br/>FastAPI + ONNX Runtime<br/>YOLOv8, NLP models]
        REG[Model Registry<br/>MLflow<br/>Versioned models]
    end

    subgraph Data Tier
        PG[(PostgreSQL 16<br/>PostGIS, partitioned<br/>Read replicas)]
        RD[(Redis 7<br/>Cache + Task Queue)]
        S3[(Object Storage<br/>S3 / MinIO<br/>Images, model artifacts)]
    end

    subgraph Observability Tier
        LOK[(Loki<br/>Log aggregation)]
        PROM[(Prometheus<br/>Metrics)]
        JAE[(Jaeger<br/>Distributed tracing)]
        GRA[Grafana<br/>Dashboards]
    end

    WB -->|HTTPS REST/JSON| LB
    LB -->|HTTPS| API
    CDN -->|Cache hit| WB

    API -->|SQLAlchemy async| PG
    API -->|aioredis| RD
    API -->|boto3| S3
    API -->|gRPC/HTTP| INF
    API -->|Enqueue tasks| RD

    WRK -->|Consume tasks| RD
    WRK -->|SQLAlchemy| PG
    WRK -->|boto3| S3
    WRK -->|HTTP| INF
    WRK -->|External APIs| IMD
    WRK -->|External APIs| SEN

    BEAT -->|Schedule| RD

    INF -->|Load model| REG
    REG -->|Store artifacts| S3

    API -->|Structured logs| LOK
    WRK -->|Structured logs| LOK
    INF -->|Structured logs| LOK
    API -->|/metrics| PROM
    WRK -->|/metrics| PROM
    INF -->|/metrics| PROM
    API -->|Spans| JAE
    INF -->|Spans| JAE

    GRA -->|Query| LOK
    GRA -->|Query| PROM
    GRA -->|Query| JAE

    style WB fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style API fill:#0F766E,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style WRK fill:#0F766E,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style BEAT fill:#0F766E,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style INF fill:#7C3AED,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style REG fill:#7C3AED,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style PG fill:#1E40AF,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style RD fill:#DC2626,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style S3 fill:#D97706,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style LOK fill:#374151,color:#FFFFFF,stroke:#4CAF50
    style PROM fill:#374151,color:#FFFFFF,stroke:#4CAF50
    style JAE fill:#374151,color:#FFFFFF,stroke:#4CAF50
    style GRA fill:#374151,color:#FFFFFF,stroke:#4CAF50
```

### 6.3 Request Flow

A typical authenticated request from a farmer's browser to the KrishiSetu API flows through the system as follows:

1. The farmer opens the Next.js app in their browser. The initial HTML is server-rendered by Next.js (RSC) and streamed to the client, minimizing time-to-first-contentful-paint even on slow networks.
2. Static assets (JS bundles, CSS, fonts, images) are served from the CDN edge location closest to the farmer, reducing latency.
3. When the farmer navigates to "My Plots" or submits a disease photo, the Next.js client component makes a fetch call to `https://api.krishisetu.in/v1/...` with the JWT bearer token in the Authorization header.
4. The request hits the load balancer, which terminates TLS, applies global rate-limiting rules, and forwards the request to a healthy FastAPI worker.
5. The FastAPI worker receives the request, runs the ASGI middleware chain (CORS, request ID injection, structured logging, Prometheus metrics, exception handler), then dispatches to the route handler.
6. The route handler runs the dependency injection chain — `get_current_user` (JWT verification), `require_permissions` (RBAC check), `rate_limit` (per-user limit), `validate_input` (Pydantic schema) — before executing business logic.
7. Business logic queries PostgreSQL via async SQLAlchemy, reads from Redis cache where applicable, and may enqueue a Celery task for long-running work (e.g., NDVI computation).
8. The response is serialized through a Pydantic response model, logged with the request ID, and returned to the client.
9. Throughout the flow, OpenTelemetry spans are emitted to Jaeger, structured logs to Loki, and metrics to Prometheus, all keyed by the same request ID.

### 6.4 Async Task Flow

Long-running or external-API-dependent operations are offloaded to Celery workers via Redis broker. The typical patterns are:

- **ML Inference Jobs.** When a farmer uploads a crop photo, the API stores the image in S3, enqueues a `predict_disease` Celery task, and returns a `202 Accepted` with a task ID. The worker pulls the task, calls the ML Inference Service, persists the result, and notifies the farmer via WebSocket or polling endpoint.
- **Satellite NDVI Refresh.** A Celery Beat job runs nightly to identify plots whose NDVI is older than 7 days, fetches the latest Sentinel-2 imagery for those plot bounding boxes, computes NDVI statistics, and persists them.
- **External API Sync.** Scheme catalogs, mandi prices, and weather forecasts are periodically synced from government APIs via Celery Beat jobs, with results cached in PostgreSQL and Redis.
- **Notification Dispatch.** Voice advisories triggered by weather alerts are generated via TTS API calls inside Celery workers, then dispatched via SMS/push channels.

---

## 7. Technology Stack Decisions

The technology stack is the result of deliberate evaluation against the requirements: government-grade reliability, Python-first backend, PostgreSQL flexibility, high scalability, security rigor, and a component-based, accessible UI. The stack is fixed; substitutions require formal architectural review.

### 7.1 Stack Summary Table

| Layer | Technology | Version | Justification |
|-------|-----------|---------|---------------|
| **Backend Framework** | FastAPI | 0.115+ | Async, type-safe, automatic OpenAPI docs, dependency injection, Pydantic-native validation, best Python framework for production ML APIs |
| **Python Runtime** | CPython | 3.12 | Performance improvements, exception groups, task groups, type system improvements |
| **ASGI Server** | Uvicorn + Gunicorn | latest | Uvicorn for ASGI, Gunicorn as process manager for production |
| **ORM** | SQLAlchemy | 2.0+ (async) | Mature, async support, type-safe with mypy, Alembic migrations |
| **Database** | PostgreSQL | 16 | Required by spec; PostGIS for geospatial, partitioning for scale, JSONB for flexible schemas, mature replication |
| **Cache & Message Broker** | Redis | 7.4+ | Sub-ms latency for caching, pub/sub for notifications, Celery broker, streams for event log |
| **Background Tasks** | Celery | 5.4+ | Distributed task queue, scheduling via Beat, retries, priority queues, mature observability |
| **Frontend Framework** | Next.js | 14+ (App Router) | RSC for SSR + low bandwidth, component-based, i18n routing, image optimization, mature ecosystem |
| **Frontend Language** | TypeScript | 5.5+ | Type safety, IDE support, refactor confidence |
| **UI Library** | shadcn/ui + Radix UI | latest | Accessible (WAI-ARIA), composable, no opinionated styling, professional aesthetic matching reference UI |
| **Styling** | Tailwind CSS | 3.4+ | Utility-first, consistent design tokens, small production bundles |
| **Maps** | Leaflet + React-Leaflet | latest | Open-source, performant, integrates with PostGIS-served GeoJSON |
| **Charts** | Recharts | latest | React-native, responsive, accessible |
| **ML Training** | PyTorch + Ultralytics + HuggingFace Transformers | 2.4+, 8.2+, 4.4+ | Industry standard for vision and NLP |
| **ML Serving** | ONNX Runtime + FastAPI microservice | 1.19+ | Hardware-agnostic, optimized inference, single model server for all models |
| **ML Tracking** | MLflow | 2.16+ | Model registry, experiment tracking, model versioning |
| **Object Storage** | MinIO (dev) / S3 (prod) | latest | S3-compatible API for local development, seamless prod migration |
| **Search** | PostgreSQL FTS + pg_trgm (Phase 1) → OpenSearch (Phase 2) | built-in | Start with Postgres for simplicity, migrate to OpenSearch when search load justifies |
| **Containerization** | Docker + Docker Compose | 24+, 2.29+ | Standard packaging, local dev parity with prod |
| **Reverse Proxy** | NGINX | 1.27+ | TLS termination, static asset serving, rate limiting at edge |
| **Observability — Logs** | Loki + Promtail | 3.1+ | Cost-effective log aggregation, integrates with Grafana |
| **Observability — Metrics** | Prometheus | 2.54+ | De facto standard, dimensional metrics, alerting |
| **Observability — Tracing** | OpenTelemetry + Jaeger | 1.50+ | Vendor-neutral, auto-instrumentation for FastAPI/SQLAlchemy |
| **Dashboards** | Grafana | 11.3+ | Unified dashboards across Loki/Prometheus/Jaeger |
| **CI/CD** | GitHub Actions | n/a | Free for public repos, matrix builds, reusable workflows |
| **Testing — Backend** | pytest + pytest-asyncio + httpx | 8.3+, 0.24+, 0.27+ | Standard Python testing stack |
| **Testing — Frontend** | Vitest + Playwright | 2.1+, 1.47+ | Fast unit tests, modern e2e |
| **Load Testing** | Locust | 2.31+ | Python-native, distributed, realistic user simulation |
| **Secrets Management** | HashiCorp Vault (prod) / .env (dev) | 1.18+ | Centralized secrets, rotation, audit trail |

### 7.2 Key Decision Rationales

#### 7.2.1 Why FastAPI over Django/Flask

The user's specification called for a modern, production-ready Python backend. FastAPI was selected over Django and Flask for the following reasons:

- **Async-First.** KrishiSetu's API layer is fundamentally I/O-bound — it makes frequent calls to PostgreSQL, Redis, external government APIs (Aadhaar, IMD, PMFBY), and the ML inference service. FastAPI's native async/await support on ASGI enables high concurrency with minimal worker threads, whereas Django's async story is still maturing and Flask requires explicit async extensions.
- **Type Safety End-to-End.** FastAPI's Pydantic-native request/response validation means every API contract is enforced at the framework level, with the same Pydantic models generating OpenAPI documentation. This eliminates an entire class of bugs where documentation drifts from implementation.
- **Dependency Injection.** FastAPI's `Depends()` system is purpose-built for the kind of layered authentication, authorization, rate limiting, and validation that a government platform requires. Each route declares its requirements declaratively, and the framework handles the wiring.
- **Automatic OpenAPI.** Every endpoint's contract is auto-generated as OpenAPI 3.1, which the Next.js frontend consumes via `openapi-typescript` to generate type-safe API clients. This eliminates the manual API client maintenance tax.
- **Performance.** FastAPI on Uvicorn with UVloop achieves throughput comparable to Node.js frameworks, comfortably handling the platform's expected request volume.
- **ML Ecosystem Alignment.** The Python ML ecosystem (PyTorch, Transformers, Ultralytics) is native to Python, and serving models via FastAPI microservices is the industry-standard pattern.

The trade-off is that FastAPI lacks Django's batteries-included admin, auth, and ORM — but for a government platform with custom RBAC and a custom admin console, these "batteries" would need to be replaced anyway, and SQLAlchemy 2.0's async mode provides a more flexible ORM than Django's.

#### 7.2.2 Why Next.js 14 over Jinja2+HTMX

The user asked for "the best frontend that fits the FastAPI stack." While HTMX+Jinja2 is a valid choice for simpler applications, Next.js 14 was selected for the following reasons:

- **Component-Based.** The user explicitly requested a component-based approach. Next.js with React Server Components provides the most mature component model in the frontend ecosystem, with shadcn/ui offering a comprehensive accessible component library that matches the reference UI's professional aesthetic.
- **Server-Side Rendering.** Next.js App Router renders initial HTML on the server and streams it to the client, dramatically improving time-to-first-contentful-paint for low-bandwidth rural users. This is critical for a platform whose primary users are on 2G/3G connections.
- **Rich Dashboard Support.** The Crop Analysis NDVI reference UI shows a complex dashboard with maps, charts, parameter cards, and tab navigation. Next.js with React-Leaflet (maps), Recharts (charts), and shadcn/ui (cards, tabs) provides native support for this kind of dashboard.
- **Decoupled from Backend.** Next.js talks to FastAPI purely over JSON APIs, enabling independent deployment, scaling, and team ownership. The frontend can be served from a CDN edge while the API runs in a single region.
- **i18n Routing.** Next.js's App Router has built-in internationalized routing, making the 10-language requirement straightforward to implement.
- **TypeScript End-to-End.** The OpenAPI spec generated by FastAPI is consumed by `openapi-typescript` to produce TypeScript types, ensuring the frontend and backend agree on every API contract. This eliminates an entire class of integration bugs.

The trade-off is that Next.js adds a Node.js service to the deployment topology, slightly increasing operational complexity. This is acceptable given the user experience benefits.

#### 7.2.3 Why PostgreSQL with PostGIS

PostgreSQL is mandated by the user specification. PostGIS is added because the platform's geographic capabilities — plot boundary storage, NDVI tile queries, district-level aggregations, supplier proximity search — require spatial indexing and queries that PostGIS provides natively. PostGIS extends PostgreSQL with `geometry` and `geography` types, spatial indexes (GiST), and hundreds of spatial functions, all of which are required for the platform's map-based features.

#### 7.2.4 Why a Separate ML Inference Service

The ML inference service is deployed as a separate FastAPI microservice rather than embedded in the main API for three reasons:

- **Independent Scaling.** ML inference is GPU-bound and has different scaling characteristics than the I/O-bound main API. Separating the two allows the inference service to scale horizontally on GPU node pools while the main API scales on cheaper CPU nodes.
- **Model Versioning.** A separate service can be deployed with a specific model version, allowing A/B testing and canary rollouts of new models without redeploying the main API.
- **Resource Isolation.** A misbehaving model (e.g., infinite loop, memory leak) cannot take down the main API. The inference service can be restarted independently.

The main API communicates with the inference service over HTTP with a short timeout and circuit breaker pattern, falling back to a "model unavailable" error rather than blocking.

#### 7.2.5 Why Celery over FastAPI BackgroundTasks

FastAPI's built-in `BackgroundTasks` is suitable for fire-and-forget operations within a single process, but KrishiSetu's requirements demand a real task queue because:

- **Persistence.** Tasks must survive worker restarts. A farmer uploading a disease photo at 2 AM must not lose the inference if the worker pod restarts at 2:01 AM.
- **Retries.** External API calls (Sentinel-2, IMD) frequently fail transiently. Celery's exponential backoff retry policy is essential.
- **Scheduling.** Celery Beat provides cron-like scheduling for nightly NDVI refresh, hourly weather sync, and daily scheme catalog updates.
- **Observability.** Celery integrates with Flower for task monitoring, Prometheus for metrics, and structured logging for traceability.
- **Priority Queues.** Disease ID requests (real-time, user-facing) and NDVI computation (background, batch) can be separated into priority queues.

---

## 8. Repository & Project Structure

KrishiSetu is organized as a **monorepo** managed by `pnpm` workspaces (for the frontend and shared TypeScript packages) and Python virtual environments (for the backend and ML services). A monorepo was chosen over polyrepo because the platform's modules are tightly coupled through shared types, API contracts, and ML model versions, and the team is small enough that monorepo coordination overhead is minimal.

### 8.1 Top-Level Layout

```
krishisetu/
├── apps/
│   ├── web/                       # Next.js 14 frontend application
│   ├── api/                       # FastAPI backend application
│   ├── ml-inference/              # FastAPI ML inference microservice
│   └── worker/                    # Celery worker application
│
├── packages/
│   ├── ts-types/                  # Shared TypeScript types (auto-generated from OpenAPI)
│   ├── ts-config/                 # Shared TypeScript config
│   ├── eslint-config/             # Shared ESLint config
│   └── ui/                        # Shared shadcn/ui components (web-specific)
│
├── services/
│   ├── postgres/                  # Postgres init scripts, extensions, migrations
│   ├── redis/                     # Redis config
│   ├── nginx/                     # NGINX reverse proxy config
│   └── observability/             # Loki, Prometheus, Jaeger, Grafana configs
│
├── ml/
│   ├── datasets/                  # Dataset definitions and loaders (not the data itself)
│   ├── training/                  # Training scripts per use case
│   ├── evaluation/                # Evaluation scripts and metrics
│   └── registry/                  # MLflow model registry configs
│
├── infra/
│   ├── docker/                    # Dockerfiles per service
│   ├── docker-compose.yml         # Local dev environment
│   ├── docker-compose.prod.yml    # Production overrides
│   └── terraform/                 # (Future) Infrastructure as Code
│
├── tools/
│   ├── scripts/                   # Utility scripts (seed, migrate, backfill)
│   └── cli/                       # Admin CLI tools
│
├── docs/
│   ├── architecture/              # ADRs (Architecture Decision Records)
│   ├── api/                       # API documentation (auto-generated)
│   ├── runbooks/                  # Operational runbooks
│   └── onboarding/                # Engineering onboarding
│
├── .github/
│   ├── workflows/                 # GitHub Actions CI/CD pipelines
│   └── PULL_REQUEST_TEMPLATE.md
│
├── pnpm-workspace.yaml
├── package.json
├── turbo.json                     # Turborepo build orchestration
├── pyproject.toml                 # Python project config (uv / poetry)
├── .env.example
├── .gitignore
├── README.md
└── LICENSE
```

### 8.2 Backend Application Structure (`apps/api/`)

The FastAPI backend follows a **layered, domain-driven** structure. Each domain module is self-contained with its own routes, services, schemas, and models, while shared infrastructure (database, cache, auth, logging) lives in a `core/` package.

```
apps/api/
├── krishisetu/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory, middleware, router mounting
│   ├── core/
│   │   ├── config.py              # Pydantic Settings (env vars)
│   │   ├── database.py            # Async SQLAlchemy engine, session factory
│   │   ├── redis.py               # Redis client, cache helpers
│   │   ├── security.py            # JWT, password hashing, Aadhaar encryption
│   │   ├── dependencies.py        # Shared FastAPI dependencies (current_user, RBAC, rate limit)
│   │   ├── middleware.py          # Request ID, logging, metrics, error handlers
│   │   ├── exceptions.py          # Custom exception hierarchy
│   │   └── logging.py             # Structured logging config (structlog)
│   │
│   ├── domains/
│   │   ├── identity/              # Auth, Aadhaar e-KYC, sessions
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── schemas.py
│   │   │   ├── models.py
│   │   │   └── repository.py
│   │   ├── profile/               # Farmer profile, plots, land records
│   │   ├── disease/               # Crop disease identification
│   │   ├── soil/                  # Soil health, weather
│   │   ├── ndvi/                  # Satellite NDVI
│   │   ├── insurance/             # PMFBY, policies, claims
│   │   ├── marketplace/           # Catalog, orders, suppliers
│   │   ├── schemes/               # Govt scheme discovery
│   │   └── localization/          # i18n strings, voice TTS/STT
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py        # v1 router aggregator
│   │       └── ...                # Per-domain route modules re-exported
│   │
│   └── workers/                   # Celery task definitions
│       ├── celery_app.py
│       ├── tasks/
│       │   ├── disease.py
│       │   ├── ndvi.py
│       │   ├── weather.py
│       │   └── notifications.py
│       └── beat_schedule.py
│
├── alembic/                       # Database migrations
│   ├── env.py
│   ├── versions/
│   └── alembic.ini
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── conftest.py
│
├── pyproject.toml
├── Dockerfile
└── README.md
```

### 8.3 Frontend Application Structure (`apps/web/`)

The Next.js frontend follows the **App Router** conventions with feature-based organization. Each route segment has its own directory with co-located components, queries, and types.

```
apps/web/
├── src/
│   ├── app/                       # Next.js App Router
│   │   ├── [locale]/              # i18n locale segment (en, hi, mr, ta, ...)
│   │   │   ├── (auth)/            # Auth route group (login, signup, forgot)
│   │   │   ├── (dashboard)/       # Authenticated dashboard route group
│   │   │   │   ├── layout.tsx     # Dashboard layout (sidebar, header)
│   │   │   │   ├── plots/         # Plot management
│   │   │   │   ├── disease/       # Disease identification
│   │   │   │   ├── ndvi/          # NDVI monitoring
│   │   │   │   ├── weather/       # Weather dashboard
│   │   │   │   ├── insurance/     # Insurance & PMFBY
│   │   │   │   ├── marketplace/   # Marketplace browsing + orders
│   │   │   │   ├── schemes/       # Govt schemes
│   │   │   │   └── settings/      # Profile settings
│   │   │   ├── (public)/          # Public (unauthenticated) pages
│   │   │   │   ├── page.tsx       # Landing page
│   │   │   │   ├── about/
│   │   │   │   └── schemes/       # Public scheme catalog
│   │   │   └── layout.tsx         # Root locale layout
│   │   ├── api/                   # Next.js API routes (BFF pattern)
│   │   │   └── auth/              # Next-auth session handlers
│   │   ├── layout.tsx             # Root layout (html, body, providers)
│   │   └── globals.css            # Tailwind base + design tokens
│   │
│   ├── components/
│   │   ├── ui/                    # shadcn/ui primitives (button, card, dialog, etc.)
│   │   ├── charts/                # Recharts wrappers
│   │   ├── maps/                  # Leaflet wrappers
│   │   ├── forms/                 # Form components (react-hook-form + zod)
│   │   ├── layouts/               # Layout components (sidebar, header, footer)
│   │   └── features/              # Feature-specific composite components
│   │       ├── disease/
│   │       ├── ndvi/
│   │       ├── insurance/
│   │       └── ...
│   │
│   ├── lib/
│   │   ├── api/                   # Auto-generated API client from OpenAPI
│   │   ├── auth/                  # Next-auth config
│   │   ├── i18n/                  # i18n config, locale loaders
│   │   ├── utils/                 # Utility functions
│   │   └── constants.ts
│   │
│   ├── hooks/                     # React hooks (usePlots, useDiseaseReport, etc.)
│   ├── stores/                    # Zustand stores (UI state, auth state)
│   ├── types/                     # App-specific TypeScript types
│   └── messages/                  # i18n message files per locale
│       ├── en.json
│       ├── hi.json
│       ├── mr.json
│       ├── ta.json
│       ├── te.json
│       ├── bn.json
│       ├── kn.json
│       ├── gu.json
│       ├── pa.json
│       └── ml.json
│
├── public/
│   ├── images/
│   └── icons/
│
├── tests/
│   ├── unit/                      # Vitest tests
│   └── e2e/                       # Playwright tests
│
├── next.config.mjs
├── tailwind.config.ts
├── tsconfig.json
├── package.json
├── Dockerfile
└── README.md
```

### 8.4 ML Inference Service Structure (`apps/ml-inference/`)

```
apps/ml-inference/
├── krishisetu_ml/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app for inference service
│   ├── core/
│   │   ├── config.py
│   │   ├── model_registry.py      # MLflow model loader
│   │   └── onnx_runtime.py        # ONNX session management
│   │
│   ├── models/                    # Model wrappers per use case
│   │   ├── disease_classifier.py  # YOLOv8 disease detection
│   │   ├── soil_classifier.py     # Soil type classification
│   │   ├── voice_asr.py           # Multilingual ASR
│   │   ├── voice_tts.py           # Multilingual TTS
│   │   └── query_nlp.py           # Vernacular query understanding
│   │
│   └── api/
│       ├── disease.py             # /predict/disease endpoint
│       ├── soil.py                # /predict/soil endpoint
│       ├── voice.py               # /asr and /tts endpoints
│       └── nlp.py                 # /understand endpoint
│
├── tests/
├── pyproject.toml
├── Dockerfile
└── README.md
```

### 8.5 Shared TypeScript Package (`packages/ts-types/`)

The shared types package is **auto-generated** from the FastAPI OpenAPI spec using `openapi-typescript`. This package is consumed by both `apps/web` and any other TypeScript consumers (e.g., admin tools). The generation pipeline runs in CI on every backend change, ensuring the frontend always has up-to-date types.

```
packages/ts-types/
├── src/
│   ├── index.ts                   # Re-exports generated types
│   └── generated/                 # Auto-generated from OpenAPI (do not edit)
│       └── api.d.ts
├── scripts/
│   └── generate.ts                # Fetches OpenAPI spec and generates types
├── package.json
└── tsconfig.json
```

---

## 9. Backend Architecture (FastAPI)

The backend is the platform's core engineering surface. Every architectural choice in this section is driven by the requirements of a government-grade, millions-of-users, security-sensitive, ML-powered system. The guiding constraint is that the backend must be horizontally scalable, observable, type-safe, and secure-by-construction.

### 9.1 Application Bootstrap

The FastAPI application is constructed via an **application factory** pattern, which enables the creation of multiple application variants (e.g., main API, admin API, internal API) from the same codebase with different middleware and router configurations. The factory is defined in `apps/api/krishisetu/main.py` and is responsible for:

1. Loading configuration from environment variables via Pydantic Settings, with validation that all required variables are present at startup.
2. Initializing the async SQLAlchemy engine and session factory with connection pool tuning.
3. Initializing the Redis client with connection retry logic.
4. Mounting middleware in the correct order (request ID → CORS → logging → metrics → exception handler).
5. Mounting domain routers under the `/api/v1` prefix.
6. Mounting health check endpoints at `/health`, `/ready`, and `/metrics` (Prometheus).
7. Registering startup and shutdown handlers for graceful initialization and cleanup.

```python
# apps/api/krishisetu/main.py (illustrative)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from krishisetu.core.config import settings
from krishisetu.core.database import engine, SessionLocal
from krishisetu.core.redis import redis_client
from krishisetu.core.middleware import (
    RequestIDMiddleware,
    LoggingMiddleware,
    PrometheusMiddleware,
    ExceptionHandlerMiddleware,
)
from krishisetu.api.v1 import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await redis_client.ping()
    yield
    # Shutdown
    await engine.dispose()
    await redis_client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="KrishiSetu API",
        version="1.0.0",
        docs_url="/docs" if settings.ENV != "production" else None,
        redoc_url="/redoc" if settings.ENV != "production" else None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware (order matters — outermost first)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(api_router, prefix="/api/v1")

    # Health
    app.add_route("/health", health_check)
    app.add_route("/ready", readiness_check)

    return app


app = create_app()
```

### 9.2 Configuration Management

All configuration is loaded through a single `Settings` class that extends `pydantic_settings.BaseSettings`. This approach provides:

- **Type validation at startup.** A misconfigured environment variable (e.g., a non-integer where an integer is expected) causes the application to fail fast at boot, rather than fail mysteriously at runtime.
- **Secret separation.** Sensitive values (database URLs, JWT secrets, API keys) are loaded from environment variables or a secrets manager (Vault in production), never from the codebase.
- **Environment profiles.** Distinct settings files for `dev`, `staging`, and `production` enable environment-specific behavior (e.g., debug mode, log level, rate limits).

```python
# apps/api/krishisetu/core/config.py (illustrative)
from functools import lru_cache
from pydantic import Field, SecretStr, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Environment
    ENV: str = Field("development", pattern="^(development|staging|production)$")
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Redis
    REDIS_URL: RedisDsn

    # Security
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_BCRYPT_ROUNDS: int = 12
    Aadhaar_ENCRYPTION_KEY: SecretStr

    # Aadhaar e-KYC
    UIDAI_API_URL: str = "https://api.uidai.gov.in"
    UIDAI_API_KEY: SecretStr
    UIDAI_OTP_TEMPLATE_ID: str

    # External APIs
    IMD_API_KEY: SecretStr
    OPENWEATHERMAP_API_KEY: SecretStr
    SENTINEL_HUB_CLIENT_ID: SecretStr
    SENTINEL_HUB_CLIENT_SECRET: SecretStr
    PMFBY_API_BASE_URL: str
    PMFBY_API_KEY: SecretStr

    # SMS / Push
    MSG91_AUTH_KEY: SecretStr
    FCM_SERVER_KEY: SecretStr

    # Object Storage
    S3_ENDPOINT: str
    S3_ACCESS_KEY: SecretStr
    S3_SECRET_KEY: SecretStr
    S3_BUCKET_NAME: str
    S3_REGION: str = "ap-south-1"

    # Rate Limiting
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_ML: str = "20/minute"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

### 9.3 Database Layer

The database layer uses **SQLAlchemy 2.0 in async mode** with `asyncpg` as the driver. The key design choices are:

- **Async Engine.** All database operations are non-blocking, enabling the FastAPI event loop to handle thousands of concurrent requests without being starved by I/O.
- **Declarative Base with Type Annotations.** SQLAlchemy 2.0's typed declarative base provides IDE autocompletion and mypy type checking of all model attributes.
- **Session-per-Request.** Each request gets its own async session, scoped via FastAPI dependency injection. The session is committed on successful handler completion and rolled back on exception.
- **Connection Pool Tuning.** Pool size, max overflow, and recycle interval are configured via environment variables to match the deployment's database capacity.
- **Read Replica Routing.** Read-heavy endpoints (NDVI view, marketplace browse, scheme list) are routed to read replicas via a custom SQLAlchemy execution option, while write operations always hit the primary.

```python
# apps/api/krishisetu/core/database.py (illustrative)
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from krishisetu.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    str(settings.DATABASE_URL),
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### 9.4 Authentication & Authorization

Authentication is **JWT-based** with short-lived access tokens (30 minutes) and longer-lived refresh tokens (30 days). The flow is:

1. User submits phone number + OTP (or Aadhaar + OTP) to `/auth/login/request-otp`.
2. The system generates a 6-digit OTP, stores it in Redis with a 5-minute TTL keyed by phone number, and dispatches it via the SMS gateway.
3. User submits the OTP to `/auth/login/verify-otp`. The system verifies the OTP, looks up or creates the user record, and issues an access token + refresh token pair.
4. The access token is sent in the `Authorization: Bearer <token>` header on every subsequent request.
5. When the access token expires, the client uses the refresh token to obtain a new access token at `/auth/refresh`.
6. Refresh tokens are **rotated** — each refresh issues a new refresh token and invalidates the old one, mitigating token theft.
7. Refresh tokens are stored as **hashed** values in a `refresh_tokens` table, enabling revocation.

```python
# apps/api/krishisetu/core/security.py (illustrative)
from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from passlib.context import CryptContext

from krishisetu.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", rounds=settings.PASSWORD_BCRYPT_ROUNDS)


def create_access_token(subject: str, claims: dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, "type": "access", **claims}
    return jwt.encode(payload, settings.JWT_SECRET.get_secret_value(), algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": subject, "exp": expire, "type": "refresh", "jti": secrets.token_urlsafe(32)}
    return jwt.encode(payload, settings.JWT_SECRET.get_secret_value(), algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != expected_type:
            raise InvalidTokenError("Wrong token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Token expired")
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(str(e))
```

#### RBAC Implementation

RBAC is enforced through a single reusable FastAPI dependency, `require_permissions`, which is declared on every protected route. The dependency takes a list of required permission strings and raises `403 Forbidden` if the authenticated user's role does not grant all required permissions.

```python
# apps/api/krishisetu/core/dependencies.py (illustrative)
from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import get_db
from krishisetu.core.security import verify_token
from krishisetu.domains.identity.models import User, UserRole
from krishisetu.domains.identity.repository import get_user_by_id


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = verify_token(token, expected_type="access")
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))

    user = await get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_permissions(*permissions: str):
    async def checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        user_permissions = ROLE_PERMISSIONS.get(current_user.role, set())
        if not all(p in user_permissions for p in permissions):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Missing permissions: {set(permissions) - user_permissions}",
            )
        return current_user
    return checker
```

### 9.5 Rate Limiting

Rate limiting is implemented at two layers:

- **Edge Rate Limiting (NGINX).** Coarse-grained, IP-based limits applied at the load balancer to prevent DDoS and basic abuse. Configured to allow 100 requests per second per IP, with bursts up to 200.
- **Application Rate Limiting (FastAPI).** Fine-grained, per-user-or-IP limits applied in middleware using Redis as the counter store. Limits are declared per-route via a custom decorator and stored in Redis with sliding window semantics.

```python
# apps/api/krishisetu/core/rate_limit.py (illustrative)
from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from krishisetu.core.redis import redis_client


def rate_limit(limit: str):
    """e.g. @rate_limit('100/minute')"""
    count, _, window = limit.partition("/")
    count, window = int(count), window.rstrip("s")
    window_seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[window]

    async def checker(request: Request):
        identifier = request.headers.get("X-User-Id") or request.client.host
        key = f"ratelimit:{request.url.path}:{identifier}"
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, window_seconds)
        if current > count:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Rate limit exceeded. Retry after {window_seconds} seconds.",
                headers={"Retry-After": str(window_seconds)},
            )
    return checker
```

### 9.6 Background Tasks (Celery)

Celery is configured with the following queue topology, allowing task prioritization and worker specialization:

| Queue | Purpose | Worker Concurrency |
|-------|---------|-------------------|
| `default` | General-purpose async tasks (notifications, profile updates) | 8 workers |
| `ml-realtime` | User-triggered ML inference (disease ID, voice ASR) | 4 workers (GPU) |
| `ml-batch` | Scheduled ML jobs (NDVI refresh, model retraining) | 2 workers (GPU) |
| `external-api` | Syncs with government / third-party APIs | 16 workers |
| `notifications` | SMS, push, email, voice dispatch | 16 workers |

```python
# apps/api/krishisetu/workers/celery_app.py (illustrative)
from celery import Celery
from krishisetu.core.config import settings

celery_app = Celery(
    "krishisetu",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
)

celery_app.conf.update(
    task_routes={
        "krishisetu.workers.tasks.disease.*": {"queue": "ml-realtime"},
        "krishisetu.workers.tasks.ndvi.*": {"queue": "ml-batch"},
        "krishisetu.workers.tasks.weather.*": {"queue": "external-api"},
        "krishisetu.workers.tasks.notifications.*": {"queue": "notifications"},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=240,
    task_default_retry_delay=60,
    task_default_max_retries=3,
)
```

### 9.7 File Storage

All file uploads (crop photos, satellite imagery tiles, voice recordings, supplier product images, government scheme PDFs) are stored in **S3-compatible object storage** (MinIO for local development, AWS S3 in production). The API never serves files directly from disk; instead, it generates **pre-signed URLs** with short TTLs (15 minutes) that the client uses to download or upload files directly from S3, bypassing the API entirely.

```python
# apps/api/krishisetu/core/storage.py (illustrative)
import boto3
from botocore.config import Config
from krishisetu.core.config import settings


class StorageClient:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY.get_secret_value(),
            aws_secret_access_key=settings.S3_SECRET_KEY.get_secret_value(),
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4"),
        )

    def generate_upload_url(self, key: str, content_type: str, expires_in: int = 900) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    def generate_download_url(self, key: str, expires_in: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )


storage = StorageClient()
```

### 9.8 Structured Logging

All logs are emitted as **structured JSON** via `structlog`, with the following fields on every log entry:

- `timestamp` — ISO 8601 UTC
- `level` — DEBUG/INFO/WARNING/ERROR/CRITICAL
- `request_id` — UUID v4, propagated from the `X-Request-ID` header
- `user_id` — ID of authenticated user (or `anonymous`)
- `route` — FastAPI route path
- `method` — HTTP method
- `status_code` — HTTP status code
- `duration_ms` — Request duration in milliseconds
- `message` — Human-readable message
- `extra` — Arbitrary key-value context

Logs are shipped to Loki via Promtail, where they can be queried in Grafana with LogQL.

---

## 10. Frontend Architecture (Next.js 14)

The frontend is built on **Next.js 14 with the App Router**, using React Server Components (RSC) for server-rendered content, Client Components for interactivity, and a comprehensive design system built on shadcn/ui + Tailwind CSS. The architecture prioritizes: (1) fast first paint on low-bandwidth networks, (2) a component-based, accessible UI matching the reference designs, (3) type safety end-to-end with the backend, and (4) native multilingual support for ten languages.

### 10.1 Rendering Strategy

Next.js 14 supports multiple rendering strategies, and KrishiSetu uses each where it is most appropriate:

- **Static Site Generation (SSG).** Public, non-personalized pages (landing page, scheme catalog, about, FAQs) are statically generated at build time and served from the CDN edge. These pages have the fastest possible load time and require no server compute.
- **Server-Side Rendering (SSR) with React Server Components.** Authenticated dashboard pages are server-rendered on each request, fetching data from the FastAPI backend server-to-server (avoiding the client round-trip). This reduces the JavaScript bundle size and improves time-to-interactive on low-end devices.
- **Client Components.** Interactive elements (forms, map interactions, charts, voice recorders) use the `"use client"` directive. The goal is to keep client components as small as possible, pushing most rendering to the server.
- **Incremental Static Regeneration (ISR).** Pages that change infrequently but cannot be fully static (e.g., scheme detail pages) are regenerated every few hours in the background.

### 10.2 Data Fetching Pattern

The frontend uses a **Backend-for-Frontend (BFF)** pattern. Next.js Route Handlers (`app/api/*`) act as a thin proxy between the browser and the FastAPI backend, allowing:

- **Cookie-based auth on the browser side** (the BFF stores the JWT in an HTTP-only cookie and translates it to a Bearer token when calling FastAPI). This mitigates XSS-based token theft.
- **Request batching and response shaping.** The BFF can combine multiple FastAPI calls into a single browser request, reducing round-trips on slow networks.
- **Server-to-server authentication.** The BFF can hold service-to-service credentials (e.g., for calling government APIs directly from the frontend's edge functions, if appropriate).

The data fetching primitives are:

```typescript
// apps/web/src/lib/api/client.ts (illustrative)
import type { components } from "@krishisetu/ts-types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

export class ApiClient {
  constructor(private readonly baseUrl: string = API_BASE) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({ message: res.statusText }));
      throw new ApiError(res.status, error.message ?? "Unknown error", error);
    }
    return res.json();
  }

  // Fully typed — types come from OpenAPI-generated package
  getPlots() {
    return this.request<components["schemas"]["PlotListResponse"]>("/plots");
  }

  submitDiseaseReport(payload: components["schemas"]["DiseaseReportCreate"]) {
    return this.request<components["schemas"]["DiseaseReport"]>("/disease/reports", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

export const apiClient = new ApiClient();
```

### 10.3 Design System

The design system is built on **shadcn/ui** (which provides Radix UI primitives with Tailwind styling) and follows these design principles derived from the reference UI:

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | `#4CAF50` (green) | Primary actions, active states, NDVI healthy |
| `--color-primary-dark` | `#1E293B` (dark slate) | Headers, footers, dark sections |
| `--color-background` | `#F8FAFC` (off-white) | Page background |
| `--color-card` | `#FFFFFF` (white) | Cards, panels |
| `--color-foreground` | `#111827` (near-black) | Primary text |
| `--color-muted` | `#6C757D` (medium gray) | Secondary text |
| `--color-accent` | `#FF9800` (orange) | NDVI low, warnings |
| `--color-warning` | `#FFEB3B` (yellow) | NDVI medium |
| `--color-danger` | `#DC2626` (red) | Errors, destructive actions |
| `--radius-sm` | `4px` | Small elements |
| `--radius-md` | `8px` | Cards, buttons |
| `--radius-lg` | `16px` | Large panels |
| `--font-sans` | `Inter, Noto Sans, system-ui` | Body text |
| `--font-heading` | `Inter Display, Noto Sans` | Headings |

**No emojis are used in the production UI.** All icons come from `lucide-react` (line icons matching the minimalist aesthetic of the reference UI). Decorative graphics are restricted to actual photographic imagery (farm scenes, crop photos) and data visualizations (NDVI maps, charts).

### 10.4 Component Organization

Components are organized in three tiers:

1. **Primitives (`components/ui/`).** shadcn/ui components — Button, Card, Dialog, DropdownMenu, Input, Select, Tabs, Toast, etc. These are the atomic building blocks, fully accessible (WAI-ARIA), keyboard-navigable, and themeable.
2. **Composites (`components/charts/`, `components/maps/`, `components/forms/`).** Higher-level components built from primitives — e.g., `NDVIMap` (Leaflet + color scale legend), `WeatherParameterCard` (icon + value + trend arrow), `DiseaseUploadForm` (react-hook-form + zod validation + file upload).
3. **Features (`components/features/<domain>/`).** Domain-specific composite components — e.g., `DiseaseReportCard`, `PlotBoundaryEditor`, `InsurancePolicySummary`, `MarketplaceProductCard`. These are the building blocks of pages.

### 10.5 Internationalization (i18n)

i18n is implemented via `next-intl` with locale-prefixed routing:

- URLs are locale-prefixed: `/en/dashboard`, `/hi/dashboard`, `/mr/dashboard`, etc.
- The default locale is `en` (English), but the platform auto-detects the user's preferred locale from the `Accept-Language` header on first visit.
- Locale preference is persisted in a cookie (`NEXT_LOCALE`) after the user explicitly selects a language.
- All UI strings live in `src/messages/<locale>.json` files, versioned alongside the code.
- The `useTranslations` hook from `next-intl` is used in components to access localized strings.

The ten supported locales are:

| Code | Language | Script | Native Name |
|------|----------|--------|-------------|
| `en` | English | Latin | English |
| `hi` | Hindi | Devanagari | हिन्दी |
| `mr` | Marathi | Devanagari | मराठी |
| `ta` | Tamil | Tamil | தமிழ் |
| `te` | Telugu | Telugu | తెలుగు |
| `bn` | Bengali | Bengali | বাংলা |
| `kn` | Kannada | Kannada | ಕನ್ನಡ |
| `gu` | Gujarati | Gujarati | ગુજરાતી |
| `pa` | Punjabi | Gurmukhi | ਪੰਜਾਬੀ |
| `ml` | Malayalam | Malayalam | മലയാളം |

### 10.6 State Management

The frontend uses a **layered state management strategy**:

- **Server state** (data fetched from the API) is managed by **TanStack Query** (React Query). It handles caching, background refetching, optimistic updates, and pagination. Cache keys are derived from the API path and parameters.
- **Client UI state** (sidebar open/closed, theme, locale, modal open) is managed by **Zustand**, a minimal store that avoids the boilerplate of Redux.
- **Form state** is managed by **react-hook-form** with **zod** schemas for validation. The same zod schemas are shared between the frontend and (where applicable) the backend's Pydantic models, ensuring validation parity.
- **URL state** (filters, page numbers, sort order) is managed via Next.js's `useSearchParams` hook, ensuring that any shareable view is also bookmarkable.

### 10.7 Performance Budgets

The frontend enforces strict performance budgets to ensure acceptable performance on low-end devices:

- **LCP (Largest Contentful Paint)** < 2.5s on 3G network
- **TBT (Total Blocking Time)** < 200ms
- **CLS (Cumulative Layout Shift)** < 0.1
- **Initial JS bundle** < 200KB gzipped
- **Initial CSS bundle** < 50KB gzipped
- **No single image > 200KB** without explicit `loading="lazy"`

These budgets are enforced in CI via Lighthouse CI, which fails the build if any metric regresses beyond a configured threshold.

### 10.8 Progressive Web App (PWA)

The web app is configured as a PWA with:

- **Service Worker** for offline caching of static assets and previously-fetched API responses.
- **Web App Manifest** for installability on Android home screens.
- **Background Sync** for queuing actions (e.g., disease photo uploads) when offline and replaying them when connectivity returns.
- **Push Notifications** via Firebase Cloud Messaging for weather alerts, scheme notifications, and order updates.

---

## 11. Data Model & PostgreSQL Schema

The data model is the platform's foundation. It is designed to support: (1) a verified identity graph anchored on Aadhaar, (2) farmer-owned plots with geographic boundaries, (3) time-series data for NDVI and weather observations, (4) transactional records for insurance and marketplace, and (5) full audit history of every state-changing action.

### 11.1 Schema Overview

The database is organized into six logical schemas (PostgreSQL `schema` objects, not just logical groupings):

| Schema | Purpose | Example Tables |
|--------|---------|----------------|
| `identity` | Users, roles, sessions, OTPs | `users`, `roles`, `user_roles`, `sessions`, `otps`, `aadhaar_verifications` |
| `farmer` | Farmer profiles, plots, land records | `farmer_profiles`, `plots`, `plot_boundaries`, `crops`, `crop_calendars` |
| `intelligence` | ML predictions, NDVI, weather | `disease_reports`, `disease_predictions`, `ndvi_observations`, `weather_observations`, `soil_tests` |
| `commerce` | Marketplace, orders, suppliers | `suppliers`, `products`, `orders`, `order_items`, `shipments`, `payments` |
| `insurance` | PMFBY policies, claims, evidence | `insurance_policies`, `insurance_claims`, `claim_evidence`, `insurers` |
| `schemes` | Govt schemes, applications, eligibility | `schemes`, `scheme_eligibility_rules`, `scheme_applications` |
| `audit` | Append-only audit log | `audit_log`, `auth_events` |
| `notifications` | Notification templates, dispatch log | `notification_templates`, `notification_log` |

### 11.2 Entity-Relationship Diagram (Core)

The following ER diagram shows the core entities and their relationships. It is intentionally simplified for readability — the full schema has additional lookup tables, audit columns, and indexes.

```mermaid
erDiagram
    users ||--o| farmer_profiles : "1:1 if role=Farmer"
    users ||--o| supplier_profiles : "1:1 if role=Supplier"
    users ||--o| officer_profiles : "1:1 if role=AgriOfficer"
    users ||--o| insurer_profiles : "1:1 if role=Insurer"
    users ||--o{ sessions : "has many"
    users ||--o{ audit_log : "performs"

    farmer_profiles ||--o{ plots : "owns"
    plots ||--o{ plot_boundaries : "has"
    plots ||--o{ crop_cycles : "has"
    crop_cycles }o--|| crops : "grows"
    plots ||--o{ ndvi_observations : "monitored by"
    plots ||--o{ weather_observations : "experiences"
    plots ||--o{ soil_tests : "tested by"
    plots ||--o{ disease_reports : "affected by"
    plots ||--o{ insurance_policies : "insured by"

    disease_reports ||--|| disease_predictions : "analyzed by"
    disease_predictions }o--|| diseases : "classifies as"
    disease_reports ||--o{ claim_evidence : "used as"

    insurance_policies }o--|| insurance_products : "instance of"
    insurance_policies ||--o{ insurance_claims : "may have"
    insurance_claims ||--o{ claim_evidence : "supported by"

    suppliers ||--o{ products : "sells"
    products }o--|| product_categories : "categorized as"
    farmer_profiles ||--o{ orders : "places"
    orders ||--o{ order_items : "contains"
    order_items }o--|| products : "references"
    orders ||--o{ shipments : "fulfilled by"
    orders ||--|| payments : "paid by"

    schemes ||--o{ scheme_applications : "applied for"
    farmer_profiles ||--o{ scheme_applications : "submits"

    users {
        uuid id PK
        string phone UK
        string aadhaar_hash UK
        string email
        string full_name
        enum role
        boolean is_active
        boolean aadhaar_verified
        timestamp created_at
        timestamp updated_at
    }

    farmer_profiles {
        uuid id PK
        uuid user_id FK
        string father_name
        string village
        string district
        string state
        string pincode
        decimal total_land_holding_ha
        string preferred_language
        string preferred_notification_channel
    }

    plots {
        uuid id PK
        uuid farmer_id FK
        string survey_number
        string village
        string district
        string state
        decimal area_ha
        geometry boundary
        string soil_type
        string irrigation_source
    }

    disease_reports {
        uuid id PK
        uuid plot_id FK
        uuid farmer_id FK
        string image_url
        timestamp captured_at
        timestamp submitted_at
        enum status
    }

    disease_predictions {
        uuid id PK
        uuid report_id FK
        string disease_label
        decimal confidence
        string model_version
        jsonb all_predictions
        timestamp inferred_at
    }

    insurance_policies {
        uuid id PK
        uuid plot_id FK
        uuid farmer_id FK
        string insurer_id FK
        string policy_number UK
        string scheme_code
        decimal sum_insured
        decimal premium_paid
        date season_start
        date season_end
        enum status
    }

    insurance_claims {
        uuid id PK
        uuid policy_id FK
        uuid farmer_id FK
        string claim_number UK
        enum claim_type
        decimal claimed_amount
        text description
        enum status
        timestamp filed_at
        timestamp resolved_at
    }

    orders {
        uuid id PK
        uuid farmer_id FK
        string order_number UK
        decimal total_amount
        enum status
        string shipping_address
        timestamp placed_at
    }

    scheme_applications {
        uuid id PK
        uuid scheme_id FK
        uuid farmer_id FK
        jsonb submitted_data
        enum status
        uuid reviewed_by FK
        timestamp submitted_at
        timestamp reviewed_at
    }
```

### 11.3 Key Tables — Detailed Definitions

#### `users` (Identity Schema)

The central identity table. Stores only authentication-related fields; profile data lives in role-specific profile tables.

```sql
CREATE TABLE identity.users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone           VARCHAR(15) UNIQUE NOT NULL,
    phone_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    email           VARCHAR(255) UNIQUE,
    email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    aadhaar_hash    VARCHAR(64) UNIQUE,  -- SHA-256 hash, never store raw Aadhaar
    aadhaar_verified BOOLEAN NOT NULL DEFAULT FALSE,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL CHECK (role IN ('farmer', 'agri_officer', 'supplier', 'insurer', 'admin')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    password_hash   VARCHAR(255),  -- NULL if OTP-only auth
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_phone ON identity.users (phone);
CREATE INDEX idx_users_aadhaar_hash ON identity.users (aadhaar_hash) WHERE aadhaar_hash IS NOT NULL;
CREATE INDEX idx_users_role ON identity.users (role) WHERE is_active = TRUE;
```

#### `plots` (Farmer Schema)

Stores farmer plots with PostGIS geometry for the boundary.

```sql
CREATE TABLE farmer.plots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id         UUID NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    survey_number     VARCHAR(100) NOT NULL,  -- State land record identifier
    village           VARCHAR(255) NOT NULL,
    district          VARCHAR(100) NOT NULL,
    state             VARCHAR(100) NOT NULL,
    pincode           VARCHAR(10),
    area_ha           DECIMAL(10,4) NOT NULL CHECK (area_ha > 0),
    boundary          GEOGRAPHY(POLYGON, 4326) NOT NULL,  -- PostGIS geography
    centroid          GEOGRAPHY(POINT, 4326) GENERATED ALWAYS AS (ST_Centroid(boundary)) STORED,
    soil_type         VARCHAR(50),
    irrigation_source VARCHAR(50) CHECK (irrigation_source IN ('canal', 'borewell', 'river', 'rainfed', 'drip', 'sprinkler')),
    ownership_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by       UUID REFERENCES identity.users(id),
    verified_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (farmer_id, survey_number, village, district, state)
);

CREATE INDEX idx_plots_farmer ON farmer.plots (farmer_id);
CREATE INDEX idx_plots_boundary_gist ON farmer.plots USING GIST (boundary);
CREATE INDEX idx_plots_centroid_gist ON farmer.plots USING GIST (centroid);
CREATE INDEX idx_plots_district ON farmer.plots (district, state);
```

#### `ndvi_observations` (Intelligence Schema)

Time-series NDVI data per plot. Partitioned by month for query performance.

```sql
CREATE TABLE intelligence.ndvi_observations (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    plot_id         UUID NOT NULL REFERENCES farmer.plots(id) ON DELETE CASCADE,
    observed_at     TIMESTAMPTZ NOT NULL,
    ndvi_mean       DECIMAL(5,4) NOT NULL CHECK (ndvi_mean BETWEEN -1 AND 1),
    ndvi_min        DECIMAL(5,4) NOT NULL,
    ndvi_max        DECIMAL(5,4) NOT NULL,
    ndvi_stddev     DECIMAL(5,4) NOT NULL,
    cloud_cover_pct DECIMAL(5,2) NOT NULL,
    raster_url      VARCHAR(512),  -- S3 URL to full NDVI raster
    source          VARCHAR(20) NOT NULL CHECK (source IN ('sentinel2', 'landsat8')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);

-- Create monthly partitions (managed by pg_partman in production)
CREATE TABLE intelligence.ndvi_observations_2026_01 PARTITION OF intelligence.ndvi_observations
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
-- ... etc.

CREATE INDEX idx_ndvi_plot_time ON intelligence.ndvi_observations (plot_id, observed_at DESC);
```

#### `disease_predictions` (Intelligence Schema)

ML model predictions with full provenance for auditability.

```sql
CREATE TABLE intelligence.disease_predictions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id       UUID NOT NULL REFERENCES intelligence.disease_reports(id) ON DELETE CASCADE,
    disease_label   VARCHAR(100) NOT NULL,
    confidence      DECIMAL(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    model_name      VARCHAR(50) NOT NULL,
    model_version   VARCHAR(20) NOT NULL,
    inference_time_ms INTEGER NOT NULL,
    all_predictions JSONB NOT NULL,  -- Full prediction distribution
    heat_map_url    VARCHAR(512),  -- S3 URL to localization heatmap
    inferred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_disease_predictions_label ON intelligence.disease_predictions (disease_label);
CREATE INDEX idx_disease_predictions_model ON intelligence.disease_predictions (model_name, model_version);
```

#### `audit_log` (Audit Schema)

Append-only audit trail of every state-changing action.

```sql
CREATE TABLE audit.audit_log (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_user_id   UUID REFERENCES identity.users(id),
    actor_role      VARCHAR(20),
    action          VARCHAR(50) NOT NULL,  -- e.g., 'plot.create', 'disease.report_submit'
    resource_type   VARCHAR(50) NOT NULL,
    resource_id     UUID,
    request_id      VARCHAR(64),
    ip_address      INET,
    user_agent      TEXT,
    before_state    JSONB,
    after_state     JSONB,
    metadata        JSONB
) PARTITION BY RANGE (timestamp);

CREATE INDEX idx_audit_actor ON audit.audit_log (actor_user_id, timestamp DESC);
CREATE INDEX idx_audit_resource ON audit.audit_log (resource_type, resource_id);
CREATE INDEX idx_audit_action ON audit.audit_log (action, timestamp DESC);
```

### 11.4 Migration Strategy

Database migrations are managed by **Alembic** with the following discipline:

- Every schema change is a new Alembic revision file, generated via `alembic revision --autogenerate` and reviewed manually before commit.
- Migrations are **forward-only** — no destructive `downgrade()` in production. Rollbacks are achieved by writing a new forward migration that reverses the change.
- Migrations are tested against a copy of the production database in CI before deployment.
- Long-running migrations (e.g., adding a column with default to a large table) are broken into multiple steps: (1) add nullable column, (2) backfill in batches, (3) set default and NOT NULL.
- Critical migrations are wrapped in transactions with explicit locks to prevent concurrent-write issues.

### 11.5 Partitioning & Indexing Strategy

| Table | Partition Strategy | Index Strategy |
|-------|-------------------|-----------------|
| `ndvi_observations` | RANGE on `observed_at` (monthly) | B-tree on (plot_id, observed_at DESC) |
| `weather_observations` | RANGE on `observed_at` (monthly) | B-tree on (plot_id, observed_at DESC) |
| `audit_log` | RANGE on `timestamp` (monthly) | B-tree on (actor_user_id, timestamp DESC) |
| `disease_reports` | None (sub-million rows initially) | B-tree on (farmer_id, submitted_at DESC) |
| `plots` | None | GiST on boundary and centroid for spatial queries |
| `orders` | None initially, RANGE on `placed_at` if grows | B-tree on (farmer_id, placed_at DESC) |
| `notification_log` | RANGE on `created_at` (monthly) | B-tree on (user_id, created_at DESC) |

### 11.6 Backup & Recovery

- **Daily full backups** with 30-day retention via `pg_dump` (logical) and EBS snapshots (physical).
- **Point-in-time recovery (PITR)** via WAL archiving with 7-day retention, enabling recovery to any second within the last week.
- **Cross-region backup replication** for disaster recovery.
- **Quarterly restore drills** to validate backup integrity and recovery procedures.

---

## 12. API Design & Endpoint Catalog

The API follows **REST conventions** with strict adherence to resource-oriented design, JSON:API-style relationships (simplified), and a consistent error format. All endpoints are versioned under `/api/v1`.

### 12.1 Conventions

- **URL Structure.** Plural, kebab-case resource names: `/plots`, `/disease-reports`, `/insurance-policies`.
- **HTTP Methods.** `GET` (read), `POST` (create), `PUT` (full update), `PATCH` (partial update), `DELETE` (remove).
- **Status Codes.** Standard HTTP semantics:
  - `200 OK` — successful GET, PUT, PATCH
  - `201 Created` — successful POST (with `Location` header)
  - `202 Accepted` — async task accepted (with `task_id`)
  - `204 No Content` — successful DELETE
  - `400 Bad Request` — validation error
  - `401 Unauthorized` — missing or invalid token
  - `403 Forbidden` — authenticated but insufficient permissions
  - `404 Not Found` — resource does not exist
  - `409 Conflict` — duplicate or state conflict
  - `422 Unprocessable Entity` — semantic validation failure
  - `429 Too Many Requests` — rate limited
  - `500 Internal Server Error` — unhandled server error
- **Pagination.** Cursor-based pagination for list endpoints, with `cursor`, `limit` (default 20, max 100), and `has_more` fields in the response.
- **Filtering.** Query parameters: `?status=active&district=pune&created_after=2026-01-01`.
- **Sorting.** `?sort=-created_at` (descending), `?sort=name,created_at` (multi-field).
- **Field Selection.** `?fields=id,name,created_at` to reduce payload size.
- **Embedding.** `?expand=farmer,plot` to include related resources in the response.
- **Idempotency.** All `POST` endpoints accept an `Idempotency-Key` header; the server caches the response for 24 hours and returns the same result if the same key is reused.
- **Time Format.** All timestamps are ISO 8601 UTC strings (`2026-07-19T08:30:00Z`).
- **Identifiers.** All resource IDs are UUID v4 strings.

### 12.2 Error Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "phone",
        "code": "INVALID_FORMAT",
        "message": "Phone must be a 10-digit Indian mobile number"
      }
    ],
    "request_id": "req_abc123def456",
    "documentation_url": "https://docs.krishisetu.in/api/v1/errors#VALIDATION_ERROR"
  }
}
```

### 12.3 Endpoint Catalog

The following table catalogues the platform's API endpoints. It is not exhaustive (the full OpenAPI spec defines 200+ endpoints), but it covers the primary surface area.

#### 12.3.1 Identity & Auth

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| POST | `/auth/send-otp` | Send OTP to phone | Public | — |
| POST | `/auth/verify-otp` | Verify OTP, return tokens | Public | — |
| POST | `/auth/refresh` | Refresh access token | Refresh token | — |
| POST | `/auth/logout` | Revoke session | JWT | All |
| POST | `/auth/aadhaar/send-otp` | Trigger Aadhaar OTP | JWT | Farmer |
| POST | `/auth/aadhaar/verify-otp` | Verify Aadhaar OTP, mark verified | JWT | Farmer |
| GET | `/me` | Get current user profile | JWT | All |
| PATCH | `/me` | Update current user profile | JWT | All |
| POST | `/me/change-phone` | Initiate phone number change | JWT | All |
| GET | `/admin/users` | List all users (paginated) | JWT | Admin |
| PATCH | `/admin/users/{id}` | Update user (active, role) | JWT | Admin |

#### 12.3.2 Farmer Profile & Plots

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| GET | `/plots` | List current user's plots | JWT | Farmer |
| POST | `/plots` | Register a new plot | JWT | Farmer |
| GET | `/plots/{id}` | Get plot details | JWT | Farmer, AgriOfficer |
| PATCH | `/plots/{id}` | Update plot | JWT | Farmer |
| DELETE | `/plots/{id}` | Remove plot (soft delete) | JWT | Farmer |
| POST | `/plots/{id}/boundary` | Upload plot boundary GeoJSON | JWT | Farmer |
| GET | `/plots/{id}/crops` | List crop cycles on plot | JWT | Farmer, AgriOfficer |
| POST | `/plots/{id}/crops` | Add crop cycle | JWT | Farmer |
| GET | `/officer/plots` | List plots in officer's district | JWT | AgriOfficer |
| PATCH | `/officer/plots/{id}/verify` | Verify plot ownership | JWT | AgriOfficer |

#### 12.3.3 Crop Disease Identification

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| POST | `/disease-reports` | Submit disease report (image upload URL + metadata) | JWT | Farmer |
| GET | `/disease-reports` | List own reports (paginated) | JWT | Farmer |
| GET | `/disease-reports/{id}` | Get report + prediction | JWT | Farmer, AgriOfficer |
| GET | `/diseases` | List disease catalog | Public | — |
| GET | `/diseases/{slug}` | Get disease detail (symptoms, treatment, prevention) | Public | — |
| GET | `/diseases/{slug}/treatment-products` | Get recommended marketplace products | Public | — |
| POST | `/disease-reports/{id}/feedback` | Submit prediction feedback (correct/incorrect) | JWT | Farmer |

#### 12.3.4 Soil Health & Weather

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| GET | `/plots/{id}/soil-tests` | List soil tests for plot | JWT | Farmer, AgriOfficer |
| POST | `/plots/{id}/soil-tests` | Add soil test result | JWT | Farmer, AgriOfficer |
| GET | `/plots/{id}/weather/current` | Current weather at plot | JWT | Farmer |
| GET | `/plots/{id}/weather/forecast` | 7-day forecast at plot | JWT | Farmer |
| GET | `/plots/{id}/weather/history` | Historical weather (paginated) | JWT | Farmer |
| GET | `/weather/district/{district}` | District weather summary | Public | — |

#### 12.3.5 Satellite NDVI

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| GET | `/plots/{id}/ndvi` | Latest NDVI for plot | JWT | Farmer |
| GET | `/plots/{id}/ndvi/history` | NDVI time series | JWT | Farmer |
| GET | `/plots/{id}/ndvi/raster` | Pre-signed URL for NDVI raster | JWT | Farmer |
| POST | `/plots/{id}/ndvi/refresh` | Trigger immediate NDVI refresh | JWT | Farmer |
| GET | `/officer/ndvi/district/{district}` | District NDVI heatmap | JWT | AgriOfficer |
| GET | `/insurer/plots/{id}/ndvi` | NDVI for insured plot | JWT | Insurer |

#### 12.3.6 Insurance & PMFBY

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| GET | `/insurance/products` | List available products (PMFBY + others) | JWT | Farmer |
| GET | `/insurance/products/{id}` | Product detail | JWT | Farmer |
| POST | `/insurance/policies` | Enroll in policy | JWT | Farmer |
| GET | `/insurance/policies` | List own policies | JWT | Farmer |
| GET | `/insurance/policies/{id}` | Policy detail | JWT | Farmer, Insurer |
| POST | `/insurance/policies/{id}/claims` | File a claim | JWT | Farmer |
| GET | `/insurance/claims` | List own claims | JWT | Farmer |
| GET | `/insurance/claims/{id}` | Claim detail | JWT | Farmer, Insurer |
| POST | `/insurance/claims/{id}/evidence` | Upload claim evidence | JWT | Farmer |
| PATCH | `/insurer/claims/{id}/status` | Update claim status | JWT | Insurer |

#### 12.3.7 Marketplace

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| GET | `/products` | Browse marketplace (search, filter) | Public | — |
| GET | `/products/{id}` | Product detail | Public | — |
| GET | `/suppliers/{id}/products` | List supplier's products | Public | — |
| POST | `/cart` | Add to cart | JWT | Farmer |
| GET | `/cart` | Get cart | JWT | Farmer |
| POST | `/orders` | Place order | JWT | Farmer |
| GET | `/orders` | List own orders | JWT | Farmer |
| GET | `/orders/{id}` | Order detail | JWT | Farmer, Supplier |
| POST | `/orders/{id}/cancel` | Cancel order (if eligible) | JWT | Farmer |
| POST | `/supplier/products` | Create product | JWT | Supplier |
| PATCH | `/supplier/products/{id}` | Update product | JWT | Supplier |
| GET | `/supplier/orders` | List supplier's orders | JWT | Supplier |
| POST | `/supplier/orders/{id}/ship` | Mark as shipped | JWT | Supplier |
| POST | `/supplier/orders/{id}/deliver` | Mark as delivered | JWT | Supplier |

#### 12.3.8 Govt Schemes

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| GET | `/schemes` | List schemes (with filters) | Public | — |
| GET | `/schemes/{slug}` | Scheme detail | Public | — |
| GET | `/schemes/{slug}/eligibility` | Check current user's eligibility | JWT | Farmer |
| POST | `/schemes/{slug}/applications` | Submit application | JWT | Farmer |
| GET | `/schemes/applications` | List own applications | JWT | Farmer |
| GET | `/schemes/applications/{id}` | Application detail | JWT | Farmer, AgriOfficer |
| PATCH | `/officer/schemes/applications/{id}/review` | Approve / reject application | JWT | AgriOfficer |

#### 12.3.9 Notifications & Voice

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|------|-------|
| GET | `/notifications` | List notifications | JWT | All |
| PATCH | `/notifications/{id}/read` | Mark as read | JWT | All |
| POST | `/voice/asr` | Upload audio, get transcription | JWT | All |
| POST | `/voice/tts` | Synthesize speech from text | JWT | All |
| POST | `/voice/query` | Natural language query (returns intent + response) | JWT | All |

### 12.4 API Versioning Strategy

- **URL-based versioning.** All endpoints under `/api/v1`. Breaking changes go to `/api/v2` with the old version maintained for at least 12 months.
- **Deprecation policy.** Deprecated endpoints return a `Sunset` header with the deprecation date. Email notifications are sent to API consumers 90 days in advance.
- **Changelog.** Every API change is documented in `docs/api/CHANGELOG.md` and surfaced in the developer portal.

### 12.5 Webhooks

For async events that external systems need to subscribe to (e.g., insurer needs to know when a claim is filed), the platform supports outbound webhooks:

- Subscriptions are created via `POST /webhooks` with a target URL and event types.
- Events are delivered via HTTP POST with HMAC-SHA256 signature in the `X-KrishiSetu-Signature` header.
- Failed deliveries are retried with exponential backoff (1m, 5m, 30m, 2h, 6h, 24h) before being marked as failed.
- Webhook deliveries are stored in a `webhook_deliveries` table for audit and manual replay.

---

## 13. ML Pipeline Architecture

The ML subsystem is engineered as a first-class platform citizen, not a bolt-on feature. It is responsible for: (1) crop disease classification from leaf photos, (2) soil type classification from imagery and metadata, (3) vernacular speech recognition (ASR) for voice queries, (4) vernacular text-to-speech (TTS) for voice responses, and (5) natural language understanding of farmer queries in ten Indian languages. Each use case has its own model selection, fine-tuning strategy, serving infrastructure, and observability — chosen based on dataset compatibility, inference latency, and production maturity, not hype.

### 13.1 Model Selection Per Use Case

The following table documents the deliberate model selection for each ML use case. Every choice is justified by the specific characteristics of the task and the available datasets.

| Use Case | Selected Model | Alternative Considered | Why Selected | Dataset | Target Accuracy |
|----------|----------------|----------------------|--------------|---------|-----------------|
| Crop Disease Classification | **YOLOv8x-cls** fine-tuned | EfficientNet-B7, ResNet-152, ViT-Base | YOLOv8 family is SOTA for plant pathology on PlantVillage/PlantDoc, real-time inference on CPU/GPU, mature Ultralytics ecosystem, native ONNX export | PlantVillage (54K imgs, 38 classes) + PlantDoc (2.6K imgs, 27 classes) + custom Indian crop disease dataset (~10K imgs) | Top-1 ≥ 92%, Top-5 ≥ 98% |
| Soil Type Classification | **EfficientNet-B0** fine-tuned | MobileNetV3, ResNet-18 | Lightweight, well-suited for soil macro-classification (6-8 major Indian soil types), low inference cost | Soildataset (Kaggle, ~1.2K imgs) + ISRIC global soil grid imagery | Top-1 ≥ 85% |
| Multilingual ASR | **Whisper-large-v3** fine-tuned with Indic corpus | Google STT API, Azure Speech, Wav2Vec2-Indic | Whisper is open-source, supports 10 Indian languages, fine-tunable on Indic speech, can be self-hosted for data residency | IndicSUPERB + custom farmer voice corpus | WER ≤ 12% on rural Indian accents |
| Multilingual TTS | **Azure Cognitive Services Speech** (managed) + fallback to **Coqui TTS** | Google TTS, Amazon Polly | Azure supports all 10 target languages with natural voices; Coqui fallback for offline/self-hosted scenarios | n/a (managed service) | MOS ≥ 4.0 |
| Vernacular NLU | **MuRIL** (Multilingual Representations for Indian Languages) fine-tuned | IndicBERT, mBERT, XLM-RoBERTa | MuRIL is Google's SOTA model for Indian languages, outperforms mBERT on Indic benchmarks, supports all 10 target languages | IndicGLUE + custom intent classification dataset | Intent F1 ≥ 0.85 |
| NDVI Computation | **Not ML** — direct computation from Sentinel-2 bands B04 (red) and B08 (NIR) | n/a | NDVI = (NIR − Red) / (NIR + Red) is a deterministic formula; no ML required | Sentinel-2 L2A imagery | n/a |
| Crop Yield Prediction (Phase 2) | **XGBoost** on tabular features | Random Forest, simple linear regression | Strong tabular performance, feature importance interpretability, fast inference | Historical yield data + weather + NDVI | RMSE ≤ 15% of mean |

### 13.2 Model Lifecycle

```mermaid
graph LR
    A[Raw Data Collection] --> B[Data Labeling<br/>CVAT / Label Studio]
    B --> C[Dataset Versioning<br/>DVC]
    C --> D[Training Script<br/>PyTorch + Ultralytics / HF]
    D --> E[Evaluation<br/>held-out test set]
    E --> F{Metrics pass<br/>threshold?}
    F -->|No| G[Tune hyperparams<br/>or augment data]
    G --> D
    F -->|Yes| H[Model Packaging<br/>ONNX export]
    H --> I[MLflow Registry<br/>versioned]
    I --> J[Staging deployment<br/>canary 5%]
    J --> K{Production<br/>metrics healthy?}
    K -->|No| L[Rollback]
    K -->|Yes| M[Production deployment<br/>100%]
    M --> N[Drift Monitoring<br/>Prometheus + Grafana]
    N -->|Drift detected| A

    style A fill:#E6F4EA,stroke:#4CAF50
    style D fill:#FEF3C7,stroke:#D97706
    style I fill:#DBEAFE,stroke:#2563EB
    style M fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:3px
    style N fill:#FCE7F3,stroke:#DB2777
```

### 13.3 Training Infrastructure

Training is performed on a dedicated GPU machine (NVIDIA A10G or A100), separate from the inference infrastructure. The training workflow is:

1. **Data preparation.** Raw images are stored in S3. A DVC pipeline (`ml/training/dvc.yaml`) defines data versioning, preprocessing, augmentation, and train/val/test splits. Each dataset version is tagged in DVC and pushed to a dedicated S3 bucket.
2. **Augmentation.** For crop disease classification, augmentations include: random rotation (±30°), horizontal/vertical flip, color jitter (brightness, contrast, saturation ±20%), random crop (80-100% of original), Gaussian noise, and simulated motion blur. This is critical because farmer-submitted photos will vary widely in lighting, angle, and quality.
3. **Training.** PyTorch + Ultralytics YOLOv8 training scripts in `ml/training/disease_classifier.py`. Hyperparameters (learning rate, batch size, epochs, optimizer) are managed via Hydra config files. Training runs are tracked in MLflow with full reproducibility (commit hash, dataset version, hyperparameters, metrics).
4. **Evaluation.** Held-out test set is evaluated after every training run. Metrics: Top-1 accuracy, Top-5 accuracy, per-class precision/recall/F1, confusion matrix. Per-class metrics are critical because some diseases have very few training samples.
5. **Model packaging.** The trained PyTorch model is exported to ONNX format for hardware-agnostic inference. The ONNX file is uploaded to S3 and registered in MLflow with a semantic version (e.g., `disease-classifier-v1.2.0`).
6. **Staging deployment.** The new model version is deployed to a staging endpoint. A canary 5% of production traffic is routed to it for 24 hours, with metrics (latency, error rate, prediction distribution) compared against the current production model.
7. **Production deployment.** If staging metrics are healthy, the new model is promoted to production. The old model is retained for 30 days for rollback.
8. **Drift monitoring.** Production model predictions are continuously monitored for distribution drift (Population Stability Index). If drift exceeds threshold (PSI > 0.2), an alert fires to trigger retraining.

### 13.4 Inference Service Architecture

The ML inference service is a separate FastAPI application (`apps/ml-inference/`) that loads ONNX models into memory at startup and serves predictions via HTTP. Key design choices:

- **Single Service, Multiple Models.** All ML models live in one inference service to reduce operational overhead. Models are loaded into memory at startup based on a config file mapping model name → ONNX file path → version.
- **ONNX Runtime.** ONNX Runtime provides optimized inference across CPU, GPU, and edge devices, with hardware acceleration (CUDA, TensorRT) where available.
- **Batched Inference.** For high-throughput use cases (e.g., NDVI tile processing), the service supports batched inference — multiple inputs in a single request, processed in parallel on the GPU.
- **Model Warmup.** At startup, the service runs a dummy inference for each loaded model to warm up the ONNX session, avoiding cold-start latency on the first real request.
- **Health Endpoint.** `/health` returns model status (loaded, version, last inference time) for monitoring.
- **Metrics.** Prometheus metrics for inference latency, throughput, error rate, per-model.

```python
# apps/ml-inference/krishisetu_ml/api/disease.py (illustrative)
from fastapi import APIRouter, HTTPException, UploadFile, File
import numpy as np
from PIL import Image
import io

from krishisetu_ml.models.disease_classifier import DiseaseClassifier
from krishisetu_ml.core.onnx_runtime import get_model

router = APIRouter()
classifier = DiseaseClassifier(get_model("disease-classifier"))


@router.post("/predict/disease")
async def predict_disease(file: UploadFile = File(...)):
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Unsupported image format")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(413, "Image too large (max 10MB)")

    image = Image.open(io.BytesIO(contents)).convert("RGB")
    preprocessed = classifier.preprocess(image)
    prediction = classifier.predict(preprocessed)

    return {
        "top_prediction": {
            "label": prediction.top_label,
            "confidence": float(prediction.top_confidence),
        },
        "all_predictions": prediction.all_predictions,
        "model_version": classifier.model_version,
        "inference_time_ms": prediction.inference_time_ms,
    }
```

### 13.5 Model Governance

Every model deployed to production has:

- **A model card** (`ml/registry/<model-name>/card.md`) documenting: intended use, training data, evaluation metrics, known limitations, ethical considerations, and contact for issues.
- **A versioned release** in MLflow with: commit hash, dataset version, hyperparameters, training metrics, evaluation metrics.
- **An approval workflow** — new model versions require sign-off from the ML lead and the domain lead (e.g., agriculture expert for disease classifier) before promotion to production.
- **A rollback plan** — any model version can be rolled back to the previous version with a single config change, no code deployment required.

---

## 14. Module Deep-Dives

Each module is documented with: (1) Goal, (2) User Stories, (3) Data Sources, (4) Architecture, (5) API Surface, (6) Data Model, (7) ML Pipeline (if applicable), (8) Key Flows (sequence diagrams), (9) Edge Cases & Failure Handling, (10) Metrics & SLOs.

---

### 14.1 Identity, Auth & Aadhaar e-KYC

#### 14.1.1 Goal

Establish a verified identity graph for every platform user, anchored on Aadhaar e-KYC, such that all subsequent capabilities (schemes, insurance, marketplace, plot registration) inherit trust from the identity verification rather than re-verifying at each step.

#### 14.1.2 User Stories

- As a farmer, I want to sign up with my phone number and verify via OTP, so that I can access the platform without needing an email account.
- As a farmer, I want to verify my identity via Aadhaar OTP, so that I can apply for government schemes and insurance that require KYC.
- As a farmer, I want my session to persist across browser restarts, so that I don't have to log in every time.
- As an admin, I want to deactivate users who violate platform policies, so that the platform remains trustworthy.
- As an admin, I want to see all authentication events for forensic analysis, so that I can investigate security incidents.

#### 14.1.3 Data Sources

- **UIDAI Aadhaar e-KYC API.** Used for OTP-based Aadhaar verification. Returns masked Aadhaar number, name, demographic details (DOB, gender, address), and photograph.
- **SMS Gateway (MSG91/Karix).** Used for phone number OTP delivery.
- **Internal user store** in PostgreSQL.

#### 14.1.4 Architecture

```mermaid
sequenceDiagram
    participant F as Farmer (Browser)
    participant W as Next.js Web
    participant A as FastAPI
    participant R as Redis
    participant S as SMS Gateway
    participant U as UIDAI API
    participant DB as PostgreSQL

    Note over F,DB: Phase 1 — Phone OTP Signup
    F->>W: Enter phone number
    W->>A: POST /auth/send-otp {phone}
    A->>A: Validate phone format
    A->>R: Generate 6-digit OTP, store with 5min TTL
    A->>S: Send OTP SMS
    A-->>W: 202 Accepted
    S->>F: SMS arrives
    F->>W: Enter OTP
    W->>A: POST /auth/verify-otp {phone, otp}
    A->>R: Verify OTP
    A->>DB: Create user if not exists
    A->>DB: Create session, store refresh token hash
    A-->>W: 200 OK {access_token, refresh_token, user}
    W->>F: Redirect to dashboard

    Note over F,DB: Phase 2 — Aadhaar e-KYC (optional)
    F->>W: Click "Verify Aadhaar"
    W->>A: POST /auth/aadhaar/send-otp {aadhaar}
    A->>A: Validate Aadhaar format (12 digits, Verhoeff checksum)
    A->>U: Aadhaar OTP generation request (encrypted)
    U-->>A: 200 OK (OTP dispatched to registered phone)
    A-->>W: 202 Accepted
    U->>F: Aadhaar OTP SMS arrives
    F->>W: Enter Aadhaar OTP
    W->>A: POST /auth/aadhaar/verify-otp {aadhaar, otp}
    A->>U: Aadhaar OTP verification (encrypted)
    U-->>A: 200 OK {masked_aadhaar, name, dob, gender, address, photo}
    A->>DB: Update user: aadhaar_hash, aadhaar_verified=true, demographic data
    A->>DB: Store Aadhaar verification record (audit)
    A-->>W: 200 OK {user with verified status}
    W->>F: Show "Verified" badge
```

#### 14.1.5 API Surface

See Section 12.3.1 for the complete endpoint list.

#### 14.1.6 Data Model

The `users` table is the central identity record (see Section 11.3). Additional tables:

- `identity.sessions` — JWT refresh token hashes with device info and expiry.
- `identity.otps` — OTP records with hash, expiry, attempts count (for audit, even though Redis is the primary store).
- `identity.aadhaar_verifications` — Append-only audit of every Aadhaar verification (timestamp, masked Aadhaar, UIDAI transaction ID, response fields).
- `identity.auth_events` — Every login, logout, failed attempt, lockout, password change.

#### 14.1.7 Security Considerations

- **Aadhaar is never stored in plaintext.** Only a SHA-256 hash is stored, with a per-record salt. The full Aadhaar number is never persisted.
- **Aadhaar encryption in transit.** All communication with UIDAI uses TLS 1.3. Request payloads are additionally encrypted with UIDAI's public key per their API spec.
- **OTP rate limiting.** Maximum 5 OTP requests per phone number per hour, 3 OTP verification attempts per OTP, exponential backoff on repeated failures.
- **Account lockout.** After 5 failed login attempts, the account is locked for 15 minutes. After 3 lockouts in 24 hours, the account is locked for 24 hours and requires admin intervention.
- **Refresh token rotation.** Each refresh token use issues a new refresh token and invalidates the old one. Suspected token reuse (use of an invalidated refresh token) immediately revokes the entire session family.
- **JWT in HTTP-only cookie.** The frontend stores the access token in an HTTP-only, Secure, SameSite=Strict cookie, not in localStorage, mitigating XSS-based token theft.

#### 14.1.8 Edge Cases

- **Phone number change.** Farmer changes their phone number. Workflow: verify new phone via OTP, then verify identity via Aadhaar OTP, then update phone.
- **Aadhaar not linked to current phone.** UIDAI OTP goes to Aadhaar-linked phone, which may differ from current phone. UI must explain this clearly.
- **UIDAI API downtime.** Fall back to "Aadhaar verification pending" state — farmer can still use platform features that don't require KYC, but cannot apply for schemes/insurance.
- **Duplicate account detection.** If a farmer signs up with a new phone but the same Aadhaar, the system detects the duplicate via `aadhaar_hash` unique constraint and offers account merge.

#### 14.1.9 SLOs

- OTP delivery latency: P95 < 30 seconds
- OTP verification latency: P95 < 2 seconds
- Aadhaar e-KYC completion latency: P95 < 60 seconds (depends on UIDAI)
- Authentication success rate: > 99% (excluding user errors)

---

### 14.2 Farmer Profile & Land Records

#### 14.2.1 Goal

Enable farmers to register and manage their plots with verified geographic boundaries, crop cycles, and ownership status — establishing a "land graph" that becomes the spatial anchor for NDVI, weather, insurance, and scheme eligibility.

#### 14.2.2 User Stories

- As a farmer, I want to draw my plot boundary on a map, so that the platform knows exactly where my land is for NDVI and weather monitoring.
- As a farmer, I want to enter my survey number, so that the platform can verify ownership against state land records.
- As a farmer, I want to record what crop I am growing on each plot, so that I get crop-specific advisories.
- As an agri officer, I want to see all plots in my district, so that I can verify ownership and review scheme applications.

#### 14.2.3 Data Sources

- **State Bhulekh / Land Records APIs.** Vary by state — Maharashtra Bhumi Abhilekh, Karnataka Bhoomi, etc. Used for ownership verification.
- **OpenStreetMap tiles / Mapbox.** For the map UI.
- **User input** for plot boundary drawing and crop cycle entry.
- **ISRIC Soil Grids** for default soil type at registered plot location.

#### 14.2.4 Architecture

The plot registration flow uses a wizard-style multi-step form:

1. **Locate plot.** Farmer searches for their village, navigates the map to their plot, or enters survey number to auto-center.
2. **Draw boundary.** Farmer draws a polygon on the map (Leaflet + `leaflet-draw`). Boundary is captured as GeoJSON.
3. **Enter details.** Survey number, area (auto-computed from polygon), soil type (auto-suggested from ISRIC, editable), irrigation source.
4. **Submit.** Plot saved with `ownership_verified=false`. A verification task is created in the agri officer's worklist.
5. **Officer review.** Officer cross-references survey number with state land records. If match: marks `ownership_verified=true`. If no match: requests additional documentation from farmer.
6. **Verification complete.** Farmer notified; plot is now eligible for insurance and scheme applications.

#### 14.2.5 Data Model

See Section 11.3 for `plots` table. Additional:

- `farmer.plot_boundaries` — Stores historical boundaries (in case farmer re-draws).
- `farmer.crop_cycles` — Records crop grown, sowing date, expected harvest date, area under cultivation.
- `farmer.crops` — Master list of crops with scientific names, growing seasons, water requirements.

#### 14.2.6 Edge Cases

- **Plot spans multiple survey numbers.** Farmer can register one plot with multiple survey numbers (comma-separated), each verified independently.
- **Leased land.** Farmer can mark a plot as leased, with lessor name and lease duration. Leased plots are eligible for advisories but not for insurance (insurance must be in the name of the legal owner).
- **Shared ownership.** Multiple farmers can be linked to a single plot (joint ownership), with each farmer's share percentage recorded.
- **Boundary redraw.** If farmer redraws boundary, old boundary is archived. NDVI history is preserved with the new boundary (re-computed if needed).

#### 14.2.7 SLOs

- Plot registration: P95 < 2 minutes from start to submit
- Boundary area computation: P95 < 500ms
- Officer verification SLA: 7 business days

---

### 14.3 Crop Disease Identification

#### 14.3.1 Goal

Provide farmers with instantaneous, AI-powered diagnosis of crop diseases from a single photo of the affected plant, with actionable treatment recommendations and direct links to relevant marketplace products.

#### 14.3.2 User Stories

- As a farmer, I want to take a photo of an affected leaf and instantly know what disease it is, so that I can take corrective action immediately.
- As a farmer, I want to see the confidence of the diagnosis, so that I know whether to trust it or seek a second opinion.
- As a farmer, I want to see treatment recommendations (organic + chemical), so that I know what to do next.
- As a farmer, I want to order the recommended treatment directly from the marketplace, so that I don't have to search for it separately.
- As an agri officer, I want to see disease hotspots in my district, so that I can issue advisories.

#### 14.3.3 Data Sources

- **PlantVillage dataset** (54,303 images, 38 classes — 14 crops × ~3 diseases each). Open source, well-curated.
- **PlantDoc dataset** (2,598 images, 27 classes). Real-world field images (vs. PlantVillage's lab-controlled).
- **Custom Indian crop disease dataset** (~10,000 images, target). Collected from agricultural universities (ICAR, state agricultural universities) and farmer submissions verified by agronomy experts. Critical for Indian-specific crops (e.g., turmeric, pigeon pea, groundnut) underrepresented in global datasets.
- **ICAR plant pathology database** for disease metadata (symptoms, treatment, prevention, host range).

#### 14.3.4 Architecture

```mermaid
sequenceDiagram
    participant F as Farmer (Browser)
    participant W as Next.js Web
    participant A as FastAPI API
    participant S3 as Object Storage
    participant Q as Celery Queue
    participant WKR as ML Worker
    participant ML as Inference Service
    participant DB as PostgreSQL
    participant N as Notification Service

    F->>W: Select plot, upload photo
    W->>A: POST /disease-reports {plot_id, captured_at}
    A->>A: Validate request
    A->>S3: Generate pre-signed upload URL
    A->>DB: Create disease_report (status=pending)
    A->>Q: Enqueue predict_disease task
    A-->>W: 202 Accepted {report_id, status=pending}
    W->>F: Show "Analyzing..." with polling

    F->>S3: PUT image (direct upload)
    S3-->>F: 200 OK

    Q->>WKR: Deliver task
    WKR->>S3: Download image
    WKR->>ML: POST /predict/disease (image bytes)
    ML->>ML: Preprocess (resize 640x640, normalize)
    ML->>ML: ONNX inference
    ML-->>WKR: Predictions {label, confidence, all_predictions}
    WKR->>DB: Update disease_report (status=completed)
    WKR->>DB: Create disease_prediction record
    WKR->>N: Send push notification to farmer
    WKR-->>Q: ACK

    F->>W: Poll /disease-reports/{id}
    W->>A: GET /disease-reports/{id}
    A->>DB: Fetch report + prediction
    A-->>W: 200 OK {report, prediction, treatment_recommendations}
    W->>F: Display result + treatment options
```

#### 14.3.5 ML Pipeline

**Model.** YOLOv8x-cls (classification variant), fine-tuned on the combined dataset (PlantVillage + PlantDoc + custom).

**Preprocessing.**
1. Decode JPEG/PNG to RGB
2. Resize to 640×640 (preserve aspect ratio with letterbox padding)
3. Normalize to [0, 1] (divide by 255)
4. Standardize per-channel mean/std
5. Convert to NCHW format for ONNX

**Augmentation during training.**
- Random rotation ±30°
- Horizontal flip (p=0.5)
- Vertical flip (p=0.1)
- Color jitter (brightness ±20%, contrast ±20%, saturation ±20%, hue ±5%)
- Random crop (80-100% of original)
- Gaussian blur (p=0.1, kernel 3-7)
- Simulated motion blur (p=0.05)
- Random shadow (p=0.1)
- Cutout / random erasing (p=0.1)

**Class balancing.** The custom Indian dataset has class imbalance (some diseases have 50 samples, others have 2000). Use **focal loss** with class weights to address this.

**Evaluation.**
- Held-out test set (15% of dataset, stratified by class)
- Metrics: Top-1 accuracy, Top-5 accuracy, per-class precision/recall/F1, macro-F1, confusion matrix
- Thresholds: Top-1 ≥ 92%, macro-F1 ≥ 0.88, no single class with F1 < 0.75
- Per-class confusion analysis to identify which diseases are most commonly confused

**Confidence calibration.** Apply **temperature scaling** to softmax outputs so that confidence scores reflect true accuracy. A predicted confidence of 0.85 should mean the model is correct 85% of the time.

**Low-confidence handling.** If top prediction confidence < 70%, the UI displays "Diagnosis uncertain — please consult an agricultural officer" and creates a task in the officer's worklist for manual review.

#### 14.3.6 Treatment Recommendation Engine

The disease prediction is mapped to treatment recommendations via a curated `disease_treatments` table:

```sql
CREATE TABLE intelligence.disease_treatments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disease_slug    VARCHAR(100) NOT NULL,  -- e.g., 'tomato_early_blight'
    treatment_type  VARCHAR(20) NOT NULL CHECK (treatment_type IN ('organic', 'chemical', 'biological', 'cultural')),
    product_id      UUID REFERENCES commerce.products(id),  -- Link to marketplace
    dosage          VARCHAR(255),
    application_method TEXT,
    timing          TEXT,
    precautions     TEXT,
    source          VARCHAR(255),  -- Citation (ICAR, university extension)
    is_primary      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

This enables the "Order Treatment" button on the disease result page — one click adds the recommended product to the cart.

#### 14.3.7 Edge Cases

- **Non-plant image uploaded.** Model trained to recognize "not a plant" class. If image is detected as non-plant, return 422 with message "Please upload a clear photo of the affected plant."
- **Multiple diseases in one image.** YOLOv8 can be configured for multi-label classification. Top-3 predictions shown, with confidence for each.
- **Image too blurry.** Pre-inference blur detection (Laplacian variance). If below threshold, prompt farmer to retake photo.
- **Offline upload.** PWA service worker queues the upload; when connectivity returns, photo is uploaded and inference triggered. Farmer notified via push notification when result is ready.
- **Model unavailable.** If ML service is down, API returns 503 with message "Diagnosis temporarily unavailable. Please try again in a few minutes." No silent failure.

#### 14.3.8 Disease Hotspot Detection

Daily batch job aggregates disease reports by district and crop, computing a "disease pressure index" for each (district, crop, week) tuple. If the index exceeds threshold, an alert is sent to the district agri officer, who can issue a region-wide advisory.

#### 14.3.9 SLOs

- Inference latency (model only): P95 < 500ms on GPU, P95 < 3s on CPU
- End-to-end (upload → result): P95 < 15 seconds on 4G, P95 < 60 seconds on 3G
- Model availability: 99.9%
- Top-1 accuracy in production: ≥ 90% (continuously measured via farmer feedback)

---

### 14.4 Soil Health & Weather Intelligence

#### 14.4.1 Goal

Provide farmers with plot-specific soil information and accurate, timely weather data (current conditions, 7-day forecast, historical trends) to support decisions on irrigation, fertilizer application, sowing, and harvesting.

#### 14.4.2 User Stories

- As a farmer, I want to see the current weather at my plot, so that I can decide whether to irrigate today.
- As a farmer, I want to see a 7-day forecast, so that I can plan my week's activities.
- As a farmer, I want to see my soil test results, so that I know which nutrients to add.
- As a farmer, I want alerts for extreme weather (frost, hail, heat wave), so that I can protect my crops.

#### 14.4.3 Data Sources

- **India Meteorological Department (IMD) API.** Official government source for Indian weather. Provides current conditions, 7-day forecasts, agromet advisories, and historical data. Free for government use.
- **OpenWeatherMap (OWM).** Backup source for current conditions; richer API but commercial.
- **Sentinel Hub Weather.** For weather data overlaid on satellite imagery.
- **State Soil Health Card (SHC) portal.** For farmer's official soil test results.
- **ISRIC SoilGrids.** Global soil property predictions at 250m resolution. Used to auto-populate soil type when a plot is registered.

#### 14.4.4 Architecture

```mermaid
graph TB
    subgraph External Sources
        IMD[IMD API]
        OWM[OpenWeatherMap]
        SHC[Soil Health Card Portal]
        ISR[ISRIC SoilGrids]
    end

    subgraph KrishiSetu
        BEAT[Celery Beat<br/>Hourly weather sync]
        WRK[Celery Worker]
        API[FastAPI Endpoint]
        DB[(PostgreSQL<br/>weather_observations)]
        RD[(Redis<br/>Current weather cache)]
    end

    IMD -->|REST| WRK
    OWM -->|REST fallback| WRK
    SHC -->|REST| WRK
    ISR -->|REST once per plot| WRK

    BEAT -->|Schedule hourly| WRK
    WRK -->|Upsert| DB
    WRK -->|Update cache| RD

    API -->|Read current| RD
    API -->|Read history| DB
    API -->|Read SHC| DB

    style IMD fill:#FEF3C7,stroke:#D97706,stroke-width:2px
    style OWM fill:#FEF3C7,stroke:#D97706
    style SHC fill:#FEF3C7,stroke:#D97706
    style ISR fill:#FEF3C7,stroke:#D97706
    style API fill:#0F766E,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
```

#### 14.4.5 Weather Data Flow

1. **Hourly sync.** Celery Beat triggers a weather sync job every hour. The job identifies all districts with registered plots, fetches current conditions + 7-day forecast from IMD for each district, and upserts into `weather_observations` (current) and `weather_forecasts` (7-day).
2. **Per-plot interpolation.** When a farmer views weather for their plot, the API uses the plot's centroid to interpolate from nearby district observations. Redis caches the per-plot result with a 15-minute TTL.
3. **Extreme weather alerts.** A separate Celery job runs every 3 hours, comparing forecasts against thresholds (e.g., temperature > 42°C, hail risk, frost risk). If threshold exceeded for a district, alerts are dispatched to all farmers with plots in that district, in their preferred language and channel (SMS, push, voice).

#### 14.4.6 Soil Health Integration

1. **Auto-population at plot registration.** When a plot is registered, the system queries ISRIC SoilGrids with the plot centroid and populates `soil_type`, `ph`, `organic_carbon`, `clay_pct`, `sand_pct`, `silt_pct`. Farmer can override with manual values.
2. **SHC import.** Farmer can fetch their official Soil Health Card by entering their SHC ID. The system calls the SHC portal API, retrieves test results (N, P, K, pH, EC, organic carbon, micronutrients), and stores them with the plot.
3. **Manual entry.** Farmer or agri officer can manually enter soil test results from any lab.
4. **Fertilizer recommendation.** Based on soil test results + crop type + growth stage, the system recommends fertilizer dosage (NPK) following ICAR guidelines.

#### 14.4.7 SLOs

- Weather sync freshness: < 1 hour lag (P95)
- Current weather query latency: P95 < 200ms (Redis cached)
- Forecast query latency: P95 < 500ms
- Extreme weather alert delivery latency: < 15 minutes from forecast publication

---

### 14.5 Satellite NDVI & Farm Monitoring

#### 14.5.1 Goal

Provide farmers with weekly, plot-level vegetation health monitoring using free Sentinel-2 satellite imagery, with anomaly detection that flags declining areas for inspection and historical trends that support season-over-season comparison.

#### 14.5.2 User Stories

- As a farmer, I want to see the latest NDVI map of my plot, so that I know which areas need attention.
- As a farmer, I want a 12-week NDVI trend chart, so that I can see how my crop is progressing.
- As a farmer, I want an alert when my plot's NDVI drops unexpectedly, so that I can investigate.
- As an agri officer, I want a district NDVI heatmap, so that I can identify regions under stress.
- As an insurer, I want NDVI evidence for an insured plot, so that I can validate a crop loss claim.

#### 14.5.3 Data Sources

- **Sentinel-2 L2A imagery** via Sentinel Hub or direct download from Copernicus Open Access Hub. Free, 5-day revisit, 10m resolution. Bands used: B04 (red), B08 (NIR), B02 (blue), B03 (green), B11 (SWIR), SCL (scene classification for cloud masking).
- **Landsat 8/9** as backup when Sentinel-2 has cloud cover.
- **OpenStreetMap** for plot boundary context.

#### 14.5.4 NDVI Computation Pipeline

NDVI (Normalized Difference Vegetation Index) is a deterministic computation, not an ML task:

$$NDVI = \frac{NIR - Red}{NIR + Red} = \frac{B08 - B04}{B08 + B04}$$

Values range from -1 to +1. Healthy vegetation: 0.6 to 0.9. Sparse vegetation: 0.2 to 0.5. Bare soil: 0.1 to 0.2. Water: < 0.

```mermaid
sequenceDiagram
    participant BEAT as Celery Beat
    participant Q as Celery Queue
    participant WKR as NDVI Worker
    participant SH as Sentinel Hub API
    participant S3 as Object Storage
    participant DB as PostgreSQL
    participant N as Notifications

    BEAT->>Q: Schedule nightly NDVI refresh
    Q->>WKR: Deliver task

    WKR->>DB: Fetch plots needing refresh (last_ndvi > 7 days)
    loop For each plot
        WKR->>SH: Request Sentinel-2 imagery for plot bbox, last 14 days
        SH-->>WKR: Imagery (GeoTIFF) + metadata
        WKR->>WKR: Cloud mask (SCL band)
        WKR->>WKR: Crop to plot boundary
        WKR->>WKR: Compute NDVI per pixel
        WKR->>WKR: Compute stats (mean, min, max, stddev)
        WKR->>S3: Upload NDVI raster (GeoTIFF)
        WKR->>DB: Insert ndvi_observation
        WKR->>DB: Compare to previous observation
        alt NDVI drop > 0.15
            WKR->>N: Trigger alert to farmer
        end
    end
    WKR-->>Q: ACK
```

#### 14.5.5 Implementation Details

- **Sentinel Hub API.** Used instead of direct Copernicus download for reliability and speed. Returns processed imagery (atmospheric correction applied). Pricing is per-request, cost managed by caching.
- **Cloud masking.** Use the SCL (Scene Classification Layer) band to mask cloud, cloud shadow, and snow pixels. If cloud cover > 30%, mark observation as "cloudy" and try the next available date.
- **Raster processing.** `rasterio` + `numpy` for NDVI computation and statistics. The full NDVI raster is uploaded to S3 as a GeoTIFF, served to the frontend via pre-signed URL, and rendered on a Leaflet map with a color scale legend.
- **Color scale.** Matches the reference UI: green (#4CAF50) for high NDVI, yellow (#FFEB3B) for medium, orange (#FF9800) for low.
- **Stats computation.** For each plot: mean NDVI, min, max, stddev. Stored as a single `ndvi_observations` row per plot per observation date.
- **Weekly refresh.** Celery Beat triggers nightly. Each plot is refreshed every 7 days (configurable per plot). Immediate refresh available via `POST /plots/{id}/ndvi/refresh` (rate-limited to once per day).

#### 14.5.6 Anomaly Detection

Compare latest NDVI to previous observation. If drop > 0.15 (significant vegetation loss), trigger an alert:
- Push notification to farmer: "NDVI for plot X dropped by 18% in the last week. Tap to view map and inspect."
- Task in agri officer's worklist if the drop is severe (>0.3).
- Linked to disease report submission flow — "Did you observe any disease symptoms on this plot?"

#### 14.5.7 District Heatmap

For agri officers: aggregate plot NDVI by district, render as a choropleth map. Updates daily. Color scale: green (healthy average) → yellow → orange → red (district under stress). Click on a district to drill down to plot-level NDVI.

#### 14.5.8 SLOs

- NDVI observation freshness: < 7 days lag (assuming cloud-free imagery available)
- NDVI computation time per plot: P95 < 30 seconds
- District heatmap refresh: < 1 hour after new observations
- Raster tile serving latency: P95 < 500ms (via S3 pre-signed URL)

---

### 14.6 Insurance & PMFBY Integration

#### 14.6.1 Goal

Simplify the crop insurance lifecycle for farmers — from product discovery and enrollment through premium payment, claim filing, and payout tracking — with integrated NDVI evidence and agri officer verification to reduce claim rejection rates.

#### 14.6.2 User Stories

- As a farmer, I want to see all insurance products available for my crops and plots, so that I can compare and choose.
- As a farmer, I want to enroll in PMFBY with one click, so that I don't have to fill lengthy forms.
- As a farmer, I want to file a claim when my crop is damaged, with auto-attached NDVI evidence, so that my claim has higher chance of approval.
- As an insurer, I want to see all policies I have issued, with NDVI trends for each, so that I can detect anomalies.
- As an insurer, I want to review claims with all evidence (NDVI, disease reports, weather) in one view, so that I can make decisions quickly.

#### 14.6.3 Data Sources

- **PMFBY portal API** (Pradhan Mantri Fasal Bima Yojana). Government crop insurance scheme. Provides scheme details, empaneled insurers, premium rates, claim status.
- **State government crop insurance portals.** Some states have their own portals; integrate via state-specific adapters.
- **Internal NDVI, disease reports, weather** — used as claim evidence.

#### 14.6.4 Architecture

```mermaid
stateDiagram-v2
    [*] --> ProductDiscovered: Farmer browses products
    ProductDiscovered --> Enrolled: Farmer enrolls (auto-fill from profile)
    Enrolled --> Active: Insurer confirms policy
    Active --> ClaimFiled: Farmer files claim
    Active --> Expired: Season ends (no claim)
    ClaimFiled --> UnderReview: Insurer reviews
    UnderReview --> EvidenceRequested: Insurer requests more evidence
    EvidenceRequested --> UnderReview: Farmer submits additional
    UnderReview --> Approved: Insurer approves
    UnderReview --> Rejected: Insurer rejects (with reason)
    Approved --> PayoutDisbursed: Bank transfer
    Rejected --> [*]: Case closed
    PayoutDisbursed --> [*]
    Expired --> [*]
```

#### 14.6.5 Claim Evidence Workflow

When a farmer files a claim, the platform automatically compiles evidence:

1. **NDVI history** for the insured plot, showing the drop that corroborates loss.
2. **Disease reports** submitted by the farmer for the same plot in the relevant period.
3. **Weather events** (extreme weather alerts) for the plot's district in the claim period.
4. **Plot boundary map** with the affected area highlighted (if farmer marks a specific area).
5. **Agricultural officer verification** (optional) — officer visits the plot and submits a ground-truth report.

All evidence is packaged into a single PDF + JSON bundle, sent to the insurer via API or webhook.

#### 14.6.6 SLOs

- Product listing query: P95 < 500ms
- Enrollment (form submission): P95 < 5 seconds
- Claim filing (with auto-evidence): P95 < 10 seconds
- Insurer claim review SLA: 21 business days (per PMFBY guidelines)

---

### 14.7 Agricultural Marketplace

#### 14.7.1 Goal

Connect verified farmers with verified suppliers of seeds, fertilizers, pesticides, and farm machinery, with transparent pricing, quality certification display, and integrated order tracking — eliminating counterfeit inputs and price opacity.

#### 14.7.2 User Stories

- As a farmer, I want to browse products by category (seeds, fertilizers, pesticides, machinery), so that I can find what I need.
- As a farmer, I want to see product prices upfront, with quality certifications, so that I can compare.
- As a farmer, I want to order a product and pay via UPI, so that I don't have to carry cash.
- As a farmer, I want to track my order from placement to delivery, so that I know when to expect it.
- As a supplier, I want to manage my product catalog, inventory, and orders in one place, so that I can run my business efficiently.
- As an admin, I want to verify supplier licenses (seed license, fertilizer license), so that only legitimate suppliers operate on the platform.

#### 14.7.3 Architecture

The marketplace follows an **order state machine** pattern:

```mermaid
stateDiagram-v2
    [*] --> Cart: Farmer adds products
    Cart --> Placed: Farmer places order
    Placed --> Confirmed: Supplier accepts
    Placed --> Cancelled: Supplier rejects / out of stock
    Confirmed --> Packed: Supplier packs
    Packed --> Shipped: Supplier ships (with tracking ID)
    Shipped --> OutForDelivery: Courier out for delivery
    OutForDelivery --> Delivered: Farmer confirms receipt
    OutForDelivery --> DeliveryFailed: Courier returns
    Delivered --> Completed: 7-day return window expires
    DeliveryFailed --> RefundInitiated
    RefundInitiated --> [*]
    Completed --> [*]
    Cancelled --> RefundInitiated
```

#### 14.7.4 Payment Integration

- **UPI (primary).** Native UPI intent for mobile; UPI ID entry for desktop. Settles instantly.
- **Razorpay (secondary).** For credit/debit cards, net banking, wallets.
- **Cash on Delivery (limited).** Only for verified farmers with prior order history.
- **Escrow.** Payment held in escrow until delivery confirmation; released to supplier on `Delivered` state.

#### 14.7.5 Supplier Verification

Suppliers must upload their licenses (seed license, fertilizer license, GST certificate) during registration. Admin verifies each license against the issuing authority's database before activating the supplier account. Verified suppliers display a "Verified Supplier" badge with the license numbers visible on their profile.

#### 14.7.6 Inventory Management

Suppliers manage inventory through their dashboard:
- Add products with photos, description, price, certification, batch number, expiry date.
- Set stock quantity (with low-stock alerts).
- View order list with one-click accept/reject.
- Update shipment tracking ID for each order.

#### 14.7.7 SLOs

- Product search latency: P95 < 300ms
- Order placement latency: P95 < 2 seconds
- Order confirmation dispatch: < 5 minutes

---

### 14.8 Government Schemes Discovery

#### 14.8.1 Goal

Maintain a comprehensive, always-up-to-date catalog of central and state government agricultural schemes (PM-Kisan, KCC, PMFBY, Soil Health Card, etc.), with an eligibility engine that matches farmers to schemes based on their verified profile.

#### 14.8.2 User Stories

- As a farmer, I want to see all schemes I am eligible for, so that I don't miss out on benefits.
- As a farmer, I want to see schemes I have already applied for, with current status, so that I can track progress.
- As a farmer, I want to apply for a scheme with my profile auto-filled, so that I don't have to re-enter information.
- As an agri officer, I want to review scheme applications in my district, so that I can approve or request more info.
- As an admin, I want to add new schemes and update eligibility rules, so that the catalog stays current.

#### 14.8.3 Architecture

The eligibility engine is a **rules engine** that evaluates a farmer's profile against a scheme's eligibility criteria. Rules are defined in YAML, versioned, and stored in the database:

```yaml
# schemes/pm-kisan.yaml
scheme_code: pm-kisan
name: Pradhan Mantri Kisan Samman Nidhi
description: |
  Income support of Rs 6000 per year to all landholding farmer families.
eligibility_rules:
  - field: role
    operator: eq
    value: farmer
  - field: aadhaar_verified
    operator: eq
    value: true
  - field: total_land_holding_ha
    operator: gt
    value: 0
  - field: occupation_category
    operator: not_in
    value: ["institutional", "government_job", "tax_payer"]
benefits:
  amount_inr: 6000
  frequency: yearly
  payment_mode: dbt
application_flow:
  - field: aadhaar
    auto_fill: true
  - field: bank_account
    auto_fill: true
    verify: penny_drop
  - field: land_records
    auto_fill: true
    verify: bhulekh
```

#### 14.8.4 Scheme Sync

A Celery Beat job syncs the scheme catalog from government sources daily:
- PM-Kisan: Check for new installments, update beneficiary status.
- PMFBY: Sync season dates, premium rates.
- State schemes: Per-state adapters (Maharashtra, Karnataka, etc.).

#### 14.8.5 Application Workflow

1. **Eligibility check.** Farmer visits scheme detail page; engine evaluates rules against their profile; shows "Eligible" / "Not Eligible" with reasons.
2. **Auto-fill.** Application form pre-populated from profile (Aadhaar, bank account, land records).
3. **Submit.** Application stored with `submitted_data` JSON snapshot.
4. **Sync to govt portal.** If the scheme has an API, application is forwarded automatically. Otherwise, generates a PDF for manual submission at the govt office.
5. **Status tracking.** Status polled from govt portal daily. Farmer notified on status change.

#### 14.8.6 SLOs

- Eligibility check latency: P95 < 500ms
- Application submission latency: P95 < 3 seconds
- Status sync freshness: < 24 hours

---

### 14.9 Multilingual & Voice Interface

#### 14.9.1 Goal

Make the platform accessible to farmers who cannot read or who prefer their native language, through comprehensive multilingual support (10 languages) and voice-based query and response.

#### 14.9.2 User Stories

- As a farmer, I want the entire UI in my native language, so that I can understand everything.
- As a farmer, I want to ask a question by speaking, so that I don't have to type.
- As a farmer, I want the response spoken aloud, so that I can listen while working in the field.
- As a farmer, I want to navigate the app by voice, so that I can use it hands-free.

#### 14.9.3 Architecture

```mermaid
graph LR
    F[Farmer speaks<br/>in Marathi]
    ASR[Whisper ASR<br/>multilingual]
    NLP[MuRIL NLU<br/>intent classification]
    API[FastAPI Handler<br/>fetch data]
    TTS[Azure TTS<br/>Marathi voice]
    F2[Farmer hears<br/>response]

    F -->|Audio upload| ASR
    ASR -->|Marathi text| NLP
    NLP -->|Intent + entities| API
    API -->|Response data| TTS
    TTS -->|Audio response| F2

    style F fill:#E6F4EA,stroke:#4CAF50
    style ASR fill:#7C3AED,color:#FFFFFF,stroke:#4CAF50
    style NLP fill:#7C3AED,color:#FFFFFF,stroke:#4CAF50
    style API fill:#0F766E,color:#FFFFFF,stroke:#4CAF50
    style TTS fill:#7C3AED,color:#FFFFFF,stroke:#4CAF50
    style F2 fill:#E6F4EA,stroke:#4CAF50
```

#### 14.9.4 Localization Pipeline

1. **Translation source.** All UI strings authored in English, translated by certified translators (English → 9 Indian languages).
2. **Translation memory.** Use Crowdin or Lokalise for translation management, with translator review and versioning.
3. **String catalog.** Translations stored as JSON files in `apps/web/src/messages/<locale>.json`. Loaded at build time for SSG, runtime for SSR.
4. **RTL support.** Not required for the 10 target languages (all LTR), but the architecture supports it for future Urdu/Arabic.
5. **Cultural adaptation.** Beyond strings: date formats (DD/MM/YYYY), currency (₹ with Indian numbering — lakh, crore), units (hectares vs. acres toggle), voice gender (matching user preference).

#### 14.9.5 Voice Pipeline

- **Speech-to-Text (ASR).** OpenAI Whisper large-v3, fine-tuned on Indic speech corpus (IndicSUPERB + custom farmer voice samples). Self-hosted on GPU inference service. Returns text in the spoken language.
- **Natural Language Understanding (NLU).** Google MuRIL (Multilingual Representations for Indian Languages) fine-tuned for intent classification. Supports intents like `check_weather`, `report_disease`, `scheme_eligibility`, `market_price`, `insurance_status`. Returns structured intent + entities.
- **Response generation.** Based on intent, the FastAPI handler fetches relevant data (weather, scheme, etc.) and constructs a response template in the user's language.
- **Text-to-Speech (TTS).** Azure Cognitive Services Speech API for natural voices in all 10 languages. Audio streamed back to the client.

#### 14.9.6 Sample Voice Flow

```
Farmer (Marathi): "माझ्या शेतात आज हवामान कसा आहे?"
                  ("How is the weather at my field today?")

ASR output:       "माझ्या शेतात आज हवामान कसा आहे?"

NLU output: {
  "intent": "check_weather",
  "entities": { "when": "today", "location": "my_field" },
  "language": "mr"
}

API handler: Fetches current weather for farmer's primary plot.

Response template (Marathi): "तुमच्या शेतात आज तापमान 28 अंश सेल्सिअस आहे.
                              आर्द्रता 65% आहे. पाऊस अजून 3 दिवसांनी होण्याची शक्यता आहे."

TTS output:       (Marathi audio response streamed back)
```

#### 14.9.7 Edge Cases

- **Unrecognized language.** If ASR detects a language outside the 10 supported, prompt user to switch language.
- **Ambiguous intent.** If NLU confidence < 0.7, ask clarifying question.
- **Background noise.** ASR can handle moderate noise. If SNR too low, prompt user to repeat in a quieter environment.
- **Long queries.** Truncate at 30 seconds. If farmer speaks longer, prompt to break into multiple queries.

#### 14.9.8 SLOs

- ASR latency: P95 < 3 seconds for 10-second audio
- NLU latency: P95 < 200ms
- TTS latency (time to first audio byte): P95 < 1 second
- End-to-end voice query: P95 < 8 seconds

---

## 15. Security Architecture

Security is engineered into every layer of KrishiSetu, not added as an afterthought. The platform handles Aadhaar numbers, bank account details, land ownership records, and financial transactions — making it a high-value target for adversaries ranging from individual fraudsters to organized cybercrime. The security architecture is designed against the **STRIDE threat model** and **OWASP Top 10** with explicit mitigations for each threat category.

### 15.1 Threat Model (STRIDE)

| Threat Category | Specific Threats | Mitigations |
|-----------------|------------------|-------------|
| **Spoofing** | Impersonating a farmer to file false claims; impersonating UIDAI to capture Aadhaar | JWT with short-lived access tokens + refresh token rotation; mutual TLS to UIDAI API; certificate pinning for UIDAI calls; OTP-based second factor for sensitive actions |
| **Tampering** | Modifying plot boundary to claim larger area; altering disease report to inflate insurance claim | Append-only audit log for all mutations; cryptographic integrity checks on critical records; server-side validation of all client-supplied data; row-level security on multi-tenant data |
| **Repudiation** | Farmer denies submitting a scheme application; supplier denies receiving an order | Every state-changing action logged with user ID, timestamp, IP, user agent, request payload hash, and digital signature; audit log is append-only with database-level write protection |
| **Information Disclosure** | Aadhaar numbers leaked; farmer PII sold to third parties; NDVI data exploited by competitors | Aadhaar never stored in plaintext (SHA-256 + per-record salt); all PII encrypted at rest (PostgreSQL TDE); strict RBAC on PII access; data classification policy with handling rules; no PII in logs |
| **Denial of Service** | Botnet floods API endpoints; large image uploads exhaust storage; ML inference DDoS | Edge rate limiting at NGINX (IP-based); application rate limiting per-user per-route; upload size limits (10MB images, 5MB audio); ML inference queue with backpressure; DDoS protection via Cloudflare |
| **Elevation of Privilege** | Farmer escalates to admin role; supplier accesses other suppliers' orders; insurer reads unrelated farmer data | Role-based access control enforced at route, service, and database layer; row-level security in PostgreSQL; principle of least privilege for all service accounts; periodic access review |

### 15.2 OWASP Top 10 Mitigations

| OWASP Risk (2021) | KrishiSetu Mitigation |
|-------------------|----------------------|
| **A01 — Broken Access Control** | RBAC dependency on every protected route; row-level security in PostgreSQL; deny-by-default for all resources; server-side ownership verification (`WHERE farmer_id = current_user.id`) |
| **A02 — Cryptographic Failures** | TLS 1.3 everywhere; AES-256-GCM at rest; Aadhaar hashed with SHA-256 + salt; bank account numbers encrypted with envelope encryption (KMS-managed master key); HSM for Aadhaar API signing key |
| **A03 — Injection** | SQLAlchemy 2.0 with parameterized queries everywhere (no string concatenation); Pydantic input validation; strict allowlist for file uploads (magic byte validation, not just extension) |
| **A04 — Insecure Design** | Threat modeling for every new feature; security architecture review at design phase; abuse-case testing alongside happy-path testing |
| **A05 — Security Misconfiguration** | Infrastructure as Code (Terraform/Docker Compose); security baseline configs versioned; no default credentials; production configs differ from dev; security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) |
| **A06 — Vulnerable & Outdated Components** | Dependabot / Renovate for automated dependency updates; Snyk for vulnerability scanning; pinned versions in `requirements.txt` with hashes; monthly dependency review |
| **A07 — Identification & Authentication Failures** | OTP-based auth with rate limiting; account lockout after failed attempts; JWT in HTTP-only Secure cookies; refresh token rotation; session invalidation on password change |
| **A08 — Software & Data Integrity Failures** | Signed container images (Cosign); SBOM generation (Syft); signed releases; ML model signatures verified at load time |
| **A09 — Security Logging & Monitoring Failures** | Structured audit log for every state change; Loki + Grafana for log analysis; Prometheus alerting on security anomalies (spike in 401s, repeated 403s, unusual access patterns); 90-day log retention with optional longer for security incidents |
| **A10 — Server-Side Request Forgery (SSRF)** | Strict allowlist for outbound HTTP calls (only known govt APIs, OWM, Sentinel Hub); no user-controlled URLs in server-side fetches; egress firewall rules |

### 15.3 Authentication Security Details

- **Password storage.** Bcrypt with 12 rounds (configurable upward as hardware improves). Passwords are optional — farmers can use OTP-only auth.
- **OTP security.** 6-digit OTP, 5-minute TTL, max 3 verification attempts, max 5 OTP requests per phone per hour. OTPs stored in Redis (not database) with hash. After 3 failed attempts, OTP invalidated and new one required.
- **JWT signing.** HS256 with a 256-bit secret from Vault. Secret rotated every 90 days; old secret valid for 1 week after rotation to allow in-flight tokens to expire naturally.
- **Refresh token storage.** Hashed (SHA-256) in `refresh_tokens` table with `user_id`, `device_info`, `expires_at`, `revoked_at`. New token issued on each refresh; old token revoked.
- **Session invalidation.** On logout, refresh token revoked. On password change / phone change, all sessions for the user revoked.
- **Suspicious activity detection.** Login from new device → SMS alert. Login from new geographic region (IP geolocation) → SMS alert. Multiple failed logins → admin notification.

### 15.4 Authorization (RBAC) Details

- **Roles.** Five fixed roles: `farmer`, `agri_officer`, `supplier`, `insurer`, `admin`. Roles are stored on the `users` table and propagated into JWT claims.
- **Permissions.** Each role has a defined set of permissions (e.g., `plot:create`, `plot:read:own`, `plot:read:district`, `disease:report:create`). Permissions are defined in a single configuration file (`krishisetu/core/permissions.py`) and enforced via the `require_permissions` dependency.
- **Resource ownership.** Beyond role-based permissions, every resource has an owner (e.g., `plots.farmer_id`). All queries for resources are scoped by ownership: `SELECT * FROM plots WHERE farmer_id = :current_user_id`. This is enforced at the repository layer, not the route layer, to prevent accidental leaks.
- **Row-Level Security (RLS).** PostgreSQL RLS policies add defense-in-depth: even if a bug in the application layer constructs an unscoped query, the database refuses to return rows not owned by the current user (or in their district, for officers).

```sql
-- Example RLS policy
ALTER TABLE farmer.plots ENABLE ROW LEVEL SECURITY;

CREATE POLICY plots_farmer_isolation ON farmer.plots
    FOR ALL
    USING (farmer_id = current_setting('app.current_user_id')::uuid);

CREATE POLICY plots_officer_district ON farmer.plots
    FOR SELECT
    TO agri_officer_role
    USING (district = ANY (
        SELECT district FROM officer_districts
        WHERE officer_id = current_setting('app.current_user_id')::uuid
    ));
```

### 15.5 Data Protection

- **Encryption at rest.** PostgreSQL TDE ( Transparent Data Encryption) via `pgcrypto` extension for column-level encryption of PII (bank account numbers, Aadhaar hash salts). Full-disk encryption on EBS volumes. S3 server-side encryption with KMS-managed keys (SSE-KMS).
- **Encryption in transit.** TLS 1.3 for all external traffic. mTLS for service-to-service communication within the VPC. Certificate rotation automated via cert-manager.
- **PII classification.** Data classified into four tiers:
  - **Tier 1 (Public).** Scheme catalogs, weather, mandi prices.
  - **Tier 2 (Internal).** Aggregate statistics, anonymized analytics.
  - **Tier 3 (Confidential).** Farmer profile, plot records, order history.
  - **Tier 4 (Restricted).** Aadhaar hash, bank account numbers, OTPs.
- **Access logging for Tier 4.** Every read of Tier 4 data is logged with the accessing user, time, and purpose. Reviewed monthly by security team.

### 15.6 API Security

- **Rate limiting.** Three layers: (1) NGINX IP-based (100 req/sec per IP, burst 200), (2) FastAPI per-user per-route (configurable, e.g., 5/min for auth, 20/min for ML, 100/min for general), (3) per-resource (e.g., 1 NDVI refresh per plot per day).
- **Input validation.** Pydantic schemas on every endpoint, with strict types, regex validation (phone, Aadhaar, pincode), length limits, and value range checks.
- **Output sanitization.** Pydantic response models prevent accidental data leakage (e.g., never returning `password_hash` even if it's on the model).
- **CORS.** Strict allowlist of origins (only the Next.js frontend domain). No wildcards in production.
- **Security headers.** Set via NGINX:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.sentinel-hub.com https://*.openstreetmap.org; ...`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: geolocation=(self), microphone=(self), camera=(self)`
- **Web Application Firewall (WAF).** Cloudflare or AWS WAF in front of NGINX. Rules: SQL injection patterns, XSS patterns, path traversal, known bot signatures.

### 15.7 Secrets Management

- **Local development.** `.env` files (gitignored). `.env.example` checked in as a template.
- **Production.** HashiCorp Vault stores all secrets (DB credentials, JWT secret, API keys, signing keys). FastAPI retrieves secrets at startup via Vault's Kubernetes auth (or AppRole for VM deployments). No secrets in environment variables or container images.
- **Secret rotation.** JWT secret rotated quarterly. Database passwords rotated monthly. API keys rotated per provider policy. Vault handles rotation transparently where supported.
- **No secrets in code.** Pre-commit hook scans for high-entropy strings and known secret patterns (TruffleHog). CI fails on any detected secret.

### 15.8 Vulnerability Management

- **Dependency scanning.** Snyk scans `requirements.txt` and `package.json` on every PR. Fail on high or critical vulnerabilities.
- **Container scanning.** Trivy scans Docker images on build. Fail on critical vulnerabilities.
- **Static analysis.** Bandit (Python), Semgrep (multi-language), ESLint security plugin. Run in CI.
- **Dynamic scanning.** OWASP ZAP scan against staging environment weekly.
- **Penetration testing.** Annual third-party pentest. Bug bounty program (private, via HackerOne or Bugcrowd) for ongoing external testing.
- **Responsible disclosure.** Public `security@krishisetu.in` email with 72-hour acknowledgement SLA and 90-day remediation SLA.

### 15.9 Compliance

- **DPDP Act 2023 (Digital Personal Data Protection Act).** India's data protection law. KrishiSetu complies by:
  - Explicit consent for data collection, with granular opt-in per data category.
  - Right to access, correct, delete personal data (implemented as `GET /me/data-export` and `DELETE /me` endpoints).
  - Data minimization — only collect what's needed for the specific purpose.
  - Data residency — all data stored in India (AWS Mumbai or MeghRaj).
  - Data Protection Officer (DPO) designated, contact info in privacy policy.
- **Aadhaar Act 2016.** Compliance for Aadhaar data:
  - Never store raw Aadhaar number.
  - Only store masked Aadhaar (last 4 digits) and hash.
  - Use only UIDAI-authorized e-KYC APIs.
  - Audit trail for every Aadhaar verification.
- **CERT-In directives.** 6-hour incident reporting to CERT-In. Incident response plan documented and tested quarterly.

### 15.10 Security Development Lifecycle (SDL)

Every feature goes through:
1. **Design phase.** Threat model updated for new attack surfaces. Security review by security lead.
2. **Implementation.** Secure coding guidelines followed. Pre-commit hooks for secret scanning.
3. **Code review.** Security-focused review checklist. Two-reviewer approval for security-sensitive code.
4. **Testing.** Unit tests for auth/RBAC logic. Integration tests for permission boundaries. Abuse-case testing.
5. **Deployment.** Canary deployment with security metric monitoring.
6. **Operation.** Anomaly detection on access patterns. Periodic access review.

---

## 16. Scalability & Performance Strategy

KrishiSetu is designed to handle **10 million registered farmers** and **1 million daily active users** at steady state, with peak loads during scheme enrollment windows, weather alert broadcasts, and harvest seasons potentially reaching 5x average traffic. The scalability strategy is horizontal, with each tier independently scalable based on its specific bottleneck.

### 16.1 Traffic Projections

| Metric | Year 1 (MVP) | Year 2 (Growth) | Year 3 (Scale) |
|--------|--------------|-----------------|----------------|
| Registered users | 100K | 1M | 10M |
| Daily active users | 10K | 100K | 1M |
| Peak QPS (API) | 50 | 500 | 5,000 |
| Peak QPS (ML inference) | 5 | 50 | 500 |
| Storage (PostgreSQL) | 50 GB | 500 GB | 5 TB |
| Storage (S3 — images, rasters) | 500 GB | 5 TB | 50 TB |
| Celery tasks/day | 10K | 100K | 1M |

### 16.2 Horizontal Scaling Architecture

```mermaid
graph TB
    subgraph Edge Layer
        CF[Cloudflare CDN<br/>+ WAF + DDoS protection]
        ALB[Application Load Balancer<br/>TLS termination<br/>Health-checked]
    end

    subgraph API Tier Auto-scaling Group
        API1[FastAPI Pod 1]
        API2[FastAPI Pod 2]
        APIN[FastAPI Pod N<br/>scales on CPU + request queue depth]
    end

    subgraph ML Inference Tier
        ML1[ML Pod 1<br/>GPU]
        ML2[ML Pod 2<br/>GPU]
    end

    subgraph Worker Tier
        WKR1[Celery Worker Pod 1<br/>ml-realtime queue]
        WKR2[Celery Worker Pod 2<br/>ml-batch queue]
        WKR3[Celery Worker Pod 3<br/>external-api queue]
        WKR4[Celery Worker Pod 4<br/>notifications queue]
    end

    subgraph Data Tier
        PG[(PostgreSQL Primary<br/>+ 2 Read Replicas)]
        RD[(Redis Cluster<br/>3 shards, 3 replicas)]
        S3[(S3<br/>auto-scaling)]
    end

    CF --> ALB
    ALB --> API1
    ALB --> API2
    ALB --> APIN

    API1 --> PG
    API1 --> RD
    API1 --> S3
    API1 --> ML1
    API1 --> RD

    API2 --> PG
    API2 --> RD

    APIN --> PG
    APIN --> RD

    ML1 --> S3
    ML2 --> S3

    WKR1 --> RD
    WKR1 --> ML1
    WKR1 --> PG

    WKR2 --> PG
    WKR2 --> S3

    WKR3 --> PG

    WKR4 --> RD

    style ALB fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style API1 fill:#0F766E,color:#FFFFFF,stroke:#4CAF50
    style API2 fill:#0F766E,color:#FFFFFF,stroke:#4CAF50
    style APIN fill:#0F766E,color:#FFFFFF,stroke:#4CAF50
    style ML1 fill:#7C3AED,color:#FFFFFF,stroke:#4CAF50
    style ML2 fill:#7C3AED,color:#FFFFFF,stroke:#4CAF50
    style PG fill:#1E40AF,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style RD fill:#DC2626,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
```

### 16.3 Per-Tier Scaling Strategy

#### 16.3.1 API Tier (FastAPI)

- **Auto-scaling.** HPA (Horizontal Pod Autoscaler) on Kubernetes, scaling on CPU utilization (target 70%) and request queue depth (target 10). Min 3 pods, max 30 pods.
- **Each pod.** Uvicorn workers = `2 * CPU_cores + 1`. Gunicorn as process manager. UVloop enabled.
- **Connection pooling.** SQLAlchemy async engine with pool_size=20, max_overflow=10 per pod. Total max connections = 30 * 30 = 900, well within PostgreSQL's `max_connections=1000`.
- **Read replica routing.** Read-heavy endpoints (NDVI view, marketplace browse, scheme list) route to read replicas via `db.execute(stmt, execution_options={"read_only": True})` which routes to the read-only engine.

#### 16.3.2 ML Inference Tier

- **Auto-scaling.** Scales on GPU utilization (target 80%) and request latency (target P95 < 1s).
- **Each pod.** 1 GPU (NVIDIA T4 or A10G), 1 ONNX Runtime session per loaded model. Models loaded at startup, kept warm.
- **Cold start mitigation.** Min 2 pods always running. Scale-up triggered before queue builds up.

#### 16.3.3 Worker Tier (Celery)

- **Per-queue scaling.** Each queue (`ml-realtime`, `ml-batch`, `external-api`, `notifications`) has its own worker pool, scaled independently based on queue depth.
- **Autoscaling.** Celery's built-in `--autoscale=max,min` mode, driven by queue depth metrics.
- **Prefetch.** `worker_prefetch_multiplier=1` to ensure fair task distribution across workers.
- **Long-running tasks.** Tasks that may exceed 5 minutes are split into subtasks or use Celery's chord primitive for parallel execution.

#### 16.3.4 Database Tier (PostgreSQL)

- **Primary + Read Replicas.** 1 primary (writes), 2 read replicas (reads). Read replicas are async (eventual consistency, ~1s lag).
- **Connection pooling.** PgBouncer in front of PostgreSQL with transaction-mode pooling, max client connections = 1000, max server connections = 100 (per PostgreSQL instance).
- **Partitioning.** Large time-series tables (`ndvi_observations`, `weather_observations`, `audit_log`) partitioned by month, with old partitions archived to S3 after 2 years.
- **Indexing.** All foreign keys indexed. All query patterns reviewed quarterly via `pg_stat_statements` for missing indexes.
- **Vacuum tuning.** Autovacuum configured aggressively on high-write tables. Manual VACUUM during low-traffic windows for partition maintenance.

#### 16.3.5 Cache Tier (Redis)

- **Redis Cluster.** 3 shards, 3 replicas per shard (6 nodes total). Shard by key prefix.
- **Eviction policy.** `allkeys-lru` for general cache, `volatile-ttl` for session data.
- **Max memory.** 16 GB per node, 48 GB total cluster capacity.
- **Persistence.** AOF (append-only file) every second for durability, RDB snapshot every hour for backups.

### 16.4 Caching Strategy

| Data Type | Cache Location | TTL | Invalidation |
|-----------|---------------|-----|--------------|
| User session | Redis | 30 minutes (sliding) | On logout |
| Plot list (per user) | Redis | 5 minutes | On plot create/update/delete |
| Disease catalog | Redis | 1 hour | On admin update |
| Scheme catalog | Redis | 1 hour | On daily sync |
| Weather current (per plot) | Redis | 15 minutes | On hourly sync |
| NDVI latest (per plot) | Redis | 1 hour | On new observation |
| Marketplace product list | Redis | 5 minutes | On product create/update/delete |
| Static assets | CDN | 1 year | Cache-bust on file hash change |
| Public scheme detail page | Next.js ISR | 1 hour | On-demand revalidation |
| API OpenAPI spec | CDN | 1 hour | On backend deploy |

### 16.5 Performance Targets

| Endpoint Category | P50 Latency | P95 Latency | P99 Latency |
|-------------------|-------------|-------------|-------------|
| Auth (login, refresh) | 200ms | 500ms | 1s |
| Read endpoints (plots, schemes) | 100ms | 300ms | 800ms |
| List endpoints (paginated) | 200ms | 500ms | 1.5s |
| Write endpoints (plot create, order place) | 300ms | 800ms | 2s |
| ML inference (disease) | 1s | 3s | 8s |
| Async task end-to-end (disease upload → result) | 5s | 15s | 30s |
| NDVI raster fetch | 200ms | 500ms | 1.5s |
| Voice query (end-to-end) | 3s | 8s | 15s |

### 16.6 Database Query Optimization

- **EXPLAIN ANALYZE on every slow query.** Queries exceeding 100ms are logged and analyzed weekly.
- **N+1 query elimination.** SQLAlchemy `selectinload` and `joinedload` for related resources. N+1 detection in tests via `pytest-sqlalchemy-exc` plugin.
- **Denormalization where appropriate.** For read-heavy views (e.g., dashboard), pre-compute summary fields into a `plot_summary` materialized view, refreshed nightly.
- **Composite indexes.** Designed based on actual query patterns, not speculative. Reviewed quarterly.

### 16.7 Frontend Performance

- **Code splitting.** Next.js App Router automatically code-splits per route. Heavy components (Leaflet maps, Recharts) loaded via `dynamic()` with `ssr: false`.
- **Image optimization.** `next/image` for automatic WebP/AVIF conversion, responsive sizes, lazy loading. Crop photos served as progressive JPEG.
- **Font optimization.** Variable fonts (Inter) with `font-display: swap`. Subsetted per locale.
- **Bundle analysis.** `@next/bundle-analyzer` in CI. Build fails if bundle size grows > 10% without PR explanation.
- **Service Worker.** Caches static assets and previously-fetched API responses for offline access. Cache versioning on every deploy.

---

## 17. Observability

Observability is the difference between a system that is "up" and a system that is "working." KrishiSetu implements the three pillars of observability — logs, metrics, traces — with a unified query layer (Grafana) that allows engineers to investigate any issue by pivoting between these signals via a shared request ID.

### 17.1 Observability Stack

```mermaid
graph LR
    APP[FastAPI / Celery / ML]
    PROM[Prometheus<br/>metrics]
    LOKI[Loki<br/>logs]
    JAE[Jaeger<br/>traces]
    GRA[Grafana<br/>unified dashboards]
    ALT[AlertManager<br/>→ PagerDuty / Slack]

    APP -->|/metrics endpoint<br/>scraped every 15s| PROM
    APP -->|structured JSON logs<br/>via Promtail| LOKI
    APP -->|OpenTelemetry spans| JAE

    GRA -->|query| PROM
    GRA -->|query| LOKI
    GRA -->|query| JAE

    PROM -->|alert rules| ALT

    style APP fill:#0F766E,color:#FFFFFF,stroke:#4CAF50
    style PROM fill:#374151,color:#FFFFFF,stroke:#4CAF50
    style LOKI fill:#374151,color:#FFFFFF,stroke:#4CAF50
    style JAE.fill:#374151,color:#FFFFFF,stroke:#4CAF50
    style GRA fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style ALT fill:#DC2626,color:#FFFFFF,stroke:#4CAF50
```

### 17.2 Structured Logging

Every log entry is structured JSON with the following fields (see Section 9.8). Logs are emitted via `structlog` and shipped to Loki via Promtail. Engineers query logs in Grafana with LogQL:

```logql
{service="api", level="error"} |= "disease" | json | line_format "{{.request_id}} {{.message}}"
```

Critical log categories:
- **Auth events.** Login, logout, OTP send, OTP verify (success/failure), token refresh, account lockout.
- **API requests.** Every request logged with route, method, status, duration, user_id, request_id, error (if any).
- **ML inferences.** Model name, version, input shape, prediction, confidence, inference time.
- **External API calls.** Service name, endpoint, request payload (PII redacted), response status, latency, retries.
- **Celery tasks.** Task name, queue, args (PII redacted), status, duration, retries.
- **Audit events.** Resource type, resource ID, action, actor, before/after state.

### 17.3 Metrics

Prometheus metrics exposed at `/metrics` on every service. Key metric families:

**RED metrics (Rate, Errors, Duration) per route:**
- `http_requests_total{method, route, status}` — counter
- `http_request_duration_seconds{method, route}` — histogram
- `http_requests_in_flight{method, route}` — gauge

**Business metrics:**
- `disease_reports_submitted_total{plot_district, crop_type}` — counter
- `disease_predictions_total{disease_label, confidence_bucket, model_version}` — counter
- `ndvi_observations_computed_total{source}` — counter
- `insurance_claims_filed_total{insurer, status}` — counter
- `marketplace_orders_placed_total{product_category, total_amount_bucket}` — counter
- `scheme_applications_submitted_total{scheme_code, status}` — counter

**Infrastructure metrics:**
- `db_connection_pool_size{engine}` — gauge
- `db_query_duration_seconds{operation}` — histogram
- `redis_operations_total{command, status}` — counter
- `celery_task_duration_seconds{task, queue}` — histogram
- `celery_task_queue_length{queue}` — gauge
- `ml_inference_duration_seconds{model}` — histogram
- `ml_inference_queue_length` — gauge

**SLO metrics:**
- `slo:request_latency_p95{endpoint}` — computed from histogram quantile
- `slo:error_rate{endpoint}` — computed from counter ratio
- `slo:availability{service}` — computed from up gauge

### 17.4 Distributed Tracing

OpenTelemetry auto-instruments:
- FastAPI requests (server span)
- SQLAlchemy queries (client span)
- Redis operations (client span)
- HTTP calls to external APIs (client span)
- Celery tasks (consumer span)

All spans carry the same `trace_id` and `request_id`, enabling engineers to start from a slow API request in Grafana, pivot to its trace in Jaeger, see the SQL query that took 800ms, pivot to the log line for that query, and identify the missing index — all in under 30 seconds.

### 17.5 Dashboards

Pre-built Grafana dashboards:
- **API Overview.** QPS, P95/P99 latency, error rate, status code distribution, top slowest endpoints.
- **ML Inference.** Inference latency per model, GPU utilization, queue depth, prediction distribution.
- **Database.** Connections, query latency, slow queries, replication lag, cache hit ratio.
- **Celery.** Queue depth, task duration, task failures, worker count.
- **Business — Disease.** Daily reports, top diseases, accuracy feedback, district heatmap.
- **Business — Insurance.** Policies, claims, claim approval rate, average claim processing time.
- **Business — Marketplace.** Orders, GMV, top products, supplier performance.
- **Security.** Failed logins, 401/403 spikes, suspicious access patterns.

### 17.6 Alerting

AlertManager routes alerts to PagerDuty (critical), Slack (warning), email (info). Example alerts:

| Alert | Condition | Severity |
|-------|-----------|----------|
| API 5xx rate high | `rate(http_requests_total{status=~"5.."}[5m]) > 0.01` | Critical |
| API P95 latency high | `histogram_quantile(0.95, http_request_duration_seconds_bucket) > 2` for 5m | Warning |
| DB connection pool exhausted | `db_connection_pool_size / db_connection_pool_max > 0.9` | Critical |
| DB replication lag high | `pg_replication_lag_seconds > 30` | Critical |
| Celery queue backed up | `celery_task_queue_length > 1000` for 5m | Warning |
| ML inference latency high | `histogram_quantile(0.95, ml_inference_duration_seconds_bucket) > 5` | Warning |
| ML model drift detected | `model_prediction_distribution_psi > 0.2` | Warning |
| Failed login spike | `rate(auth_events_total{event="login_failed"}[5m]) > 10` | Critical |
| External API down | `up{job="external_api"} == 0` for 2m | Critical |
| Disk usage high | `disk_usage_pct > 85` | Warning |

### 17.7 SLO Review

Monthly SLO review meeting:
- Did we meet SLOs? (Availability > 99.9%, P95 latency targets)
- What incidents occurred? Root cause analysis.
- Are alert thresholds correct? (Too noisy → tune down. Missed incidents → tune up.)
- What metrics need to be added?

---

## 18. DevOps & CI/CD

KrishiSetu uses a GitOps workflow with GitHub Actions for CI and Docker Compose (local) / Kubernetes (production, future) for deployment. The discipline is: every change goes through a PR, every PR runs the full CI pipeline, every merge to `main` triggers a staging deployment, every staging promotion to production requires manual approval.

### 18.1 Local Development Environment

Local development uses Docker Compose to spin up the entire stack with hot-reloading:

```yaml
# infra/docker-compose.yml (abridged)
services:
  postgres:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: krishisetu
      POSTGRES_USER: krishisetu
      POSTGRES_PASSWORD: krishisetu_dev
    ports: ["5432:5432"]
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./services/postgres/init:/docker-entrypoint-initdb.d

  redis:
    image: redis:7.4-alpine
    ports: ["6379:6379"]
    volumes: [redis_data:/data]

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: krishisetu
      MINIO_ROOT_PASSWORD: krishisetu_dev
    volumes: [minio_data:/data]

  api:
    build: ./apps/api
    command: uvicorn krishisetu.main:app --host 0.0.0.0 --port 8000 --reload
    volumes: [./apps/api:/app]
    environment:
      DATABASE_URL: postgresql+asyncpg://krishisetu:krishisetu_dev@postgres:5432/krishisetu
      REDIS_URL: redis://redis:6379/0
      S3_ENDPOINT: http://minio:9000
      # ... etc
    ports: ["8000:8000"]
    depends_on: [postgres, redis, minio]

  worker:
    build: ./apps/api
    command: celery -A krishisetu.workers.celery_app worker --loglevel=info -Q default,ml-realtime,external-api,notifications
    volumes: [./apps/api:/app]
    environment: # same as api
    depends_on: [postgres, redis, minio]

  ml-inference:
    build: ./apps/ml-inference
    command: uvicorn krishisetu_ml.main:app --host 0.0.0.0 --port 8001 --reload
    volumes: [./apps/ml-inference:/app]
    ports: ["8001:8001"]

  web:
    build: ./apps/web
    command: pnpm dev
    volumes: [./apps/web:/app, /app/node_modules, /app/.next]
    ports: ["3000:3000"]
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8000/api/v1

  nginx:
    image: nginx:1.27-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./services/nginx/nginx.conf:/etc/nginx/nginx.conf
    depends_on: [api, web]

  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes: [./services/observability/prometheus.yml:/etc/prometheus/prometheus.yml]

  grafana:
    image: grafana/grafana:latest
    ports: ["3001:3000"]
    volumes: [grafana_data:/var/lib/grafana]

  loki:
    image: grafana/loki:latest
    ports: ["3100:3100"]

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports: ["16686:16686"]

volumes:
  postgres_data:
  redis_data:
  minio_data:
  grafana_data:
```

A single command (`docker compose up`) brings up the entire system, giving engineers a production-like environment for development.

### 18.2 CI Pipeline (GitHub Actions)

Every PR triggers the CI pipeline:

```mermaid
graph TD
    PR[Pull Request Opened] --> LINT[Lint<br/>ruff, eslint]
    LINT --> TYPE[Type Check<br/>mypy, tsc]
    TYPE --> TEST[Tests<br/>pytest, vitest]
    TEST --> COV[Coverage<br/>>= 80% required]
    COV --> SEC[Security Scan<br/>bandit, semgrep, snypy, trufflehog]
    SEC --> BUILD[Docker Build<br/>all services]
    BUILD --> SCAN[Image Scan<br/>trivy]
    SCAN --> E2E[E2E Tests<br/>playwright]
    E2E --> LH[Lighthouse CI<br/>performance budget]
    LH --> REV[Code Review<br/>2 approvers]
    REV --> MERGE[Merge to main]

    style PR fill:#1E293B,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
    style MERGE fill:#1E40AF,color:#FFFFFF,stroke:#4CAF50,stroke-width:2px
```

Example CI workflow:

```yaml
# .github/workflows/ci.yml (abridged)
name: CI
on: [pull_request]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install uv && uv sync --all-extras
      - run: ruff check .
      - run: mypy krishisetu/
      - run: pytest tests/ --cov=krishisetu --cov-fail-under=80
      - run: bandit -r krishisetu/
      - run: semgrep --config=auto

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck
      - run: pnpm test --coverage
      - run: pnpm build

  e2e:
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d
      - run: pnpm e2e
      - run: pnpm lighthouse
```

### 18.3 CD Pipeline

- **Merge to `main`.** Triggers staging deployment via GitHub Actions. Docker images built, tagged with git SHA, pushed to container registry. Staging environment updated with new images via rolling deploy.
- **Staging verification.** Smoke tests run against staging. If pass, PR is eligible for production promotion.
- **Production promotion.** Manual GitHub Environment approval. Tagged release created (`v1.2.3`). Production deployment via rolling update with health checks. If health check fails, automatic rollback to previous version.
- **Database migrations.** Run as a separate pre-deployment step. If migration fails, deployment halts and on-call engineer is paged.

### 18.4 Environment Strategy

| Environment | Purpose | Data | Access |
|-------------|---------|------|--------|
| **Local** | Engineer's machine | Synthetic fixtures | Engineer only |
| **CI** | Automated tests | Synthetic fixtures | GitHub Actions only |
| **Staging** | Pre-production testing | Anonymized production copy | Engineering + QA |
| **Production** | Live user traffic | Real user data | Authenticated users |

### 18.5 Release Management

- **Semantic versioning.** `vMAJOR.MINOR.PATCH` per service.
- **Release notes.** Auto-generated from PR titles via `release-drafter`, manually curated for production releases.
- **Feature flags.** Unleash or Flagsmith for gradual feature rollout. Every new feature ships behind a flag, enabled for 5% of users initially, ramped to 100% over a week if metrics are healthy.
- **Rollback.** Every deployment has a one-command rollback (`kubectl rollout undo` or Docker Compose image tag revert). Database migrations are forward-only, so rollback may require a forward "reversal" migration.
- **Maintenance windows.** Scheduled for Sunday 2-4 AM IST. Communicated to users 48 hours in advance via in-app banner and SMS.

### 18.6 Incident Management

- **On-call rotation.** Engineering team rotates weekly. PagerDuty schedule.
- **Incident severity levels:**
  - **SEV-1 (Critical).** Platform down, data loss, security breach. Page on-call + leadership. Acknowledge < 5 min, resolve < 4 hr.
  - **SEV-2 (High).** Major feature broken for many users. Page on-call. Acknowledge < 15 min, resolve < 8 hr.
  - **SEV-3 (Medium).** Feature broken for some users. Slack notification. Resolve < 24 hr.
  - **SEV-4 (Low).** Minor bug, workaround exists. Ticket. Resolve < 1 week.
- **Post-mortems.** For every SEV-1 and SEV-2, a blameless post-mortem within 48 hours, documented in `docs/postmortems/`. Action items tracked to closure.
- **CERT-In reporting.** Security incidents reported to CERT-In within 6 hours per regulation.

---

## 19. Testing Strategy

Testing is not optional. Every line of production code is accompanied by tests, and CI enforces minimum 80% coverage with meaningful assertions (not just line coverage).

### 19.1 Test Pyramid

```mermaid
graph TB
    A[E2E Tests<br/>~50 tests<br/>Playwright<br/>Critical user journeys]
    B[Integration Tests<br/>~500 tests<br/>pytest + httpx<br/>API + DB + Redis]
    C[Unit Tests<br/>~5000 tests<br/>pytest + vitest<br/>Pure functions, logic]

    A --> B --> C

    style A fill:#FCE7F3,stroke:#DB2777,stroke-width:2px
    style B fill:#DBEAFE,stroke:#2563EB,stroke-width:2px
    style C fill:#E6F4EA,stroke:#4CAF50,stroke-width:2px
```

### 19.2 Backend Testing

- **Unit tests (pytest).** Test pure functions: validation, business logic, ML preprocessing. No external dependencies. Mock database, Redis, external APIs. Fast (< 1s per test).
- **Integration tests (pytest + httpx).** Test API endpoints against a real (containerized) PostgreSQL + Redis. Use test fixtures to seed data. Verify request/response, database state changes, cache invalidation.
- **Contract tests (pytest).** Verify that the API's OpenAPI spec matches actual behavior. Schemathesis generates random inputs based on the spec and verifies the API handles them correctly.
- **Load tests (Locust).** Simulate realistic user traffic (e.g., 1000 concurrent farmers submitting disease photos). Identify bottlenecks before production. Run weekly against staging.

```python
# apps/api/tests/integration/test_disease_report.py (illustrative)
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_farmer_can_submit_disease_report(
    authed_farmer_client: AsyncClient, sample_plot
):
    response = await authed_farmer_client.post(
        "/api/v1/disease-reports",
        json={"plot_id": str(sample_plot.id), "captured_at": "2026-07-19T10:00:00Z"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert "report_id" in data

@pytest.mark.asyncio
async def test_farmer_cannot_submit_report_for_other_plot(
    authed_farmer_client: AsyncClient, other_farmer_plot
):
    response = await authed_farmer_client.post(
        "/api/v1/disease-reports",
        json={"plot_id": str(other_farmer_plot.id), "captured_at": "2026-07-19T10:00:00Z"},
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_officer_can_view_any_plot_disease_report(
    authed_officer_client: AsyncClient, farmer_disease_report
):
    response = await authed_officer_client.get(
        f"/api/v1/disease-reports/{farmer_disease_report.id}"
    )
    assert response.status_code == 200
```

### 19.3 Frontend Testing

- **Unit tests (Vitest).** Test pure functions: utilities, hooks, component logic.
- **Component tests (Vitest + Testing Library).** Test component rendering and interaction with mocked API responses. Verify accessibility (axe-core).
- **E2E tests (Playwright).** Test critical user journeys: signup, plot registration, disease upload, scheme application, marketplace order. Run against full stack in Docker Compose.

### 19.4 ML Testing

- **Model evaluation tests.** Every model training run triggers an evaluation test that verifies the model meets accuracy thresholds on a held-out test set. Fails CI if metrics regress.
- **Inference service tests.** Test the inference service with sample inputs. Verify response format, latency, error handling for invalid inputs (non-image, too large, corrupt).
- **Drift detection tests.** Synthetic drift scenarios verify the drift alerting pipeline.

### 19.5 Security Testing

- **Authentication tests.** Verify every protected endpoint returns 401 without token, 403 with insufficient role.
- **Authorization tests.** Verify resource isolation — farmer A cannot read farmer B's plots, orders, etc.
- **Input validation tests.** Fuzz testing with malformed inputs (Schemathesis, hypothesis).
- **OWASP ZAP scan.** Weekly against staging.
- **Dependency scan.** Snyk on every PR.

### 19.6 Test Data Management

- **Synthetic fixtures.** Version-controlled JSON files in `tests/fixtures/`. Used for unit and integration tests.
- **Anonymized production data.** For staging. Production database dumped, PII anonymized via `pg_anonymizer`, loaded into staging weekly.
- **No PII in test data.** All test data uses fake names, fake phone numbers (555-01-XX pattern), fake Aadhaar numbers (9999XXXXXX pattern that fails Verhoeff checksum).

### 19.7 Coverage Targets

| Layer | Coverage Target |
|-------|----------------|
| Backend core (security, db, redis) | 95% |
| Backend domains (business logic) | 85% |
| Backend API routes | 80% |
| Frontend utilities/hooks | 90% |
| Frontend components | 70% |
| ML training scripts | 70% |
| ML inference service | 85% |

---

## 20. Localization Strategy

Localization is not an afterthought — it is a first-class architectural concern that affects UI design, content authoring, ML model training, and operational workflows. KrishiSetu supports ten languages from day one, with the infrastructure to add more without code changes.

### 20.1 Supported Languages

| Code | Language | Native Script | Speakers in India (millions) |
|------|----------|---------------|------------------------------|
| `en` | English | Latin | 125 |
| `hi` | Hindi | Devanagari | 615 |
| `mr` | Marathi | Devanagari | 83 |
| `ta` | Tamil | Tamil | 78 |
| `te` | Telugu | Telugu | 81 |
| `bn` | Bengali | Bengali | 97 |
| `kn` | Kannada | Kannada | 44 |
| `gu` | Gujarati | Gujarati | 56 |
| `pa` | Punjabi | Gurmukhi | 33 |
| `ml` | Malayalam | Malayalam | 37 |

Combined coverage: ~99% of Indian population.

### 20.2 Localization Architecture

- **String catalog.** All UI strings in `apps/web/src/messages/<locale>.json`. Loaded at build time (SSG) or runtime (SSR) based on the user's locale.
- **Translation management.** Crowdin or Lokalise for translator workflow. Source strings in English, translations reviewed by certified translators.
- **Context for translators.** Every string includes: source file location, screenshot of UI context, max length constraint, pluralization rules.
- **Pluralization.** All strings with counts use ICU MessageFormat: `{count, plural, one {# plot} other {# plots}}`.
- **Date/time formatting.** `Intl.DateTimeFormat` with locale-specific formatting. Indian convention: DD/MM/YYYY.
- **Number formatting.** `Intl.NumberFormat` with Indian numbering system (lakh, crore). Currency in ₹ with Indian symbol.
- **Unit localization.** Toggle between hectares and acres, kilograms and quintals, Celsius and Fahrenheit (default Celsius).

### 20.3 Content Localization

Beyond UI strings, content (disease descriptions, treatment recommendations, scheme details) must be localized:

- **Disease catalog.** Each disease has descriptions in all 10 languages, authored by agricultural experts in each language (not machine-translated). Critical for accuracy.
- **Scheme details.** Pulled from government APIs in English, translated by certified translators for the 9 Indian languages. Updates tracked and re-translated within 7 days of source change.
- **Advisory content.** Weather advisories and disease alerts generated from templates with localized variables.

### 20.4 Voice Localization

- **ASR.** Whisper large-v3 fine-tuned on Indic speech. Handles all 10 languages.
- **TTS.** Azure Cognitive Services Speech API, with locale-specific voices:
  - `hi-IN`: Madhur (male), Swara (female)
  - `mr-IN`: Aarohi (female)
  - `ta-IN`: Pallavi (female), Prem (male)
  - `te-IN`: Shruti (female), Mohan (male)
  - `bn-IN`: Bashkar (male), Tanishaa (female)
  - `kn-IN`: Gagan (male), Sapna (female)
  - `gu-IN`: Niranjan (male), Aarohi (female)
  - `pa-IN`: Vaani (female)
  - `ml-IN`: Midhun (male), Sooraj (male)
- **Voice gender preference.** User can select preferred voice gender in settings.

### 20.5 Quality Assurance

- **In-context review.** Translators review strings in the actual UI (via Lokalise In-Context), not just spreadsheets.
- **Linguistic QA.** Native speakers in each language perform UI walkthroughs before each release.
- **Continuous localization.** New strings are translated within 48 hours of being added to the codebase.

---

## 21. 12-Month Development Roadmap

The roadmap is structured as four phases of three months each, with each phase delivering a coherent increment of platform capability. The phases are designed so that each one independently delivers value to farmers — there is no "big bang" release where the platform only becomes useful at the end.

### 21.1 Phase 1 (Months 1-3) — Foundation

**Theme.** Identity, profile, and the core agricultural intelligence loop (disease identification).

**Deliverables:**
- Project scaffolding: monorepo, FastAPI app, Next.js app, Docker Compose, CI/CD
- Identity & Auth module: phone OTP signup, JWT auth, refresh tokens, RBAC framework
- Aadhaar e-KYC integration (OTP flow)
- Farmer profile & plot registration with map boundary drawing
- Crop Disease Identification module: YOLOv8 fine-tuned on PlantVillage + PlantDoc + custom dataset
- ML inference service with disease classifier model
- Basic frontend: auth pages, dashboard, plot management, disease report submission
- Localization infrastructure (EN + HI initial)
- Observability stack: Loki, Prometheus, Grafana, Jaeger
- Test infrastructure: pytest, vitest, playwright, Locust
- Documentation: README, ADRs, onboarding guide

**Phase 1 Exit Criteria:**
- 100 farmers can sign up, verify Aadhaar, register plots, submit disease photos, and receive accurate diagnoses
- End-to-end latency (disease upload → result) P95 < 15 seconds
- Top-1 accuracy on held-out test set ≥ 90%
- All SLOs met in load test simulating 1000 concurrent users
- Security audit (internal) passes with no SEV-1/SEV-2 findings

### 21.2 Phase 2 (Months 4-6) — Intelligence Expansion

**Theme.** Soil health, weather intelligence, and satellite NDVI monitoring — transforming the platform from a diagnostic tool into a continuous intelligence platform.

**Deliverables:**
- Soil Health & Weather module: IMD integration, OpenWeatherMap fallback, ISRIC SoilGrids auto-population, Soil Health Card import
- Real-time weather dashboard with 7-day forecast and historical trends
- Extreme weather alert system (SMS, push, voice)
- Satellite NDVI module: Sentinel Hub integration, NDVI computation pipeline, plot-level NDVI maps with color scale legend (matching reference UI)
- NDVI time series charts and trend analysis
- District NDVI heatmap for agricultural officers
- Anomaly detection: NDVI drop alerts linked to disease report flow
- Multilingual expansion: add MR, TA, TE, BN (5 total)
- Voice ASR (Whisper) and TTS (Azure) integration for first 5 languages
- Cross-module workflow: Disease-to-Claim (auto-suggest insurance claim if disease detected on insured plot)

**Phase 2 Exit Criteria:**
- 10,000 registered farmers
- NDVI observations refreshed weekly for all registered plots
- Weather data freshness < 1 hour
- Voice query end-to-end P95 < 8 seconds in 5 languages
- All Phase 1 functionality continues to meet SLOs

### 21.3 Phase 3 (Months 7-9) — Transactions

**Theme.** Insurance/PMFBY and marketplace — enabling farmers to take action based on intelligence.

**Deliverables:**
- Insurance & PMFBY module: product catalog, enrollment, policy management, claim filing
- PMFBY portal API integration (with fallback to PDF generation for offline submission)
- Claim evidence workflow: auto-attach NDVI history, disease reports, weather events
- Insurer dashboard: claim review with integrated evidence view
- Marketplace module: supplier onboarding, product catalog, cart, orders
- Payment integration: UPI (primary), Razorpay (secondary), escrow
- Order state machine with delivery tracking
- Supplier dashboard: catalog management, order fulfillment, inventory
- Multilingual expansion: add KN, GU, PA, ML (9 total + EN = 10)
- Voice query expansion to all 10 languages

**Phase 3 Exit Criteria:**
- 100,000 registered farmers
- 10,000 policies enrolled
- 50,000 orders placed
- Marketplace GMV > ₹1 crore
- Claim approval rate > 70% (vs. industry avg 50%)
- All 10 languages fully localized and voice-enabled

### 21.4 Phase 4 (Months 10-12) — Govt Integration & Scale

**Theme.** Government schemes discovery, scalability hardening, and production-grade operations.

**Deliverables:**
- Govt Schemes module: scheme catalog, eligibility engine, application workflow
- PM-Kisan integration: beneficiary status, installment tracking
- KCC (Kisan Credit Card) integration: eligibility check, application routing
- DigiLocker integration: document vault
- Eligibility rules engine with YAML-based rule definitions
- Officer dashboard: application review workflow, district analytics
- Scalability hardening: load test to 1M DAU, optimize bottlenecks
- Disaster recovery: cross-region replication, backup drills
- Performance optimization: query optimization, cache tuning, CDN edge caching
- Public API release (with developer portal) for third-party integrations
- Mobile PWA polish: offline mode, push notifications, home screen install
- Security audit (external third-party)
- DPDP Act compliance audit

**Phase 4 Exit Criteria:**
- 1,000,000 registered farmers
- 100,000 daily active users
- All SLOs met under 5x peak load
- External security audit passes with no SEV-1/SEV-2 findings
- DPDP Act compliance certified
- Platform certified as "Production-Ready" by GoI review

### 21.5 Roadmap Visualization

```mermaid
gantt
    title KrishiSetu 12-Month Development Roadmap
    dateFormat YYYY-MM-DD
    axisFormat %b %Y

    section Phase 1 - Foundation
    Project Scaffolding          :p1a, 2026-08-01, 14d
    Identity & Auth              :p1b, 2026-08-15, 30d
    Aadhaar e-KYC                :p1c, 2026-09-01, 21d
    Profile & Plots              :p1d, 2026-09-15, 30d
    Disease ID (ML)              :p1e, 2026-09-01, 45d
    Frontend Dashboards          :p1f, 2026-09-15, 30d
    Observability Stack          :p1g, 2026-10-01, 21d

    section Phase 2 - Intelligence
    Soil & Weather               :p2a, 2026-11-01, 45d
    IMD Integration              :p2b, 2026-11-01, 30d
    Sentinel-2 NDVI              :p2c, 2026-11-15, 45d
    NDVI Heatmaps                :p2d, 2026-12-15, 21d
    Voice ASR/TTS (5 langs)      :p2e, 2026-12-01, 45d
    Disease-to-Claim Flow        :p2f, 2027-01-01, 21d

    section Phase 3 - Transactions
    Insurance & PMFBY            :p3a, 2027-02-01, 45d
    Claim Evidence Workflow      :p3b, 2027-02-15, 30d
    Marketplace Catalog          :p3c, 2027-02-15, 30d
    Payments (UPI + Razorpay)    :p3d, 2027-03-01, 30d
    Order State Machine          :p3e, 2027-03-15, 30d
    Voice (10 langs)             :p3f, 2027-03-01, 30d

    section Phase 4 - Scale
    Govt Schemes Catalog         :p4a, 2027-05-01, 30d
    Eligibility Engine           :p4b, 2027-05-15, 30d
    PM-Kisan + KCC + DigiLocker  :p4c, 2027-06-01, 30d
    Scalability Hardening        :p4d, 2027-05-01, 60d
    External Security Audit      :p4e, 2027-06-15, 21d
    DPDP Compliance              :p4f, 2027-06-15, 30d
```

### 21.6 Team Composition

| Role | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|------|---------|---------|---------|---------|
| Tech Lead / Architect | 1 | 1 | 1 | 1 |
| Backend Engineers | 2 | 3 | 3 | 4 |
| Frontend Engineers | 1 | 2 | 2 | 3 |
| ML Engineers | 1 | 2 | 2 | 2 |
| DevOps Engineer | 1 | 1 | 1 | 1 |
| QA Engineer | 1 | 1 | 2 | 2 |
| UI/UX Designer | 1 | 1 | 1 | 1 |
| Product Manager | 1 | 1 | 1 | 1 |
| Agronomy Consultant (part-time) | 1 | 1 | 1 | 1 |
| Localization Lead (part-time) | 0 | 1 | 1 | 1 |
| **Total** | **10** | **13** | **14** | **17** |

---

## 22. Risk Assessment & Mitigations

The following risks have been identified through systematic analysis. Each risk has a probability (Low/Medium/High), impact (Low/Medium/High), and mitigation strategy.

### 22.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **ML model accuracy below threshold on Indian crop diseases** | Medium | High | Invest in custom dataset collection (10K images) upfront; collaborate with ICAR agricultural universities; if accuracy below 90%, ship with "low confidence" UX that prompts officer review |
| **UIDAI Aadhaar API rate limits or downtime** | High | Medium | Implement graceful degradation — platform usable without Aadhaar verification for non-KYC features; cache verification status; queue API calls during high traffic |
| **Sentinel-2 cloud cover obscuring plot imagery** | High | Medium | Multi-date compositing — use best cloud-free image from last 14 days; fallback to Landsat 8/9 when Sentinel-2 unavailable; clearly show observation date in UI |
| **Database write contention under peak load** | Medium | High | Read replicas for read traffic; connection pooling via PgBouncer; partition hot tables; batch writes where possible |
| **ML inference latency spikes under concurrent load** | Medium | High | GPU autoscaling on inference service; request batching; circuit breaker with fallback to "service busy" message; queue-based async pattern for non-urgent requests |
| **Frontend bundle size growth degrading performance** | Medium | Medium | CI-enforced bundle size budget; code splitting per route; dynamic imports for heavy components (maps, charts); tree-shaking audit per release |

### 22.2 External / Dependency Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Government API spec changes without notice** | Medium | High | Abstract all govt APIs behind adapter layer; monitor API health daily; alert on schema changes; maintain PDF fallback for critical workflows |
| **PMFBY portal doesn't expose public API** | High | Medium | Build adapter to scrape portal (with permission); fall back to PDF generation for offline submission; insurer-side integration as alternative |
| **SMS gateway outage (OTP delivery failure)** | Low | High | Multi-vendor SMS gateway (MSG91 primary, Karix backup); automatic failover; retry queue; voice OTP as last resort |
| **Azure TTS rate limits during peak** | Medium | Medium | Cache common TTS responses; fallback to Coqui TTS self-hosted; degrade gracefully (text response if TTS unavailable) |
| **OpenStreetMap tile server downtime** | Low | Low | Multiple tile providers (OSM, Mapbox, ESRI) with runtime fallback |

### 22.3 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Data breach of Aadhaar / PII** | Low | Critical | Encryption at rest and in transit; strict RBAC; row-level security; audit log; no PII in logs; annual pentest; bug bounty program |
| **Insider threat (engineer with prod access)** | Low | Critical | Principle of least privilege; JIT (just-in-time) access via Vault; all access logged and reviewed; no standing prod access for engineers |
| **DDoS attack during scheme enrollment window** | Medium | High | Cloudflare DDoS protection; rate limiting at multiple layers; auto-scaling; queue-based request handling for non-urgent traffic |
| **Database corruption requiring restore** | Low | Critical | Daily backups with 30-day retention; PITR via WAL archiving (7-day); quarterly restore drills; cross-region backup replication |
| **ML model drift (degrading accuracy over time)** | High | Medium | Continuous drift monitoring (PSI); monthly retraining cadence; farmer feedback loop (thumbs up/down on predictions); model version A/B testing |

### 22.4 Product / Adoption Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Farmer digital literacy barrier** | High | High | Voice-first interface in 10 languages; PWA installable on low-end Android; offline mode; partnerships with FPOs (Farmer Producer Organizations) for on-ground onboarding |
| **Slow user acquisition (chicken-and-egg: no users → no data → no value)** | Medium | High | Phase 1 ships disease ID (high immediate value) before network-effect features (marketplace); partner with state govts for bulk onboarding; referral incentives |
| **Supplier reluctance to join marketplace** | Medium | Medium | Zero commission for first 6 months; verified supplier badge as trust signal; bulk onboarding via distributor networks |
| **Competing govt platforms (UMANG, etc.) duplicating features** | Medium | Medium | Differentiate through superior UX, ML-powered intelligence, and unified workflow; integrate with (not compete against) govt platforms via APIs |
| **Regulatory changes (new data protection rules)** | Medium | Medium | Architect for compliance from day one (DPDP Act); modular PII handling; legal counsel on retainer |

### 22.5 Risk Monitoring

- **Risk register.** Maintained in `docs/risks/REGISTER.md`. Reviewed monthly by tech lead and product manager.
- **Risk burn-down.** Each risk has an owner and a mitigation plan with milestones. Status tracked in the register.
- **Incident-driven risk updates.** Every incident triggers a risk register review — were there risks we missed? Were mitigations inadequate?

---

## 23. Recommendations & Future Work

This section captures recommendations that go beyond the current scope but should inform architectural decisions made today, so the platform can accommodate them without rewrites. It also highlights areas where the team should pay particular attention during implementation.

### 23.1 What to Pay Extra Attention To

#### 23.1.1 The Aadhaar Integration is the Single Most Critical Path

The Aadhaar e-KYC integration has the highest complexity-to-value ratio in the entire platform. It involves: cryptographic encryption of requests, UIDAI's specific XML/JSON protocols, rate limits, audit requirements, and legal compliance with the Aadhaar Act. Get this right first. Recommendations:

- **Read the UIDAI authentication API specification end-to-end before writing any code.** The spec is dense but every detail matters (encryption padding, request timeout, OTP retry policy).
- **Build a sandbox environment first.** UIDAI provides a sandbox for testing. Use it exhaustively — simulate every error case (wrong OTP, expired OTP, network timeout, invalid Aadhaar, biometric mismatch).
- **Invest in audit logging from day one.** Every Aadhaar API call must be logged with timestamp, transaction ID, request type, response status, and (masked) response data. This is a legal requirement.
- **Plan for Aadhaar API downtime.** The platform must degrade gracefully when UIDAI is unavailable. Non-KYC features (disease ID, weather, NDVI) must continue to work.

#### 23.1.2 ML Model Quality is the Platform's Reputation

If the disease classifier misdiagnoses frequently, farmers will lose trust in the entire platform — not just the disease feature. Recommendations:

- **Invest disproportionately in the custom Indian crop disease dataset.** 10,000 well-labeled images is the floor, not the ceiling. Partner with ICAR research stations and agricultural universities (Punjab Agricultural University, Tamil Nadu Agricultural University, etc.) for high-quality labeled data.
- **Build the feedback loop from day one.** Every prediction should have a "Was this correct?" feedback mechanism. Use this data to identify model weaknesses and prioritize data collection for underperforming classes.
- **Calibrate confidence scores.** A 90% confidence prediction should be correct 90% of the time. Apply temperature scaling and validate calibration on a held-out set.
- **Be transparent about limitations.** The UI should clearly say "This is an AI prediction. For confirmation, consult an agricultural officer." This manages expectations and creates an escalation path for uncertain cases.

#### 23.1.3 The Plot Boundary is the Spatial Anchor — Get It Right

Every geographic feature (NDVI, weather, district aggregation) depends on the plot boundary being accurate. If a farmer draws a sloppy polygon, every downstream computation is wrong. Recommendations:

- **Make boundary drawing as easy as possible.** Auto-suggest the boundary based on satellite imagery (this is a Phase 2 enhancement). For Phase 1, provide clear instructions and a tutorial.
- **Validate the boundary against the declared area.** If farmer says "2 hectares" but draws a polygon that's 5 hectares, prompt for confirmation.
- **Allow boundary revision.** Farmer should be able to redraw the boundary, with the old boundary archived. NDVI history should be recomputed against the new boundary if significantly different.
- **Snap boundaries to visible features.** Use OSM land parcels or cadastral boundaries (where available) to snap drawn polygons to actual field boundaries.

#### 23.1.4 The Audit Log is Non-Negotiable

Every state-changing action — plot create, disease report submit, claim file, order place, scheme application — must be in the audit log with full before/after state. This is essential for: regulatory compliance, dispute resolution (farmer says "I didn't apply for this scheme" — audit log proves otherwise), security investigation, and analytics. Recommendations:

- **Build the audit log infrastructure in Phase 1, not as an afterthought.** Retrofitting audit logging to a system that didn't have it is painful.
- **Use append-only tables with database-level write protection.** Even a DBA should not be able to silently modify audit entries.
- **Include the request ID from the API call in every audit entry.** This enables pivoting from audit log to logs to traces.
- **Hash the after_state.** This enables tamper detection — if anyone modifies the actual data, the hash won't match.

#### 23.1.5 Performance on Low-End Devices

The reference UI is clean and professional, but it must render acceptably on a ₹6,000 Android phone with 2GB RAM on a 2G connection. Recommendations:

- **Test on real low-end devices.** Emulators lie. Get a few real low-end Android devices for testing.
- **Aggressive code splitting.** The initial dashboard load should be < 100KB JS. Lazy-load everything else.
- **Server-rendered initial paint.** RSC delivers real HTML, not a loading spinner. Critical for perceived performance.
- **Image optimization.** `next/image` with responsive sizes and WebP. Crop photos should be served as progressive JPEG at multiple resolutions.
- **Service worker for offline.** Previously-visited pages should work offline. Critical for rural users with intermittent connectivity.

### 23.2 Future Enhancements (Phase 5+)

These are not in the 12-month roadmap but should be architecturally accommodated:

#### 23.2.1 IoT Sensor Integration

Soil moisture sensors, weather stations, and drip irrigation controllers from third-party hardware vendors. The API should have a generic `/sensors/{id}/readings` endpoint that accepts standardized payloads. Recommendations:
- Build a generic sensor ingestion pipeline in Phase 2 architecture (even if no sensors integrated yet).
- Adopt the FIWARE data model for sensor payloads — it's an open standard for IoT in agriculture.

#### 23.2.2 Crop Yield Prediction

ML model that predicts yield at harvest based on sowing date, crop variety, weather, NDVI trend, soil test results, and historical yields. Recommendations:
- Start collecting yield data in Phase 2 (ask farmers for yield at harvest time, with optional photo evidence).
- Train the first yield prediction model in Phase 4 or 5, once enough historical data accumulates.

#### 23.2.3 Peer-to-Peer Farmer Network

Farmers helping farmers — Q&A forum, equipment sharing, labor exchange. Recommendations:
- Design the `users` table with a `connections` field from day one (JSON array of connected user IDs) to support social features later.
- Use a separate `social` schema for forum posts, messages, etc. to keep the core transactional schema clean.

#### 23.2.4 Mobile App (Native)

PWA covers most use cases, but a native app may be needed for: background location tracking (for officers doing field visits), native camera integration (faster disease photo capture), offline-first with local database sync. Recommendations:
- The API is already mobile-friendly (REST + JWT). A native app can be built later without API changes.
- If native app is pursued, use React Native or Flutter for code sharing with the web app.

#### 23.2.5 Blockchain for Provenance

For high-value supply chains (organic produce, export-quality grains), blockchain-based provenance tracking from farm to consumer. Recommendations:
- Not in scope for now, but the marketplace data model (orders, shipments, payments) is already structured to support a blockchain ledger layer in the future.

#### 23.2.6 Multilingual Voice Assistant (Conversational)

Beyond single-turn voice queries, a multi-turn conversational assistant that can handle complex requests ("What's the weather? And should I irrigate today? And what's the price of my crop at the mandi?"). Recommendations:
- The NLU intent classification in Phase 2 lays the groundwork. Multi-turn conversation requires dialog state management — adopt Rasa or build a custom state machine.

#### 23.2.7 Carbon Credit Tracking

As carbon markets mature, farmers may earn carbon credits for sustainable practices (no-till, cover cropping, agroforestry). KrishiSetu could track practices and issue verifiable credits. Recommendations:
- Add a `farming_practices` field to `crop_cycles` table in Phase 2 to start collecting data, even before carbon credit tracking is built.

### 23.3 Strategic Recommendations

#### 23.3.1 Partner with State Governments for Onboarding

User acquisition is the hardest problem. A direct-to-farmer approach is slow and expensive. Recommendations:
- Prioritize partnership with 2-3 progressive state governments (Maharashtra, Karnataka, Tamil Nadu) for bulk farmer onboarding via their agriculture departments.
- Co-brand the platform with state govt (e.g., "Maharashtra KrishiSetu") to leverage trust.
- Integrate with state-specific schemes and land record portals (Bhumi Abhilekh, Bhoomi, etc.) as a value-add for state partners.

#### 23.3.2 Build a Data Moat

The platform's long-term defensibility comes from its data — plot boundaries, crop cycles, disease reports with photos, NDVI history, yield data. This dataset is unique and valuable. Recommendations:
- Treat data quality as a first-class metric. Track completeness (what % of farmer profiles have Aadhaar verified, plot boundaries drawn, soil tests imported).
- Use the data to train better ML models, creating a virtuous cycle: more users → more data → better models → more users.
- Explore data licensing to researchers and policymakers (with farmer consent and anonymization) as a revenue stream.

#### 23.3.3 Establish an Independent Advisory Board

For a platform handling farmer data, agricultural decisions, and financial transactions, an independent advisory board provides governance and trust. Recommendations:
- Include agricultural scientists (ICAR), data privacy experts, farmer representatives, and government officials.
- Board reviews major product decisions, especially ML model deployments that affect farmer outcomes.
- Publish an annual transparency report.

#### 23.3.4 Plan for Open API from Day One

The platform's value multiplies when third parties (FPOs, agri-tech startups, researchers, govt agencies) build on top of it. Recommendations:
- The API is already RESTful and versioned. Maintain a public developer portal from Phase 4.
- Define rate limits for third-party developers (different from farmer-facing limits).
- Provide SDKs in Python, JavaScript, and Hindi/Bengali documentation.

#### 23.3.5 Invest in Developer Experience

Engineer productivity is the bottleneck for platform evolution. Recommendations:
- Local dev environment must work with a single command (`docker compose up`). No multi-day setup.
- CI must be fast (< 10 minutes for full pipeline). Parallelize aggressively.
- Documentation must be in the repo, version-controlled, and kept up to date. Stale docs are worse than no docs.
- Onboard new engineers in < 1 day. Write an onboarding guide that walks through a complete change (PR, CI, merge, deploy).

---

## 24. Appendix: Glossary & References

### 24.1 Glossary

| Term | Definition |
|------|------------|
| **Aadhaar** | 12-digit unique identity number issued by UIDAI to all Indian residents |
| **ASR** | Automatic Speech Recognition — converting spoken audio to text |
| **CDN** | Content Delivery Network — geographically distributed cache of static assets |
| **Celery** | Python distributed task queue library |
| **C4 Model** | Context, Container, Component, Code — a way to visualize software architecture |
| **DPDP Act** | Digital Personal Data Protection Act, 2023 — India's data protection law |
| **e-KYC** | Electronic Know Your Customer — identity verification via Aadhaar |
| **ER Diagram** | Entity-Relationship Diagram — visualizes database schema |
| **FCM** | Firebase Cloud Messaging — push notification service |
| **FPO** | Farmer Producer Organization — collective of farmers for marketing and input procurement |
| **HPA** | Horizontal Pod Autoscaler — Kubernetes component that scales pods based on metrics |
| **ICAR** | Indian Council of Agricultural Research |
| **IMD** | India Meteorological Department |
| **i18n** | Internationalization — designing software for multiple locales |
| **Jaeger** | Distributed tracing system |
| **JWT** | JSON Web Token — stateless authentication token |
| **KCC** | Kisan Credit Card — government credit facility for farmers |
| **LCP** | Largest Contentful Paint — Core Web Vital metric |
| **Loki** | Log aggregation system by Grafana Labs |
| **MLflow** | Open-source ML model tracking and registry |
| **MOS** | Mean Opinion Score — voice quality metric |
| **MVP** | Minimum Viable Product |
| **NDVI** | Normalized Difference Vegetation Index — measure of vegetation health from satellite imagery |
| **NIR** | Near-Infrared (satellite band) |
| **NLU** | Natural Language Understanding — extracting intent and entities from text |
| **OWASP** | Open Web Application Security Project |
| **PMFBY** | Pradhan Mantri Fasal Bima Yojana — government crop insurance scheme |
| **PM-Kisan** | Pradhan Mantri Kisan Samman Nidhi — income support scheme for farmers |
| **PostGIS** | Spatial database extension for PostgreSQL |
| **PROM** | Prometheus — monitoring and alerting system |
| **PSI** | Population Stability Index — metric for ML model drift |
| **RBAC** | Role-Based Access Control |
| **RSC** | React Server Components — Next.js 14 feature for server-rendered React |
| **SLO** | Service Level Objective — target for service reliability |
| **STRIDE** | Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege — threat model |
| **SHC** | Soil Health Card — government scheme providing soil test results to farmers |
| **TTS** | Text-to-Speech — converting text to spoken audio |
| **UIDAI** | Unique Identification Authority of India — issuer of Aadhaar |
| **UPI** | Unified Payments Interface — Indian real-time payment system |
| **WER** | Word Error Rate — ASR accuracy metric |

### 24.2 References

#### Standards & Specifications

- **FastAPI Documentation** — https://fastapi.tiangolo.com/
- **Next.js 14 Documentation** — https://nextjs.org/docs
- **PostgreSQL 16 Documentation** — https://www.postgresql.org/docs/16/
- **PostGIS Documentation** — https://postgis.net/documentation/
- **OpenAPI Specification 3.1** — https://spec.openapis.org/oas/v3.1.0
- **OWASP Top 10 (2021)** — https://owasp.org/Top10/
- **OWASP ASVS (Application Security Verification Standard)** — https://owasp.org/www-project-application-security-verification-standard/
- **NIST SP 800-63B** — Digital Identity Guidelines (authentication)
- **DPDP Act 2023** — https://www.meity.gov.in/data-protection-framework
- **Aadhaar Act 2016** — https://uidai.gov.in/images/act/The_Aadhaar_Act_2016.pdf

#### Government APIs & Resources

- **UIDAI Authentication API** — https://uidai.gov.in/developers/aadhaar-authentication-api-specification.html
- **IMD Weather Services** — https://mausam.imd.gov.in/
- **PM-Kisan Portal** — https://pmkisan.gov.in/
- **PMFBY Portal** — https://pmfby.gov.in/
- **Soil Health Card Portal** — https://soilhealth.dac.gov.in/
- **eNAM (National Agriculture Market)** — https://enam.gov.in/
- **DigiLocker API** — https://docs.digilocker.gov.in/
- **Bhulekh (Land Records, state portals)** — e.g., https://bhumiabhilekh.maharashtra.gov.in/
- **Sentinel Hub** — https://www.sentinel-hub.com/
- **Copernicus Open Access Hub** — https://scihub.copernicus.eu/
- **ISRIC SoilGrids** — https://www.isric.org/explore/soilgrids

#### Datasets & ML Resources

- **PlantVillage Dataset** — https://www.kaggle.com/datasets/abdallahalidev/plantvillage-dataset
- **PlantDoc Dataset** — https://github.com/pratikkayal/PlantDoc-Dataset
- **IndicSUPERB (Speech)** — https://ai4bharat.iitm.ac.in/indic-superb/
- **IndicGLUE (NLP)** — https://ai4bharat.iitm.ac.in/indic-glue/
- **MuRIL Model** — https://huggingface.co/google/muril-base-cased
- **Whisper Model** — https://huggingface.co/openai/whisper-large-v3
- **YOLOv8 (Ultralytics)** — https://docs.ultralytics.com/

#### Operational Tools

- **Prometheus** — https://prometheus.io/docs/
- **Grafana Loki** — https://grafana.com/docs/loki/latest/
- **Jaeger** — https://www.jaegertracing.io/docs/
- **OpenTelemetry** — https://opentelemetry.io/docs/
- **Celery** — https://docs.celeryq.dev/
- **MLflow** — https://mlflow.org/docs/latest/index.html
- **DVC** — https://dvc.org/doc
- **Locust** — https://docs.locust.io/
- **Playwright** — https://playwright.dev/
- **Vitest** — https://vitest.dev/

#### Architectural References

- **C4 Model** — https://c4model.com/
- **The Twelve-Factor App** — https://12factor.net/
- **Google SRE Book** — https://sre.google/sre-book/table-of-contents/
- **Microsoft Azure Architecture Center** — https://learn.microsoft.com/en-us/azure/architecture/

---

*End of Architecture & Engineering Plan. This document is the comprehensive blueprint for KrishiSetu's development. The next step is engineering execution against this plan, beginning with Phase 1: project scaffolding, identity & authentication, and the crop disease identification ML pipeline.*

