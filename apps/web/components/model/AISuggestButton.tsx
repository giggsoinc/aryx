"use client";

import { useState } from "react";
import { Sparkles, Loader2, Plus, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

interface Props {
  workspaceId: number;
  typeName: string;
  existing: string[];
  onAccept: (attr: string) => void;
}

/** Inspector AI button: calls /ontology/assist/suggest-attrs and shows
 *  proposed attribute names as chips the user can accept individually. */
export function AISuggestButton({
  workspaceId, typeName, existing, onAccept,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.suggestAttrs(workspaceId, typeName, existing);
      setSuggestions(result.attributes);
      setRationale(result.rationale);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Suggestion failed");
    } finally {
      setBusy(false);
    }
  };

  const accept = (a: string) => {
    onAccept(a);
    setSuggestions((prev) => prev.filter((x) => x !== a));
  };

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={ask}
        disabled={busy}
        className={cn(
          "focus-ring inline-flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[12px] font-medium transition-colors",
          suggestions.length > 0
            ? "border border-navy-100 bg-white text-navy-700 hover:bg-navy-50"
            : "border border-dashed border-navy-200 text-navy-600 hover:border-steel-400 hover:bg-navy-50",
        )}
      >
        {busy ? (
          <Loader2 size={13} className="animate-spin" />
        ) : (
          <Sparkles size={13} />
        )}
        {suggestions.length > 0 ? "Suggest more" : "AI: suggest attributes"}
      </button>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
          {error}
        </div>
      )}

      <AnimatePresence>
        {suggestions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="space-y-2 rounded-xl border border-navy-100 bg-navy-50/60 p-3"
          >
            {rationale && (
              <p className="text-[11px] italic text-subtle">{rationale}</p>
            )}
            <ul className="flex flex-wrap gap-1.5">
              {suggestions.map((a) => (
                <li
                  key={a}
                  className="group inline-flex items-center gap-1 rounded-full border border-navy-100 bg-white pl-3 pr-1 py-0.5 font-mono text-[11px] text-navy-700 shadow-soft"
                >
                  <span>{a}</span>
                  <button
                    type="button"
                    onClick={() => accept(a)}
                    title="Add this attribute"
                    className="focus-ring inline-flex size-5 items-center justify-center rounded-full text-emerald-600 hover:bg-emerald-50"
                  >
                    <Plus size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setSuggestions((prev) =>
                      prev.filter((x) => x !== a))}
                    title="Dismiss"
                    className="focus-ring inline-flex size-5 items-center justify-center rounded-full text-subtle hover:bg-navy-50"
                  >
                    <X size={10} />
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
