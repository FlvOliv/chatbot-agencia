"use server";

import { revalidatePath } from "next/cache";

import type { ConversationState, ReplyResult, Tag } from "./types";

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

async function deleteApi(path: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api${path}`, {
    method: "DELETE",
    headers: { "X-API-Key": API_KEY },
    cache: "no-store",
  });
  if (!res.ok && res.status !== 204) {
    const t = await res.text().catch(() => "");
    throw new Error(`API ${path} (${res.status}): ${t.slice(0, 200)}`);
  }
}

/** Inscrição de push web (Fase 3) — recebe o JSON do navegador da Lu e
 *  repassa pro backend com a X-API-Key (que fica só no servidor). */
export async function subscribeToPush(
  subscription: unknown,
): Promise<{ status: string }> {
  return postApi<{ status: string }>("/push/subscribe", subscription);
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

/** Apaga o log da conversa + limpa a memória (Redis) do número. Faxina de
 *  testes: some do painel e a Malu trata a próxima msg como nova. Não toca em
 *  leads/clientes. */
export async function deleteConversation(phone: string): Promise<void> {
  await deleteApi(`/conversations/${encodeURIComponent(phone)}`);
  revalidatePath("/conversas");
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

export async function replyAudioConversation(
  phone: string,
  formData: FormData,
): Promise<ReplyResult> {
  const file = formData.get("audio");
  if (!(file instanceof Blob)) throw new Error("Áudio ausente.");
  const name = (file as File).name || "nota.webm";

  const fd = new FormData();
  fd.append("audio", file, name);

  // Sem Content-Type manual: o fetch monta o boundary do multipart.
  const res = await fetch(
    `${API_BASE_URL}/api/conversations/${encodeURIComponent(phone)}/reply-audio`,
    {
      method: "POST",
      headers: { "X-API-Key": API_KEY },
      body: fd,
      cache: "no-store",
    },
  );
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`API reply-audio (${res.status}): ${t.slice(0, 200)}`);
  }
  const r = (await res.json()) as ReplyResult;
  revalidatePath(`/conversas/${encodeURIComponent(phone)}`);
  return r;
}

export async function createTag(name: string, color: string): Promise<Tag> {
  const tag = await postApi<Tag>("/tags", { name, color });
  revalidatePath("/conversas");
  return tag;
}

export async function deleteTag(tagId: string): Promise<void> {
  await deleteApi(`/tags/${tagId}`);
  revalidatePath("/conversas");
}

export async function addTagToConversation(
  phone: string,
  tagId: string,
): Promise<void> {
  await postApi(`/conversations/${encodeURIComponent(phone)}/tags/${tagId}`);
  revalidatePath(`/conversas/${encodeURIComponent(phone)}`);
  revalidatePath("/conversas");
}

export async function removeTagFromConversation(
  phone: string,
  tagId: string,
): Promise<void> {
  await deleteApi(`/conversations/${encodeURIComponent(phone)}/tags/${tagId}`);
  revalidatePath(`/conversas/${encodeURIComponent(phone)}`);
  revalidatePath("/conversas");
}
