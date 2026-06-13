"use client";

import {
  createContext, useContext, useEffect, useState, type ReactNode,
} from "react";
import { api } from "./api";
import type { Workspace } from "./types";

interface WorkspaceContext {
  workspaceId: number;
  workspaces: Workspace[];
  setWorkspaceId: (id: number) => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<WorkspaceContext | null>(null);

const STORAGE_KEY = "aryx.workspaceId";

/** Shared workspace selection across Ask, Model, and any future surface.
 *  First-time visitors land on the workspace named "Default" (typically the
 *  empty onboarding one), so the auto-redirect on / bounces them to /start.
 *  Returning users stay on whatever they last selected (localStorage). */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaceId, setWorkspaceIdState] = useState(1);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  const refresh = async () => {
    try {
      const list = await api.listWorkspaces();
      setWorkspaces(list);
    } catch {
      setWorkspaces([]);
    }
  };

  useEffect(() => {
    api.listWorkspaces().then((list) => {
      setWorkspaces(list);
      const stored = typeof window !== "undefined"
        ? localStorage.getItem(STORAGE_KEY) : null;
      if (stored) {
        const id = Number(stored);
        if (list.some((w) => w.id === id)) {
          setWorkspaceIdState(id);
          return;
        }
      }
      // First visit (or stale id): prefer the workspace literally named
      // "Default" so onboarding/test users get the wizard. Fall back to
      // first workspace, then id=1.
      const def = list.find((w) => w.name === "Default") || list[0];
      if (def) setWorkspaceIdState(def.id);
    }).catch(() => setWorkspaces([]));
  }, []);

  const setWorkspaceId = (id: number) => {
    setWorkspaceIdState(id);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, String(id));
    }
  };

  return (
    <Ctx.Provider value={{ workspaceId, workspaces, setWorkspaceId, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export function useWorkspace() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be inside <WorkspaceProvider>");
  return v;
}
