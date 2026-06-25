"use client";

import { useState, useTransition, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Plus, X } from "lucide-react";

import { createLead } from "@/lib/actions";
import type { LeadTemp } from "@/lib/types";

const TEMPS: Array<{ value: LeadTemp; label: string }> = [
  { value: "frio", label: "Frio" },
  { value: "morno", label: "Morno" },
  { value: "quente", label: "Quente" },
  { value: "urgente", label: "Urgente" },
];

const inputCls =
  "w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-500">{label}</span>
      {children}
    </label>
  );
}

export function NewLeadButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [destination, setDestination] = useState("");
  const [travelType, setTravelType] = useState("");
  const [temp, setTemp] = useState<LeadTemp | "">("");

  function close() {
    setOpen(false);
    setPhone("");
    setName("");
    setDestination("");
    setTravelType("");
    setTemp("");
    setError(null);
  }

  function handleSubmit() {
    const p = phone.trim();
    if (p.length < 5) {
      setError("Informe um telefone válido.");
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const r = await createLead({
          phone: p,
          name: name.trim() || undefined,
          destination: destination.trim() || undefined,
          travel_type: travelType.trim() || undefined,
          lead_temp: temp || undefined,
        });
        close();
        if (r.numero) router.push(`/leads/${r.numero}`);
        else router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao criar lead.");
      }
    });
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-zinc-50 hover:opacity-90 dark:bg-zinc-100 dark:text-zinc-900"
      >
        <Plus className="size-4" /> Novo lead
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
          onClick={close}
        >
          <div
            className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-950"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold">Novo lead manual</h2>
              <button
                onClick={close}
                aria-label="Fechar"
                className="rounded p-1 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="space-y-3">
              <Field label="Telefone *">
                <input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="5511999999999"
                  autoFocus
                  className={inputCls}
                />
              </Field>
              <Field label="Nome">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Destino">
                  <input
                    value={destination}
                    onChange={(e) => setDestination(e.target.value)}
                    className={inputCls}
                  />
                </Field>
                <Field label="Tipo de viagem">
                  <input
                    value={travelType}
                    onChange={(e) => setTravelType(e.target.value)}
                    className={inputCls}
                  />
                </Field>
              </div>
              <Field label="Temperatura">
                <select
                  value={temp}
                  onChange={(e) => setTemp(e.target.value as LeadTemp | "")}
                  className={inputCls}
                >
                  <option value="">—</option>
                  {TEMPS.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </Field>

              {error && <p className="text-xs text-red-600">{error}</p>}

              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={close}
                  className="rounded-lg px-3 py-1.5 text-sm text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={pending}
                  className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-zinc-50 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                >
                  {pending ? "Criando…" : "Criar lead"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
