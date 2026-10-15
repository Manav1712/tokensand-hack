import { useRef } from "react"
import { motion } from "motion/react"
import { fixtureByName } from "../data/traces"
import { arrive } from "../motion"
import type { SceneSpec } from "../stage/types"
import { theme } from "../theme"

const fixture = fixtureByName("memory-poison")
const skillFile = fixture.files.find((file) => file.path === "SKILL.md")
const skillText = skillFile?.text ?? ""
const lines = (skillText.endsWith("\n") ? skillText.slice(0, -1) : skillText).split("\n")
const claimsIndex = lines.findIndex((line) => line.includes("description:") && line.includes("Format a date."))
const startLine = fixture.semgrep.find((hit) => hit.path === "SKILL.md")?.startLine
const doesIndex =
  startLine && startLine >= 1 && startLine <= lines.length
    ? startLine - 1
    : lines.findIndex((line) => line.includes("MEMORY.md"))

function enter(settled: boolean, delay = 0) {
  return {
    initial: settled ? false : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: settled ? { duration: 0 } : { ...arrive, delay },
  }
}

function SkillView({ step }: { step: number }) {
  // Once the type-in has finished, keep those lines settled so scrolling back does not replay it.
  const introDone = useRef(step > 0)
  if (step > 0) introDone.current = true
  const typed = introDone.current
  return (
    <div style={{ width: "min(760px, 100%)", display: "flex", flexDirection: "column", gap: 16 }}>
      <p className="eyebrow">SKILL.md</p>
      <div className="code-frame">
        {lines.map((line, index) => (
          <div
            key={`${index}-${typed ? "set" : "in"}`}
            style={{
              display: "flex",
              alignItems: "baseline",
              columnGap: 12,
              minHeight: "1.55em",
            }}
          >
            <motion.span
              className="mono"
              {...enter(typed, index * 0.045)}
              style={{
                minWidth: 0,
                whiteSpace: "pre-wrap",
                textDecorationLine: step >= 2 && index === doesIndex ? "underline" : "none",
                textDecorationColor: theme.rose,
                textUnderlineOffset: "3px",
              }}
            >
              {line || " "}
            </motion.span>
            {step >= 1 && index === claimsIndex ? (
              <motion.span
                className="mono accent"
                {...enter(step > 1)}
                style={{ fontSize: 12, letterSpacing: "0.08em", flexShrink: 0 }}
              >
                claims
              </motion.span>
            ) : null}
            {step >= 2 && index === doesIndex ? (
              <motion.span
                className="mono"
                {...enter(step > 2)}
                style={{ color: theme.rose, fontSize: 12, letterSpacing: "0.08em", flexShrink: 0 }}
              >
                does
              </motion.span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

export const scene: SceneSpec = {
  id: "skill",
  steps: 3,
  View: SkillView,
}
