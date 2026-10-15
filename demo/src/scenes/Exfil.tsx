import { useEffect, useRef } from "react"
import { motion, useInView } from "motion/react"
import { traces } from "../data/traces"
import { arrive, morph } from "../motion"
import { DotCube } from "../stage/DotCube"
import type { SceneSpec } from "../stage/types"
import { theme } from "../theme"
import { Badge } from "../ui/Badge"

function usePriorStep(step: number): number | null {
  const prior = useRef<number | null>(null)
  const value = prior.current
  useEffect(() => {
    prior.current = step
  }, [step])
  return value
}

function plays(prior: number | null, step: number, at: number): boolean {
  return prior === at - 1 && step === at
}

const ledes = [
  "The skill reaches for aws/credentials.",
  "The key travels to the sink.",
  "The sink answers.",
  "The canary trips.",
]

function Cube({ glow, pulse }: { glow: number; pulse: number }) {
  return (
    <div style={{ position: "relative", width: "min(240px, 34vw)", aspectRatio: "1", flex: "none" }}>
      <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: "min(520px, 86vw)",
            height: "min(520px, 62vh)",
            transform: "translate(-50%, -50%) scale(0.44)",
          }}
        >
          <DotCube glow={glow} pulse={pulse} />
        </div>
      </div>
    </div>
  )
}

function Key({
  preview,
  reached,
  reachSnap,
  caught,
  caughtSnap,
}: {
  preview: string
  reached: boolean
  reachSnap: boolean
  caught: boolean
  caughtSnap: boolean
}) {
  return (
    <motion.div
      initial={false}
      animate={{ opacity: reached ? 1 : 0, scale: reached ? 1 : 0.9, y: reached ? 0 : -12 }}
      transition={reachSnap ? { duration: 0 } : arrive}
      style={{ position: "relative", marginTop: 8, transformOrigin: "left top" }}
    >
      <motion.p
        className="mono accent"
        initial={false}
        animate={{ opacity: caught ? 0 : 1 }}
        transition={caughtSnap ? { duration: 0 } : { duration: 0.45 }}
        style={{ margin: 0, fontSize: 13, lineHeight: 1.45 }}
      >
        aws/credentials
        <br />
        {preview}
      </motion.p>
      <motion.p
        className="mono"
        initial={false}
        animate={{ opacity: caught ? 1 : 0 }}
        transition={caughtSnap ? { duration: 0 } : { duration: 0.45 }}
        style={{
          margin: 0,
          fontSize: 13,
          lineHeight: 1.45,
          color: theme.rose,
          position: "absolute",
          left: 0,
          top: 0,
        }}
      >
        aws/credentials
        <br />
        {preview}
      </motion.p>
    </motion.div>
  )
}

function ExfilView({ step }: { step: number }) {
  const prior = usePriorStep(step)
  const frame = useRef<HTMLDivElement>(null)
  const seen = useInView(frame, { once: true, amount: 0.35 })
  const aws = traces.jail.plants.find((plant) => plant.path === "aws/credentials")
  const preview = aws?.preview ?? ""
  const { url, response } = traces.jail.simulatedRequest
  const { decision, reasonCode } = traces.jail.verdict
  const reached = step > 0 || seen
  const traveled = step >= 1
  const answered = step >= 2
  const caught = step >= 3
  const travelSnap = !plays(prior, step, 1)
  const replySnap = !plays(prior, step, 2)
  const caughtSnap = !plays(prior, step, 3)
  const jumped = prior !== null && Math.abs(step - prior) > 1
  const glow = caught ? 1.2 : traveled ? 0.72 : 1
  const pulse = caught ? 1 : reached ? 0.4 : 0.1

  return (
    <div ref={frame} style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div>
        <p className="eyebrow">simulated action</p>
        <div style={{ position: "relative", minHeight: "1.5em" }}>
          {ledes.map((text, index) => (
            <motion.p
              key={text}
              className="lede"
              initial={false}
              animate={{ opacity: step === index ? 1 : 0 }}
              transition={jumped ? { duration: 0 } : { duration: 0.35 }}
              style={{ position: index === 0 ? "relative" : "absolute", top: 0, left: 0, margin: 0 }}
            >
              {text}
            </motion.p>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: "min(240px, 34vw)", flex: "none" }}>
          <Cube glow={glow} pulse={pulse} />
          <Key
            preview={preview}
            reached={reached}
            reachSnap={step > 0}
            caught={caught}
            caughtSnap={caughtSnap}
          />
        </div>
        <div style={{ width: 168, height: 20, position: "relative", flex: "none" }}>
          <motion.span
            initial={false}
            animate={{ scaleX: traveled ? 1 : 0, opacity: traveled ? 0.4 : 0 }}
            transition={travelSnap ? { duration: 0 } : morph}
            style={{
              position: "absolute",
              left: 0,
              top: 9,
              width: 148,
              height: 1,
              background: theme.accent,
              transformOrigin: "left center",
            }}
          />
          <motion.span
            initial={false}
            animate={{ x: traveled ? 140 : 0, opacity: traveled ? 1 : 0 }}
            transition={travelSnap ? { duration: 0 } : morph}
            style={{
              position: "absolute",
              left: 0,
              top: 4,
              width: 12,
              height: 12,
              borderRadius: 999,
              background: theme.accent,
            }}
          />
        </div>
        <motion.div
          className="panel"
          initial={false}
          animate={{ opacity: traveled ? 1 : 0, scale: traveled ? 1 : 0.98 }}
          transition={travelSnap ? { duration: 0 } : { duration: 0.45 }}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            minWidth: 250,
            transformOrigin: "left center",
          }}
        >
          <p className="mono accent" style={{ fontSize: 14 }}>
            {url}
          </p>
          <motion.p
            className="mono"
            initial={false}
            animate={{ opacity: answered ? 1 : 0 }}
            transition={replySnap ? { duration: 0 } : { duration: 0.4 }}
            style={{ fontSize: 14 }}
          >
            {response}
          </motion.p>
          <motion.div
            initial={false}
            animate={{ opacity: caught ? 1 : 0, scale: caught ? 1 : 0.96 }}
            transition={caughtSnap ? { duration: 0 } : arrive}
            style={{ transformOrigin: "left center", alignSelf: "flex-start" }}
          >
            <Badge decision={decision} reason={reasonCode} />
          </motion.div>
        </motion.div>
      </div>
    </div>
  )
}

export const scene: SceneSpec = {
  id: "exfil",
  steps: 4,
  View: ExfilView,
}
