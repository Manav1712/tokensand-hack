import { useEffect, useRef } from "react"

type DotCubeProps = {
  rotation?: number
  glow?: number
  pulse?: number
  glyphs?: string[]
  className?: string
}

type Point = [number, number, number]

function face(axis: 0 | 1 | 2, sign: number, n: number): Point[] {
  const points: Point[] = []
  for (let i = 0; i < n; i += 1) {
    for (let j = 0; j < n; j += 1) {
      const a = n === 1 ? 0 : -1 + (2 * i) / (n - 1)
      const b = n === 1 ? 0 : -1 + (2 * j) / (n - 1)
      const point: Point = [0, 0, 0]
      let k = 0
      for (let axisIndex = 0; axisIndex < 3; axisIndex += 1) {
        if (axisIndex === axis) point[axisIndex] = sign
        else {
          point[axisIndex] = k === 0 ? a : b
          k += 1
        }
      }
      points.push(point)
    }
  }
  return points
}

const POINTS: Point[] = (
  [
    [0, 1],
    [0, -1],
    [1, 1],
    [1, -1],
    [2, 1],
    [2, -1],
  ] as const
).flatMap(([axis, sign]) => face(axis, sign, 8))

function rotate(point: Point, yaw: number, pitch: number): Point {
  const [x, y, z] = point
  const cy = Math.cos(yaw)
  const sy = Math.sin(yaw)
  const x1 = x * cy - z * sy
  const z1 = x * sy + z * cy
  const cp = Math.cos(pitch)
  const sp = Math.sin(pitch)
  return [x1, y * cp - z1 * sp, y * sp + z1 * cp]
}

export function DotCube({ rotation = 0, glow = 1, pulse = 0, glyphs, className }: DotCubeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const props = useRef({ rotation, glow, pulse, glyphs })
  props.current = { rotation, glow, pulse, glyphs }
  const pointer = useRef({ x: 0, y: 0 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext("2d")
    if (!context) return
    const surface = canvas
    const paint = context
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    let frame = 0

    function draw(now: number) {
      const { rotation: extra, glow: amount, pulse: beat, glyphs: labels } = props.current
      const width = surface.clientWidth
      const height = surface.clientHeight
      if (width < 2 || height < 2) {
        if (!reduce) frame = requestAnimationFrame(draw)
        return
      }
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      const pixelWidth = Math.max(1, Math.floor(width * ratio))
      const pixelHeight = Math.max(1, Math.floor(height * ratio))
      if (surface.width !== pixelWidth || surface.height !== pixelHeight) {
        surface.width = pixelWidth
        surface.height = pixelHeight
      }
      paint.setTransform(ratio, 0, 0, ratio, 0, 0)
      paint.clearRect(0, 0, width, height)
      paint.globalCompositeOperation = "lighter"
      const wave = reduce ? 0 : Math.sin(now / 340)
      const glowAmount = Math.max(0, amount)
      const beatAmount = Math.max(0, beat)
      const wobble = 1 + beatAmount * 0.55 * wave
      const yaw = extra + pointer.current.x * 0.35 + (reduce ? 0.6 : now * 0.00018)
      const pitch = 0.52 + pointer.current.y * 0.22
      const camera = 4.15
      const scale = Math.min(width, height) * (0.7 + beatAmount * 0.05 * wave)
      const halo = Math.min(width, height) * (0.3 + Math.min(glowAmount, 1.8) * 0.08) * (1 + beatAmount * 0.07 * wave)
      const haloAlpha = Math.min(0.55, 0.2 * glowAmount) * (0.82 + beatAmount * 0.28 * (wave * 0.5 + 0.5))
      const gradient = paint.createRadialGradient(width / 2, height / 2, halo * 0.08, width / 2, height / 2, halo)
      gradient.addColorStop(0, `rgba(99, 179, 237, ${haloAlpha.toFixed(3)})`)
      gradient.addColorStop(0.42, `rgba(99, 179, 237, ${(haloAlpha * 0.38).toFixed(3)})`)
      gradient.addColorStop(1, "rgba(99, 179, 237, 0)")
      paint.fillStyle = gradient
      paint.beginPath()
      paint.arc(width / 2, height / 2, halo, 0, Math.PI * 2)
      paint.fill()
      const projected = POINTS.map((point) => {
        const [x, y, z] = rotate(point, yaw, pitch)
        const depth = camera - z
        return {
          x: width / 2 + (x / depth) * scale,
          y: height / 2 + (y / depth) * scale,
          depth,
        }
      }).sort((a, b) => b.depth - a.depth)
      const nearest = projected[projected.length - 1]?.depth ?? camera
      const farthest = projected[0]?.depth ?? camera
      const breathe = 0.75 + 0.25 * (wave * 0.5 + 0.5) * Math.min(beatAmount, 1.5)
      projected.forEach((dot, index) => {
        const closeness = farthest === nearest ? 1 : (farthest - dot.depth) / (farthest - nearest)
        const alpha = Math.min(1, Math.max(0, glowAmount * (0.16 + closeness * 0.9) * breathe))
        const radius = (1.35 + closeness * 2.7) * wobble
        if (labels && labels.length > 0) {
          paint.fillStyle = `rgba(99, 179, 237, ${alpha.toFixed(3)})`
          paint.font = `${Math.max(9, radius * 3.2)}px "JetBrains Mono", monospace`
          paint.textAlign = "center"
          paint.textBaseline = "middle"
          paint.fillText(labels[index % labels.length], dot.x, dot.y)
          return
        }
        paint.fillStyle = `rgba(99, 179, 237, ${(alpha * 0.28).toFixed(3)})`
        paint.beginPath()
        paint.arc(dot.x, dot.y, radius * 2.15, 0, Math.PI * 2)
        paint.fill()
        paint.fillStyle = `rgba(99, 179, 237, ${alpha.toFixed(3)})`
        paint.beginPath()
        paint.arc(dot.x, dot.y, radius * 0.72, 0, Math.PI * 2)
        paint.fill()
      })
      if (!reduce) frame = requestAnimationFrame(draw)
    }

    function onPointer(event: PointerEvent) {
      pointer.current = {
        x: (event.clientX / window.innerWidth) * 2 - 1,
        y: (event.clientY / window.innerHeight) * 2 - 1,
      }
    }

    frame = requestAnimationFrame(draw)
    window.addEventListener("pointermove", onPointer)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("pointermove", onPointer)
    }
  }, [])

  return <canvas ref={canvasRef} className={className ? `dotcube ${className}` : "dotcube"} aria-hidden="true" />
}
