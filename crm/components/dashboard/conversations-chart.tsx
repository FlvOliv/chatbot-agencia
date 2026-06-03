"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ConversationsPoint {
  day: string;
  conversas: number;
}

interface Props {
  data: ConversationsPoint[];
}

export function ConversationsChart({ data }: Props) {
  return (
    <div className="h-[180px] sm:h-[220px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 8, right: 8, bottom: 0, left: -20 }}
        >
          <defs>
            <linearGradient id="convGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="currentColor" stopOpacity={0.25} />
              <stop offset="95%" stopColor="currentColor" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
          <XAxis
            dataKey="day"
            stroke="currentColor"
            strokeOpacity={0.3}
            fontSize={11}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            stroke="currentColor"
            strokeOpacity={0.3}
            fontSize={11}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={28}
          />
          <Tooltip
            contentStyle={{
              background: "var(--color-popover)",
              borderColor: "var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ fontWeight: 500 }}
            cursor={{ stroke: "currentColor", strokeOpacity: 0.2 }}
          />
          <Area
            type="monotone"
            dataKey="conversas"
            stroke="currentColor"
            strokeWidth={2}
            fill="url(#convGrad)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
