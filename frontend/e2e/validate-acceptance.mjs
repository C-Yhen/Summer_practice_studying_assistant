import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontend = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const documentPath = path.join(frontend, '..', 'docs', 'VISIBLE_FUNCTION_ACCEPTANCE.md')
const content = await readFile(documentPath, 'utf8')
const allowed = new Set(['PASS', 'FIXED_AND_PASS', 'EXCLUDED', 'BLOCKED'])
const rows = content
  .split(/\r?\n/)
  .filter((line) => /^\|\s*[A-Z]\d{2}\s*\|/.test(line))
  .map((line) => line.split('|').slice(1, -1).map((cell) => cell.trim()))

const ids = new Set()
const counts = { PASS: 0, FIXED_AND_PASS: 0, EXCLUDED: 0, BLOCKED: 0 }
const errors = []

for (const cells of rows) {
  const id = cells[0]
  const status = cells.at(-1)
  if (ids.has(id)) errors.push(`重复 ID：${id}`)
  ids.add(id)
  if (!allowed.has(status)) errors.push(`非法状态：${id} -> ${status}`)
  else counts[status] += 1
}

const summary = {}
for (const match of content.matchAll(/^- (清单条目|PASS|FIXED_AND_PASS|EXCLUDED|BLOCKED)：(\d+)$/gm)) {
  summary[match[1]] = Number(match[2])
}

const expected = { 清单条目: rows.length, ...counts }
for (const [label, value] of Object.entries(expected)) {
  if (summary[label] !== value) {
    errors.push(`汇总不一致：${label} 文档=${summary[label] ?? '缺失'} 实际=${value}`)
  }
}

if (errors.length) {
  console.error(errors.join('\n'))
  process.exit(1)
}

console.log(
  `验收清单有效：${rows.length} 项，PASS=${counts.PASS}，FIXED_AND_PASS=${counts.FIXED_AND_PASS}，EXCLUDED=${counts.EXCLUDED}，BLOCKED=${counts.BLOCKED}`,
)
