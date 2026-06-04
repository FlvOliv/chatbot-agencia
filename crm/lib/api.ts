import "server-only";

import type {
  ConversationDetail,
  DashboardInsights,
  DashboardMetrics,
  LeadDetail,
  LeadListResponse,
  LeadTemp,
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
    console.warn("[api] getDashboardInsights", err);
    return null;
  }
}

export interface ListLeadsParams {
  temp?: LeadTemp;
  q?: string;
  page?: number;
  page_size?: number;
}

export async function listLeads(
  params: ListLeadsParams = {},
): Promise<LeadListResponse | null> {
  const qs = new URLSearchParams();
  if (params.temp) qs.set("temp", params.temp);
  if (params.q) qs.set("q", params.q);
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

export async function getConversation(
  phone: string,
  limit = 100,
): Promise<ConversationDetail | null> {
  try {
    return await apiFetch<ConversationDetail>(
      `/conversations/${encodeURIComponent(phone)}?limit=${limit}`,
    );
  } catch (err) {
    console.error("[api] getConversation", err);
    return null;
  }
}
