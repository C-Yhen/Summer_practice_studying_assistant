import { expect, type Locator, type Page } from '@playwright/test'

export async function activateVisible(page: Page, locator: Locator) {
  if ((page.viewportSize()?.width || 0) > 700) {
    await locator.click()
    return
  }
  await expect(locator).toBeVisible()
  const box = await locator.boundingBox()
  if (!box) throw new Error('Visible mobile control has no bounding box')
  await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2)
}

export async function activateVisibleTwice(page: Page, locator: Locator) {
  if ((page.viewportSize()?.width || 0) > 700) {
    await locator.dblclick()
    return
  }
  await activateVisible(page, locator)
  await activateVisible(page, locator)
}
