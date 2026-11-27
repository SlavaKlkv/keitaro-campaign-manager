import type {
  BulkCampaignCreateItem,
  BulkCampaignCreateResponse,
  BulkOfferReplaceApplyResponse,
  BulkOfferReplacePreviewResponse,
  CampaignCreatePayload,
  CampaignCreateResponse,
  CampaignHealthSummary,
  CampaignStatsResponse,
  CampaignStreamsResponse,
  CampaignSummary,
  CloneGeosResponse,
  MetaResponse,
  OperationLogItem,
  StatsPeriod,
  StreamOfferShareInput,
  UpdateStreamOffersResponse,
} from "../types";

/** Ошибка API с понятным текстом и HTTP-кодом. */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let message = `Ошибка запроса (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") {
        message = data.detail;
      } else if (Array.isArray(data?.detail)) {
        message = data.detail
          .map((item: { msg?: string }) => item.msg || JSON.stringify(item))
          .join("; ");
      } else if (data?.detail && typeof data.detail === "object") {
        message = data.detail.message || JSON.stringify(data.detail);
      }
    } catch {
      /* Оставляем сообщение по умолчанию */
    }
    throw new ApiError(message, response.status);
  }

  return response.json() as Promise<T>;
}

/** Клиент REST API собственного backend. */
export const api = {
  getHealth: () =>
    requestJson<{ status: string; database: string; demo_mode?: boolean }>(
      "/health"
    ),
  getMeta: (refresh = false) =>
    requestJson<MetaResponse>(refresh ? "/api/meta?refresh=true" : "/api/meta"),
  listCampaigns: () => requestJson<CampaignSummary[]>("/api/campaigns"),
  createCampaign: (payload: CampaignCreatePayload) =>
    requestJson<CampaignCreateResponse>("/api/campaigns", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getCampaignStreams: (campaignId: number) =>
    requestJson<CampaignStreamsResponse>(`/api/campaigns/${campaignId}/streams`),
  getCampaignsHealth: () =>
    requestJson<Record<string, CampaignHealthSummary>>("/api/campaigns/health"),
  getCampaignStats: (campaignId: number, period: StatsPeriod = "7d") =>
    requestJson<CampaignStatsResponse>(
      `/api/campaigns/${campaignId}/stats?period=${period}`
    ),
  updateStreamOffers: (
    campaignId: number,
    streamId: number,
    offers: StreamOfferShareInput[]
  ) =>
    requestJson<UpdateStreamOffersResponse>(
      `/api/campaigns/${campaignId}/streams/${streamId}/offers`,
      {
        method: "PUT",
        body: JSON.stringify({ offers }),
      }
    ),
  listLogs: (limit = 50, operation?: string, resourceId?: number) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (operation) params.set("operation", operation);
    if (resourceId !== undefined) params.set("resource_id", String(resourceId));
    return requestJson<OperationLogItem[]>(`/api/logs?${params.toString()}`);
  },
  bulkCreateCampaigns: (payload: {
    domain_id: number;
    group_id: number;
    traffic_source_id: number;
    items: BulkCampaignCreateItem[];
  }) =>
    requestJson<BulkCampaignCreateResponse>("/api/campaigns/bulk", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cloneCampaignToGeos: (campaignId: number, country_codes: string[]) =>
    requestJson<CloneGeosResponse>(`/api/campaigns/${campaignId}/clone-geos`, {
      method: "POST",
      body: JSON.stringify({ country_codes }),
    }),
  previewBulkOfferReplace: (payload: {
    source_offer_id: number;
    target_offer_id: number | null;
    campaign_ids?: number[] | null;
  }) =>
    requestJson<BulkOfferReplacePreviewResponse>(
      "/api/campaigns/bulk-offer-replace/preview",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
  applyBulkOfferReplace: (payload: {
    source_offer_id: number;
    target_offer_id: number | null;
    campaign_ids?: number[] | null;
  }) =>
    requestJson<BulkOfferReplaceApplyResponse>(
      "/api/campaigns/bulk-offer-replace/apply",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
};
