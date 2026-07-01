"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Users, MessageCircle, Settings, Circle, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { signOut } from "@/app/login/actions";
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
  userName,
}: {
  children: React.ReactNode;
  status: HealthStatus;
  userName?: string | null;
}) {
  const pathname = usePathname();

  // Tela de login: sem navegação/cabeçalho (ela tem layout próprio).
  if (pathname === "/login") return <>{children}</>;

  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <Header status={status} userName={userName} />

      <div className="flex flex-1 w-full">
        <aside className="hidden lg:flex w-[60px] shrink-0 border-r border-sidebar-border bg-sidebar flex-col items-center py-4 gap-1 sticky top-14 self-start h-[calc(100dvh-3.5rem)]">
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
                    ? "bg-sidebar-primary text-sidebar-primary-foreground"
                    : "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                )}
              >
                <Icon className="size-5" />
              </Link>
            );
          })}
        </aside>

        <main className="flex-1 min-w-0 pb-20 lg:pb-8">
          <div
            className={cn(
              "mx-auto w-full px-4 py-4 sm:px-6 sm:py-6",
              pathname.startsWith("/conversas") ? "max-w-7xl" : "max-w-5xl",
            )}
          >
            {children}
          </div>
        </main>
      </div>

      <BottomNav pathname={pathname} />
    </div>
  );
}

function Header({
  status,
  userName,
}: {
  status: HealthStatus;
  userName?: string | null;
}) {
  const statusColor =
    status === "ok"
      ? "fill-emerald-500 text-emerald-500"
      : status === "degraded"
        ? "fill-amber-500 text-amber-500"
        : "fill-rose-500 text-rose-500";
  const statusLabel =
    status === "ok" ? "Online" : status === "degraded" ? "Instável" : "Offline";

  return (
    <header className="sticky top-0 z-30 h-14 border-b border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="mx-auto flex h-full max-w-5xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="font-heading text-lg font-semibold tracking-tight text-gold">
            Malu
          </span>
          <span className="hidden sm:inline text-xs text-sidebar-foreground/70">
            · Lu Milhas
          </span>
        </Link>

        <div className="flex items-center gap-2 sm:gap-3">
          <span className="flex items-center gap-1.5 text-xs text-sidebar-foreground/80">
            <Circle className={cn("size-2.5", statusColor)} strokeWidth={0} />
            <span>{statusLabel}</span>
          </span>
          <Link
            href="/configuracoes"
            aria-label="Configurações"
            className="size-11 grid place-items-center rounded-md text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            <Settings className="size-5" />
          </Link>
          {userName ? (
            <div className="flex items-center gap-1 border-l border-sidebar-border pl-1.5">
              <span className="hidden text-xs text-sidebar-foreground/80 sm:inline">
                {userName}
              </span>
              <form action={signOut}>
                <button
                  type="submit"
                  aria-label="Sair"
                  title="Sair"
                  className="size-11 grid place-items-center rounded-md text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                >
                  <LogOut className="size-5" />
                </button>
              </form>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}

function BottomNav({ pathname }: { pathname: string }) {
  return (
    <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 h-16 border-t border-sidebar-border bg-sidebar/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
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
                    ? "text-gold"
                    : "text-sidebar-foreground/65",
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
