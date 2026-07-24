declare const katex: {
  renderToString(formula: string, options?: { displayMode?: boolean; throwOnError?: boolean }): string
}

export function renderLatex(text: string): string {
  if (!text) return ''
  // Escape HTML first (except for our LaTeX delimiters)
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Block math: $$...$$
  html = html.replace(/\$\$([\s\S]*?)\$\$/g, (_: string, formula: string) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false })
    } catch {
      return `<code>$${formula}$</code>`
    }
  })

  // Inline math: $...$
  html = html.replace(/\$([^\$]+?)\$/g, (_: string, formula: string) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false })
    } catch {
      return `<code>$${formula}$</code>`
    }
  })

  // Restore newlines as <br> for non-block-math content
  html = html.replace(/\n/g, '<br>')

  return html
}
