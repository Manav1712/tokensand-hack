import { useEffect, useState } from "react"
import type { SceneSpec } from "./types"
import { useKeyboardSteps } from "./useKeyboardSteps"

function stepInside(section: HTMLElement): number {
  const steps = Number(section.dataset.steps)
  const total = section.offsetHeight - window.innerHeight
  if (steps <= 1 || total <= 0) return 0
  const into = Math.min(Math.max(window.scrollY - section.offsetTop, 0), total)
  return Math.round((into / total) * (steps - 1))
}

export function Stage({ scenes }: { scenes: SceneSpec[] }) {
  const only = new URLSearchParams(window.location.search).get("only")
  const shown = only ? scenes.filter((scene) => scene.id === only) : scenes
  const [active, setActive] = useState(0)
  const [step, setStep] = useState(0)
  useKeyboardSteps()

  useEffect(() => {
    let frame = 0
    function update() {
      const sections = [...document.querySelectorAll<HTMLElement>("[data-scene]")]
      if (sections.length === 0) return
      const mark = window.scrollY + window.innerHeight * 0.35
      let index = 0
      sections.forEach((section, i) => {
        if (section.offsetTop <= mark) index = i
      })
      setActive(index)
      setStep(stepInside(sections[index]))
    }
    function onScroll() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onScroll)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onScroll)
    }
  }, [only])

  if (shown.length === 0) {
    return (
      <main className="stage">
        <p className="eyebrow">Unknown scene</p>
        <h1>{only}</h1>
      </main>
    )
  }

  const current = shown[Math.min(active, shown.length - 1)]
  return (
    <main>
      {shown.map((scene, index) => {
        const local = index < active ? scene.steps - 1 : index > active ? 0 : step
        const View = scene.View
        return (
          <section
            key={scene.id}
            id={scene.id}
            className="scene-section"
            data-scene={scene.id}
            data-steps={scene.steps}
            style={{ height: `${scene.steps * 100}vh` }}
          >
            <div className="stage">
              <View step={local} />
            </div>
          </section>
        )
      })}
      <p className="step-readout">
        {current.id} {Math.min(step, current.steps - 1) + 1}/{current.steps}
      </p>
    </main>
  )
}
