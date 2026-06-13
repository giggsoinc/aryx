"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/brand/Header";
import { Composer } from "@/components/ask/Composer";
import { MessageList } from "@/components/ask/MessageList";
import { FollowupChips } from "@/components/ask/FollowupChips";
import { api } from "@/lib/api";
import { streamReveal } from "@/lib/stream";
import { useWorkspace } from "@/lib/workspace";
import type { ChatTurn, Citation } from "@/lib/types";

const STARTERS = [
  "What types of entities did you find?",
  "Show me 5 random entities and how they connect",
  "Which entities have the most relationships?",
  "Summarise this workspace in three sentences",
];

const FOLLOWUPS = [
  "Why?",
  "Show me the underlying records",
  "What's missing or weak in this data?",
];

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export default function HomePage() {
  const router = useRouter();
  const { workspaceId } = useWorkspace();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  // First-run redirect: empty workspace → guided setup.
  useEffect(() => {
    api.getOntology(workspaceId).then((d) => {
      const empty = (d.entity_count || 0) === 0 && (d.types || []).length === 0;
      if (empty) router.replace("/start");
    }).catch(() => {});
  }, [workspaceId, router]);

  const send = async (question?: string) => {
    const q = (question ?? input).trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);

    const userTurn: ChatTurn = { id: uid(), role: "user", content: q };
    const assistantId = uid();
    const placeholder: ChatTurn = {
      id: assistantId,
      role: "assistant",
      content: "",
      streaming: true,
    };
    setTurns((t) => [...t, userTurn, placeholder]);

    try {
      const resp = await api.ask(q, workspaceId);
      // Lightweight citation extraction — V1: derive from terms.
      const citations: Citation[] = (resp.terms || [])
        .slice(0, 5)
        .map((label, i) => ({ entity_id: i, label }));

      streamReveal(resp.answer, (full) => {
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId ? { ...t, content: full } : t,
          ),
        );
      }, { msPerChunk: 18, chunkSize: 5 });

      // After reveal finishes (text length / chunk_size * ms), finalise.
      const totalMs = Math.ceil(resp.answer.length / 5) * 18 + 250;
      setTimeout(() => {
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId
              ? {
                  ...t,
                  content: resp.answer,
                  citations,
                  usage: resp.usage,
                  streaming: false,
                }
              : t,
          ),
        );
        setBusy(false);
      }, totalMs);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setTurns((prev) =>
        prev.map((t) =>
          t.id === assistantId
            ? {
                ...t,
                content: `Couldn't reach the API — ${message}`,
                streaming: false,
              }
            : t,
        ),
      );
      setBusy(false);
    }
  };

  const empty = turns.length === 0;

  return (
    <div className="flex min-h-screen flex-col">
      <Header />

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-6 py-10">
        {empty ? (
          <div className="flex flex-1 flex-col items-center justify-center text-center animate-fade-in">
            <h1 className="font-display text-[2.6rem] leading-tight text-navy-900">
              Ask your knowledge graph.
            </h1>
            <p className="mt-4 max-w-md text-[15px] text-subtle">
              Aryx has read your sources, resolved the duplicates, and built a
              graph. Ask anything — the answer cites the entities it stands on.
            </p>
            <div className="mt-10 w-full max-w-prose">
              <FollowupChips
                prompts={STARTERS}
                onPick={(p) => send(p)}
                className="justify-center"
              />
            </div>
          </div>
        ) : (
          <div className="flex-1">
            <MessageList turns={turns} />
            {!busy && (
              <div className="mt-6 pl-12">
                <FollowupChips prompts={FOLLOWUPS} onPick={(p) => send(p)} />
              </div>
            )}
          </div>
        )}

        <div className="sticky bottom-6 mt-8">
          <Composer
            value={input}
            onChange={setInput}
            onSubmit={() => send()}
            busy={busy}
            placeholder={
              empty
                ? "Ask Aryx about your knowledge graph…  (⌘K to focus)"
                : "Continue the conversation…"
            }
          />
          <p className="mt-2 text-center text-[11px] text-subtle">
            Answers are grounded in the workspace's resolved entities.
            Provenance shown beneath each response.
          </p>
        </div>
      </main>
    </div>
  );
}
