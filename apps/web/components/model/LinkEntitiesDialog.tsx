"use client";

import { useEffect, useState } from "react";
import { Link2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { OntologyType } from "@/lib/types";
import { Field, Modal, OutcomeBanner, Select } from "./DialogPrimitives";

interface Props {
  open: boolean;
  workspaceId: number;
  types: OntologyType[];
  onClose: () => void;
}

/** Real, data-level FK link between two already-ingested entity types —
 *  POSTs to /pipeline/link-entities (wraps orchestrate.link_entities), NOT
 *  the cosmetic /ontology/relationships edge drawn by dragging on the
 *  canvas. Match count is always shown, including a real 0 — a 0-match
 *  link never reads as silent success. */
export function LinkEntitiesDialog({ open, workspaceId, types, onClose }: Props) {
  const [sourceType, setSourceType] = useState("");
  const [sourceAttr, setSourceAttr] = useState("");
  const [targetType, setTargetType] = useState("");
  const [targetAttr, setTargetAttr] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<number | null>(null);

  useEffect(() => {
    if (open) {
      setSourceType(""); setSourceAttr(""); setTargetType(""); setTargetAttr("");
      setName(""); setError(null); setResult(null);
    }
  }, [open]);

  const sourceAttrs = types.find((t) => t.name === sourceType)?.attributes || [];
  const targetAttrs = types.find((t) => t.name === targetType)?.attributes || [];
  const canSubmit = sourceType && sourceAttr && targetType && targetAttr && name.trim();
  const missing = [
    !sourceType && "source type",
    !targetType && "target type",
    sourceType && !sourceAttr && "source attribute",
    targetType && !targetAttr && "target attribute",
    !name.trim() && "link name",
  ].filter((v): v is string => Boolean(v));

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.linkEntities(workspaceId, {
        source_type: sourceType, source_attr: sourceAttr,
        target_type: targetType, target_attr: targetAttr, name: name.trim(),
      });
      setResult(res.relationships);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Link failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Link entities"
      onClose={onClose}
      footer={
        <>
          {result === null && missing.length > 0 ? (
            <p className="text-[11px] text-subtle">Needs {missing.join(", ")} to create the link.</p>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="focus-ring rounded-lg px-3 py-1.5 text-[12px] font-medium text-navy-700 hover:bg-white"
            >
              {result !== null ? "Done" : "Cancel"}
            </button>
            <button
              onClick={submit}
              disabled={!canSubmit || busy}
              className="focus-ring inline-flex items-center gap-2 rounded-lg bg-navy-800 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
            >
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}
              Create link
            </button>
          </div>
        </>
      }
    >
      <p className="text-[12px] text-subtle">
        Creates a real foreign-key edge between already-ingested records
        (exact value matches only) — different from dragging a connection
        on the canvas, which only labels the diagram.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Source type">
          <Select value={sourceType} onChange={setSourceType}
                 options={types.map((t) => t.name)} placeholder="Contract" />
        </Field>
        <Field label="Source attribute">
          <Select value={sourceAttr} onChange={setSourceAttr}
                 options={sourceAttrs} placeholder="customer_id"
                 disabled={!sourceType} />
        </Field>
        <Field label="Target type">
          <Select value={targetType} onChange={setTargetType}
                 options={types.map((t) => t.name)} placeholder="Customer" />
        </Field>
        <Field label="Target attribute">
          <Select value={targetAttr} onChange={setTargetAttr}
                 options={targetAttrs} placeholder="id"
                 disabled={!targetType} />
        </Field>
      </div>
      <Field label="Link name" hint="snake_case, e.g. belongs_to">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="belongs_to"
          className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 font-mono text-[13px] text-navy-800 focus:border-steel-500"
        />
      </Field>
      {error && <OutcomeBanner tone="error">{error}</OutcomeBanner>}
      {result !== null && (
        <OutcomeBanner tone={result > 0 ? "success" : "warning"}>
          {result > 0
            ? `${result} edge${result === 1 ? "" : "s"} created.`
            : "0 edges created — these two attributes never matched on any real value."}
        </OutcomeBanner>
      )}
    </Modal>
  );
}
