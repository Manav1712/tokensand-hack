import { useState } from "react"
import { fixtureByName, reasonLine, traces, type Fixture } from "../data/traces"
import type { SceneSpec } from "../stage/types"
import { Badge } from "../ui/Badge"
import { CodeMorph } from "../ui/CodeMorph"

const README_OFF = "memory-poison"
const README_ON = "audited-exfil"

function skillMarkdown(fixture: Fixture): string {
  return [...fixture.files]
    .sort((a, b) => a.path.localeCompare(b.path))
    .map((file) => `# ${file.path}\n\n${file.text.trimEnd()}`)
    .join("\n\n")
}

function View() {
  const [name, setName] = useState(traces.fixtures[0].name)
  const fixture = fixtureByName(name)
  const readmePair = name === README_OFF || name === README_ON
  const line = reasonLine(traces.verdictSql, fixture.verdict.reasonCode)

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="eyebrow">playground</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          {traces.fixtures.map((item) => (
            <button
              key={item.name}
              type="button"
              aria-pressed={item.name === name}
              onClick={() => setName(item.name)}
            >
              {item.name}
            </button>
          ))}
          <button
            type="button"
            aria-pressed={name === README_ON}
            disabled={!readmePair}
            onClick={() => setName(name === README_ON ? README_OFF : README_ON)}
            style={readmePair ? undefined : { opacity: 0.4 }}
          >
            README says audited
          </button>
        </div>
      </div>
      <CodeMorph code={skillMarkdown(fixture)} lang="markdown" />
      <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {fixture.findings.map((finding, index) => (
            <span
              key={`${finding.source}-${finding.ruleId}-${index}`}
              className="muted mono"
              style={{
                fontSize: 12,
                border: "1px solid rgba(235, 236, 239, 0.12)",
                borderRadius: 999,
                padding: "3px 10px",
              }}
            >
              {finding.source} {finding.ruleId} {finding.severity}
            </span>
          ))}
        </div>
        <Badge decision={fixture.verdict.decision} reason={fixture.verdict.reasonCode} />
        {line ? (
          <p className="muted mono" style={{ fontSize: 13 }}>
            {line}
          </p>
        ) : null}
        {fixture.reader.flags.length > 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>
            reader flags are scripted
          </p>
        ) : null}
      </div>
    </>
  )
}

export const scene: SceneSpec = { id: "playground", steps: 1, View }
