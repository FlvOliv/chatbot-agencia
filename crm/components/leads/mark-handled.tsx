"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";

export function MarkHandled() {
  const [hint, setHint] = useState<string | null>(null);

  function onClick() {
    setHint("Funcionalidade chegando em breve.");
    setTimeout(() => setHint(null), 2500);
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={onClick} variant="outline" className="min-h-11">
        <Check className="size-4" /> Marcar como atendido
      </Button>
      {hint && (
        <span className="text-[11px] text-zinc-500" role="status">
          {hint}
        </span>
      )}
    </div>
  );
}
