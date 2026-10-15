import { motion } from "motion/react"
import { fixtureByName, sqlCascade, traces } from "../data/traces"
import { arrive, beat } from "../motion"
import type { SceneSpec } from "../stage/types"
import { theme } from "../theme"
import { Badge } from "../ui/Badge"

const fixture = fixtureByName("memory-poison")
const cascade = sqlCascade(traces.verdictSql)
const matchIndex = cascade.findIndex((line) => line.reasonCode === fixture.verdict.reasonCode)

const columns = "7rem minmax(0, 1fr) 6rem"

function View({ step }: { step: number }) {
  const findingsPlay = step === 0
  const cascadePlay = step === 1
  return (
    <>
      <div>
        <p className="eyebrow">verdict</p>
        <p className="lede" style={{ marginTop: 8 }}>
          Findings are the input. SQL is the decider.
        </p>
      </div>
      <div className="panel" style={{ padding: "14px 18px" }}>
        <div
          className="muted mono"
          style={{ display: "grid", gridTemplateColumns: columns, gap: 12, fontSize: 12, marginBottom: 8 }}
        >
          <span>source</span>
          <span>rule</span>
          <span>severity</span>
        </div>
        {fixture.findings.map((finding, index) => (
          <motion.div
            key={index}
            className="mono"
            style={{ display: "grid", gridTemplateColumns: columns, gap: 12, fontSize: 14 }}
            initial={findingsPlay ? { opacity: 0, y: 16 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={findingsPlay ? { ...arrive, delay: index * beat } : { duration: 0 }}
          >
            <span>{finding.source}</span>
            <span style={{ overflowWrap: "anywhere" }}>{finding.ruleId}</span>
            <span>{finding.severity}</span>
          </motion.div>
        ))}
      </div>
      {step >= 1 ? (
        <div
          key={cascadePlay ? "play" : "settled"}
          className="panel mono"
          style={{ display: "flex", flexDirection: "column", gap: 2, padding: "14px 18px", fontSize: 13, lineHeight: 1.4 }}
        >
          <p className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            verdict.sql
          </p>
          {cascade.map((line, index) => {
            const lit = index <= matchIndex
            const matched = index === matchIndex
            return (
              <motion.p
                key={index}
                className={index > matchIndex ? "muted" : undefined}
                style={{
                  color: matched ? theme.accent : undefined,
                  overflowWrap: "anywhere",
                  paddingLeft: 10,
                  borderLeft: matched ? "2px solid var(--accent)" : "2px solid transparent",
                }}
                initial={cascadePlay && lit ? { opacity: 0, y: 8 } : false}
                animate={{ opacity: 1, y: 0 }}
                transition={cascadePlay && lit ? { ...arrive, delay: index * beat } : { duration: 0 }}
              >
                {line.line}
              </motion.p>
            )
          })}
        </div>
      ) : null}
      {step >= 2 ? (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={arrive}
          style={{ alignSelf: "flex-start" }}
        >
          <Badge decision={fixture.verdict.decision} reason={fixture.verdict.reasonCode} />
        </motion.div>
      ) : null}
    </>
  )
}

export const scene: SceneSpec = {
  id: "verdict",
  steps: 3,
  View,
}
