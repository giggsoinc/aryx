"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useWorkspace } from "@/lib/workspace";
import type { Brief, SmartUnderstandResult } from "@/lib/types";
import { Intro } from "@/components/start/Intro";
import { BriefStep } from "@/components/start/BriefStep";
import { Sources, type SourceKind } from "@/components/start/Sources";
import { Connect } from "@/components/start/Connect";
import { Files } from "@/components/start/Files";
import { SmartReview } from "@/components/start/SmartReview";
import { Running } from "@/components/start/Running";
import { Done } from "@/components/start/Done";

type Step =
  | "intro" | "brief" | "sources" | "connect" | "files"
  | "smart" | "running" | "done";

/**
 * Guided setup: brief first → data → build.
 *
 * Restores the v1.5.3 ordering. The customer states what they want BEFORE
 * uploading anything, so ingestion and the dashboard are both grounded in
 * their words rather than in whatever a model inferred from column names.
 * The brief step is a SOFT gate — "skip for now" is allowed, and a skipped
 * brief is back-filled from the data (stamped `brief_source: "derived"`).
 */
export default function StartWizard() {
  const router = useRouter();
  const { workspaceId, refresh } = useWorkspace();

  const [step, setStep] = useState<Step>("intro");
  const [sources, setSources] = useState<SourceKind[]>(["files"]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [smart, setSmart] = useState<SmartUnderstandResult | null>(null);
  const [briefSkipped, setBriefSkipped] = useState(false);

  const nextSource = (completed: SourceKind) => {
    const remaining = sources.filter((s) => s !== completed);
    setSources(remaining);
    if (remaining.includes("database")) setStep("connect");
    else if (remaining.includes("files")) setStep("files");
    else if (pendingFiles.length && smart) setStep("smart");
    else setStep("running");
  };

  return (
    <>
      {step === "intro" && <Intro onStart={() => setStep("brief")} />}

      {step === "brief" && (
        <BriefStep
          workspaceId={workspaceId}
          onDone={async (_brief: Brief) => {
            // Re-read so later steps see the saved brief, not local state.
            await refresh();
            setBriefSkipped(false);
            setStep("sources");
          }}
          onSkip={() => {
            setBriefSkipped(true);
            setStep("sources");
          }}
          onBack={() => setStep("intro")}
        />
      )}

      {step === "sources" && (
        <Sources
          initial={sources}
          briefSkipped={briefSkipped}
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
          mode="understand"
          onUnderstood={(files, result) => {
            setPendingFiles(files);
            setSmart(result);
            setStep("smart");
          }}
          onUploaded={(id) => { setJobId(id); nextSource("files"); }}
          onBack={() => setStep("sources")}
          onSkip={() => nextSource("files")}
        />
      )}

      {step === "smart" && smart && (
        <SmartReview
          workspaceId={workspaceId}
          files={pendingFiles}
          result={smart}
          onBuilt={(id) => {
            setJobId(id);
            setStep("running");
          }}
          onBack={() => setStep("files")}
          onAddMore={() => setStep("files")}
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
