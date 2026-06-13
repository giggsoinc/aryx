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
}

const Ctx = createContext<WorkspaceContext | null>(null);

/** Shared workspace selection across Ask, Model, and any future surface. */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaceId, setWorkspaceIdState] = useState(1);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    const stored = typeof window !== "undefined"
      ? Number(localStorage.getItem("aryx.workspaceId") || "1") : 1;
    setWorkspaceIdState(stored);
    api.listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]));
  }, []);

  const setWorkspaceId = (id: number) => {
    setWorkspaceIdState(id);
    if (typeof window !== "undefined") {
      localStorage.setItem("aryx.workspaceId", String(id));
    }
  };

  return (
    <Ctx.Provider value={{ workspaceId, workspaces, setWorkspaceId }}>
      {children}
    </Ctx.Provider>
  );
}

export function useWorkspace() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be inside <WorkspaceProvider>");
  return v;
}
