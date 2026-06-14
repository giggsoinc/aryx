"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  ChevronDown, MessageCircle, Network, Plus, Sparkles, Loader2,
} from "lucide-react";
import { Logo } from "./Logo";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/cn";
import { HITLBadge } from "@/components/hitl/HITLBadge";

interface HeaderProps {
  /** Optional explicit overrides; defaults to the WorkspaceProvider. */
  workspaceId?: number;
  onWorkspaceChange?: (id: number) => void;
}

/** Top bar: brand + primary nav + workspace picker. The picker dropdown
 *  ITSELF hosts the "create workspace" form inline (no modal, no z-index
 *  surprises with backdrop-blur containing-block traps). */
export function Header(props: HeaderProps) {
  const ws = useWorkspace();
  const router = useRouter();
  const workspaceId = props.workspaceId ?? ws.workspaceId;
  const setWorkspace = props.onWorkspaceChange ?? ws.setWorkspaceId;

  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const active = ws.workspaces.find((w) => w.id === workspaceId)
    || ws.workspaces[0];

  // Hide the HITL bell during the wizard (no ingest has run yet, no
  // questions can exist) and when the active workspace has no entities.
  const onWizard = pathname?.startsWith("/start") || false;
  const showBell = !onWizard && !!active;

  return (
    <header className="sticky top-0 z-20 border-b border-navy-100/80 bg-canvas/85">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-8">
          <Link href="/" className="focus-ring rounded-md">
            <Logo size={34} withWordmark />
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink href="/" icon={<MessageCircle size={14} />} label="Ask"
                      active={pathname === "/"} />
            <NavLink href="/model" icon={<Network size={14} />} label="Model"
                      active={pathname?.startsWith("/model") || false} />
            <NavLink href="/start" icon={<Sparkles size={14} />} label="Onboard"
                      active={pathname?.startsWith("/start") || false} />
          </nav>
        </div>
        <div className="flex items-center gap-2">
          {showBell && <HITLBadge />}
          <WorkspacePicker
            workspaces={ws.workspaces}
            activeId={workspaceId}
            activeName={active?.name}
            open={open}
            onToggle={() => setOpen((v) => !v)}
            onSelect={(id) => { setWorkspace(id); setOpen(false); }}
            onCreated={async (id) => {
              await ws.refresh();
              setWorkspace(id);
              setOpen(false);
              router.push("/start");
            }}
          />
        </div>
      </div>
    </header>
  );
}

interface PickerProps {
  workspaces: { id: number; name: string }[];
  activeId: number;
  activeName?: string;
  open: boolean;
  onToggle: () => void;
  onSelect: (id: number) => void;
  onCreated: (id: number) => void;
}

/** Trigger button + dropdown panel — when "create" is clicked the dropdown
 *  morphs into an inline form, NO separate modal. */
function WorkspacePicker({
  workspaces, activeId, activeName, open, onToggle, onSelect, onCreated,
}: PickerProps) {
  const [mode, setMode] = useState<"list" | "create">("list");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => { setMode("list"); setName(""); setDesc(""); setError(null); };

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true); setError(null);
    try {
      const w = await api.createWorkspace(name.trim(), desc.trim());
      onCreated(w.id);
      reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => { if (open) reset(); onToggle(); }}
        className="focus-ring inline-flex items-center gap-2 rounded-full border border-navy-100 bg-white px-4 py-2 text-sm font-medium text-navy-700 hover:border-navy-200 hover:bg-navy-50"
      >
        <span className="inline-block size-2 rounded-full bg-steel-500" />
        <span>{activeName || "Default"}</span>
        <ChevronDown size={14} className="text-subtle" />
      </button>
      {open && (
        <div className="absolute right-0 top-12 w-72 overflow-hidden rounded-xl border border-navy-100 bg-white shadow-soft animate-rise">
          {mode === "list" ? (
            <ul>
              {workspaces.map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(w.id)}
                    className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-navy-50"
                  >
                    <span className="text-navy-800">{w.name}</span>
                    {w.id === activeId && (
                      <span className="size-1.5 rounded-full bg-steel-500" />
                    )}
                  </button>
                </li>
              ))}
              <li className="border-t border-navy-100">
                <button
                  type="button"
                  onClick={() => setMode("create")}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-[13px] font-medium text-steel-600 hover:bg-navy-50"
                >
                  <Plus size={14} /> New workspace…
                </button>
              </li>
            </ul>
          ) : (
            <div className="space-y-3 p-4">
              <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-700">
                Create a workspace
              </div>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="Name (e.g. Sales Pipeline)"
                className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
              />
              <input
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="What it's for (optional)"
                className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[12px] text-navy-800 focus:border-steel-500"
              />
              {error && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-700">
                  {error}
                </div>
              )}
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={reset}
                  className="focus-ring rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-navy-700 hover:bg-navy-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={submit}
                  disabled={!name.trim() || busy}
                  className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
                >
                  {busy ? <Loader2 size={12} className="animate-spin" />
                         : <Plus size={12} />}
                  Create &amp; open setup
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
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
        active ? "bg-navy-800 text-white"
                : "text-navy-600 hover:bg-navy-50 hover:text-navy-900",
      )}
    >
      {icon}
      {label}
    </Link>
  );
}
