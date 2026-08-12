"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useWorkspace } from "@/lib/workspace";
import type { SmartUnderstandResult } from "@/lib/types";
import { Intro } from "@/components/start/Intro";
import { Sources, type SourceKind } from "@/components/start/Sources";
import { Connect } from "@/components/start/Connect";
import { Files } from "@/components/start/Files";
import { SmartReview } from "@/components/start/SmartReview";
import { Running } from "@/components/start/Running";
import { Done } from "@/components/start/Done";

type Step =
  | "intro" | "sources" | "connect" | "files"
  | "smart" | "running" | "done";

/** Guided setup: data first → smart understand → build. */
export default function StartWizard() {
  const router = useRouter();
  const { workspaceId } = useWorkspace();

  const [step, setStep] = useState<Step>("intro");
  const [sources, setSources] = useState<SourceKind[]>(["files"]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [smart, setSmart] = useState<SmartUnderstandResult | null>(null);

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
      {step === "intro" && <Intro onStart={() => setStep("sources")} />}

      {step === "sources" && (
        <Sources
          initial={sources}
          onContinue={(picked) => {
            setSources(picked);
            if (picked.includes("database")) setStep("connect");
            else if (picked.includes("files")) setStep("files");
            else setStep("running");
          }}
          onBack={() => setStep("intro")}
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
