import type {
  CampaignCreatePayload,
  CampaignCreateResponse,
  CampaignStreamsResponse,
  CampaignSummary,
  MetaResponse,
  OperationLogItem,
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
  getHealth: () => requestJson<{ status: string; database: string }>("/health"),
  getMeta: () => requestJson<MetaResponse>("/api/meta"),
  listCampaigns: () => requestJson<CampaignSummary[]>("/api/campaigns"),
  createCampaign: (payload: CampaignCreatePayload) =>
    requestJson<CampaignCreateResponse>("/api/campaigns", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getCampaignStreams: (campaignId: number) =>
    requestJson<CampaignStreamsResponse>(`/api/campaigns/${campaignId}/streams`),
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
  listLogs: (limit = 50) =>
    requestJson<OperationLogItem[]>(`/api/logs?limit=${limit}`),
};
