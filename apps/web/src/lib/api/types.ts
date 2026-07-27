/**
 * Shared API types — mirrors backend Pydantic schemas.
 *
 * Keep these in sync with the backend schemas in apps/api/krishisetu/domains/.
 */

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export type UserRole = "farmer" | "agri_officer" | "supplier" | "insurer" | "admin";

export interface UserPublic {
  id: string;
  phone: string;
  phone_verified: boolean;
  email: string | null;
  email_verified: boolean;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  preferred_language: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserPublic;
}

// ---------------------------------------------------------------------------
// Consent (Phase F)
// ---------------------------------------------------------------------------

export type ConsentPurpose =
  | "identity_verification"
  | "disease_diagnosis"
  | "weather_advisory"
  | "ndvi_monitoring"
  | "insurance_processing"
  | "marketplace_transactions"
  | "scheme_matching"
  | "voice_processing"
  | "communication"
  | "research_anonymized"
  | "service_improvement";

export type ConsentStatus = "granted" | "withdrawn" | "expired";

export interface ConsentRecord {
  id: string;
  purpose: ConsentPurpose;
  status: ConsentStatus;
  notice_version: string;
  granted_at: string;
  withdrawn_at: string | null;
  expires_at: string | null;
  withdrawal_reason: string | null;
}

export interface ConsentStatusResponse {
  granted: ConsentPurpose[];
  withdrawn: ConsentPurpose[];
  not_yet_asked: ConsentPurpose[];
}

// ---------------------------------------------------------------------------
// Privacy / DSR (Phase F)
// ---------------------------------------------------------------------------

export type DSRType = "access" | "correction" | "erasure" | "portability" | "restriction";
export type DSRStatus =
  | "submitted"
  | "acknowledged"
  | "in_review"
  | "processing"
  | "awaiting_verification"
  | "completed"
  | "rejected"
  | "withdrawn";

export interface DataSubjectRequest {
  id: string;
  user_id: string;
  request_type: DSRType;
  status: DSRStatus;
  description: string | null;
  requested_changes: Record<string, string> | null;
  export_url: string | null;
  export_expires_at: string | null;
  submitted_at: string;
  acknowledged_at: string | null;
  completed_at: string | null;
  due_at: string;
  assigned_to: string | null;
  resolution_notes: string | null;
  rejection_reason: string | null;
}

// ---------------------------------------------------------------------------
// Grievances (Phase F)
// ---------------------------------------------------------------------------

export type GrievanceStatus =
  | "filed"
  | "acknowledged"
  | "in_review"
  | "resolved"
  | "escalated"
  | "rejected";

export interface Grievance {
  id: string;
  grievance_number: string;
  user_id: string;
  category: string;
  subject: string;
  description: string;
  status: GrievanceStatus;
  filed_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  due_at: string;
  assigned_to: string | null;
  resolution: string | null;
  escalation_reference: string | null;
}

// ---------------------------------------------------------------------------
// Audit log (Phase F admin)
// ---------------------------------------------------------------------------

export type AuditOutcome = "success" | "failure" | "denied" | "error";

export interface AuditLog {
  id: string;
  action: string;
  outcome: AuditOutcome;
  actor_id: string | null;
  actor_role: string | null;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  request_id: string | null;
  occurred_at: string;
}

export interface AuditLogListResponse {
  total: number;
  limit: number;
  offset: number;
  logs: AuditLog[];
}

export interface AuditStatsResponse {
  hours: number;
  total_events: number;
  by_action: Record<string, number>;
  by_action_outcome: Record<string, Record<string, number>>;
}

// ---------------------------------------------------------------------------
// Generic
// ---------------------------------------------------------------------------

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

// ---------------------------------------------------------------------------
// Disease (Phase F)
// ---------------------------------------------------------------------------

export interface DiseasePrediction {
  disease_slug: string;
  confidence: number;
  is_reliable: boolean;
  disease?: {
    name_en: string;
    disease_type: string;
  };
}

export interface DiseaseReport {
  id: string;
  user_id: string;
  image_url: string;
  status: "pending" | "processing" | "completed" | "failed" | "officer_review" | "reviewed";
  prediction: DiseasePrediction | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface DiseaseReportListResponse {
  reports: DiseaseReport[];
  total: number;
  limit: number;
  offset: number;
}

export interface DiseaseReportStats {
  total_reports: number;
  completed: number;
  pending: number;
  needs_review: number;
}

// ---------------------------------------------------------------------------
// NDVI (Phase F)
// ---------------------------------------------------------------------------

export interface NDVIObservation {
  id: string;
  plot_id: string;
  observed_at: string;
  ndvi_mean: number;
  ndvi_anomaly: boolean;
  source: string;
}

export interface NDVIAnomalyAlert {
  id: string;
  plot_id: string;
  alert_date: string;
  severity: "low" | "medium" | "high";
  z_score: number;
  acknowledged: boolean;
}

// ---------------------------------------------------------------------------
// Plots (Phase F)
// ---------------------------------------------------------------------------

export interface PlotListItem {
  id: string;
  user_id: string;
  name: string;
  area_hec: number;
  crop_type: string | null;
  soil_type: string | null;
  created_at: string;
}

export interface PlotListResponse {
  plots: PlotListItem[];
  total: number;
}

export interface PlotStatsResponse {
  total_plots: number;
  total_area_hec: number;
}

export interface PlotResponse extends PlotListItem {
  boundary_geojson: GeoJSONPolygon | null;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Soil / Weather (Phase F)
// ---------------------------------------------------------------------------

export interface SoilTestRecord {
  id: string;
  plot_id: string;
  test_date: string;
  ph: number | null;
  organic_carbon: number | null;
  nitrogen: number | null;
  phosphorus: number | null;
  potassium: number | null;
}

export interface WeatherForecast {
  day: string;
  temp_max: number;
  temp_min: number;
  rainfall_mm: number;
  humidity: number;
}

export interface WeatherAdvisory {
  generated_at: string;
  summary: string;
  forecast: WeatherForecast[];
}

export interface SoilTestListResponse {
  tests: SoilTestRecord[];
  total: number;
}

// ---------------------------------------------------------------------------
// Insurance (Phase F)
// ---------------------------------------------------------------------------

export interface InsurancePolicy {
  id: string;
  policy_number: string;
  scheme_name: string;
  coverage_amount_inr: number;
  premium_inr: number;
  status: string;
  start_date: string;
  end_date: string;
  created_at: string;
}

export interface InsuranceClaim {
  id: string;
  policy_id: string;
  claim_number: string;
  incident_date: string;
  amount_inr: number;
  status: "submitted" | "approved" | "rejected" | "paid";
  created_at: string;
}

export interface ClaimListResponse {
  claims: InsuranceClaim[];
  total: number;
}

export interface PolicyListResponse {
  policies: InsurancePolicy[];
  total: number;
}

// ---------------------------------------------------------------------------
// Marketplace (Phase F)
// ---------------------------------------------------------------------------

export interface Product {
  id: string;
  name: string;
  category: string;
  price_inr: number;
  unit: string;
  image_url: string | null;
  seller_name: string;
}

export interface Order {
  id: string;
  order_number: string;
  items: Product[];
  total_inr: number;
  status: string;
  created_at: string;
}

export interface OrderListResponse {
  orders: Order[];
  total: number;
}

export interface MarketplaceStats {
  total_orders: number;
  active_listings: number;
}

// ---------------------------------------------------------------------------
// Schemes (Phase F)
// ---------------------------------------------------------------------------

export interface GovtScheme {
  id: string;
  name: string;
  description: string;
  eligibility_criteria: string;
  benefit_amount_inr: number | null;
  apply_url: string | null;
  created_at: string;
}

export interface SchemeApplication {
  id: string;
  scheme_id: string;
  status: string;
  applied_at: string;
  notes: string | null;
}

export interface SchemeStats {
  eligible_schemes: number;
  applied_schemes: number;
}
