/**
 * Login simples do painel — 2 usuários (Flávio + Lu).
 *
 * Sem biblioteca externa: a sessão é um cookie assinado com HMAC-SHA256 via
 * Web Crypto (`crypto.subtle`), que funciona tanto no middleware (edge) quanto
 * nos server actions (node). As senhas ficam em variáveis de ambiente (Vercel),
 * nunca no código.
 *
 * Regra das senhas (você segue ao criar no Vercel): mín. 8 caracteres, com pelo
 * menos 1 maiúscula, 1 número e 1 caractere especial.
 */

export const SESSION_COOKIE = "malu_session";
const SESSION_DAYS = 30;
export const sessionMaxAgeSeconds = SESSION_DAYS * 24 * 60 * 60;

export type SessionUser = { login: string; name: string };

type PanelUser = { login: string; name: string; passwordEnv: string };

// Usuários fixos (login + nome no código; a SENHA vem da variável de ambiente).
const USERS: PanelUser[] = [
  { login: "flavio", name: "Flávio", passwordEnv: "FLAVIO_PASSWORD" },
  { login: "lu", name: "Lu", passwordEnv: "LU_PASSWORD" },
];

const encoder = new TextEncoder();

function getSecret(): string | null {
  return process.env.AUTH_SECRET || null;
}

// Comparação em tempo constante (evita vazar info por timing).
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function bytesToB64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlToBytes(input: string): Uint8Array {
  let s = input.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4 ? 4 - (s.length % 4) : 0;
  s += "=".repeat(pad);
  const bin = atob(s);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function hmac(data: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(data));
  return bytesToB64url(new Uint8Array(sig));
}

/** Confere usuário + senha contra as variáveis de ambiente. */
export function verifyCredentials(
  login: string,
  password: string,
): SessionUser | null {
  const user = USERS.find((u) => u.login === login);
  if (!user || !password) return null;
  const expected = process.env[user.passwordEnv];
  if (!expected || !safeEqual(password, expected)) return null;
  return { login: user.login, name: user.name };
}

/** Cria o token de sessão assinado (payload.assinatura). */
export async function createSessionToken(user: SessionUser): Promise<string> {
  const secret = getSecret();
  if (!secret) throw new Error("AUTH_SECRET não configurada");
  const exp = Date.now() + sessionMaxAgeSeconds * 1000;
  const payload = bytesToB64url(
    encoder.encode(JSON.stringify({ login: user.login, name: user.name, exp })),
  );
  const sig = await hmac(payload, secret);
  return `${payload}.${sig}`;
}

/** Valida o token (assinatura + expiração). Retorna o usuário ou null. */
export async function verifySessionToken(
  token: string | undefined | null,
): Promise<SessionUser | null> {
  const secret = getSecret();
  if (!token || !secret) return null;
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return null;
  const expected = await hmac(payload, secret);
  if (!safeEqual(sig, expected)) return null;
  try {
    const obj = JSON.parse(new TextDecoder().decode(b64urlToBytes(payload)));
    if (!obj.exp || Date.now() > obj.exp) return null;
    return { login: String(obj.login), name: String(obj.name) };
  } catch {
    return null;
  }
}
