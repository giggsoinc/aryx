"use client";

import { useEffect, useRef } from "react";
import { Sparkles, User } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/cn";
import { Citations } from "./Citation";
import { Markdown } from "./Markdown";
import type { ChatTurn } from "@/lib/types";

interface Props {
  turns: ChatTurn[];
}

/** Conversation transcript — alternating user / assistant turns. */
export function MessageList({ turns }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, turns[turns.length - 1]?.content]);

  return (
    <div className="flex flex-col gap-7">
      {turns.map((t) => (
        <motion.div
          key={t.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className={cn(
            "flex gap-4",
            t.role === "user" ? "flex-row-reverse" : "flex-row",
          )}
        >
          <div
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-full",
              t.role === "user"
                ? "bg-navy-800 text-white"
                : "bg-navy-50 text-steel-500",
            )}
          >
            {t.role === "user" ? <User size={15} /> : <Sparkles size={15} />}
          </div>
          <div
            className={cn(
              "max-w-prose",
              t.role === "user" ? "text-right" : "text-left",
            )}
          >
            <div
              className={cn(
                "inline-block rounded-2xl px-4 py-3 text-[15px] leading-relaxed",
                t.role === "user"
                  ? "bg-navy-800 text-white"
                  : "bg-white text-ink shadow-soft border border-navy-100",
                t.streaming && "caret",
              )}
            >
              {t.content ? (
                t.role === "assistant"
                  ? <Markdown>{t.content}</Markdown>
                  : t.content
              ) : (
                <span className="text-subtle italic">Thinking…</span>
              )}
            </div>
            {t.role === "assistant" && (
              <>
                {t.citations && <Citations citations={t.citations} />}
                {t.usage && (
                  <div className="mt-2 text-[11px] text-subtle">
                    {t.usage.answer_model} ·{" "}
                    {(t.usage.latency_ms / 1000).toFixed(1)}s ·{" "}
                    {t.usage.prompt_tokens + t.usage.completion_tokens} tokens
                  </div>
                )}
              </>
            )}
          </div>
        </motion.div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
