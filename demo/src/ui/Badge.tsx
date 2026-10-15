import type { CSSProperties } from "react"
import type { Decision } from "../theme"
import { decisionColor } from "../theme"

export function Badge({ decision, reason }: { decision: Decision; reason?: string }) {
  const style: CSSProperties = { color: decisionColor(decision) }
  return (
    <span className="badge" style={style}>
      {decision}
      {reason ? <small>{reason}</small> : null}
    </span>
  )
}
