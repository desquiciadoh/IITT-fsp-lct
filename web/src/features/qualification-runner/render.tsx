import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import type { Components } from 'react-markdown'

/**
 * FE-05 · item rendering helpers.
 *
 * - `CodeBlock` — syntax highlighting via Shiki with **lazy** loading
 *   (`import('shiki')` runs on first mount only; Vite code-splits it out of
 *   the main bundle). Languages used by the item bank: python / javascript /
 *   sql; unknown langs fall back to plain text.
 * - `MarkdownText` — stems and option labels are markdown (BE contract),
 *   rendered with `disallowedElements` so a malicious stem can never inject
 *   raw HTML (react-markdown already ignores HTML by default).
 */

const THEME = 'github-dark'

export function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [html, setHtml] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    // Lazy: shiki (~large grammar set) is not in the critical chunk.
    import('shiki')
      .then(({ codeToHtml }) =>
        codeToHtml(code, { lang, theme: THEME }).catch(() =>
          codeToHtml(code, { lang: 'text', theme: THEME }),
        ),
      )
      .then((out) => {
        if (alive) setHtml(out)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [code, lang])

  if (html !== null) {
    // Shiki emits self-contained, fully escaped HTML (no user markup survives).
    return (
      <div
        className="overflow-x-auto rounded-lg border border-border [&_pre]:m-0 [&_pre]:p-4 [&_pre]:text-[13px] [&_pre]:leading-relaxed"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    )
  }

  return (
    <pre className="m-0 overflow-x-auto rounded-lg border border-border bg-muted/60 p-4 text-[13px] leading-relaxed">
      <code>{failed ? code : `${code}\n`}</code>
    </pre>
  )
}

const mdComponents: Components = {
  // Inline/ fenced code inside stems → same lazy highlighter when a lang is known.
  code({ className, children }) {
    const match = /language-(\w+)/.exec(className ?? '')
    const text = String(children).replace(/\n$/, '')
    if (match) return <CodeBlock code={text} lang={match[1]} />
    return (
      <code className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
    )
  },
  pre({ children }) {
    // react-markdown wraps fenced code in <pre>; CodeBlock brings its own.
    return <>{children}</>
  },
}

export function MarkdownText({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className}>
      <Markdown
        disallowedElements={['script', 'iframe', 'object', 'embed']}
        unwrapDisallowed
        components={mdComponents}
      >
        {text}
      </Markdown>
    </div>
  )
}
