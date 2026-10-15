import { useEffect } from "react"

function spots(): { top: number }[] {
  return [...document.querySelectorAll<HTMLElement>("[data-scene]")].flatMap((section) => {
    const steps = Number(section.dataset.steps)
    const total = section.offsetHeight - window.innerHeight
    const origin = section.getBoundingClientRect().top + window.scrollY
    return Array.from({ length: steps }, (_, step) => ({
      top: steps <= 1 || total <= 0 ? origin : origin + (step / (steps - 1)) * total,
    }))
  })
}

export function useKeyboardSteps(): void {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target
      if (target instanceof Element && target.closest("input, textarea, select, button, a")) return
      const forward =
        event.key === "ArrowRight" ||
        event.key === "ArrowDown" ||
        event.key === " " ||
        event.key === "PageDown"
      const back = event.key === "ArrowLeft" || event.key === "ArrowUp" || event.key === "PageUp"
      if (!forward && !back) return
      const list = spots()
      if (list.length === 0) return
      event.preventDefault()
      let index = 0
      let best = Infinity
      list.forEach((spot, i) => {
        const distance = Math.abs(spot.top - window.scrollY)
        if (distance < best) {
          best = distance
          index = i
        }
      })
      const next = list[Math.min(list.length - 1, Math.max(0, index + (forward ? 1 : -1)))]
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches
      window.scrollTo({ top: next.top, behavior: reduce ? "auto" : "smooth" })
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])
}
