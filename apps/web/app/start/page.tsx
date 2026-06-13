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
import { Running } from "@/components/start/Running";
import { Done } from "@/components/start/Done";

type Step =
  | "intro" | "goals" | "confirm" | "sources" | "connect"
  | "running" | "done";

/** Guided setup. Single state machine, no URL routing — back/forward by
 *  state so the user always lands where they left off in a page refresh. */
export default function StartWizard() {
  const router = useRouter();
  const { workspaceId } = useWorkspace();

  const [step, setStep] = useState<Step>("intro");
  const [brief, setBrief] = useState<Brief>({});
  const [sources, setSources] = useState<SourceKind[]>(["database"]);

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
            setStep(picked.includes("database") ? "connect" : "running");
          }}
          onBack={() => setStep("confirm")}
        />
      )}

      {step === "connect" && (
        <Connect
          workspaceId={workspaceId}
          kind="postgres"
          onConnected={() => setStep("running")}
          onBack={() => setStep("sources")}
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
