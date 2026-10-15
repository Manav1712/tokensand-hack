import { useEffect, useRef } from "react"
import { motion, useInView } from "motion/react"
import { traces } from "../data/traces"
import { arrive, beat, morph } from "../motion"
import { DotCube } from "../stage/DotCube"
import type { SceneSpec } from "../stage/types"

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

function jailWalls(argv: string[]): string[] {
  const walls: string[] = []
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i]
    const next = argv[i + 1]
    if (flag === "--network" && next === "jailnet") walls.push("no public network")
    else if (flag === "--read-only") walls.push("read-only")
    else if (flag === "--cap-drop=ALL") walls.push("cap-drop ALL")
    else if (flag === "--security-opt" && next === "no-new-privileges") walls.push("no-new-privileges")
    else if (flag === "--pids-limit" && next) walls.push(`pids ${next}`)
    else if (flag === "--memory" && next) walls.push(`memory ${next}`)
  }
  return walls
}

function Cube({ glow, pulse, live, snap }: { glow: number; pulse: number; live: boolean; snap: boolean }) {
  return (
    <div style={{ position: "relative", width: "min(280px, 40vw)", aspectRatio: "1", flex: "none" }}>
      <motion.div
        initial={false}
        animate={{ opacity: live ? 1 : 0.28, scale: live ? 1 : 0.84 }}
        transition={snap ? { duration: 0 } : morph}
        style={{ position: "absolute", inset: 0, transformOrigin: "center center" }}
      >
        <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: "min(520px, 86vw)",
              height: "min(520px, 62vh)",
              transform: "translate(-50%, -50%) scale(0.52)",
            }}
          >
            <DotCube glow={glow} pulse={pulse} />
          </div>
        </div>
      </motion.div>
      <motion.p
        className="mono"
        initial={false}
        animate={{
          x: "-50%",
          y: "-50%",
          scale: live ? 0.16 : 1,
          opacity: live ? 0 : 1,
        }}
        transition={snap ? { duration: 0 } : { ...morph, delay: 0.35 }}
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          width: "min(240px, 64vw)",
          margin: 0,
          textAlign: "center",
          fontSize: 14,
          lineHeight: 1.45,
          zIndex: 1,
          pointerEvents: "none",
        }}
      >
        SKILL.md
        <span className="muted"> — Format the current date as YYYY-MM-DD.</span>
      </motion.p>
    </div>
  )
}

function Wall({ label, show, snap, index }: { label: string; show: boolean; snap: boolean; index: number }) {
  const transition = snap ? { duration: 0 } : { ...arrive, delay: index * beat * 0.7 }
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 22 }}>
      <motion.span
        initial={false}
        animate={{ scaleX: show ? 1 : 0, opacity: show ? 1 : 0 }}
        transition={transition}
        style={{
          width: 26,
          height: 2,
          display: "block",
          flex: "none",
          background: "var(--accent)",
          transformOrigin: "left center",
        }}
      />
      <motion.span
        className="mono accent"
        initial={false}
        animate={{ opacity: show ? 1 : 0, x: show ? 0 : -8 }}
        transition={transition}
        style={{ fontSize: 13 }}
      >
        {label}
      </motion.span>
    </div>
  )
}

function PlantLine({
  path,
  preview,
  show,
  snap,
  index,
}: {
  path: string
  preview: string
  show: boolean
  snap: boolean
  index: number
}) {
  return (
    <motion.p
      className="mono accent"
      initial={false}
      animate={{ opacity: show ? 1 : 0, scale: show ? 1 : 0.96 }}
      transition={snap ? { duration: 0 } : { ...arrive, delay: index * beat * 0.28 }}
      style={{ margin: 0, fontSize: 12, lineHeight: 1.4, transformOrigin: "left center" }}
    >
      {path}
      <br />
      {preview}
    </motion.p>
  )
}

function JailView({ step }: { step: number }) {
  const prior = usePriorStep(step)
  const frame = useRef<HTMLDivElement>(null)
  const seen = useInView(frame, { once: true, amount: 0.35 })
  const inside = step > 0 || seen
  const walls = jailWalls(traces.jail.argv)
  const showWalls = step >= 1
  const showPlants = step >= 2
  const glow = showPlants ? 1.25 : showWalls ? 1.05 : inside ? 0.95 : 0.4
  const pulse = showPlants ? 0.75 : showWalls ? 0.22 : inside ? 0.45 : 0

  return (
    <div ref={frame} style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div>
        <p className="eyebrow">jail</p>
        <p className="lede">The skill runs inside, not in the prompt.</p>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 28 }}>
        <div style={{ width: 196, display: "flex", flexDirection: "column", gap: 12 }}>
          {walls.map((label, index) => (
            <Wall
              key={label}
              label={label}
              show={showWalls}
              snap={!plays(prior, step, 1)}
              index={index}
            />
          ))}
        </div>
        <Cube glow={glow} pulse={pulse} live={inside} snap={step > 0} />
        <div style={{ width: 230, display: "flex", flexDirection: "column", gap: 8 }}>
          {traces.jail.plants.map((plant, index) => (
            <PlantLine
              key={plant.path}
              path={plant.path}
              preview={plant.preview}
              show={showPlants}
              snap={!plays(prior, step, 2)}
              index={index}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

export const scene: SceneSpec = {
  id: "jail",
  steps: 3,
  View: JailView,
}
