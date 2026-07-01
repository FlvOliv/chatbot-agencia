import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: number | string;
  helper?: string;
  accent?: "neutral" | "gold" | "emerald" | "blue" | "amber";
}

const ACCENTS: Record<NonNullable<KpiCardProps["accent"]>, string> = {
  neutral: "text-foreground",
  gold: "text-gold",
  emerald: "text-emerald-700 dark:text-emerald-300",
  blue: "text-blue-700 dark:text-blue-300",
  amber: "text-amber-700 dark:text-amber-300",
};

export function KpiCard({ label, value, helper, accent = "neutral" }: KpiCardProps) {
  return (
    <Card className="shadow-sm">
      <CardContent className="p-4 sm:p-5">
        <p className="text-[11px] sm:text-xs font-medium uppercase tracking-wide text-muted-foreground">
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
          <p className="mt-1 text-[11px] sm:text-xs text-muted-foreground">
            {helper}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
