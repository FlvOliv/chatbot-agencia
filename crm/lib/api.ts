import "server-only";

import type {
  AppConfig,
  ConversationDetail,
  ConversationState,
  ConversationSummary,
  DashboardInsights,
  DashboardMetrics,
  HealthStatus,
  LeadDetail,
  LeadListResponse,
  LeadTemp,
  Tag,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.CRM_API_KEY ?? "";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  init: RequestInit & { revalidate?: number } = {},
): Promise<T> {
  const { revalidate = 15, ...rest } = init;
  const url = `${API_BASE_URL}/api${path}`;
  const res = await fetch(url, {
    ...rest,
    headers: {
      "X-API-Key": API_KEY,
      Accept: "application/json",
      ...(rest.headers ?? {}),
    },
    next: { revalidate },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(
      res.status,
      `API ${path} failed (${res.status}): ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function getDashboardMetrics(): Promise<DashboardMetrics | null> {
  try {
    return await apiFetch<DashboardMetrics>("/dashboard/metrics");
  } catch (err) {
    console.error("[api] getDashboardMetrics", err);
    return null;
  }
}

export async function getDashboardInsights(
  days = 7,
): Promise<DashboardInsights | null> {
  try {
    return await apiFetch<DashboardInsights>(
      `/dashboard/insights?days=${days}`,
    );
  } catch (err) {
    console.error("[api] getDashboardInsights", err);
    return null;
  }
}

export async function getConfig(): Promise<AppConfig | null> {
  try {
    return await apiFetch<AppConfig>("/config", { revalidate: 60 });
  } catch (err) {
    console.error("[api] getConfig", err);
    return null;
  }
}

export async function getHealthStatus(): Promise<HealthStatus> {
  try {
    const url = `${API_BASE_URL}/health`;
    const r = await fetch(url, {
      signal: AbortSignal.timeout(3000),
      cache: "no-store",
    });
    if (r.ok) return "ok";
    if (r.status >= 500) return "degraded";
    return "down";
  } catch {
    return "down";
  }
}

export interface ListLeadsParams {
  temp?: LeadTemp;
  q?: string;
  sort?: "recent" | "oldest";
  page?: number;
  page_size?: number;
}

export async function listLeads(
  params: ListLeadsParams = {},
): Promise<LeadListResponse | null> {
  const qs = new URLSearchParams();
  if (params.temp) qs.set("temp", params.temp);
  if (params.q) qs.set("q", params.q);
  if (params.sort) qs.set("sort", params.sort);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  try {
    return await apiFetch<LeadListResponse>(`/leads${suffix}`);
  } catch (err) {
    console.error("[api] listLeads", err);
    return null;
  }
}

export async function getLead(phone: string): Promise<LeadDetail | null> {
  try {
    return await apiFetch<LeadDetail>(
      `/leads/${encodeURIComponent(phone)}`,
    );
  } catch (err) {
    console.error("[api] getLead", err);
    return null;
  }
}

// Detalhe de UMA cotação específica pelo número (#1001...). O mesmo cliente
// pode ter várias cotações, então o detalhe é aberto pelo número, não telefone.
export async function getLeadByNumero(
  numero: string | number,
): Promise<LeadDetail | null> {
  try {
    return await apiFetch<LeadDetail>(
      `/leads/by-numero/${encodeURIComponent(String(numero))}`,
    );
  } catch (err) {
    console.error("[api] getLeadByNumero", err);
    return null;
  }
}

export async function getConversation(
  phone: string,
  limit = 100,
): Promise<ConversationDetail | null> {
  try {
    return await apiFetch<ConversationDetail>(
      `/conversations/${encodeURIComponent(phone)}?limit=${limit}`,
      { revalidate: 0 },
    );
  } catch (err) {
    console.error("[api] getConversation", err);
    return null;
  }
}

export async function listConversations(
  params: { q?: string; limit?: number } = {},
): Promise<ConversationSummary[]> {
  const { q, limit = 50 } = params;
  const qs = new URLSearchParams();
  qs.set("limit", String(limit));
  if (q) qs.set("q", q);
  try {
    return await apiFetch<ConversationSummary[]>(
      `/conversations?${qs.toString()}`,
      { revalidate: 5 },
    );
  } catch (err) {
    console.error("[api] listConversations", err);
    return [];
  }
}

export async function listTags(): Promise<Tag[]> {
  try {
    return await apiFetch<Tag[]>("/tags", { revalidate: 30 });
  } catch (err) {
    console.error("[api] listTags", err);
    return [];
  }
}

export async function getConversationState(
  phone: string,
): Promise<ConversationState> {
  try {
    return await apiFetch<ConversationState>(
      `/conversations/${encodeURIComponent(phone)}/state`,
      { revalidate: 0 },
    );
  } catch (err) {
    console.error("[api] getConversationState", err);
    return { phone, bot_paused: false };
  }
}
