"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Plus, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

interface Props {
  open: boolean;
  workspaceId: number;
  onClose: () => void;
  onCreated: () => void;
}

/** Minimal modal: name + comma-separated attrs → POST /ontology/types. */
export function NewTypeDialog({ open, workspaceId, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [attrs, setAttrs] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) { setName(""); setAttrs(""); setError(null); }
  }, [open]);

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const list = attrs.split(",").map((s) => s.trim()).filter(Boolean);
      await api.createType(workspaceId, name.trim(), list);
      onCreated();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-30 flex items-center justify-center bg-navy-950/30 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="w-[420px] overflow-hidden rounded-2xl border border-navy-100 bg-white shadow-soft"
          >
            <header className="flex items-center justify-between border-b border-navy-100 px-5 py-3">
              <h3 className="font-display text-[1.05rem] text-navy-900">
                New entity type
              </h3>
              <button
                onClick={onClose}
                className="focus-ring rounded-lg p-1 text-subtle hover:bg-navy-50"
                aria-label="Close"
              >
                <X size={15} />
              </button>
            </header>
            <div className="space-y-4 px-5 py-4">
              <Field label="Name" hint="Singular, PascalCase (e.g. Customer)">
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                  placeholder="Customer"
                  className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[14px] text-navy-800 focus:border-steel-500"
                />
              </Field>
              <Field
                label="Attributes"
                hint="Comma-separated. You can add more later."
              >
                <input
                  value={attrs}
                  onChange={(e) => setAttrs(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                  placeholder="name, region, segment"
                  className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 font-mono text-[13px] text-navy-800 focus:border-steel-500"
                />
              </Field>
              {error && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
                  {error}
                </div>
              )}
            </div>
            <footer className="flex items-center justify-end gap-2 border-t border-navy-100 bg-navy-50/40 px-5 py-3">
              <button
                onClick={onClose}
                className="focus-ring rounded-lg px-3 py-1.5 text-[12px] font-medium text-navy-700 hover:bg-white"
              >
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={!name.trim() || busy}
                className="focus-ring inline-flex items-center gap-2 rounded-lg bg-navy-800 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
              >
                {busy ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Plus size={13} />
                )}
                Create
              </button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Field({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-[11px] uppercase tracking-wider text-subtle">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11px] text-subtle">{hint}</p>}
    </div>
  );
}
