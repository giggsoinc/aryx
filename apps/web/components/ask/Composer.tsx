"use client";

import { useEffect, useRef } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  busy?: boolean;
  placeholder?: string;
}

/** Auto-growing textarea with Enter-to-send + Cmd+K focus shortcut. */
export function Composer({
  value,
  onChange,
  onSubmit,
  disabled = false,
  busy = false,
  placeholder = "Ask Aryx about your knowledge graph…",
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [value]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled && !busy) onSubmit();
    }
  };

  return (
    <div
      className={cn(
        "group relative flex items-end rounded-2xl border bg-white p-3 shadow-soft transition-all",
        "focus-within:border-steel-500 focus-within:shadow-glow",
        disabled ? "border-navy-100 opacity-60" : "border-navy-100",
      )}
    >
      <textarea
        ref={ref}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        placeholder={placeholder}
        disabled={disabled}
        className="focus-ring max-h-60 flex-1 resize-none bg-transparent px-3 py-2 text-[15px] text-ink placeholder:text-subtle focus:outline-none"
      />
      <button
        type="button"
        onClick={onSubmit}
        disabled={disabled || busy || !value.trim()}
        aria-label="Send"
        className={cn(
          "focus-ring ml-1 inline-flex size-10 items-center justify-center rounded-xl transition-all",
          busy || !value.trim() || disabled
            ? "bg-navy-100 text-navy-300"
            : "bg-navy-800 text-white hover:bg-navy-700 active:scale-[0.97]",
        )}
      >
        {busy ? (
          <Loader2 size={18} className="animate-spin" />
        ) : (
          <ArrowUp size={18} />
        )}
      </button>
    </div>
  );
}
