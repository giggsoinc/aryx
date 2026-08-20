"use client";

import { BriefBuilder } from "@/components/brief/BriefBuilder";
import type { Brief } from "@/lib/types";
import { StepShell } from "./StepShell";

interface Props {
  workspaceId: number;
  onDone: (brief: Brief) => void;
  onSkip: () => void;
  onBack?: () => void;
}

/**
 * Wizard step 1 — the customer brief, captured BEFORE any upload.
 *
 * This is the anchor of the whole run: what you write here steers what the
 * extractors look for during ingestion and what the dashboard is built to
 * answer. Soft gate — you may skip, and Aryx will infer a brief from the
 * data instead, but an inferred brief only ever reflects your column names,
 * never your goal.
 */
export function BriefStep({ workspaceId, onDone, onSkip, onBack }: Props) {
  return (
    <StepShell progress={15}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        First, tell Aryx what world it&apos;s&nbsp;entering.
      </h1>
      <p className="mb-8 mt-3 max-w-lg text-center text-[14px] text-subtle">
        Drop a document or type one sentence — Aryx drafts the whole brief and
        you just correct it. This grounds everything ingested next, and it is
        what your dashboard will be built to answer.
      </p>
      <BriefBuilder
        workspaceId={workspaceId}
        submitLabel="Looks right — continue →"
        onSubmitted={onDone}
        onSkip={onSkip}
      />
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="focus-ring mt-6 text-[12px] text-subtle hover:text-navy-700"
        >
          &larr; Back
        </button>
      )}
    </StepShell>
  );
}
