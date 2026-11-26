/** Типы данных API для создаватора, редактора и журнала операций. */

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
  cost_type?: string | NoneType;
  keitaro_url: string;
}

type NoneType = null;

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
  keitaro_url: string;
}

export interface StreamOfferItem {
  offer_id: number;
  name: string;
  share: number;
  state: string;
  country: string[];
}

export interface StreamFilterItem {
  name: string;
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

export interface CampaignStreamsResponse {
  campaign: CampaignSummary;
  streams: StreamInfo[];
}

export interface StreamOfferShareInput {
  offer_id: number;
  share: number;
  state: "active" | "disabled";
}

export interface UpdateStreamOffersResponse {
  campaign_id: number;
  stream_id: number;
  offers: StreamOfferShareInput[];
  updated: boolean;
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
