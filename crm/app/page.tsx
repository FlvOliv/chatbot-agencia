import Link from "next/link";
import { ArrowRight, Info } from "lucide-react";
import {
  getDashboardInsights,
  getDashboardMetrics,
  listLeads,
} from "@/lib/api";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { ConversationsChart } from "@/components/dashboard/conversations-chart";
import { TemperatureChart } from "@/components/dashboard/temperature-chart";
import { TopDestinations } from "@/components/dashboard/top-destinations";
import { RecentLeadCard } from "@/components/dashboard/recent-lead-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const dynamic = "force-dynamic";

const WEEKDAY_PT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

function dailyToSeries(daily: { date: string; count: number }[]) {
  return daily.map((d) => {
    const parsed = new Date(`${d.date}T00:00:00`);
    const label = Number.isNaN(parsed.getTime())
      ? d.date
      : WEEKDAY_PT[parsed.getDay()];
    return { day: label, conversas: d.count };
  });
}

export default async function DashboardPage() {
  const [metrics, insights, recent] = await Promise.all([
    getDashboardMetrics(),
    getDashboardInsights(7),
    listLeads({ page: 1, page_size: 5 }),
  ]);

  const byTemp = metrics?.by_temperature ?? {
    frio: 0,
    morno: 0,
    quente: 0,
    urgente: 0,
  };
  const hotCount = (byTemp.quente ?? 0) + (byTemp.urgente ?? 0);
  const series = insights ? dailyToSeries(insights.conversations_per_day) : [];
  const conv = insights?.conversion_rate;
  const convPct = conv ? Math.round(conv.rate * 100) : null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
          Bom dia, Lu
        </h1>
        <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
          Como a Malu trabalhou pra você hoje.
        </p>
      </header>

      {/* KPIs */}
      <section className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <KpiCard
          label="Conversas hoje"
          value={metrics?.active_conversations ?? 0}
          helper="últimas 24h"
        />
        <KpiCard
          label="Leads gerados"
          value={metrics?.leads_today ?? 0}
          helper="briefings prontos"
        />
        <KpiCard
          label="Quentes + urgentes"
          value={hotCount}
          accent={hotCount > 0 ? "emerald" : "neutral"}
          helper="aguardando você"
        />
        <KpiCard
          label="Ativas agora"
          value={metrics?.active_conversations ?? 0}
          helper="clientes em conversa"
        />
      </section>

      {!metrics && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <Info className="size-4 shrink-0 mt-0.5" />
          <span>
            Não consegui falar com o backend agora. Mostrando zeros — verifique
            se a API está rodando em <code className="font-mono">NEXT_PUBLIC_API_BASE_URL</code>.
          </span>
        </div>
      )}

      {/* Charts */}
      <section className="grid gap-4 lg:grid-cols-2">
        <Card className="border-zinc-200 dark:border-zinc-800 shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">
              Conversas nos últimos 7 dias
            </CardTitle>
          </CardHeader>
          <CardContent className="text-zinc-700 dark:text-zinc-300">
            <ConversationsChart data={series} />
          </CardContent>
        </Card>

        <Card className="border-zinc-200 dark:border-zinc-800 shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">
              Distribuição por temperatura
            </CardTitle>
          </CardHeader>
          <CardContent>
            <TemperatureChart data={byTemp} />
          </CardContent>
        </Card>
      </section>

      {/* Top destinations */}
      <section>
        <Card className="border-zinc-200 dark:border-zinc-800 shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">
              Destinos mais pedidos (7d)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <TopDestinations data={insights?.top_destinations ?? []} />
          </CardContent>
        </Card>
      </section>

      {/* Recent leads */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Últimos leads</h2>
          <Link
            href="/leads"
            className="inline-flex items-center gap-1 text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
          >
            Ver todos <ArrowRight className="size-3.5" />
          </Link>
        </div>

        {recent && recent.items.length > 0 ? (
          <ul className="space-y-2">
            {recent.items.map((lead) => (
              <li key={lead.id}>
                <RecentLeadCard lead={lead} />
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-6 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-950">
            Nenhum lead por enquanto. Quando a Malu fechar um briefing, ele aparece aqui.
          </div>
        )}
      </section>

      {conv && convPct !== null && (
        <p className="pt-2 text-center text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
          {convPct}% conversão · {conv.conversations_started} conversas ·{" "}
          {conv.leads_generated} briefings
        </p>
      )}
    </div>
  );
}
