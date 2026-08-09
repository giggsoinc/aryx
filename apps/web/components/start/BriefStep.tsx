"use client";

import { BriefBuilder } from "@/components/brief/BriefBuilder";
import type { Brief } from "@/lib/types";
import { StepShell } from "./StepShell";

interface Props {
  workspaceId: number;
  onDone: (brief: Brief) => void;
  onSkip: () => void;
}

/** Wizard step 1 — cruise-control brief. Replaces the old single-box
 *  Goals + Confirm pair: documents + one sentence in, six confirmed
 *  answers out, saved before the user ever sees a source picker. */
export function BriefStep({ workspaceId, onDone, onSkip }: Props) {
  return (
    <StepShell progress={20}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        First, tell Aryx what world it's&nbsp;entering.
      </h1>
      <p className="mb-8 mt-3 max-w-lg text-center text-[14px] text-subtle">
        Drop a document or type one sentence — Aryx drafts the whole brief
        and you just correct it. This grounds everything ingested next.
      </p>
      <BriefBuilder
        workspaceId={workspaceId}
        submitLabel="Looks right — continue →"
        onSubmitted={onDone}
        onSkip={onSkip}
      />
    </StepShell>
  );
}
