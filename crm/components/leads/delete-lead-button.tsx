"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";

import { deleteLead } from "@/lib/actions";

export function DeleteLeadButton({
  numero,
  label,
}: {
  numero: number;
  label: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleDelete() {
    if (
      !window.confirm(
        `Excluir o lead #${numero} (${label})? Não apaga as conversas nem o cliente. Ação irreversível.`,
      )
    )
      return;
    setError(null);
    startTransition(async () => {
      try {
        await deleteLead(numero);
        router.push("/leads");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao excluir.");
      }
    });
  }

  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <button
        onClick={handleDelete}
        disabled={pending}
        className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/50 dark:hover:bg-red-950/40"
      >
        <Trash2 className="size-4" /> {pending ? "Excluindo…" : "Excluir"}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
