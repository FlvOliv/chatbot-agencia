import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: number | string;
  helper?: string;
  accent?: "neutral" | "emerald" | "blue" | "amber";
}

const ACCENTS: Record<NonNullable<KpiCardProps["accent"]>, string> = {
  neutral: "text-zinc-900 dark:text-zinc-50",
  emerald: "text-emerald-700 dark:text-emerald-300",
  blue: "text-blue-700 dark:text-blue-300",
  amber: "text-amber-700 dark:text-amber-300",
};

export function KpiCard({ label, value, helper, accent = "neutral" }: KpiCardProps) {
  return (
    <Card className="border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 shadow-none">
      <CardContent className="p-4 sm:p-5">
        <p className="text-[11px] sm:text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          {label}
        </p>
        <p
          className={cn(
            "mt-1 font-semibold tabular-nums leading-tight",
            "text-[clamp(1.5rem,4vw+0.5rem,2.25rem)]",
            ACCENTS[accent],
          )}
        >
          {value}
        </p>
        {helper && (
          <p className="mt-1 text-[11px] sm:text-xs text-zinc-500 dark:text-zinc-400">
            {helper}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
