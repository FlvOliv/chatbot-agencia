"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

interface Props {
  currentSize: number;
  total: number;
  step?: number;
}

export function LoadMore({ currentSize, total, step = 20 }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();

  if (currentSize >= total) return null;

  function loadMore() {
    const next = new URLSearchParams(params.toString());
    next.set("page_size", String(Math.min(currentSize + step, 100)));
    startTransition(() =>
      router.replace(`/leads?${next}`, { scroll: false }),
    );
  }

  return (
    <div className="flex justify-center pt-2">
      <Button
        variant="outline"
        onClick={loadMore}
        disabled={pending}
        className="min-h-11"
      >
        {pending ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            Carregando…
          </>
        ) : (
          `Carregar mais (${total - currentSize} restantes)`
        )}
      </Button>
    </div>
  );
}
