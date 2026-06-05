"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TEMP_LABEL } from "@/lib/format";
import type { LeadTemp } from "@/lib/types";

interface Props {
  data: Record<LeadTemp, number>;
}

const COLORS: Record<LeadTemp, string> = {
  frio: "#a1a1aa",
  morno: "#60a5fa",
  quente: "#34d399",
  urgente: "#fb7185",
};

const ORDER: LeadTemp[] = ["urgente", "quente", "morno", "frio"];

export function TemperatureChart({ data }: Props) {
  const rows = ORDER.map((k) => ({
    key: k,
    label: TEMP_LABEL[k],
    value: data[k] ?? 0,
  }));

  return (
    <div className="h-[180px] sm:h-[220px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 4, left: 0 }}
          barCategoryGap={8}
        >
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="label"
            stroke="currentColor"
            strokeOpacity={0.4}
            fontSize={12}
            tickLine={false}
            axisLine={false}
            width={64}
          />
          <Tooltip
            cursor={{ fill: "currentColor", fillOpacity: 0.04 }}
            contentStyle={{
              background: "var(--color-popover)",
              borderColor: "var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <Bar dataKey="value" radius={[4, 4, 4, 4]}>
            {rows.map((r) => (
              <Cell key={r.key} fill={COLORS[r.key]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
