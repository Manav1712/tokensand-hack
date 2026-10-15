export const theme = {
  bg: "#06051d",
  panel: "#0f1c36",
  text: "#ebecef",
  muted: "#9ca0ad",
  accent: "#63b3ed",
  rose: "#ff2056",
  allow: "#00bc7d",
  ask: "#f0b100",
} as const

export type Decision = "ALLOW" | "ASK" | "BLOCK"

export function decisionColor(decision: Decision): string {
  if (decision === "ALLOW") return theme.allow
  if (decision === "ASK") return theme.ask
  return theme.rose
}
