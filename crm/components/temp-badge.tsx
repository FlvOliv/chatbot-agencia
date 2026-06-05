import { cn } from "@/lib/utils";
import { TEMP_CLASSES, TEMP_LABEL } from "@/lib/format";
import type { LeadTemp } from "@/lib/types";

interface TempBadgeProps {
  temp: LeadTemp | null | undefined;
  className?: string;
}

export function TempBadge({ temp, className }: TempBadgeProps) {
  const t = (temp ?? "frio") as LeadTemp;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-tight",
        TEMP_CLASSES[t],
        className,
      )}
    >
      {TEMP_LABEL[t]}
    </span>
  );
}
