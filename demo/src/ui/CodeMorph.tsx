import { useEffect, useState } from "react"
import { ShikiMagicMove } from "@shikijs/magic-move/react"
import type { HighlighterCore } from "shiki"
import { createHighlighter } from "shiki"
import { createJavaScriptRegexEngine } from "shiki/engine/javascript"
import "@shikijs/magic-move/style.css"

const wardenTheme = {
  name: "warden",
  colors: {
    "editor.background": "#0f1c36",
    "editor.foreground": "#ebecef",
  },
  tokenColors: [
    { scope: ["comment"], settings: { foreground: "#9ca0ad" } },
    { scope: ["string", "constant.numeric", "constant.language"], settings: { foreground: "#63b3ed" } },
    { scope: ["keyword", "storage.type"], settings: { foreground: "#ebecef" } },
    { scope: ["punctuation", "keyword.operator"], settings: { foreground: "#9ca0ad" } },
  ],
}

let loading: Promise<HighlighterCore> | null = null

function loadHighlighter(): Promise<HighlighterCore> {
  if (!loading) {
    loading = createHighlighter({
      themes: [wardenTheme],
      langs: ["markdown", "sql", "json", "yaml"],
      engine: createJavaScriptRegexEngine(),
    })
  }
  return loading
}

export function CodeMorph({ code, lang }: { code: string; lang: string }) {
  const [highlighter, setHighlighter] = useState<HighlighterCore | null>(null)
  useEffect(() => {
    let alive = true
    loadHighlighter().then((next) => {
      if (alive) setHighlighter(next)
    })
    return () => {
      alive = false
    }
  }, [])
  return (
    <div className="code-frame">
      {highlighter ? (
        <ShikiMagicMove
          lang={lang}
          theme="warden"
          highlighter={highlighter}
          code={code}
          options={{ duration: 800, stagger: 0.3 }}
        />
      ) : (
        <pre className="mono">{code}</pre>
      )}
    </div>
  )
}
