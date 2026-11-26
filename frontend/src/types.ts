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
  cost_type?: string | null;
  keitaro_url: string;
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
  keitaro_url: string;
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
