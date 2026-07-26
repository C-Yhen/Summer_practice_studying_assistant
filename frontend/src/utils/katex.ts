import katex from 'katex'
import 'katex/dist/katex.min.css'

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderFormula(formula: string, displayMode: boolean, original: string): string {
  try {
    return katex.renderToString(formula.trim(), {
      displayMode,
      throwOnError: false,
      trust: false,
    })
  } catch {
    return `<code>${escapeHtml(original)}</code>`
  }
}

export function renderLatex(text: string): string {
  if (!text) return ''
  const pattern = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g
  let html = ''
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    html += escapeHtml(text.slice(lastIndex, match.index)).replace(/\n/g, '<br>')
    const isBlock = match[1] !== undefined
    const formula = (isBlock ? match[1] : match[2]) ?? ''
    html += renderFormula(formula, isBlock, match[0])
    lastIndex = pattern.lastIndex
  }

  return html + escapeHtml(text.slice(lastIndex)).replace(/\n/g, '<br>')
}
