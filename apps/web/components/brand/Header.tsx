"use client";

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Logo } from "./Logo";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";

/** Top bar — brand + workspace picker. The workspace picker is read-only
 *  in V1; selection drives the Ask call's workspace_id. */
export function Header({
  workspaceId,
  onWorkspaceChange,
}: {
  workspaceId: number;
  onWorkspaceChange: (id: number) => void;
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]));
  }, []);

  const active = workspaces.find((w) => w.id === workspaceId) || workspaces[0];

  return (
    <header className="sticky top-0 z-20 border-b border-navy-100/80 bg-canvas/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Logo size={36} withWordmark />
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
          {open && workspaces.length > 0 && (
            <ul className="absolute right-0 top-12 w-56 overflow-hidden rounded-xl border border-navy-100 bg-white shadow-soft animate-rise">
              {workspaces.map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onWorkspaceChange(w.id);
                      setOpen(false);
                    }}
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
