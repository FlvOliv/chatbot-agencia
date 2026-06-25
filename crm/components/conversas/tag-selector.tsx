"use client";

import { useState, useRef, useEffect } from "react";
import { Plus, X, Tag as TagIcon, Trash2 } from "lucide-react";

import type { Tag } from "@/lib/types";
import {
  addTagToConversation,
  removeTagFromConversation,
  createTag,
  deleteTag,
} from "@/lib/actions";
import { textOn } from "@/lib/color";

export function TagSelector({
  phone,
  currentTags,
  allTags,
}: {
  phone: string;
  currentTags: Tag[];
  allTags: Tag[];
}) {
  const [tags, setTags] = useState<Tag[]>(currentTags);
  const [catalog, setCatalog] = useState<Tag[]>(allTags);
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("#6b7280");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
        setQuery("");
      }
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const currentIds = new Set(tags.map((t) => t.id));
  const available = catalog.filter((t) => !currentIds.has(t.id));
  const filteredAvailable = query.trim()
    ? available.filter((t) =>
        t.name.toLowerCase().includes(query.trim().toLowerCase()),
      )
    : available;

  async function handleAdd(tag: Tag) {
    setLoading(tag.id);
    try {
      await addTagToConversation(phone, tag.id);
      setTags((prev) => [...prev, tag]);
    } finally {
      setLoading(null);
      if (available.length <= 1) setOpen(false);
    }
  }

  async function handleRemove(tagId: string) {
    setLoading(tagId);
    try {
      await removeTagFromConversation(phone, tagId);
      setTags((prev) => prev.filter((t) => t.id !== tagId));
    } finally {
      setLoading(null);
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setLoading("new");
    try {
      const tag = await createTag(newName.trim(), newColor);
      await addTagToConversation(phone, tag.id);
      setCatalog((prev) => [...prev, tag]);
      setTags((prev) => [...prev, tag]);
      setNewName("");
      setNewColor("#6b7280");
      setCreating(false);
      setOpen(false);
    } finally {
      setLoading(null);
    }
  }

  async function handleDeleteTag(tag: Tag) {
    if (
      !window.confirm(
        `Excluir a etiqueta "${tag.name}" do sistema? Ela some de todas as conversas.`,
      )
    )
      return;
    setLoading(tag.id);
    try {
      await deleteTag(tag.id);
      setCatalog((prev) => prev.filter((t) => t.id !== tag.id));
      setTags((prev) => prev.filter((t) => t.id !== tag.id));
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <div className="flex flex-wrap items-center gap-1.5">
        {tags.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
            style={{ background: tag.color, color: textOn(tag.color) }}
          >
            {tag.name}
            <button
              onClick={() => handleRemove(tag.id)}
              disabled={loading === tag.id}
              className="rounded-full opacity-70 hover:opacity-100 disabled:opacity-40"
              aria-label={`Remover etiqueta ${tag.name}`}
            >
              <X className="size-2.5" />
            </button>
          </span>
        ))}
        <button
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-zinc-300 px-2 py-0.5 text-[11px] text-zinc-400 hover:border-zinc-500 hover:text-zinc-600 dark:border-zinc-700 dark:hover:border-zinc-500"
        >
          <Plus className="size-2.5" /> Etiqueta
        </button>
      </div>

      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-56 rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {catalog.length > 6 && (
            <div className="border-b border-zinc-100 p-1 dark:border-zinc-800">
              <input
                autoFocus
                type="text"
                placeholder="Buscar etiqueta…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full rounded bg-transparent px-2 py-1 text-xs outline-none"
              />
            </div>
          )}
          {filteredAvailable.length > 0 ? (
            <ul className="max-h-44 overflow-y-auto p-1">
              {filteredAvailable.map((tag) => (
                <li key={tag.id} className="group flex items-center">
                  <button
                    onClick={() => handleAdd(tag)}
                    disabled={loading === tag.id}
                    className="flex flex-1 items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-800"
                  >
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ background: tag.color }}
                    />
                    {tag.name}
                  </button>
                  <button
                    onClick={() => handleDeleteTag(tag)}
                    disabled={loading === tag.id}
                    aria-label={`Excluir etiqueta ${tag.name}`}
                    title="Excluir do sistema"
                    className="shrink-0 rounded p-1 text-zinc-300 opacity-0 hover:bg-zinc-100 hover:text-red-500 group-hover:opacity-100 disabled:opacity-40 dark:hover:bg-zinc-800"
                  >
                    <Trash2 className="size-3" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-3 py-2 text-xs text-zinc-400">
              {catalog.length === 0
                ? "Nenhuma etiqueta criada ainda."
                : query.trim()
                  ? "Nada encontrado."
                  : "Todas as etiquetas já aplicadas."}
            </p>
          )}

          <div className="border-t border-zinc-100 p-1 dark:border-zinc-800">
            {!creating ? (
              <button
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <TagIcon className="size-3" /> Nova etiqueta…
              </button>
            ) : (
              <div className="space-y-1.5 p-1">
                <input
                  autoFocus
                  type="text"
                  placeholder="Nome da etiqueta"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  maxLength={50}
                  className="w-full rounded border border-zinc-200 px-2 py-1 text-xs outline-none focus:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-800"
                />
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={newColor}
                    onChange={(e) => setNewColor(e.target.value)}
                    className="size-6 cursor-pointer rounded border-0 p-0"
                    title="Cor da etiqueta"
                  />
                  <button
                    onClick={handleCreate}
                    disabled={!newName.trim() || loading === "new"}
                    className="flex-1 rounded bg-zinc-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
                  >
                    {loading === "new" ? "…" : "Criar"}
                  </button>
                  <button
                    onClick={() => setCreating(false)}
                    className="text-xs text-zinc-400 hover:text-zinc-600"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
