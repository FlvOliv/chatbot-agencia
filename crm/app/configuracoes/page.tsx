import { Circle, ExternalLink, LogOut, Phone, Clock, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { formatPhone } from "@/lib/format";

export const dynamic = "force-dynamic";

function readEnv(key: string, fallback = ""): string {
  return process.env[key] ?? fallback;
}

export default function ConfiguracoesPage() {
  const lucianaPhone = readEnv("NEXT_PUBLIC_LUCIANA_PHONE", "");
  const aiPrimary = readEnv("NEXT_PUBLIC_AI_PRIMARY", "claude");
  const aiFallback = readEnv("NEXT_PUBLIC_AI_FALLBACK", "gemma");
  const bhStart = readEnv("NEXT_PUBLIC_BUSINESS_HOURS_START", "9");
  const bhEnd = readEnv("NEXT_PUBLIC_BUSINESS_HOURS_END", "18");

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
            <div className="mt-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Circle className="size-2.5 fill-emerald-500 text-emerald-500" strokeWidth={0} />
                <span className="text-sm font-medium">Online</span>
              </div>
              <span className="text-xs text-zinc-500">Última atividade: agora</span>
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
        Malu · Painel de insights v0.1
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
