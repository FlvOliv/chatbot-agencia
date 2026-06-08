"use server";

import { revalidatePath } from "next/cache";

import type { ConversationState, ReplyResult } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.CRM_API_KEY ?? "";

async function postApi<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}/api${path}`, {
    method: "POST",
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`API ${path} (${res.status}): ${t.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function takeoverConversation(
  phone: string,
): Promise<ConversationState> {
  const r = await postApi<ConversationState>(
    `/conversations/${encodeURIComponent(phone)}/takeover`,
  );
  revalidatePath(`/conversas/${phone}`);
  return r;
}

export async function releaseConversation(
  phone: string,
): Promise<ConversationState> {
  const r = await postApi<ConversationState>(
    `/conversations/${encodeURIComponent(phone)}/release`,
  );
  revalidatePath(`/conversas/${phone}`);
  return r;
}

export async function replyConversation(
  phone: string,
  text: string,
): Promise<ReplyResult> {
  const r = await postApi<ReplyResult>(
    `/conversations/${encodeURIComponent(phone)}/reply`,
    { text },
  );
  revalidatePath(`/conversas/${phone}`);
  return r;
}
