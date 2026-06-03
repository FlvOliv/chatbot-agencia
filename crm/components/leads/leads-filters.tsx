"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search } from "lucide-react";

const TEMPS = [
  { value: "all", label: "Todas as temperaturas" },
  { value: "urgente", label: "Urgente" },
  { value: "quente", label: "Quente" },
  { value: "morno", label: "Morno" },
  { value: "frio", label: "Frio" },
];

export function LeadsFilters() {
  const router = useRouter();
  const params = useSearchParams();
  const [, startTransition] = useTransition();
  const [q, setQ] = useState(params.get("q") ?? "");
  const temp = params.get("temp") ?? "all";

  useEffect(() => {
    const h = setTimeout(() => {
      const next = new URLSearchParams(params.toString());
      if (q) next.set("q", q);
      else next.delete("q");
      next.delete("page_size");
      const target = `/leads${next.toString() ? `?${next}` : ""}`;
      startTransition(() => router.replace(target, { scroll: false }));
    }, 250);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  function changeTemp(value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (!value || value === "all") next.delete("temp");
    else next.set("temp", value);
    next.delete("page_size");
    startTransition(() =>
      router.replace(`/leads${next.toString() ? `?${next}` : ""}`, {
        scroll: false,
      }),
    );
  }

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="relative flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400" />
        <Input
          placeholder="Buscar por nome ou telefone"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="pl-9 h-11"
          inputMode="search"
        />
      </div>
      <Select value={temp} onValueChange={changeTemp}>
        <SelectTrigger className="h-11 sm:w-56">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {TEMPS.map((t) => (
            <SelectItem key={t.value} value={t.value}>
              {t.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
