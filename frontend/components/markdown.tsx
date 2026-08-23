"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Markdown for assistant answers.
 *
 * The model replies in Markdown — tables of apartments, bold figures, bulleted
 * findings, and citation links in the legal answers — so rendering it as plain
 * text throws away most of the structure it deliberately produced.
 *
 * Raw HTML is NOT enabled (no rehype-raw). That is a security property, not an
 * omission: an answer can quote a tenant name or a contract note, and those
 * strings come from the database, not from us. Without the raw-HTML plugin
 * react-markdown escapes any tags they contain instead of mounting them.
 *
 * Every element is styled explicitly rather than through a prose plugin, so the
 * bubbles keep the ledger theme's ink and hairline rules in both themes.
 */
function MarkdownBody({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0 leading-relaxed">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        ul: ({ children }) => <ul className="my-1.5 ml-4 list-disc space-y-0.5 marker:text-muted-foreground">{children}</ul>,
        ol: ({ children }) => <ol className="my-1.5 ml-4 list-decimal space-y-0.5 marker:text-muted-foreground">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        h1: ({ children }) => <h3 className="mt-3 mb-1.5 first:mt-0 text-sm font-semibold">{children}</h3>,
        h2: ({ children }) => <h3 className="mt-3 mb-1.5 first:mt-0 text-sm font-semibold">{children}</h3>,
        h3: ({ children }) => <h4 className="mt-2.5 mb-1 first:mt-0 text-sm font-semibold">{children}</h4>,
        h4: ({ children }) => <h4 className="mt-2.5 mb-1 first:mt-0 text-sm font-medium">{children}</h4>,
        blockquote: ({ children }) => (
          <blockquote className="my-1.5 border-l-2 border-border pl-3 text-muted-foreground">{children}</blockquote>
        ),
        hr: () => <hr className="my-2.5 border-border" />,
        a: ({ href, children }) => (
          // Answers can cite external law sources; never hand the target a
          // window.opener handle back to the authenticated app.
          <a href={href} target="_blank" rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-primary">
            {children}
          </a>
        ),
        // Styled for the inline case; the `pre` below strips the chip back off
        // for fenced blocks. Sniffing `className` for "language-" instead would
        // misread a fence opened without a language — it carries no class at all.
        code: ({ children }) => (
          <code className="rounded bg-foreground/10 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
        ),
        pre: ({ children }) => (
          <pre className="my-1.5 overflow-x-auto rounded-md bg-foreground/5 p-2.5 text-xs [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-xs">
            {children}
          </pre>
        ),
        // A wide table must scroll inside its own bubble rather than stretching it.
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto">
            <table className="w-full border-collapse text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="border-b border-border">{children}</thead>,
        th: ({ children }) => (
          <th className="px-2 py-1.5 text-left font-medium text-muted-foreground whitespace-nowrap">{children}</th>
        ),
        td: ({ children }) => (
          <td className="border-b border-border/50 px-2 py-1.5 align-top tabular-nums">{children}</td>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

// Streaming appends a token at a time; without memo every bubble in the
// conversation re-parses its Markdown on each one.
export const Markdown = memo(MarkdownBody);
