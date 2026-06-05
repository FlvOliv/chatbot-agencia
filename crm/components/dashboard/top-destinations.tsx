import type { TopDestination } from "@/lib/types";

interface Props {
  data: TopDestination[];
}

export function TopDestinations({ data }: Props) {
  if (!data || data.length === 0) {
    return (
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Sem destinos suficientes ainda — eles aparecem quando a Malu fechar
        briefings.
      </p>
    );
  }

  const max = Math.max(...data.map((d) => d.count), 1);

  return (
    <ul className="space-y-2.5">
      {data.map((d) => {
        const width = Math.max(4, Math.round((d.count / max) * 100));
        const pct = Math.round(d.pct * 100);
        return (
          <li key={d.destination}>
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate font-medium text-zinc-800 dark:text-zinc-200">
                {d.destination}
              </span>
              <span className="shrink-0 tabular-nums text-zinc-500 dark:text-zinc-400">
                {d.count} · {pct}%
              </span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-900">
              <div
                className="h-full rounded-full bg-emerald-500/80 dark:bg-emerald-400/70"
                style={{ width: `${width}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
