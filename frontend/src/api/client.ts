import type {
  CampaignCreatePayload,
  CampaignCreateResponse,
  CampaignSummary,
  MetaResponse,
  OperationLogItem,
} from "../types";

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
    let message = `Ошибка HTTP ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") {
        message = data.detail;
      } else if (data?.detail?.message) {
        message = data.detail.message;
      } else if (Array.isArray(data?.detail)) {
        message = data.detail
          .map((item: { msg?: string }) => item.msg || JSON.stringify(item))
          .join("; ");
      }
    } catch {
      /* Оставляем текст ошибки по умолчанию */
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
  getLogs: (limit = 50) =>
    requestJson<OperationLogItem[]>(`/api/logs?limit=${limit}`),
};
