"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useWorkspace } from "@/lib/workspace";
import { Intro } from "@/components/start/Intro";
import { BriefStep } from "@/components/start/BriefStep";
import { Sources, type SourceKind } from "@/components/start/Sources";
import { Connect } from "@/components/start/Connect";
import { Files } from "@/components/start/Files";
import { Running } from "@/components/start/Running";
import { Done } from "@/components/start/Done";

type Step =
  | "intro" | "brief" | "sources" | "connect" | "files"
  | "running" | "done";

/** Guided setup state machine. Loops through every picked source kind:
 *  Database → Connect, Files → Files upload step. Manual is informational
 *  for now (Inspector on /model handles manual type creation). */
export default function StartWizard() {
  const router = useRouter();
  const { workspaceId } = useWorkspace();

  const [step, setStep] = useState<Step>("intro");
  const [sources, setSources] = useState<SourceKind[]>(["database"]);
  const [jobId, setJobId] = useState<string | null>(null);

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
      {step === "intro" && <Intro onStart={() => setStep("brief")} />}

      {step === "brief" && (
        <BriefStep
          workspaceId={workspaceId}
          onDone={() => setStep("sources")}
          onSkip={() => setStep("sources")}
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
          onBack={() => setStep("brief")}
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
          onUploaded={(id) => { setJobId(id); nextSource("files"); }}
          onBack={() => setStep("sources")}
          onSkip={() => nextSource("files")}
        />
      )}

      {step === "running" && (
        <Running
          workspaceId={workspaceId}
          jobId={jobId}
          onDone={() => setStep("done")}
          onSkip={() => router.push("/model")}
        />
      )}

      {step === "done" && <Done workspaceId={workspaceId} />}
    </>
  );
}
