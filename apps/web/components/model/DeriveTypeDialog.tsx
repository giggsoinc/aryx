"use client";

import { useEffect, useState } from "react";
import { Layers, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { DeriveEntitiesResult, OntologyType } from "@/lib/types";
import { CheckboxGroup, Field, Modal, OutcomeBanner, Select } from "./DialogPrimitives";

interface Props {
  open: boolean;
  workspaceId: number;
  types: OntologyType[];
  onClose: () => void;
  onCreated: () => void;
}

/** Dedupes an already-ingested type's column into a real, populated new
 *  entity type — POSTs to /pipeline/derive-entities. A prerequisite step
 *  before Link Entities can draw real FK edges to a type that currently
 *  has no instances (e.g. a manually-stubbed empty type). Real created
 *  count is always shown, including a real 0 — never a silent success. */
export function DeriveTypeDialog({ open, workspaceId, types, onClose, onCreated }: Props) {
  const [sourceType, setSourceType] = useState("");
  const [groupByAttr, setGroupByAttr] = useState("");
  const [newTypeName, setNewTypeName] = useState("");
  const [carryAttrs, setCarryAttrs] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeriveEntitiesResult | null>(null);

  useEffect(() => {
    if (open) {
      setSourceType(""); setGroupByAttr(""); setNewTypeName("");
      setCarryAttrs([]); setError(null); setResult(null);
    }
  }, [open]);

  const sourceAttrs = types.find((t) => t.name === sourceType)?.attributes || [];
  const carryOptions = sourceAttrs.filter((a) => a !== groupByAttr);
  const canSubmit = sourceType && groupByAttr && newTypeName.trim();
  const missing = [
    !sourceType && "source type",
    sourceType && !groupByAttr && "group-by attribute",
    !newTypeName.trim() && "new type name",
  ].filter((v): v is string => Boolean(v));

  const toggleCarry = (attr: string) =>
    setCarryAttrs((prev) => prev.includes(attr) ? prev.filter((a) => a !== attr) : [...prev, attr]);

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.deriveEntities(workspaceId, {
        source_type: sourceType, group_by_attr: groupByAttr,
        new_type_name: newTypeName.trim(), carry_attrs: carryAttrs,
      });
      setResult(res);
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Derive failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Derive type"
      onClose={onClose}
      footer={
        <>
          {result === null && missing.length > 0 ? (
            <p className="text-[11px] text-subtle">Needs {missing.join(", ")} to derive the type.</p>
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
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Layers size={13} />}
              Derive type
            </button>
          </div>
        </>
      }
    >
      <p className="text-[12px] text-subtle">
        Deduplicates an already-ingested type by one column into a real,
        populated new entity type — e.g. every ContractLineItem row sharing
        a Customer Number becomes one Customer entity. Use Link entities
        afterward to draw real edges to it.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Source type">
          <Select value={sourceType} onChange={setSourceType}
                 options={types.map((t) => t.name)} placeholder="ContractLineItem" />
        </Field>
        <Field label="Group by attribute">
          <Select value={groupByAttr} onChange={setGroupByAttr}
                 options={sourceAttrs} placeholder="Customer Number"
                 disabled={!sourceType} />
        </Field>
      </div>
      <Field label="New type name" hint="Existing type names are merged, not replaced.">
        <input
          value={newTypeName}
          onChange={(e) => setNewTypeName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Customer"
          className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 font-mono text-[13px] text-navy-800 focus:border-steel-500"
        />
      </Field>
      {carryOptions.length > 0 && (
        <Field label="Carry-forward attributes (optional)">
          <CheckboxGroup options={carryOptions} selected={carryAttrs} onToggle={toggleCarry} />
        </Field>
      )}
      {error && <OutcomeBanner tone="error">{error}</OutcomeBanner>}
      {result !== null && (
        <OutcomeBanner tone={result.created > 0 ? "success" : "warning"}>
          {result.created > 0
            ? `${result.created} ${result.type} entities created from ${result.source_groups} distinct ${groupByAttr} value(s).`
            : `0 entities created — no ${sourceType} row had a value for "${groupByAttr}".`}
          {result.created > 0 && result.skipped_missing_key > 0 && (
            <span className="block text-emerald-700/80">
              {result.skipped_missing_key} source rows skipped (missing {groupByAttr}).
            </span>
          )}
        </OutcomeBanner>
      )}
    </Modal>
  );
}
