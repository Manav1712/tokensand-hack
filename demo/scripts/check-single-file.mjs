import { copyFileSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const demo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const built = path.join(demo, "dist", "index.html")
const html = readFileSync(built, "utf8")
const problems = []

if (/<script\b[^>]*\bsrc\s*=/i.test(html)) problems.push("external script")
if (/<link\b[^>]*\bhref\s*=\s*['"]https?:/i.test(html)) problems.push("external stylesheet")
if (/@import\b/i.test(html)) problems.push("@import")

for (const match of html.matchAll(/url\(\s*['"]?([^'")]+)/gi)) {
  const value = match[1]
  if (!value.startsWith("data:")) problems.push(`asset url not inlined: ${value.slice(0, 80)}`)
}

const size = statSync(built).size
const limit = 3 * 1024 * 1024
if (size > limit) problems.push(`size ${size} exceeds ${limit}`)

if (problems.length > 0) {
  console.error(problems.join("\n"))
  process.exit(1)
}

const out = path.join(demo, "skill-warden-demo.html")
copyFileSync(built, out)
console.log(`ok ${(size / 1024).toFixed(0)} KiB -> ${path.basename(out)}`)
