import { describe, expect, it } from "vitest"
import rawText from "./traces.json?raw"
import { fixtureByName, reasonLine, sqlCascade, traces } from "./traces"

const NONCE = "FAKE-CANARY-NONCE-DEMO"

const expected: Record<string, [string, string]> = {
  "clean-date": ["ALLOW", "clean"],
  "memory-poison": ["BLOCK", "high_finding"],
  "audited-exfil": ["BLOCK", "high_finding"],
  "prose-exfil": ["BLOCK", "high_finding"],
}

describe("traces", () => {
  it("matches the recorded verdict for each fixture", () => {
    expect(traces.fixtures.map((item) => item.name).sort()).toEqual(Object.keys(expected).sort())
    for (const [name, [decision, reasonCode]] of Object.entries(expected)) {
      expect(fixtureByName(name).verdict).toEqual({ decision, reasonCode })
    }
    expect(traces.jail.verdict).toEqual({ decision: "BLOCK", reasonCode: "canary" })
  })

  it("maps every reason code onto a verdict.sql line", () => {
    const codes = new Set(sqlCascade(traces.verdictSql).map((step) => step.reasonCode))
    for (const fixture of traces.fixtures) {
      expect(codes.has(fixture.verdict.reasonCode)).toBe(true)
      expect(reasonLine(traces.verdictSql, fixture.verdict.reasonCode)).toBeTruthy()
    }
    expect(reasonLine(traces.verdictSql, traces.jail.verdict.reasonCode)).toContain("canary")
    expect(codes.has("clean")).toBe(true)
    expect(codes.has("medium_only")).toBe(true)
  })

  it("does not contain the honeytoken nonce", () => {
    expect(rawText).not.toContain(NONCE)
  })
})
