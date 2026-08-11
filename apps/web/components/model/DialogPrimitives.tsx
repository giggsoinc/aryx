"use client";

import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
  width?: number;
}

/** Shared backdrop + card chrome for the Model tab's dialogs (New type,
 *  Derive type, Link entities) — header with title/close, a body slot, a
 *  footer slot. Keeps each dialog's own file down to its actual form logic. */
export function Modal({ open, title, onClose, children, footer, width = 460 }: ModalProps) {
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
            style={{ width }}
            className="overflow-hidden rounded-2xl border border-navy-100 bg-white shadow-soft"
          >
            <header className="flex items-center justify-between border-b border-navy-100 px-5 py-3">
              <h3 className="font-display text-[1.05rem] text-navy-900">{title}</h3>
              <button
                onClick={onClose}
                className="focus-ring rounded-lg p-1 text-subtle hover:bg-navy-50"
                aria-label="Close"
              >
                <X size={15} />
              </button>
            </header>
            <div className="space-y-4 px-5 py-4">{children}</div>
            <footer className="flex items-center justify-between gap-2 border-t border-navy-100 bg-navy-50/40 px-5 py-3">
              {footer}
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Field({
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

export function Select({
  value, onChange, options, placeholder, disabled,
}: {
  value: string; onChange: (v: string) => void; options: string[];
  placeholder?: string; disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500 disabled:bg-navy-50 disabled:text-subtle"
    >
      <option value="">{placeholder || "Select…"}</option>
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

export function CheckboxGroup({
  options, selected, onToggle,
}: { options: string[]; selected: string[]; onToggle: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {options.map((opt) => (
        <label key={opt} className="flex items-center gap-1.5 text-[12px] text-navy-700">
          <input
            type="checkbox"
            checked={selected.includes(opt)}
            onChange={() => onToggle(opt)}
            className="focus-ring rounded border-navy-200"
          />
          {opt}
        </label>
      ))}
    </div>
  );
}

/** Outcome banner shared by Link entities / Derive type — a real 0-count
 *  result gets "warning" tone, never rendered as if it were success. */
export function OutcomeBanner({
  tone, children,
}: { tone: "success" | "warning" | "error"; children: React.ReactNode }) {
  const toneClass = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-800 text-[12px]",
    warning: "border-amber-200 bg-amber-50 text-amber-800 text-[12px]",
    error: "border-rose-200 bg-rose-50 text-rose-700 text-[11px]",
  }[tone];
  return <div className={`rounded-lg border px-3 py-2 ${toneClass}`}>{children}</div>;
}
