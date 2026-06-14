"use client";

import { useRef, useState } from "react";
import { ArrowRight, Loader2, UploadCloud, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { StepShell, ExampleBox } from "./StepShell";

interface Props {
  workspaceId: number;
  onUploaded: (jobId: string | null) => void;
  onBack: () => void;
  onSkip: () => void;
}

const ACCEPT = ".pdf,.docx,.doc,.pptx,.ppt,.txt,.md,.csv,.json,.png,.jpg,.jpeg";
const MAX_PER = 2 * 1024 * 1024;
const MAX_TOTAL = 50 * 1024 * 1024;
const MAX_FILES = 50;

/** Files step — drop zone + per-file list. POSTs to /admin/ingest/file
 *  which kicks the doc pipeline (chunk → PII → embed → extract). */
export function Files({ workspaceId, onUploaded, onBack, onSkip }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = (incoming: FileList | File[] | null) => {
    if (!incoming) return;
    const next = [...files, ...Array.from(incoming)].slice(0, MAX_FILES);
    setFiles(next);
    setError(null);
  };

  const remove = (i: number) =>
    setFiles((prev) => prev.filter((_, idx) => idx !== i));

  const totalBytes = files.reduce((a, f) => a + f.size, 0);
  const tooBig = files.some((f) => f.size > MAX_PER) || totalBytes > MAX_TOTAL;

  const upload = async () => {
    if (!files.length) return;
    if (tooBig) { setError("Some files exceed the size limits."); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await api.uploadFiles(workspaceId, files);
      onUploaded(r.job_id || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <StepShell progress={70}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Drop the files you want Aryx to read.
      </h1>
      <p className="mt-3 max-w-lg text-center text-[14px] text-subtle">
        PDFs, Word docs, slides, CSVs, JSON, images. Up to 50 files, 2&nbsp;MB
        each, 50&nbsp;MB total — for now.
      </p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "mt-7 w-full max-w-2xl cursor-pointer rounded-2xl border-[1.5px] border-dashed px-6 py-10 text-center transition-all",
          dragging
            ? "border-steel-500 bg-navy-50"
            : "border-navy-200 bg-white hover:border-steel-400",
        )}
      >
        <UploadCloud size={28} className="mx-auto text-steel-500" />
        <div className="mt-2 text-[14px] font-medium text-navy-800">
          Drop files here or click to browse
        </div>
        <div className="mt-1 text-[12px] text-subtle">
          {files.length === 0
            ? "PDF · DOCX · PPTX · CSV · JSON · images"
            : `${files.length} file${files.length === 1 ? "" : "s"} ready · ${(totalBytes / 1024 / 1024).toFixed(1)} MB`}
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <ul className="mt-4 w-full max-w-2xl space-y-1.5">
          {files.map((f, i) => {
            const oversize = f.size > MAX_PER;
            return (
              <li
                key={`${f.name}-${i}`}
                className={cn(
                  "flex items-center justify-between rounded-lg border px-3 py-2 text-[12.5px]",
                  oversize ? "border-rose-200 bg-rose-50/50" : "border-navy-100 bg-white",
                )}
              >
                <span className="truncate text-navy-800">{f.name}</span>
                <span className="ml-3 flex items-center gap-3 shrink-0">
                  <span className={cn(
                    "font-mono text-[11px]",
                    oversize ? "text-rose-600" : "text-subtle",
                  )}>
                    {(f.size / 1024).toFixed(0)} KB
                  </span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); remove(i); }}
                    className="focus-ring rounded p-1 text-subtle hover:bg-navy-50 hover:text-rose-500"
                    aria-label={`Remove ${f.name}`}
                  >
                    <X size={12} />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {error && (
        <div className="mt-3 w-full max-w-2xl rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {error}
        </div>
      )}

      <div className="mt-7 flex w-full max-w-2xl items-center justify-between gap-3">
        <div className="flex gap-3 text-[12px] text-subtle">
          <button onClick={onBack} className="focus-ring hover:text-navy-700">← Back</button>
          <button onClick={onSkip} className="focus-ring hover:text-navy-700">Skip</button>
        </div>
        <button
          type="button"
          onClick={upload}
          disabled={busy || files.length === 0 || tooBig}
          className="focus-ring inline-flex items-center gap-2 rounded-xl bg-navy-800 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          {busy ? <Loader2 size={15} className="animate-spin" />
                 : <>Upload &amp; continue <ArrowRight size={14} /></>}
        </button>
      </div>

      <ExampleBox label="What happens after upload">
        Aryx chunks each document, runs a PII screen, embeds the chunks for
        semantic search, and extracts entities into your graph. Progress shows
        on the next screen — you can leave and come back.
      </ExampleBox>
    </StepShell>
  );
}
