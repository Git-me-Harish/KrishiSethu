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
  aadhaar_verified: boolean;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  preferred_language: string;
  last_login_at: string | null;
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
// Disease (mirrors krishisetu/domains/disease/schemas.py)
// ---------------------------------------------------------------------------

export type DiseaseSeverity = "low" | "moderate" | "high" | "critical";
export type DiseaseReportStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "officer_review"
  | "reviewed";
export type TreatmentType = "organic" | "chemical" | "biological" | "cultural" | "preventive";
export type FeedbackType = "correct" | "incorrect" | "partially_correct";

export interface DiseaseTreatment {
  id: string;
  treatment_type: TreatmentType;
  description: string;
  dosage: string | null;
  application_method: string | null;
  timing: string | null;
  precautions: string | null;
  is_primary: boolean;
  priority: number;
  source: string | null;
}

export interface DiseaseInfo {
  id: string;
  slug: string;
  name_en: string;
  name_hi: string | null;
  scientific_name: string | null;
  disease_type: string;
  affected_crops: string[];
  default_severity: DiseaseSeverity;
  symptoms: string;
  cause: string;
  spread_mechanism: string | null;
  favorable_conditions: string | null;
  prevention_measures: string | null;
  treatments: DiseaseTreatment[];
}

export interface DiseaseListItem {
  id: string;
  slug: string;
  name_en: string;
  name_hi: string | null;
  disease_type: string;
  affected_crops: string[];
  default_severity: DiseaseSeverity;
}

export interface DiseaseListResponse {
  diseases: DiseaseListItem[];
  total: number;
}

export interface DiseasePrediction {
  id: string;
  disease_slug: string;
  confidence: number;
  all_predictions: { disease_slug: string; confidence: number }[];
  model_name: string;
  model_version: string;
  inference_time_ms: number;
  is_reliable: boolean;
  inferred_at: string;
  disease: DiseaseInfo | null;
  treatments: DiseaseTreatment[];
}

export interface DiseaseReport {
  id: string;
  farmer_id: string;
  plot_id: string | null;
  crop_cycle_id: string | null;
  image_url: string;
  captured_at: string | null;
  submitted_at: string;
  farmer_notes: string | null;
  status: DiseaseReportStatus;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  prediction: DiseasePrediction | null;
  /**
   * Tracked on the backend model (disease_reports.officer_diagnosis) but not
   * currently declared on DiseaseReportResponse in schemas.py, so the API
   * never actually serializes it — always undefined today. Kept optional so
   * the UI degrades safely rather than lying about the shape.
   */
  officer_diagnosis?: string | null;
}

export interface DiseaseReportListResponse {
  reports: DiseaseReport[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface DiseaseReportStats {
  total_reports: number;
  completed: number;
  pending: number;
  failed: number;
  needs_review: number;
  by_disease: Record<string, number>;
}

export interface DiseaseFeedbackCreate {
  feedback_type: FeedbackType;
  suggested_disease_slug?: string;
  notes?: string;
}

export interface DiseaseFeedbackResponse {
  id: string;
  report_id: string;
  feedback_type: FeedbackType;
  suggested_disease_slug: string | null;
  notes: string | null;
  created_at: string;
}

export interface UploadUrlResponse {
  upload_url: string;
  image_key: string;
  expires_in_seconds: number;
  max_size_bytes: number;
}

// ---------------------------------------------------------------------------
// NDVI (mirrors krishisetu/domains/ndvi/schemas.py)
// ---------------------------------------------------------------------------

export type NDVIHealthCategory = "healthy" | "moderate" | "sparse" | "bare";
export type NDVIAnomalyType =
  | "significant_drop"
  | "severe_drop"
  | "low_vegetation"
  | "prolonged_decline";
export type NDVIAnomalyStatus = "active" | "acknowledged" | "investigating" | "resolved";
export type NDVITrend = "improving" | "declining" | "stable" | "insufficient_data";

export interface NDVIObservation {
  id: string;
  plot_id: string;
  observed_at: string;
  source: string;
  ndvi_mean: number;
  ndvi_min: number;
  ndvi_max: number;
  ndvi_stddev: number;
  cloud_cover_pct: number;
  valid_pixel_count: number;
  total_pixel_count: number;
  raster_url: string | null;
  thumbnail_url: string | null;
  created_at: string;
  health_category: NDVIHealthCategory;
  is_cloudy: boolean;
  raster_download_url: string | null;
}

export interface NDVIHistoryResponse {
  plot_id: string;
  observations: NDVIObservation[];
  total: number;
  latest_health: string | null;
  trend: NDVITrend | null;
}

export interface NDVIRefreshResponse {
  plot_id: string;
  status: string;
  observation_id: string | null;
  ndvi_mean: number | null;
  health_category: string | null;
  cloud_cover_pct: number | null;
  message: string | null;
}

export interface NDVIAnomalyAlert {
  id: string;
  plot_id: string;
  farmer_id: string;
  anomaly_type: NDVIAnomalyType;
  status: NDVIAnomalyStatus;
  previous_ndvi: number;
  current_ndvi: number;
  drop_magnitude: number;
  drop_percentage: number;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
}

export interface NDVIAnomalyListResponse {
  alerts: NDVIAnomalyAlert[];
  total: number;
}

export interface PlotNDVISummary {
  plot_id: string;
  plot_name: string;
  latest_observation: NDVIObservation | null;
  previous_observation: NDVIObservation | null;
  trend: NDVITrend;
  trend_change: number | null;
  active_anomalies: NDVIAnomalyAlert[];
  history: NDVIObservation[];
}

// ---------------------------------------------------------------------------
// Plots / Crops (mirrors krishisetu/domains/farmer/schemas.py)
// ---------------------------------------------------------------------------

export type IrrigationSource =
  | "canal"
  | "borewell"
  | "river"
  | "rainfed"
  | "drip"
  | "sprinkler"
  | "tank"
  | "other";
export type OwnershipType = "owned" | "leased" | "shared";
export type PlotVerificationStatus =
  | "pending"
  | "verified"
  | "rejected"
  | "resubmission_requested";
export type CropSeason = "kharif" | "rabi" | "zaid";
export type CropCycleStatus = "planned" | "sown" | "growing" | "harvested" | "failed";

export interface PlotListItem {
  id: string;
  survey_number: string;
  village: string;
  district: string;
  state: string;
  area_ha: number;
  verification_status: PlotVerificationStatus;
  nickname: string | null;
  centroid: { lon: number; lat: number } | null;
  current_crop: string | null;
  current_crop_cycle_id: string | null;
  created_at: string;
}

export interface PlotListResponse {
  plots: PlotListItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface PlotResponse {
  id: string;
  farmer_id: string;
  survey_number: string;
  village: string;
  district: string;
  state: string;
  pincode: string | null;
  area_ha: number;
  boundary: GeoJSONPolygon;
  centroid: { lon: number; lat: number } | null;
  soil_type: string | null;
  soil_ph: number | null;
  irrigation_source: IrrigationSource | null;
  ownership_type: OwnershipType;
  lessor_name: string | null;
  lease_start_date: string | null;
  lease_end_date: string | null;
  verification_status: PlotVerificationStatus;
  verified_by: string | null;
  verified_at: string | null;
  verification_notes: string | null;
  nickname: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlotStatsResponse {
  total_plots: number;
  total_area_ha: number;
  verified_plots: number;
  pending_verification: number;
  rejected_plots: number;
  leased_plots: number;
  by_district: Record<string, number>;
  current_season_crops: string[];
}

export interface PlotCreatePayload {
  survey_number: string;
  village: string;
  district: string;
  state: string;
  pincode?: string;
  boundary: GeoJSONPolygon;
  irrigation_source?: string;
  ownership_type: OwnershipType;
  lessor_name?: string;
  lease_start_date?: string;
  lease_end_date?: string;
  nickname?: string;
}

export interface CropResponse {
  id: string;
  slug: string;
  name_en: string;
  name_hi: string | null;
  scientific_name: string | null;
  crop_category: string;
  primary_season: CropSeason;
  duration_days_min: number;
  duration_days_max: number;
  water_requirement_mm: number | null;
}

export interface CropListResponse {
  crops: CropResponse[];
  total: number;
}

export interface CropCycleResponse {
  id: string;
  plot_id: string;
  crop_id: string;
  crop_name: string | null;
  season: CropSeason;
  season_year: number;
  sowing_date: string | null;
  expected_harvest_date: string | null;
  actual_harvest_date: string | null;
  area_ha: number;
  status: CropCycleStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CropCycleCreatePayload {
  crop_id: string;
  season: CropSeason;
  season_year: number;
  sowing_date?: string;
  expected_harvest_date?: string;
  area_ha: number;
  notes?: string;
}

export interface CropCycleUpdatePayload {
  sowing_date?: string;
  expected_harvest_date?: string;
  actual_harvest_date?: string;
  status?: CropCycleStatus;
  notes?: string;
}

// ---------------------------------------------------------------------------
// Soil / Weather (mirrors krishisetu/domains/soil_weather/schemas.py)
// ---------------------------------------------------------------------------

export type SoilTestSource = "shc_portal" | "lab_manual" | "isric_auto" | "officer_entered";
export type WeatherAlertType =
  | "frost"
  | "hail"
  | "heat_wave"
  | "heavy_rain"
  | "cyclone"
  | "drought"
  | "high_wind"
  | "fog";
export type WeatherAlertSeverity = "info" | "warning" | "severe" | "critical";
export type WeatherAlertStatus = "active" | "expired" | "cancelled";

export interface SoilTest {
  id: string;
  plot_id: string;
  source: SoilTestSource;
  shc_id: string | null;
  lab_name: string | null;
  test_date: string;
  nitrogen_n: number | null;
  phosphorus_p: number | null;
  potassium_k: number | null;
  ph: number | null;
  electrical_conductivity: number | null;
  organic_carbon: number | null;
  clay_pct: number | null;
  sand_pct: number | null;
  silt_pct: number | null;
  soil_type: string | null;
  soil_texture: string | null;
  micronutrients: Record<string, number> | null;
  fertilizer_recommendation: string | null;
  amendment_recommendation: string | null;
  is_verified: boolean;
  verified_by: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SoilTestListResponse {
  tests: SoilTest[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface SoilTestCreatePayload {
  test_date: string;
  lab_name?: string;
  nitrogen_n?: number;
  phosphorus_p?: number;
  potassium_k?: number;
  ph?: number;
  electrical_conductivity?: number;
  organic_carbon?: number;
  clay_pct?: number;
  sand_pct?: number;
  silt_pct?: number;
  micronutrients?: Record<string, number>;
  notes?: string;
}

export interface CurrentWeather {
  district: string;
  state: string;
  plot_id: string | null;
  temperature_c: number;
  feels_like_c: number;
  temp_min_c: number;
  temp_max_c: number;
  precipitation_mm: number;
  humidity_pct: number;
  wind_speed_kmph: number;
  wind_direction_deg: number;
  pressure_hpa: number;
  cloud_cover_pct: number;
  weather_main: string;
  weather_description: string;
  weather_icon: string;
  observed_at: string;
  sunrise_at: string | null;
  sunset_at: string | null;
  source: string;
  agromet_advisory: string | null;
}

export interface DailyForecast {
  forecast_date: string;
  temp_min_c: number;
  temp_max_c: number;
  precipitation_mm: number;
  precipitation_probability: number;
  humidity_min_pct: number;
  humidity_max_pct: number;
  wind_speed_kmph: number;
  wind_direction_deg: number;
  weather_main: string;
  weather_description: string;
  weather_icon: string;
  agromet_advisory: string | null;
  source: string;
}

export interface ForecastResponse {
  district: string;
  state: string;
  plot_id: string | null;
  forecasts: DailyForecast[];
  issued_at: string;
}

export interface WeatherHistoryResponse {
  district: string;
  state: string;
  plot_id: string | null;
  observations: CurrentWeather[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface WeatherAlert {
  id: string;
  district: string;
  state: string;
  alert_type: WeatherAlertType;
  severity: WeatherAlertSeverity;
  status: WeatherAlertStatus;
  effective_at: string;
  expires_at: string;
  title: string;
  description: string;
  recommended_actions: string | null;
  source: string;
  notifications_sent: number;
  created_at: string;
}

export interface WeatherAlertListResponse {
  alerts: WeatherAlert[];
  total: number;
}

export interface PlotWeatherSummary {
  plot_id: string;
  plot_name: string;
  district: string;
  state: string;
  current: CurrentWeather;
  forecast: DailyForecast[];
  active_alerts: WeatherAlert[];
}

// ---------------------------------------------------------------------------
// Insurance (mirrors krishisetu/domains/insurance/schemas.py)
// ---------------------------------------------------------------------------

export type InsuranceProductType = "pmfby" | "rwbcis" | "state_scheme" | "commercial";
export type ClaimType =
  | "localized_risk"
  | "widespread_risk"
  | "preventive_sowing"
  | "post_harvest"
  | "mid_season_adversity";
export type ClaimStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "evidence_requested"
  | "approved"
  | "rejected"
  | "payout_disbursed"
  | "withdrawn";
export type PolicyStatus = "pending" | "active" | "expired" | "cancelled";
export type EvidenceType =
  | "ndvi_drop"
  | "disease_report"
  | "weather_alert"
  | "officer_inspection"
  | "photo_evidence"
  | "yield_data"
  | "bank_document";

export interface InsuranceProduct {
  id: string;
  slug: string;
  name: string;
  product_type: InsuranceProductType;
  insurer_name: string;
  crop_slug: string;
  crop_name: string;
  season: string;
  season_year: number;
  state: string;
  district: string | null;
  sum_insured_per_ha: number;
  farmer_premium_rate: number;
  farmer_premium_min: number | null;
  farmer_premium_max: number | null;
  coverage_start_date: string;
  coverage_end_date: string;
  claim_cutoff_yield: number | null;
  description: string | null;
  is_active: boolean;
}

export interface InsuranceProductListResponse {
  products: InsuranceProduct[];
  total: number;
}

export interface PremiumEstimate {
  product_id: string;
  plot_id: string;
  area_ha: number;
  sum_insured: number;
  premium_amount: number;
  premium_rate: number;
  farmer_premium_rate_pct: number;
}

export interface InsurancePolicy {
  id: string;
  policy_number: string;
  product_id: string;
  farmer_id: string;
  plot_id: string;
  crop_cycle_id: string | null;
  sum_insured: number;
  area_insured_ha: number;
  premium_amount: number;
  premium_rate: number;
  premium_paid: boolean;
  premium_paid_at: string | null;
  payment_reference: string | null;
  coverage_start_date: string;
  coverage_end_date: string;
  status: PolicyStatus;
  bank_account_number: string | null;
  bank_ifsc: string | null;
  created_at: string;
  updated_at: string;
  product: InsuranceProduct | null;
  active_claims_count: number;
}

export interface PolicyListResponse {
  policies: InsurancePolicy[];
  total: number;
}

export interface ClaimEvidence {
  id: string;
  claim_id: string;
  evidence_type: EvidenceType;
  source_module: string;
  source_id: string | null;
  title: string;
  description: string;
  evidence_date: string;
  snapshot_data: Record<string, unknown> | null;
  file_url: string | null;
  is_auto_attached: boolean;
  file_download_url: string | null;
  created_at: string;
}

export interface InsuranceClaim {
  id: string;
  claim_number: string;
  policy_id: string;
  farmer_id: string;
  claim_type: ClaimType;
  status: ClaimStatus;
  loss_date: string;
  loss_description: string;
  estimated_loss_pct: number;
  claimed_amount: number;
  approved_amount: number | null;
  payout_transaction_id: string | null;
  payout_date: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  rejection_reason: string | null;
  auto_evidence_summary: Record<string, unknown> | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  evidence: ClaimEvidence[];
  policy: InsurancePolicy | null;
}

export interface ClaimListResponse {
  claims: InsuranceClaim[];
  total: number;
}

export interface InsuranceStats {
  total_policies: number;
  active_policies: number;
  expired_policies: number;
  total_sum_insured: number;
  total_premium_paid: number;
  total_claims: number;
  pending_claims: number;
  approved_claims: number;
  total_claimed_amount: number;
  total_approved_amount: number;
}

export interface ClaimCreatePayload {
  policy_id: string;
  claim_type: string;
  loss_date: string;
  loss_description: string;
  estimated_loss_pct: number;
  bank_account_number?: string;
  bank_ifsc?: string;
}

export interface PolicyEnrollPayload {
  product_id: string;
  plot_id: string;
  crop_cycle_id?: string;
  bank_account_number?: string;
  bank_ifsc?: string;
}
