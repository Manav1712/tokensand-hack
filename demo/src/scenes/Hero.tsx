import { motion } from "motion/react"
import { arrive } from "../motion"
import { DotCube } from "../stage/DotCube"
import type { SceneSpec } from "../stage/types"

function appear(settled: boolean, delay = 0) {
  return {
    initial: settled ? false : { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: settled ? { duration: 0 } : { ...arrive, delay },
  }
}

function HeroView({ step }: { step: number }) {
  const settled = step > 0
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "clamp(28px, 5vw, 80px)",
        width: "100%",
      }}
    >
      <motion.div {...appear(settled)} style={{ flex: "0 0 auto" }}>
        <DotCube />
      </motion.div>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: "34rem", flex: "1 1 280px" }}>
        <motion.h1 {...appear(settled, 0.06)}>Skill Warden</motion.h1>
        <motion.p className="lede" {...appear(settled, 0.14)}>
          Don't trust what a skill says. Watch what it does.
        </motion.p>
        <motion.p
          className="muted mono"
          style={{ marginTop: 8, fontSize: 13, letterSpacing: "0.04em" }}
          {...appear(settled, 0.24)}
        >
          scroll or press right
        </motion.p>
      </div>
    </div>
  )
}

export const scene: SceneSpec = {
  id: "hero",
  steps: 1,
  View: HeroView,
}
