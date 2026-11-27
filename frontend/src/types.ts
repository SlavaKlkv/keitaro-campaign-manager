/** Типы данных API для создания кампаний, редактора и журнала операций. */

export interface DomainItem {
  id: number;
  name: string;
  status?: string | null;
  is_ssl?: boolean | null;
  state?: string | null;
}

export interface GroupItem {
  id: number;
  name: string;
  type?: string | null;
}

export interface TrafficSourceItem {
  id: number;
  name: string;
  template_name?: string | null;
  state?: string | null;
}

export interface OfferItem {
  id: number;
  name: string;
  group_id?: number | null;
  group?: string | null;
  state?: string | null;
  country: string[];
}

export interface MetaResponse {
  domains: DomainItem[];
  groups: GroupItem[];
  traffic_sources: TrafficSourceItem[];
  offers: OfferItem[];
  keitaro_base_url: string;
  defaults: {
    domain_id: number | null;
    group_id: number | null;
    traffic_source_id: number | null;
  };
  campaign_name_prefix?: string;
  demo_mode?: boolean;
  cached?: boolean;
  cached_at?: string | null;
}

export interface CampaignSummary {
  id: number;
  name: string;
  alias?: string | null;
  state?: string | null;
  domain_id?: number | null;
  domain?: string | null;
  group_id?: number | null;
  group?: string | null;
  traffic_source_id?: number | null;
  type?: string | null;
  cost_type?: string | null;
  keitaro_url: string | null;
}

export interface CampaignCreatePayload {
  name: string;
  country_code: string;
  offer_id: number;
  domain_id: number;
  group_id: number;
  traffic_source_id: number;
  alias?: string | null;
}

export interface CampaignCreateResponse {
  id: number;
  name: string;
  alias: string;
  country_code: string;
  offer_id: number;
  domain_id: number;
  group_id: number;
  traffic_source_id: number;
  streams_created: number;
  tracking_url?: string | null;
  keitaro_url: string | null;
}

export interface StreamOfferItem {
  offer_id: number;
  name?: string | null;
  share: number;
  state: string;
  country?: string[];
  removed_externally?: boolean;
}

export interface StreamFilterItem {
  name?: string;
  mode?: string | null;
  payload?: unknown;
}

export interface StreamInfo {
  id: number;
  campaign_id: number;
  name: string;
  type?: string | null;
  position?: number | null;
  weight?: number | null;
  schema?: string | null;
  action_type?: string | null;
  action_payload?: string | null;
  state?: string | null;
  filters: StreamFilterItem[];
  offers: StreamOfferItem[];
}

export interface HealthIssue {
  code: string;
  severity: "error" | "warning" | string;
  stream_id?: number | null;
  message: string;
}

export interface CampaignHealthSummary {
  status: "ok" | "warning" | "error" | string;
  issues: HealthIssue[];
}

export interface CampaignStreamsResponse {
  campaign: CampaignSummary;
  streams: StreamInfo[];
  health?: CampaignHealthSummary | null;
}

export type StatsPeriod = "today" | "7d" | "30d";

export interface OfferStatsItem {
  offer_id: number;
  offer_name?: string | null;
  clicks: number;
  conversions: number;
  cr: number;
  epc: number;
  revenue: number;
}

export interface CampaignStatsResponse {
  campaign_id: number;
  period: StatsPeriod;
  offers: OfferStatsItem[];
}

export interface StreamOfferShareInput {
  offer_id: number;
  share: number;
  state?: "active" | "disabled";
}

export interface UpdateStreamOffersResponse {
  campaign_id: number;
  stream_id: number;
  offers: StreamOfferShareInput[];
  updated: boolean;
}

export interface OfferDiffEntry {
  offer_id: number;
  name: string;
  change: "added" | "removed" | "changed" | "unchanged";
  before_share: number | null;
  after_share: number | null;
  before_state?: string | null;
  after_state?: string | null;
}

export interface SnapshotOfferEntry {
  offer_id: number;
  name?: string;
  share: number;
  state?: string;
}

export interface PendingRollback {
  logId: number;
  campaignId: number;
  streamId: number;
  label: string;
  offers: SnapshotOfferEntry[];
}

export interface OperationLogItem {
  id: number;
  operation: string;
  resource_type: string;
  resource_id: number | null;
  summary: string;
  status: string;
  details?: Record<string, unknown> | null;
  created_at: string;
}

export interface BulkCampaignCreateItem {
  name: string;
  country_code: string;
  offer_id: number;
  alias?: string | null;
}

export interface BulkCampaignResultItem {
  index: number;
  name: string;
  country_code: string;
  offer_id: number;
  status: string;
  campaign_id?: number | null;
  tracking_url?: string | null;
  keitaro_url?: string | null;
  error?: string | null;
}

export interface BulkCampaignCreateResponse {
  total: number;
  succeeded: number;
  failed: number;
  results: BulkCampaignResultItem[];
}

export interface CloneGeoResultItem {
  country_code: string;
  status: string;
  campaign_id?: number | null;
  name?: string | null;
  tracking_url?: string | null;
  keitaro_url?: string | null;
  error?: string | null;
}

export interface CloneGeosResponse {
  source_campaign_id: number;
  total: number;
  succeeded: number;
  failed: number;
  results: CloneGeoResultItem[];
}

export interface BulkReplaceStreamPreview {
  campaign_id: number;
  campaign_name: string;
  stream_id: number;
  stream_name: string;
  before: SnapshotOfferEntry[];
  after: SnapshotOfferEntry[];
  diff: OfferDiffEntry[];
}

export interface BulkReplaceStreamSkipped {
  campaign_id: number;
  campaign_name: string;
  stream_id: number;
  stream_name: string;
  reason: string;
}

export interface BulkOfferReplacePreviewResponse {
  source_offer_id: number;
  target_offer_id: number | null;
  affected_streams: BulkReplaceStreamPreview[];
  skipped_streams: BulkReplaceStreamSkipped[];
}

export interface BulkOfferReplaceApplyResult {
  campaign_id: number;
  campaign_name: string;
  stream_id: number;
  stream_name: string;
  status: string;
  error?: string | null;
}

export interface BulkOfferReplaceApplyResponse {
  source_offer_id: number;
  target_offer_id: number | null;
  total_streams: number;
  succeeded: number;
  failed: number;
  results: BulkOfferReplaceApplyResult[];
  skipped_streams: BulkReplaceStreamSkipped[];
}
