"use client";

import { useEffect, useState } from "react";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import type { ReasonerCheck } from "@/lib/types";

/** Read-only reasoner posture: how many contradictions the axioms would block
 *  right now. The third proof dimension — structure the LLM cannot fake. */
export function ReasonerCard() {
  const { workspaceId } = useWorkspace();
  const [data, setData] = useState<ReasonerCheck | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null); setErr(false);
    api.labReasoner(workspaceId)
      .then((d) => { if (live) (("error" in d && d.error) ? setErr(true) : setData(d)); })
      .catch(() => { if (live) setErr(true); });
    return () => { live = false; };
  }, [workspaceId]);

  if (err || !data) return null;
  if (data.axioms_checked === 0) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-navy-100 bg-white px-4 py-3 text-[12px] text-subtle">
        <ShieldCheck size={15} className="text-navy-300" />
        No axioms defined yet — add disjoint / cardinality rules in Model to let
        the reasoner enforce them.
      </div>
    );
  }
  const blocked = data.blocked;
  const clean = blocked === 0;
  return (
    <div
      className={
        "flex items-center gap-3 rounded-xl border px-4 py-3 " +
        (clean ? "border-emerald-200 bg-emerald-50/50"
               : "border-amber-200 bg-amber-50/60")
      }
    >
      {clean ? <ShieldCheck size={18} className="flex-none text-emerald-600" />
             : <ShieldAlert size={18} className="flex-none text-amber-600" />}
      <div className="text-[12.5px] text-navy-800">
        <b>{data.axioms_checked}</b> axiom{data.axioms_checked === 1 ? "" : "s"}{" "}
        enforced across <b>{data.entities_scanned}</b> entities —{" "}
        {clean ? (
          <span className="text-emerald-700">no contradictions; the ontology is consistent.</span>
        ) : (
          <span className="text-amber-700">
            <b>{blocked}</b> contradiction{blocked === 1 ? "" : "s"} the reasoner
            blocks that a text-only answer would let through.
          </span>
        )}
      </div>
    </div>
  );
}
