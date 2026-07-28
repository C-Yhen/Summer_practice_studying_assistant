import { expect, test as base, type Page } from '@playwright/test'

type ConsoleAudit = {
  allow(pattern: RegExp): void
}

type Fixtures = {
  consoleAudit: ConsoleAudit
}

export const test = base.extend<Fixtures>({
  consoleAudit: async ({ page }, use) => {
    const allowed: RegExp[] = []
    const failures: string[] = []
    const record = (kind: string, message: string) => {
      if (!allowed.some((pattern) => pattern.test(message))) failures.push(`${kind}: ${message}`)
    }
    page.on('pageerror', (error) => record('pageerror', error.message))
    page.on('console', (message) => {
      if (message.type() !== 'error') return
      const location = message.location().url
      record('console.error', `${message.text()}${location ? ` @ ${location}` : ''}`)
    })
    await use({ allow: (pattern) => allowed.push(pattern) })
    await page.waitForTimeout(0)
    expect(failures, 'unexpected browser console/page errors').toEqual([])
  },
})

export { expect }
export type { Page }
