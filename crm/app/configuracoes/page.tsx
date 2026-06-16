import { Circle, ExternalLink, LogOut, Phone, Clock, Bot, Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { NotificationsButton } from "@/components/push/notifications-button";
import { formatPhone } from "@/lib/format";
import { getConfig, getHealthStatus } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ConfiguracoesPage() {
  // Fonte única: tudo vem do backend (/api/config), sem duplicar em NEXT_PUBLIC_*
  const [config, health] = await Promise.all([getConfig(), getHealthStatus()]);

  const lucianaPhone = config?.luciana_phone ?? "";
  const aiPrimary = config?.ai_primary ?? "—";
  const aiFallback = config?.ai_fallback ?? "—";
  const bhStart = config ? String(config.business_hours_start) : "—";
  const bhEnd = config ? String(config.business_hours_end) : "—";
  const version = config?.version ?? "0.1";
  const statusColor =
    health === "ok"
      ? "fill-emerald-500 text-emerald-500"
      : health === "degraded"
        ? "fill-amber-500 text-amber-500"
        : "fill-rose-500 text-rose-500";
  const statusLabel =
    health === "ok"
      ? "Online"
      : health === "degraded"
        ? "Instável"
        : "Offline";
  const statusHint =
    health === "ok"
      ? "Backend respondeu agora há pouco"
      : health === "degraded"
        ? "Backend respondeu, mas com erro"
        : "Backend não respondeu";

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
          Configurações
        </h1>
        <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
          Como a Malu está operando.
        </p>
      </header>

      <Card className="border-zinc-200 dark:border-zinc-800 shadow-none">
        <CardContent className="p-4 sm:p-6 space-y-4">
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Status do bot
            </h2>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Circle
                  className={`size-2.5 ${statusColor}`}
                  strokeWidth={0}
                />
                <span className="text-sm font-medium">{statusLabel}</span>
              </div>
              <span className="text-xs text-zinc-500 text-right">
                {statusHint}
              </span>
            </div>
          </section>

          <Separator />

          <Row icon={<Bot className="size-4" />} label="IA principal" value={aiPrimary} />
          <Row icon={<Bot className="size-4" />} label="IA fallback" value={aiFallback} />
          <Row
            icon={<Phone className="size-4" />}
            label="WhatsApp da Lu"
            value={lucianaPhone ? formatPhone(lucianaPhone) : "não configurado"}
            mono
          />
          <Row
            icon={<Clock className="size-4" />}
            label="Horário comercial"
            value={`${bhStart}h – ${bhEnd}h`}
          />
        </CardContent>
      </Card>

      <Card className="border-zinc-200 dark:border-zinc-800 shadow-none">
        <CardContent className="p-4 sm:p-6 space-y-3">
          <section>
            <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              <Bell className="size-3.5" /> Notificações
            </h2>
            <p className="mt-1 mb-3 text-xs text-zinc-500">
              Receba um aviso no navegador quando chegar um lead novo, mesmo com
              o painel fechado.
            </p>
            <NotificationsButton vapidPublicKey={config?.vapid_public_key} />
          </section>
        </CardContent>
      </Card>

      <Card className="border-zinc-200 dark:border-zinc-800 shadow-none">
        <CardContent className="p-4 sm:p-6 space-y-3">
          <a
            href="#"
            className="flex items-center justify-between rounded-md px-2 py-3 min-h-11 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-900"
          >
            <span className="font-medium">Documentação</span>
            <ExternalLink className="size-4 text-zinc-400" />
          </a>
          <Separator />
          <Button
            variant="ghost"
            className="w-full justify-start min-h-11 text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950"
          >
            <LogOut className="size-4" /> Sair
          </Button>
        </CardContent>
      </Card>

      <p className="text-center text-[11px] text-zinc-400">
        Painel da Malu · v{version}
      </p>
    </div>
  );
}

function Row({
  icon,
  label,
  value,
  mono = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
        <span className="text-zinc-400">{icon}</span>
        <span>{label}</span>
      </div>
      <span
        className={
          "text-sm font-medium text-right" +
          (mono ? " font-mono tabular-nums" : "")
        }
      >
        {value}
      </span>
    </div>
  );
}
