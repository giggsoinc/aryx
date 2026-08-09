"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/brand/Header";
import { Composer } from "@/components/ask/Composer";
import { MessageList } from "@/components/ask/MessageList";
import { FollowupChips } from "@/components/ask/FollowupChips";
import { WorkspacePeek } from "@/components/ask/WorkspacePeek";
import { api } from "@/lib/api";
import { streamReveal } from "@/lib/stream";
import { useWorkspace } from "@/lib/workspace";
import type { ChatTurn, Citation } from "@/lib/types";

// Starters tuned for the demo workspace (Customer · Site · Device · Agent · Ticket).
// Each names a specific kind of record or a known field so term extraction
// always has a noun to lock onto.
const STARTERS = [
  "Show me 5 Customers",
  "Which Agents have resolved the most Tickets?",
  "What firmware versions appear most often on Devices?",
  "Tell me about the Customer NetOps Atlantic",
];

const FOLLOWUPS = [
  "What else do we know about that Customer?",
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

  // First-run redirect: empty workspace → guided setup. "Empty" means
  // zero records, regardless of whether stub types exist.
  const [isEmptyWorkspace, setIsEmptyWorkspace] =
    useState<boolean | null>(null);
  useEffect(() => {
    api.getOntology(workspaceId).then((d) => {
      const isEmpty = (d.entity_count || 0) === 0;
      setIsEmptyWorkspace(isEmpty);
      if (isEmpty && turns.length === 0) router.replace("/start");
    }).catch(() => setIsEmptyWorkspace(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

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
              Questions naming a specific kind of record or an entity work
              best. Try one of these to see how citations work.
            </p>
            <div className="mt-8 w-full">
              <WorkspacePeek workspaceId={workspaceId} />
            </div>
            <div className="mt-2 w-full max-w-prose">
              <FollowupChips
                prompts={STARTERS}
                onPick={(p) => send(p)}
                className="justify-center"
              />
            </div>
          </div>
        ) : (
          <div className="flex-1">
            <WorkspacePeek workspaceId={workspaceId} />
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
            disabled={isEmptyWorkspace === true}
            placeholder={
              isEmptyWorkspace === true
                ? "This workspace is empty — onboard data first to ask questions."
                : turns.length === 0
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
