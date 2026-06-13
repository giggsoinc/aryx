"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, MessageSquareWarning, CheckCircle2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { IngestQuestion } from "@/lib/types";
import { cn } from "@/lib/cn";

interface Props {
  open: boolean;
  workspaceId: number;
  onClose: () => void;
  onAnswered?: () => void;
}

/** Side drawer listing pending HITL ingest questions. Answer here unblocks
 *  the pipeline. Cards expand inline; suggested answer pre-fills. */
export function HITLDrawer({ open, workspaceId, onClose, onAnswered }: Props) {
  const [items, setItems] = useState<IngestQuestion[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getIngestQuestions(workspaceId, "pending");
      setItems(data);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const answer = async (q: IngestQuestion, value: string) => {
    await api.answerIngestQuestion(q.id, value, "ui");
    onAnswered?.();
    load();
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-30 bg-navy-950/20 backdrop-blur-sm"
          />
          <motion.aside
            initial={{ x: 480, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 480, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-0 z-40 flex h-screen w-[440px] flex-col border-l border-navy-100 bg-white shadow-soft"
          >
            <header className="flex items-center justify-between border-b border-navy-100 px-5 py-4">
              <div className="flex items-center gap-2">
                <MessageSquareWarning size={16} className="text-amber-500" />
                <h2 className="font-display text-[1.1rem] text-navy-900">
                  Questions for you
                </h2>
                {items.length > 0 && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                    {items.length}
                  </span>
                )}
              </div>
              <button
                onClick={onClose}
                className="focus-ring rounded-lg p-1 text-subtle hover:bg-navy-50"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </header>
            <p className="border-b border-navy-100 px-5 py-3 text-[12px] text-subtle">
              Aryx pauses ingest when it needs a human call. Answer here to
              unblock the pipeline.
            </p>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {loading ? (
                <Loading />
              ) : items.length === 0 ? (
                <Empty />
              ) : (
                <ul className="space-y-3">
                  {items.map((q) => (
                    <QuestionCard
                      key={q.id}
                      question={q}
                      onAnswer={(v) => answer(q, v)}
                    />
                  ))}
                </ul>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function QuestionCard({
  question, onAnswer,
}: { question: IngestQuestion; onAnswer: (v: string) => Promise<void> }) {
  const [value, setValue] = useState(question.suggested || "");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!value.trim()) return;
    setBusy(true);
    try { await onAnswer(value.trim()); } finally { setBusy(false); }
  };
  return (
    <li className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
      <div className="flex items-start gap-2">
        <span className="rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-700">
          {question.kind.replace(/_/g, " ")}
        </span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-navy-800">
        {question.prompt}
      </p>
      {question.options && question.options.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {question.options.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setValue(opt)}
              className={cn(
                "focus-ring rounded-full border px-3 py-1 text-[11px] font-medium transition-colors",
                value === opt
                  ? "border-steel-500 bg-navy-800 text-white"
                  : "border-navy-100 bg-white text-navy-700 hover:bg-navy-50",
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
      <div className="mt-3 flex items-center gap-2">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Your answer…"
          className="focus-ring flex-1 rounded-lg border border-navy-100 bg-white px-3 py-1.5 text-[13px] text-navy-800 focus:border-steel-500"
        />
        <button
          onClick={submit}
          disabled={!value.trim() || busy}
          className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
          Answer
        </button>
      </div>
      {question.suggested && (
        <p className="mt-1.5 text-[10px] text-subtle">
          AI suggestion: <span className="font-medium">{question.suggested}</span>
        </p>
      )}
    </li>
  );
}

function Empty() {
  return (
    <div className="rounded-xl border border-dashed border-navy-200 px-5 py-10 text-center">
      <CheckCircle2 size={20} className="mx-auto text-emerald-500" />
      <p className="mt-2 text-[13px] text-navy-700">All caught up.</p>
      <p className="mt-1 text-[11px] text-subtle">
        Aryx has no pending questions for this workspace.
      </p>
    </div>
  );
}

function Loading() {
  return (
    <div className="flex items-center justify-center py-10 text-subtle">
      <Loader2 size={18} className="animate-spin" />
    </div>
  );
}
