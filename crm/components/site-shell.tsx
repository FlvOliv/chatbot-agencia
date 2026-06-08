"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Users, MessageCircle, Settings, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HealthStatus } from "@/lib/types";

const NAV = [
  { href: "/", label: "Início", icon: Home },
  { href: "/conversas", label: "Conversas", icon: MessageCircle },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SiteShell({
  children,
  status,
}: {
  children: React.ReactNode;
  status: HealthStatus;
}) {
  const pathname = usePathname();

  return (
    <div className="min-h-dvh flex flex-col bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100">
      <Header status={status} />

      <div className="flex flex-1 w-full">
        <aside className="hidden lg:flex w-[60px] shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 flex-col items-center py-4 gap-1 sticky top-14 self-start h-[calc(100dvh-3.5rem)]">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                aria-label={label}
                title={label}
                className={cn(
                  "size-11 grid place-items-center rounded-lg transition-colors",
                  active
                    ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900",
                )}
              >
                <Icon className="size-5" />
              </Link>
            );
          })}
        </aside>

        <main className="flex-1 min-w-0 pb-20 lg:pb-8">
          <div className="mx-auto w-full max-w-5xl px-4 py-4 sm:px-6 sm:py-6">
            {children}
          </div>
        </main>
      </div>

      <BottomNav pathname={pathname} />
    </div>
  );
}

function Header({ status }: { status: HealthStatus }) {
  const statusColor =
    status === "ok"
      ? "fill-emerald-500 text-emerald-500"
      : status === "degraded"
        ? "fill-amber-500 text-amber-500"
        : "fill-rose-500 text-rose-500";
  const statusLabel =
    status === "ok" ? "Online" : status === "degraded" ? "Instável" : "Offline";

  return (
    <header className="sticky top-0 z-30 h-14 border-b border-zinc-200 dark:border-zinc-800 bg-white/90 dark:bg-zinc-950/90 backdrop-blur supports-[backdrop-filter]:bg-white/70">
      <div className="mx-auto flex h-full max-w-5xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-base font-semibold tracking-tight">Malu</span>
          <span className="hidden sm:inline text-xs text-zinc-500">
            · Lu Milhas
          </span>
        </Link>

        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
            <Circle className={cn("size-2.5", statusColor)} strokeWidth={0} />
            <span>{statusLabel}</span>
          </span>
          <Link
            href="/configuracoes"
            aria-label="Configurações"
            className="size-11 grid place-items-center rounded-md text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
          >
            <Settings className="size-5" />
          </Link>
        </div>
      </div>
    </header>
  );
}

function BottomNav({ pathname }: { pathname: string }) {
  return (
    <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 h-16 border-t border-zinc-200 dark:border-zinc-800 bg-white/95 dark:bg-zinc-950/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
      <ul className="grid grid-cols-4 h-full">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <li key={href} className="contents">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex flex-col items-center justify-center gap-0.5 min-h-11 text-[11px] font-medium transition-colors",
                  active
                    ? "text-zinc-900 dark:text-zinc-50"
                    : "text-zinc-500 dark:text-zinc-400",
                )}
              >
                <Icon className={cn("size-5", active && "stroke-[2.25]")} />
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
