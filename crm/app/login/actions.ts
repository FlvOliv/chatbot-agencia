"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  SESSION_COOKIE,
  createSessionToken,
  sessionMaxAgeSeconds,
  verifyCredentials,
} from "@/lib/auth";

export type LoginState = { error: string | null };

export async function signIn(
  _prev: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const login = String(formData.get("login") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");

  const user = verifyCredentials(login, password);
  if (!user) {
    return { error: "Usuário ou senha incorretos." };
  }

  let token: string;
  try {
    token = await createSessionToken(user);
  } catch {
    return { error: "Login indisponível no momento. Avise o suporte." };
  }

  const jar = await cookies();
  jar.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: sessionMaxAgeSeconds,
  });

  // redirect() lança internamente — fica FORA do try/catch acima.
  redirect("/");
}

export async function signOut(): Promise<void> {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  redirect("/login");
}
