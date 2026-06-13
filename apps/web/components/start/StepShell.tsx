"use client";

import Image from "next/image";
import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

interface StepShellProps {
  children: React.ReactNode;
  /** Light progress hint at the top; 0 hides it. */
  progress?: number;
  className?: string;
}

/** Shared centred layout used by every wizard step. Brand mark at top,
 *  hairline progress, max-width column, generous padding. */
export function StepShell({ children, progress = 0, className }: StepShellProps) {
  return (
    <div className="min-h-screen flex flex-col items-center bg-canvas">
      <header className="w-full border-b border-navy-100/70 bg-canvas/80 backdrop-blur-md">
        {progress > 0 && (
          <div className="h-1 w-full bg-navy-100/70">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(progress, 100)}%` }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="h-full bg-navy-800"
            />
          </div>
        )}
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <Image
              src="/aryx-logo.png"
              alt="Aryx"
              width={34}
              height={34}
              priority
            />
            <div className="flex flex-col leading-none">
              <span className="wordmark text-[1.02rem]">ARYX</span>
              <span className="mt-1.5 text-[0.6rem] uppercase tracking-[0.22em] text-subtle">
                A Fortress of Structured Knowledge
              </span>
            </div>
          </div>
          {progress > 0 && (
            <span className="text-[11px] uppercase tracking-wider text-subtle">
              Guided setup
            </span>
          )}
        </div>
      </header>
      <motion.main
        key={progress}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        className={cn(
          "flex w-full max-w-3xl flex-1 flex-col items-center px-6 py-12",
          className,
        )}
      >
        {children}
      </motion.main>
    </div>
  );
}

/** Single steel-bordered inline-example callout used across screens. */
export function ExampleBox({
  label = "Example", children,
}: { label?: string; children: React.ReactNode }) {
  return (
    <div className="mt-4 w-full max-w-prose rounded-r-xl border border-navy-100 border-l-[3px] border-l-steel-500 bg-white px-4 py-3 text-left">
      <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-steel-600">
        {label}
      </div>
      <div className="mt-1 text-[13px] leading-relaxed text-navy-800">
        {children}
      </div>
    </div>
  );
}
