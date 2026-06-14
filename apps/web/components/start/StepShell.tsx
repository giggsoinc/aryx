"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/cn";
import { Header } from "@/components/brand/Header";

interface StepShellProps {
  children: React.ReactNode;
  /** Light progress hint at the top; 0 hides it. */
  progress?: number;
  className?: string;
}

/** Shared centred layout used by every wizard step. Reuses the global
 *  Header — workspace picker, primary nav (Ask / Model / Onboard), and
 *  HITL bell are visible from inside the wizard, not just outside it.
 *  Hairline progress bar sits above the header. */
export function StepShell({ children, progress = 0, className }: StepShellProps) {
  return (
    <div className="min-h-screen flex flex-col items-center bg-canvas">
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
      <Header />
      <motion.main
        key={progress}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        className={cn(
          "flex w-full max-w-3xl flex-1 flex-col items-center px-6 py-10",
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
