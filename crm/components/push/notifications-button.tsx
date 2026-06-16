"use client";

import { Bell, BellRing } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { subscribeToPush } from "@/lib/actions";

/** Converte a chave VAPID pública (base64url) pro formato que o navegador pede.
 *  Constrói sobre um ArrayBuffer explícito (o tipo que o PushManager exige). */
function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const arr = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) arr[i] = raw.charCodeAt(i);
  return arr;
}

type State =
  | "loading"
  | "unsupported"
  | "default"
  | "granted"
  | "denied"
  | "working";

export function NotificationsButton({
  vapidPublicKey,
}: {
  vapidPublicKey?: string;
}) {
  const [state, setState] = useState<State>("loading");

  useEffect(() => {
    if (
      !("serviceWorker" in navigator) ||
      !("PushManager" in window) ||
      !("Notification" in window)
    ) {
      setState("unsupported");
      return;
    }
    setState(Notification.permission as State);
  }, []);

  async function enable() {
    if (!vapidPublicKey) {
      alert("O push ainda não está configurado no servidor.");
      return;
    }
    setState("working");
    try {
      const reg = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;

      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState(permission as State);
        return;
      }

      const existing = await reg.pushManager.getSubscription();
      const sub =
        existing ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
        }));

      await subscribeToPush(sub.toJSON());
      setState("granted");
    } catch (err) {
      console.error("push subscribe failed", err);
      setState("default");
      alert("Não consegui ativar as notificações. Tente de novo.");
    }
  }

  if (state === "unsupported") {
    return (
      <p className="text-xs text-zinc-500">
        Este navegador não suporta notificações.
      </p>
    );
  }
  if (state === "granted") {
    return (
      <div className="flex items-center gap-2 text-sm font-medium text-emerald-600">
        <BellRing className="size-4" /> Notificações ativadas neste aparelho
      </div>
    );
  }
  if (state === "denied") {
    return (
      <p className="text-xs text-zinc-500">
        As notificações estão bloqueadas. Libere nas permissões do site (cadeado
        na barra de endereço) e recarregue.
      </p>
    );
  }

  return (
    <Button
      onClick={enable}
      disabled={state === "working" || state === "loading"}
      variant="outline"
      className="w-full justify-start min-h-11"
    >
      <Bell className="size-4" />{" "}
      {state === "working" ? "Ativando…" : "Ativar notificações neste aparelho"}
    </Button>
  );
}
