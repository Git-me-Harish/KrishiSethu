// Shared API types — mirrors backend Pydantic schemas.


// Generic
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

export interface GeoJSONPoint {
  type: "Point";
  coordinates: [number, number];
}

export interface Centroid {
  lon: number;
  lat: number;
}


// Identity

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


// Consent (Phase F)
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


// Privacy / DSR 
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


// Grievances (Phase F)


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


// Audit log (Phase F admin)

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


// Plots (farmer domain)


export type IrrigationSource =
  | "canal" | "borewell" | "river" | "rainfed" | "drip" | "sprinkler" | "tank" | "other";

export type OwnershipType = "owned" | "leased" | "shared";

export type VerificationStatus =
  | "pending" | "verified" | "rejected" | "resubmission_requested";

export type CropSeason = "kharif" | "rabi" | "zaid";

export type CropCycleStatus =
  | "planned" | "sown" | "growing" | "harvested" | "failed";

export interface PlotListItem {
  id: string;
  survey_number: string;
  village: string;
  district: string;
  state: string;
  area_ha: string; // Decimal as string
  verification_status: VerificationStatus;
  nickname: string | null;
  centroid: Centroid | null;
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
  area_ha: string; // Decimal as string
  boundary: GeoJSONPolygon;
  centroid: Centroid | null;
  soil_type: string | null;
  soil_ph: string | null; // Decimal as string
  irrigation_source: IrrigationSource | null;
  ownership_type: OwnershipType;
  lessor_name: string | null;
  lease_start_date: string | null;
  lease_end_date: string | null;
  verification_status: VerificationStatus;
  verified_by: string | null;
  verified_at: string | null;
  verification_notes: string | null;
  nickname: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlotStatsResponse {
  total_plots: number;
  total_area_ha: string; // Decimal as string
  verified_plots: number;
  pending_verification: number;
  rejected_plots: number;
  leased_plots: number;
  by_district: Record<string, number>;
  current_season_crops: string[];
}

export interface PlotCreateRequest {
  survey_number: string;
  village: string;
  district: string;
  state: string;
  pincode?: string;
  boundary: GeoJSONPolygon;
  irrigation_source?: IrrigationSource;
  ownership_type?: OwnershipType;
  lessor_name?: string;
  lease_start_date?: string;
  lease_end_date?: string;
  nickname?: string;
}

export interface PlotUpdateRequest {
  nickname?: string;
  irrigation_source?: IrrigationSource;
  pincode?: string;
}

export interface PlotBoundaryUpdateRequest {
  boundary: GeoJSONPolygon;
  source?: "user_drawn" | "officer_corrected";
}


// Crops + Crop cycles
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
  area_ha: string; // Decimal as string
  status: CropCycleStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CropCycleCreateRequest {
  crop_id: string;
  season: CropSeason;
  season_year: number;
  sowing_date?: string;
  expected_harvest_date?: string;
  area_ha: string;
  notes?: string;
}

export interface CropCycleUpdateRequest {
  sowing_date?: string;
  expected_harvest_date?: string;
  actual_harvest_date?: string;
  status?: CropCycleStatus;
  notes?: string;
}


// Disease

export type DiseaseReportStatus =
  | "pending" | "processing" | "completed" | "failed" | "officer_review" | "reviewed";

export type DiseaseSeverity = "low" | "moderate" | "high" | "critical";

export type TreatmentType =
  | "organic" | "chemical" | "biological" | "cultural" | "preventive";

export type FeedbackType = "correct" | "incorrect" | "partially_correct";

export interface DiseaseTreatmentResponse {
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

export interface DiseaseResponse {
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
  treatments: DiseaseTreatmentResponse[];
}

export interface DiseaseListItemResponse {
  id: string;
  slug: string;
  name_en: string;
  name_hi: string | null;
  disease_type: string;
  affected_crops: string[];
  default_severity: DiseaseSeverity;
}

export interface DiseaseListResponse {
  diseases: DiseaseListItemResponse[];
  total: number;
}

export interface DiseasePredictionResponse {
  id: string;
  disease_slug: string;
  confidence: string; // Decimal as string
  all_predictions: Array<Record<string, unknown>>;
  model_name: string;
  model_version: string;
  inference_time_ms: number;
  is_reliable: boolean;
  inferred_at: string;
  disease: DiseaseResponse | null;
  treatments: DiseaseTreatmentResponse[];
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
  prediction: DiseasePredictionResponse | null;
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

export interface UploadUrlRequest {
  content_type: "image/jpeg" | "image/png" | "image/webp";
}

export interface UploadUrlResponse {
  upload_url: string;
  image_key: string;
  expires_in_seconds: number;
  max_size_bytes: number;
}

export interface DiseaseReportCreateRequest {
  plot_id?: string;
  crop_cycle_id?: string;
  image_key: string;
  image_content_type?: string;
  captured_at?: string;
  farmer_notes?: string;
}

export interface DiseaseFeedbackCreateRequest {
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


// NDVI


export type NDVISource = "sentinel2" | "landsat8" | "synthetic";
export type NDVIHealth = "healthy" | "moderate" | "sparse" | "bare";
export type NDVIAnomalyType =
  | "significant_drop" | "severe_drop" | "low_vegetation" | "prolonged_decline";
export type NDVIAnomalyStatus =
  | "active" | "acknowledged" | "investigating" | "resolved";

export interface NDVIObservation {
  id: string;
  plot_id: string;
  observed_at: string;
  source: NDVISource;
  ndvi_mean: string;
  ndvi_min: string;
  ndvi_max: string;
  ndvi_stddev: string;
  cloud_cover_pct: string;
  valid_pixel_count: number;
  total_pixel_count: number;
  raster_url: string | null;
  thumbnail_url: string | null;
  created_at: string;
  health_category: NDVIHealth;
  is_cloudy: boolean;
  raster_download_url: string | null;
}

export interface NDVIHistoryResponse {
  plot_id: string;
  observations: NDVIObservation[];
  total: number;
  latest_health: NDVIHealth | null;
  trend: "improving" | "declining" | "stable" | "insufficient_data" | null;
}

export interface NDVIRefreshResponse {
  plot_id: string;
  status: "queued" | "completed" | "failed";
  observation_id: string | null;
  ndvi_mean: string | null;
  health_category: NDVIHealth | null;
  cloud_cover_pct: string | null;
  message: string | null;
}

export interface NDVIAnomalyAlert {
  id: string;
  plot_id: string;
  farmer_id: string;
  anomaly_type: NDVIAnomalyType;
  status: NDVIAnomalyStatus;
  previous_ndvi: string;
  current_ndvi: string;
  drop_magnitude: string;
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

// Alias used by the NDVI page
export type PlotNDVISummary = PlotNDVISummaryResponse;

export interface PlotNDVISummaryResponse {
  plot_id: string;
  plot_name: string;
  latest_observation: NDVIObservation | null;
  previous_observation: NDVIObservation | null;
  trend: "improving" | "declining" | "stable" | "insufficient_data";
  trend_change: number | null;
  active_anomalies: NDVIAnomalyAlert[];
  history: NDVIObservation[];
}


// Soil & Weather


export type SoilTestSource =
  | "shc_portal" | "lab_manual" | "isric_auto" | "officer_entered";

export type WeatherAlertType =
  | "frost" | "hail" | "heat_wave" | "heavy_rain"
  | "cyclone" | "drought" | "high_wind" | "fog";

export type WeatherAlertSeverity = "info" | "warning" | "severe" | "critical";

export type WeatherAlertStatus = "active" | "expired" | "cancelled";

// `SoilTest` is the alias used by the soil page; `SoilTestResponse` is the
// canonical name matching the backend Pydantic schema.
export type SoilTest = SoilTestResponse;

export interface SoilTestResponse {
  id: string;
  plot_id: string;
  source: SoilTestSource;
  shc_id: string | null;
  lab_name: string | null;
  test_date: string;
  nitrogen_n: string | null;
  phosphorus_p: string | null;
  potassium_k: string | null;
  ph: string | null;
  electrical_conductivity: string | null;
  organic_carbon: string | null;
  clay_pct: string | null;
  sand_pct: string | null;
  silt_pct: string | null;
  soil_type: string | null;
  soil_texture: string | null;
  micronutrients: Record<string, string> | null;
  fertilizer_recommendation: string | null;
  amendment_recommendation: string | null;
  is_verified: boolean;
  verified_by: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SoilTestListResponse {
  tests: SoilTestResponse[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface SoilTestCreateRequest {
  test_date: string;
  lab_name?: string;
  nitrogen_n?: string;
  phosphorus_p?: string;
  potassium_k?: string;
  ph?: string;
  electrical_conductivity?: string;
  organic_carbon?: string;
  clay_pct?: string;
  sand_pct?: string;
  silt_pct?: string;
  micronutrients?: Record<string, string>;
  notes?: string;
}

export interface CurrentWeather {
  district: string;
  state: string;
  plot_id: string | null;
  temperature_c: string;
  feels_like_c: string;
  temp_min_c: string;
  temp_max_c: string;
  precipitation_mm: string;
  humidity_pct: string;
  wind_speed_kmph: string;
  wind_direction_deg: string;
  pressure_hpa: string;
  cloud_cover_pct: string;
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
  temp_min_c: string;
  temp_max_c: string;
  precipitation_mm: string;
  precipitation_probability: string;
  humidity_min_pct: string;
  humidity_max_pct: string;
  wind_speed_kmph: string;
  wind_direction_deg: string;
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

// Alias used by the weather page
export type PlotWeatherSummary = PlotWeatherSummaryResponse;

export interface PlotWeatherSummaryResponse {
  plot_id: string;
  plot_name: string;
  district: string;
  state: string;
  current: CurrentWeather;
  forecast: DailyForecast[];
  active_alerts: WeatherAlert[];
}


// Insurance


export type InsuranceProductType =
  | "pmfby" | "rwbcis" | "state_scheme" | "commercial";

export type ClaimType =
  | "localized_risk" | "widespread_risk" | "preventive_sowing"
  | "post_harvest" | "mid_season_adversity";

export type ClaimStatus =
  | "draft" | "submitted" | "under_review" | "evidence_requested"
  | "approved" | "rejected" | "payout_disbursed" | "withdrawn";

export type PolicyStatus = "pending" | "active" | "expired" | "cancelled";

export type EvidenceType =
  | "ndvi_drop" | "disease_report" | "weather_alert"
  | "officer_inspection" | "photo_evidence" | "yield_data" | "bank_document";

// Canonical type (matches backend PolicyResponse schema)
export type InsurancePolicy = PolicyResponse;

export interface InsuranceProductResponse {
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
  sum_insured_per_ha: string;
  farmer_premium_rate: string;
  farmer_premium_min: string | null;
  farmer_premium_max: string | null;
  coverage_start_date: string;
  coverage_end_date: string;
  claim_cutoff_yield: string | null;
  description: string | null;
  is_active: boolean;
}

export interface InsuranceProductListResponse {
  products: InsuranceProductResponse[];
  total: number;
}

// Alias used by the policies page
export type PremiumEstimate = InsuranceProductPremiumEstimate;

export interface InsuranceProductPremiumEstimate {
  product_id: string;
  plot_id: string;
  area_ha: string;
  sum_insured: string;
  premium_amount: string;
  premium_rate: string;
  farmer_premium_rate_pct: number;
}

export interface PolicyResponse {
  id: string;
  policy_number: string;
  product_id: string;
  farmer_id: string;
  plot_id: string;
  crop_cycle_id: string | null;
  sum_insured: string;
  area_insured_ha: string;
  premium_amount: string;
  premium_rate: string;
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
  product: InsuranceProductResponse | null;
  active_claims_count: number;
}

export interface PolicyListResponse {
  policies: PolicyResponse[];
  total: number;
}

export interface PolicyCreateRequest {
  product_id: string;
  plot_id: string;
  crop_cycle_id?: string;
  bank_account_number?: string;
  bank_ifsc?: string;
}

export interface ClaimEvidenceResponse {
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

// Canonical type (matches backend ClaimResponse schema)
export type InsuranceClaim = ClaimResponse;

export interface ClaimResponse {
  id: string;
  claim_number: string;
  policy_id: string;
  farmer_id: string;
  claim_type: ClaimType;
  status: ClaimStatus;
  loss_date: string;
  loss_description: string;
  estimated_loss_pct: string;
  claimed_amount: string;
  approved_amount: string | null;
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
  evidence: ClaimEvidenceResponse[];
  policy: PolicyResponse | null;
}

export interface ClaimListResponse {
  claims: ClaimResponse[];
  total: number;
}

export interface ClaimCreateRequest {
  policy_id: string;
  claim_type: ClaimType;
  loss_date: string;
  loss_description: string;
  estimated_loss_pct: string;
  bank_account_number?: string;
  bank_ifsc?: string;
}

export interface ClaimSubmitRequest {
  bank_account_number: string;
  bank_ifsc: string;
}

// Alias used by the insurance dashboard page
export type InsuranceStats = InsuranceStatsResponse;

export interface InsuranceStatsResponse {
  total_policies: number;
  active_policies: number;
  expired_policies: number;
  total_sum_insured: string;
  total_premium_paid: string;
  total_claims: number;
  pending_claims: number;
  approved_claims: number;
  total_claimed_amount: string;
  total_approved_amount: string;
}


// Marketplace


export type ProductCategoryType =
  | "seeds" | "fertilizers" | "pesticides" | "fungicides" | "herbicides"
  | "machinery" | "tools" | "irrigation" | "organic_inputs" | "other";

export type OrderStatus =
  | "draft" | "placed" | "confirmed" | "packed" | "shipped"
  | "out_for_delivery" | "delivered" | "delivery_failed"
  | "completed" | "cancelled" | "returned" | "refund_initiated";

export type PaymentStatus =
  | "pending" | "paid" | "escrow_held" | "released_to_supplier"
  | "refunded" | "failed";

export interface ProductCategoryResponse {
  id: string;
  slug: string;
  name: string;
  name_hi: string | null;
  category_type: string;
  icon: string | null;
  sort_order: number;
}

export interface ProductCategoryListResponse {
  categories: ProductCategoryResponse[];
  total: number;
}

export interface ProductResponse {
  id: string;
  supplier_id: string;
  category_id: string;
  name: string;
  name_hi: string | null;
  slug: string;
  description: string;
  brand: string | null;
  price: string;
  mrp: string | null;
  unit: string;
  min_order_qty: number;
  stock_quantity: number;
  is_in_stock: boolean;
  image_url: string | null;
  certifications: string[] | null;
  active_ingredient: string | null;
  concentration: string | null;
  linked_disease_slug: string | null;
  suitable_crops: string[] | null;
  rating: string;
  total_reviews: number;
  discount_pct: number;
  supplier_name: string | null;
  category_name: string | null;
}

// Backwards-compat alias used by some pages
export type Product = ProductResponse;

export interface ProductListResponse {
  products: ProductResponse[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface OrderItemResponse {
  id: string;
  product_id: string;
  product_name: string;
  product_image_url: string | null;
  unit_price: string;
  quantity: number;
  total_price: string;
  fulfillment_status: string;
}

export interface OrderResponse {
  id: string;
  order_number: string;
  farmer_id: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  subtotal: string;
  shipping_cost: string;
  total_amount: string;
  shipping_name: string;
  shipping_phone: string;
  shipping_address_line1: string;
  shipping_address_line2: string | null;
  shipping_village: string | null;
  shipping_district: string;
  shipping_state: string;
  shipping_pincode: string;
  placed_at: string | null;
  delivered_at: string | null;
  created_at: string;
  items: OrderItemResponse[];
}

// Backwards-compat alias used by some pages
export type Order = OrderResponse;

export interface OrderListResponse {
  orders: OrderResponse[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface OrderCreateRequest {
  items: Array<{ product_id: string; quantity: number }>;
  shipping_name: string;
  shipping_phone: string;
  shipping_address_line1: string;
  shipping_address_line2?: string;
  shipping_village?: string;
  shipping_district: string;
  shipping_state: string;
  shipping_pincode: string;
  payment_method?: "upi" | "razorpay" | "cod";
}

// Alias used by the marketplace page
export type MarketplaceStats = MarketplaceStatsResponse;

export interface MarketplaceStatsResponse {
  total_products: number;
  total_orders: number;
  pending_orders: number;
  completed_orders: number;
  total_spent: string;
}


// Government Schemes


export type SchemeCategory =
  | "income_support" | "crop_insurance" | "credit" | "input_subsidy"
  | "equipment_subsidy" | "irrigation" | "soil_health"
  | "market_support" | "pension" | "other";

export type ApplicationStatus =
  | "draft" | "submitted" | "under_review" | "approved" | "rejected"
  | "resubmission_requested" | "withdrawn" | "benefit_disbursed";

// Backwards-compat aliases
export type GovtScheme = SchemeResponse;
export type SchemeApplication = SchemeApplicationResponse;
export type SchemeStats = SchemeStatsResponse;

export interface SchemeResponse {
  id: string;
  code: string;
  name: string;
  name_hi: string | null;
  short_description: string;
  full_description: string;
  category: string;
  level: string;
  ministry: string | null;
  states: string[] | null;
  benefit_type: string | null;
  benefit_amount: string | null;
  benefit_frequency: string | null;
  benefit_description: string | null;
  application_mode: string;
  documents_required: string[] | null;
  application_url: string | null;
  source_url: string | null;
  helpline_number: string | null;
  is_featured: boolean;
  is_eligible: boolean | null;
  eligibility_reasons: string[] | null;
  has_applied: boolean;
  application_status: string | null;
}

export interface SchemeListResponse {
  schemes: SchemeResponse[];
  total: number;
  eligible_count: number | null;
}

export interface SchemeApplicationResponse {
  id: string;
  application_number: string;
  scheme_id: string;
  farmer_id: string;
  status: ApplicationStatus;
  submitted_data: Record<string, unknown>;
  eligibility_result: Record<string, unknown> | null;
  submitted_documents: string[] | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  rejection_reason: string | null;
  benefit_disbursed_at: string | null;
  benefit_reference: string | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  scheme_name: string | null;
  scheme_code: string | null;
}

export interface SchemeApplicationListResponse {
  applications: SchemeApplicationResponse[];
  total: number;
}

export interface SchemeApplicationCreateRequest {
  scheme_id: string;
  additional_data?: Record<string, unknown>;
}

export interface SchemeStatsResponse {
  total_schemes_available: number;
  eligible_schemes: number;
  total_applications: number;
  pending_applications: number;
  approved_applications: number;
}
