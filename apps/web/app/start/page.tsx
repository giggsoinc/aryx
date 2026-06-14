"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useWorkspace } from "@/lib/workspace";
import type { Brief } from "@/lib/types";
import { Intro } from "@/components/start/Intro";
import { Goals } from "@/components/start/Goals";
import { Confirm } from "@/components/start/Confirm";
import { Sources, type SourceKind } from "@/components/start/Sources";
import { Connect } from "@/components/start/Connect";
import { Files } from "@/components/start/Files";
import { Running } from "@/components/start/Running";
import { Done } from "@/components/start/Done";

type Step =
  | "intro" | "goals" | "confirm" | "sources" | "connect" | "files"
  | "running" | "done";

/** Guided setup state machine. Loops through every picked source kind:
 *  Database → Connect, Files → Files upload step. Manual is informational
 *  for now (Inspector on /model handles manual type creation). */
export default function StartWizard() {
  const router = useRouter();
  const { workspaceId } = useWorkspace();

  const [step, setStep] = useState<Step>("intro");
  const [brief, setBrief] = useState<Brief>({});
  const [sources, setSources] = useState<SourceKind[]>(["database"]);

  /** After a source completes, advance through any remaining picked
   *  sources before flipping to "running". */
  const nextSource = (completed: SourceKind) => {
    const remaining = sources.filter((s) => s !== completed);
    setSources(remaining);
    if (remaining.includes("database")) setStep("connect");
    else if (remaining.includes("files")) setStep("files");
    else setStep("running");
  };

  return (
    <>
      {step === "intro" && <Intro onStart={() => setStep("goals")} />}

      {step === "goals" && (
        <Goals
          workspaceId={workspaceId}
          onDrafted={(b) => { setBrief(b); setStep("confirm"); }}
          onSkip={() => setStep("sources")}
        />
      )}

      {step === "confirm" && (
        <Confirm
          workspaceId={workspaceId}
          brief={brief}
          onConfirm={() => setStep("sources")}
          onBack={() => setStep("goals")}
        />
      )}

      {step === "sources" && (
        <Sources
          initial={sources}
          onContinue={(picked) => {
            setSources(picked);
            if (picked.includes("database")) setStep("connect");
            else if (picked.includes("files")) setStep("files");
            else setStep("running");
          }}
          onBack={() => setStep("confirm")}
        />
      )}

      {step === "connect" && (
        <Connect
          workspaceId={workspaceId}
          kind="postgres"
          onConnected={() => nextSource("database")}
          onBack={() => setStep("sources")}
        />
      )}

      {step === "files" && (
        <Files
          workspaceId={workspaceId}
          onUploaded={() => nextSource("files")}
          onBack={() => setStep("sources")}
          onSkip={() => nextSource("files")}
        />
      )}

      {step === "running" && (
        <Running
          workspaceId={workspaceId}
          onDone={() => setStep("done")}
          onSkip={() => router.push("/model")}
        />
      )}

      {step === "done" && <Done workspaceId={workspaceId} />}
    </>
  );
}
