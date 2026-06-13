"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Renders assistant markdown — headings, lists, bold, inline code, tables.
 *  Brand-tuned spacing + colours so it sits inside a chat bubble cleanly. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown text-[15px] leading-relaxed text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p className="mb-2 last:mb-0">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="my-2 ml-5 list-disc space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2 ml-5 list-decimal space-y-1">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold text-navy-900">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          code: ({ children, className }) => {
            const isBlock = className?.startsWith("language-");
            if (isBlock) {
              return (
                <pre className="my-2 overflow-x-auto rounded-lg bg-navy-50 px-3 py-2 font-mono text-[12px] text-navy-800">
                  <code>{children}</code>
                </pre>
              );
            }
            return (
              <code className="rounded bg-navy-50 px-1.5 py-0.5 font-mono text-[13px] text-steel-600">
                {children}
              </code>
            );
          },
          h1: ({ children }) => (
            <h1 className="mb-2 mt-3 font-display text-[1.3rem] text-navy-900">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-3 font-display text-[1.15rem] text-navy-900">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1.5 mt-2 text-[1.05rem] font-semibold text-navy-900">
              {children}
            </h3>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-steel-500 underline decoration-steel-500/30 underline-offset-2 hover:decoration-steel-500"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="min-w-full border-collapse text-[13px]">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-navy-100 bg-navy-50 px-3 py-1.5 text-left font-semibold text-navy-800">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-navy-100 px-3 py-1.5 text-navy-700">
              {children}
            </td>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-steel-500 bg-navy-50/40 py-1 pl-3 text-subtle">
              {children}
            </blockquote>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
