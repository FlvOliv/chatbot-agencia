"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";

/** Busca de conversas por nome ou telefone — atualiza o ?q= na URL (debounced). */
export function ConversasSearch() {
  const router = useRouter();
  const params = useSearchParams();
  const [, startTransition] = useTransition();
  const [q, setQ] = useState(params.get("q") ?? "");

  useEffect(() => {
    const h = setTimeout(() => {
      const next = new URLSearchParams(params.toString());
      if (q) next.set("q", q);
      else next.delete("q");
      const target = `/conversas${next.toString() ? `?${next}` : ""}`;
      startTransition(() => router.replace(target, { scroll: false }));
    }, 250);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        placeholder="Buscar por nome ou telefone"
        aria-label="Buscar conversas por nome ou telefone"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="pl-9 h-11"
        inputMode="search"
      />
    </div>
  );
}
