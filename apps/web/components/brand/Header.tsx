"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, MessageCircle, Network } from "lucide-react";
import { Logo } from "./Logo";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/cn";

interface HeaderProps {
  /** Optional explicit overrides; defaults to the WorkspaceProvider. */
  workspaceId?: number;
  onWorkspaceChange?: (id: number) => void;
}

/** Top bar: brand + primary nav (Ask / Model) + workspace picker. */
export function Header(props: HeaderProps) {
  const ws = useWorkspace();
  const workspaceId = props.workspaceId ?? ws.workspaceId;
  const setWorkspace = props.onWorkspaceChange ?? ws.setWorkspaceId;

  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const active = ws.workspaces.find((w) => w.id === workspaceId)
    || ws.workspaces[0];

  return (
    <header className="sticky top-0 z-20 border-b border-navy-100/80 bg-canvas/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-8">
          <Link href="/" className="focus-ring rounded-md">
            <Logo size={34} withWordmark />
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink
              href="/"
              icon={<MessageCircle size={14} />}
              label="Ask"
              active={pathname === "/"}
            />
            <NavLink
              href="/model"
              icon={<Network size={14} />}
              label="Model"
              active={pathname?.startsWith("/model") || false}
            />
          </nav>
        </div>
        <div className="relative">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="focus-ring inline-flex items-center gap-2 rounded-full border border-navy-100 bg-white px-4 py-2 text-sm font-medium text-navy-700 hover:border-navy-200 hover:bg-navy-50"
          >
            <span className="inline-block size-2 rounded-full bg-steel-500" />
            <span>{active?.name || "Default"}</span>
            <ChevronDown size={14} className="text-subtle" />
          </button>
          {open && ws.workspaces.length > 0 && (
            <ul className="absolute right-0 top-12 w-56 overflow-hidden rounded-xl border border-navy-100 bg-white shadow-soft animate-rise">
              {ws.workspaces.map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    onClick={() => { setWorkspace(w.id); setOpen(false); }}
                    className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-navy-50"
                  >
                    <span className="text-navy-800">{w.name}</span>
                    {w.id === workspaceId && (
                      <span className="size-1.5 rounded-full bg-steel-500" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </header>
  );
}

function NavLink({
  href, icon, label, active,
}: { href: string; icon: React.ReactNode; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className={cn(
        "focus-ring inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors",
        active
          ? "bg-navy-800 text-white"
          : "text-navy-600 hover:bg-navy-50 hover:text-navy-900",
      )}
    >
      {icon}
      {label}
    </Link>
  );
}
