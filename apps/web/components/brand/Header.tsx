"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  Activity, ChevronDown, ClipboardList, Database, FileText, FlaskConical, Gauge, Home,
  MessageCircle, Network, Plug, Plus, Settings, Loader2, Trash2,
} from "lucide-react";
import { Logo } from "./Logo";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/cn";
import { HITLBadge } from "@/components/hitl/HITLBadge";
import { JobsBadge } from "@/components/jobs/JobsBadge";

interface HeaderProps {
  workspaceId?: number;
  onWorkspaceChange?: (id: number) => void;
}

/** Top bar: brand + primary nav + workspace picker. */
export function Header(props: HeaderProps) {
  const ws = useWorkspace();
  const router = useRouter();
  const workspaceId = props.workspaceId ?? ws.workspaceId;
  const setWorkspace = props.onWorkspaceChange ?? ws.setWorkspaceId;

  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const active = ws.workspaces.find((w) => w.id === workspaceId)
    || ws.workspaces[0];

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
            <NavLink href="/" icon={<Home size={14} />} label="Home"
                      active={pathname === "/"} />
            <NavLink href="/brief" icon={<FileText size={14} />} label="Brief"
                      active={pathname?.startsWith("/brief") || false} />
            <NavLink href="/data" icon={<Database size={14} />} label="Data"
                      active={pathname?.startsWith("/data") || false} />
            <NavLink href="/model" icon={<Network size={14} />} label="Model"
                      active={pathname?.startsWith("/model") || false} />
            <NavLink href="/lab" icon={<FlaskConical size={14} />} label="Lab"
                      active={pathname?.startsWith("/lab") || false} />
            <NavLink href="/ask" icon={<MessageCircle size={14} />} label="Ask"
                      active={pathname?.startsWith("/ask") || false} />
            <NavLink href="/dashboard" icon={<ClipboardList size={14} />} label="Dashboard"
                      active={pathname === "/dashboard"} />
            <NavLink href="/dashboard-observability" icon={<Gauge size={14} />} label="Pipeline"
                      active={pathname?.startsWith("/dashboard-observability") || false} />
            <NavLink href="/mcp" icon={<Plug size={14} />} label="MCP"
                      active={pathname?.startsWith("/mcp") || false} />
            <NavLink href="/observe" icon={<Activity size={14} />} label="Observe"
                      active={pathname?.startsWith("/observe") || false} />
            <NavLink href="/settings" icon={<Settings size={14} />} label="Settings"
                      active={pathname?.startsWith("/settings") || false} />
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <JobsBadge />
          {showBell && <HITLBadge />}
          <WorkspacePicker
            workspaces={ws.workspaces}
            activeId={workspaceId}
            activeName={active?.name}
            open={open}
            onToggle={async () => {
              if (!open) await ws.refresh();
              setOpen((v) => !v);
            }}
            onSelect={(id) => {
              setWorkspace(id);
              setOpen(false);
              if (pathname?.startsWith("/start")) router.push("/");
            }}
            onCreated={async (id) => {
              await ws.refresh();
              setWorkspace(id);
              setOpen(false);
              router.push("/start");
            }}
            onDeleted={async (id) => {
              await ws.refresh();
              if (workspaceId === id) {
                setWorkspace(1);
                router.push("/");
              }
              setOpen(false);
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
  onDeleted: (id: number) => void;
}

function WorkspacePicker({
  workspaces, activeId, activeName, open, onToggle, onSelect, onCreated, onDeleted,
}: PickerProps) {
  const [mode, setMode] = useState<"list" | "create" | "delete">("list");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [deleteAck, setDeleteAck] = useState(false);
  const [deleteTyped, setDeleteTyped] = useState("");

  const reset = () => {
    setMode("list"); setName(""); setDesc(""); setError(null);
    setDeleteId(null); setDeleteAck(false); setDeleteTyped("");
  };

  useEffect(() => {
    if (!open) reset();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

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

  const confirmDelete = async () => {
    if (deleteId == null || deleteId === 1) return;
    if (!deleteAck || deleteTyped !== "DELETE") return;
    setBusy(true); setError(null);
    try {
      await api.deleteWorkspace(deleteId);
      onDeleted(deleteId);
      reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const deleteTarget = workspaces.find((w) => w.id === deleteId);

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
        <div className="absolute right-0 top-12 z-50 w-80 overflow-hidden rounded-xl border border-navy-100 bg-white shadow-soft animate-rise">
          {mode === "list" && (
            <ul>
              <li className="border-b border-navy-50 px-4 py-2 text-[10px] font-bold uppercase tracking-wide text-navy-500">
                Workspaces{workspaces.length ? ` (${workspaces.length})` : ""}
              </li>
              {workspaces.length === 0 && (
                <li className="px-4 py-3 text-[12px] text-subtle">
                  No workspaces loaded. Create one below, or open Home and refresh.
                </li>
              )}
              {workspaces.map((w) => (
                <li key={w.id} className="flex items-stretch border-b border-navy-50 last:border-0">
                  <button
                    type="button"
                    onClick={() => onSelect(w.id)}
                    className="flex min-w-0 flex-1 items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-navy-50"
                  >
                    <span className="truncate text-navy-800">{w.name}</span>
                    {w.id === activeId && (
                      <span className="ml-2 size-1.5 shrink-0 rounded-full bg-steel-500" />
                    )}
                  </button>
                  {w.id !== 1 && (
                    <button
                      type="button"
                      title="Delete workspace"
                      onClick={() => {
                        setDeleteId(w.id);
                        setDeleteAck(false);
                        setDeleteTyped("");
                        setMode("delete");
                      }}
                      className="focus-ring shrink-0 px-3 text-rose-600 hover:bg-rose-50"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
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
              <li>
                <Link
                  href="/"
                  onClick={() => { reset(); onToggle(); }}
                  className="flex w-full px-4 py-2 text-[11px] text-subtle hover:bg-navy-50 hover:text-navy-700"
                >
                  Manage on Home →
                </Link>
              </li>
            </ul>
          )}

          {mode === "create" && (
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

          {mode === "delete" && deleteTarget && (
            <div className="space-y-3 p-4 text-[12px] text-navy-800">
              <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-rose-700">
                Delete workspace
              </div>
              <p>
                Permanently delete <b>“{deleteTarget.name}”</b> and all of its
                data? This cannot be undone. Default workspace cannot be deleted.
              </p>
              <label className="flex items-start gap-2 text-[11px]">
                <input
                  type="checkbox"
                  checked={deleteAck}
                  onChange={(e) => setDeleteAck(e.target.checked)}
                  className="mt-0.5"
                />
                I understand this cannot be undone
              </label>
              <label className="block text-[11px]">
                Type <b>DELETE</b> to confirm
                <input
                  value={deleteTyped}
                  onChange={(e) => setDeleteTyped(e.target.value)}
                  className="focus-ring mt-1 w-full rounded-lg border border-rose-200 px-2 py-1.5 font-mono text-[12px]"
                  placeholder="DELETE"
                  autoComplete="off"
                />
              </label>
              {error && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-700">
                  {error}
                </div>
              )}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={reset}
                  className="focus-ring rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-navy-700 hover:bg-navy-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!deleteAck || deleteTyped !== "DELETE" || busy}
                  onClick={confirmDelete}
                  className="focus-ring rounded-lg bg-rose-800 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-rose-900 disabled:opacity-40"
                >
                  {busy ? "Deleting…" : "Delete workspace"}
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
