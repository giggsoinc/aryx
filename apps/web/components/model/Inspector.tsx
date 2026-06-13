"use client";

import { useEffect, useState } from "react";
import { X, CheckCircle2, GitBranch, Sparkles } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import type { Axiom, OntologyType, Rule, SurvivorshipPolicy } from "@/lib/types";
import { cn } from "@/lib/cn";

interface InspectorProps {
  type: OntologyType | null;
  workspaceId: number;
  onClose: () => void;
  onChanged: () => void;
}

type Tab = "attrs" | "survivor" | "rules" | "axioms";

/** Right-side panel: details for the selected type + its modelling layers. */
export function Inspector({
  type, workspaceId, onClose, onChanged,
}: InspectorProps) {
  const [tab, setTab] = useState<Tab>("attrs");
  const [survivor, setSurvivor] = useState<SurvivorshipPolicy>({});
  const [rules, setRules] = useState<Rule[]>([]);
  const [axioms, setAxioms] = useState<Axiom[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!type) return;
    Promise.allSettled([
      api.getSurvivorship(workspaceId).then(setSurvivor),
      api.getRules(workspaceId).then(setRules),
      api.getAxioms(workspaceId).then(setAxioms),
    ]).catch(() => {});
  }, [type, workspaceId]);

  const approve = async () => {
    if (!type) return;
    setBusy(true);
    try {
      await api.approveType(workspaceId, type.name);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const isProposed = type?.status === "proposed";
  const typeRules = rules.filter((r) => r.when_type === type?.name);
  const typeAxioms = axioms.filter((a) => a.type_name === type?.name);

  return (
    <AnimatePresence>
      {type && (
        <motion.aside
          initial={{ x: 400, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 400, opacity: 0 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="z-20 flex w-[380px] shrink-0 flex-col border-l border-navy-100 bg-white shadow-soft"
        >
          <header className="flex items-start justify-between gap-2 border-b border-navy-100 px-5 py-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="truncate font-display text-[1.2rem] text-navy-900">
                  {type.name}
                </h2>
                {isProposed ? (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                    proposed
                  </span>
                ) : (
                  <CheckCircle2 size={14} className="text-emerald-500" />
                )}
              </div>
              <p className="mt-0.5 truncate text-[11px] uppercase tracking-wider text-subtle">
                {type.parent_type ? `↳ ${type.parent_type}` : "Root class"}
                {type.source && ` · ${type.source}`}
              </p>
            </div>
            <button
              onClick={onClose}
              className="focus-ring rounded-lg p-1 text-subtle hover:bg-navy-50"
              aria-label="Close"
            >
              <X size={16} />
            </button>
          </header>

          {isProposed && (
            <button
              onClick={approve}
              disabled={busy}
              className="focus-ring m-5 mb-0 inline-flex items-center justify-center gap-2 rounded-lg bg-navy-800 px-3 py-2 text-[13px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
            >
              <CheckCircle2 size={14} /> Approve this type
            </button>
          )}

          <nav className="flex border-b border-navy-100 px-3">
            {(["attrs", "survivor", "axioms", "rules"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "focus-ring relative px-3 py-2.5 text-[12px] font-medium capitalize transition-colors",
                  tab === t ? "text-navy-900" : "text-subtle hover:text-navy-700",
                )}
              >
                {t === "attrs"
                  ? `Attributes (${type.attributes.length})`
                  : t === "survivor"
                  ? "Survivorship"
                  : t === "axioms"
                  ? `Axioms (${typeAxioms.length})`
                  : `Rules (${typeRules.length})`}
                {tab === t && (
                  <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-navy-800" />
                )}
              </button>
            ))}
          </nav>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {tab === "attrs" && <AttrsView type={type} />}
            {tab === "survivor" && (
              <SurvivorView type={type} policy={survivor} />
            )}
            {tab === "axioms" && <AxiomsView axioms={typeAxioms} />}
            {tab === "rules" && <RulesView rules={typeRules} />}
          </div>

          <footer className="border-t border-navy-100 px-5 py-3">
            <button
              type="button"
              className="focus-ring inline-flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-navy-200 px-3 py-2 text-[12px] font-medium text-navy-600 hover:border-steel-400 hover:bg-navy-50"
            >
              <Sparkles size={13} /> AI: suggest improvements (coming next)
            </button>
          </footer>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function AttrsView({ type }: { type: OntologyType }) {
  if (!type.attributes.length)
    return <Empty label="No attributes — add some, or let AI propose them." />;
  return (
    <ul className="space-y-1.5">
      {type.attributes.map((a) => (
        <li
          key={a}
          className="flex items-center justify-between rounded-lg border border-navy-100 bg-navy-50/40 px-3 py-2 font-mono text-[12px] text-navy-800"
        >
          <span>{a}</span>
          <span className="text-[10px] uppercase tracking-wider text-subtle">
            DatatypeProperty
          </span>
        </li>
      ))}
    </ul>
  );
}

function SurvivorView({
  type, policy,
}: { type: OntologyType; policy: SurvivorshipPolicy }) {
  const def = policy.default_strategy || "first_non_empty";
  return (
    <div className="space-y-3">
      <Row label="Default strategy" value={def} />
      <Row
        label="Source priority"
        value={(policy.source_priority || []).join(" → ") || "—"}
      />
      <div className="rounded-lg border border-navy-100 bg-navy-50/40 px-3 py-2.5 text-[12px] text-navy-700">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-subtle">
          Per-attribute overrides
        </div>
        {type.attributes.map((a) => (
          <div key={a} className="flex items-center justify-between py-0.5">
            <span className="font-mono text-[11px]">{a}</span>
            <span className="text-[11px] text-navy-600">
              {policy.attribute_strategies?.[a] || def}
            </span>
          </div>
        ))}
        {type.attributes.length === 0 && (
          <span className="italic text-subtle">no attributes yet</span>
        )}
      </div>
    </div>
  );
}

function AxiomsView({ axioms }: { axioms: Axiom[] }) {
  if (!axioms.length)
    return <Empty label="No axioms on this type yet." />;
  return (
    <ul className="space-y-2">
      {axioms.map((a) => (
        <li
          key={a.id}
          className="rounded-lg border border-navy-100 bg-navy-50/40 px-3 py-2 text-[12px]"
        >
          <div className="text-[10px] uppercase tracking-wider text-subtle">
            {a.kind}
          </div>
          <div className="font-mono text-navy-700">
            {JSON.stringify(a.payload)}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RulesView({ rules }: { rules: Rule[] }) {
  if (!rules.length)
    return <Empty label="No inference rules yet." />;
  return (
    <ul className="space-y-2">
      {rules.map((r) => (
        <li
          key={r.name}
          className="rounded-lg border border-navy-100 bg-navy-50/40 px-3 py-2 text-[12px]"
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold text-navy-800">{r.name}</span>
            <GitBranch
              size={11}
              className={r.enabled ? "text-emerald-500" : "text-subtle"}
            />
          </div>
          <div className="mt-1 font-mono text-[11px] text-navy-600">
            when <b>{r.attribute}</b> {r.operator} {r.value} →{" "}
            <b>{r.action}</b> {r.label || r.target_name || ""}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-navy-100 bg-navy-50/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-subtle">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-[12px] text-navy-800">{value}</div>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-navy-200 px-4 py-6 text-center text-[12px] italic text-subtle">
      {label}
    </div>
  );
}
