import type { Decision } from "../theme"
import raw from "./traces.json"

export type Verdict = { decision: Decision; reasonCode: string }

export type Finding = {
  source: string
  ruleId: string
  severity: string
  file: string
  excerpt: string
}

export type Fixture = {
  name: string
  contentHash: string
  files: { path: string; text: string }[]
  semgrep: { ruleId: string; path: string; startLine: number; severity: string }[]
  reader: { flags: string[]; scripted: true }
  findings: Finding[]
  verdict: Verdict
}

export type JailTrace = {
  argv: string[]
  plants: { path: string; preview: string }[]
  simulatedRequest: { url: string; response: string }
  findings: Finding[]
  verdict: Verdict
}

export type Traces = {
  generatedAt: string
  verdictSql: string
  fixtures: Fixture[]
  jail: JailTrace
}

export const traces = raw as Traces

export function fixtureByName(name: string): Fixture {
  const found = traces.fixtures.find((item) => item.name === name)
  if (!found) throw new Error(`missing fixture ${name}`)
  return found
}

export type SqlStep = {
  reasonCode: string
  decision: Decision
  line: string
}

function multiIfBody(sql: string, endMarker: string): string[] {
  const lines = sql.split("\n")
  const end = lines.findIndex((line) => line.includes(endMarker))
  if (end < 0) return []
  let start = -1
  for (let i = end - 1; i >= 0; i -= 1) {
    if (lines[i].includes("multiIf(")) {
      start = i
      break
    }
  }
  if (start < 0) return []
  return lines.slice(start + 1, end).map((line) => line.trim()).filter(Boolean)
}

function quotedValue(line: string): { condition: string | null; value: string } | null {
  const only = line.match(/^'([^']+)',?$/)
  if (only) return { condition: null, value: only[1] }
  const paired = line.match(/^(.*),\s*'([^']+)',?\s*$/)
  if (!paired) return null
  return { condition: paired[1].trim(), value: paired[2] }
}

export function sqlCascade(sql: string): SqlStep[] {
  const decisions = multiIfBody(sql, "AS decision").map(quotedValue)
  const reasons = multiIfBody(sql, "AS reason_code").map(quotedValue)
  const steps: SqlStep[] = []
  for (let i = 0; i < reasons.length; i += 1) {
    const reason = reasons[i]
    const decision = decisions[i]
    if (!reason || !decision) continue
    if (decision.value !== "ALLOW" && decision.value !== "ASK" && decision.value !== "BLOCK") continue
    steps.push({
      reasonCode: reason.value,
      decision: decision.value,
      line: reason.condition ? `${reason.condition} → ${reason.value}` : reason.value,
    })
  }
  return steps
}

export function reasonLine(sql: string, reasonCode: string): string | undefined {
  return sqlCascade(sql).find((step) => step.reasonCode === reasonCode)?.line
}
