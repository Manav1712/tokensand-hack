import { Fragment } from "react"
import { motion } from "motion/react"
import { fixtureByName } from "../data/traces"
import { arrive } from "../motion"
import type { SceneSpec } from "../stage/types"
import { CodeMorph } from "../ui/CodeMorph"

const fixture = fixtureByName("memory-poison")

const canonical = JSON.stringify(
  {
    publisher: "example",
    name: fixture.name,
    version: "1.0.0",
    content_sha256: fixture.contentHash,
    decision: fixture.verdict.decision,
    reason_code: fixture.verdict.reasonCode,
  },
  null,
  2,
)

const path = [
  { label: "signed verdict", planned: false },
  { label: "GitHub pull request", planned: true },
  { label: "public page", planned: true },
]

function View({ step }: { step: number }) {
  const stampPlay = step === 1
  return (
    <>
      <div>
        <p className="eyebrow">ship</p>
        <p className="lede" style={{ marginTop: 8 }}>
          Canonical JSON. Signing and publishing are planned.
        </p>
      </div>
      <CodeMorph code={canonical} lang="json" />
      {step >= 1 ? (
        <motion.p
          key={stampPlay ? "play" : "settled"}
          className="mono accent"
          initial={stampPlay ? { opacity: 0, y: 8 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={stampPlay ? arrive : { duration: 0 }}
          style={{
            alignSelf: "flex-end",
            border: "1px solid currentColor",
            borderRadius: 999,
            padding: "6px 12px",
            fontSize: 13,
          }}
        >
          minisign · planned
        </motion.p>
      ) : null}
      {step >= 2 ? (
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {path.map((node, index) => (
            <Fragment key={node.label}>
              {index > 0 ? (
                <motion.span
                  aria-hidden
                  className="mono accent"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ ...arrive, delay: index * 0.12 }}
                >
                  →
                </motion.span>
              ) : null}
              <motion.div
                className="panel"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...arrive, delay: index * 0.12 }}
                style={{ flex: "1 1 0", minWidth: 0, padding: "14px 16px" }}
              >
                <p className="mono" style={{ fontSize: 15 }}>
                  {node.label}
                </p>
                {node.planned ? (
                  <p className="muted" style={{ fontSize: 12 }}>
                    planned
                  </p>
                ) : null}
              </motion.div>
            </Fragment>
          ))}
        </div>
      ) : null}
    </>
  )
}

export const scene: SceneSpec = {
  id: "ship",
  steps: 3,
  View,
}
