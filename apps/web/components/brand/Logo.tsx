import Image from "next/image";
import { cn } from "@/lib/cn";

interface LogoProps {
  size?: number;
  withWordmark?: boolean;
  className?: string;
}

/** Aryx mark — wolf shield, optionally with the wordmark below. */
export function Logo({ size = 40, withWordmark = false, className }: LogoProps) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <Image
        src="/aryx-logo.png"
        alt="Aryx"
        width={size}
        height={size}
        priority
        className="select-none"
      />
      {withWordmark && (
        <div className="flex flex-col leading-none">
          <span className="wordmark text-[1.05rem]">ARYX</span>
          <span className="mt-1.5 text-[0.6rem] uppercase tracking-[0.22em] text-subtle">
            A Fortress of Structured Knowledge
          </span>
        </div>
      )}
    </div>
  );
}
