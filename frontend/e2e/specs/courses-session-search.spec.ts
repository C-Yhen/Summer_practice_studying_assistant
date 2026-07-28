import { expect, test, type Page } from '../fixtures'
import { authenticatePage, createCourse, randomIdentity, registerAndLogin } from '../helpers/api'

async function openSearch(page: Page) {
  if ((page.viewportSize()?.width || 0) < 900) {
    await page.getByRole('button', { name: '打开全局快捷搜索' }).click()
  } else {
    await page.getByRole('button', { name: '打开全局快捷搜索' }).click()
  }
  await expect(page.getByLabel('搜索功能或课程')).toBeVisible()
}

async function logout(page: Page) {
  await page.locator('.user-chip').click()
  await page.getByText('退出登录', { exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
}

async function login(page: Page, email: string, password: string) {
  await page.getByPlaceholder('name@university.edu').fill(email)
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.getByRole('button', { name: '登录 StudyPilot' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

test('visible course creation and every desktop/mobile search entry navigate correctly', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  await authenticatePage(page, token)
  await page.goto('/courses')
  await page.getByRole('button', { name: '创建课程', exact: true }).first().click()
  const courseName = `Visible Course ${Date.now()}`
  await page.getByLabel('课程名称（必填）').fill(courseName)
  await page.getByLabel('课程编号').fill('VISIBLE-17')
  await page.getByRole('button', { name: '创建课程', exact: true }).last().click()
  await expect(page).toHaveURL(/\/courses\/\d+$/)
  const courseUrl = page.url()

  await openSearch(page)
  const search = page.getByLabel('搜索功能或课程')
  await search.fill(courseName)
  await page.getByRole('option', { name: new RegExp(courseName) }).click()
  await expect(page).toHaveURL(courseUrl)

  if ((page.viewportSize()?.width || 0) >= 900) {
    await page.keyboard.press('Control+k')
  } else {
    await page.getByRole('button', { name: '打开全局快捷搜索' }).click()
  }
  await search.fill('学习日历')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/calendar/)
  await expect(page.getByText('LEARNING CALENDAR', { exact: true })).toBeVisible()

  const trigger = page.getByRole('button', { name: '打开全局快捷搜索' })
  await trigger.click()
  await search.fill('课程')
  await page.keyboard.press('Escape')
  await expect(search).toBeHidden()
  await expect(trigger).toBeFocused()
})

test('business 401 clears session once and login returns to original URL', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/401.*courses|courses.*401|Failed to load resource.*401/)
  const { token, identity } = await registerAndLogin(request)
  await authenticatePage(page, token)
  await page.goto('/settings')
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => sessionStorage.setItem('studypilot_token', 'invalid-round17-token'))
  if ((page.viewportSize()?.width || 0) < 900) {
    await page.getByRole('button', { name: '打开导航' }).click()
    await page.locator('.drawer-menu').getByText('课程管理', { exact: true }).click()
  } else {
    await page.locator('.sidebar-menu').getByText('课程管理', { exact: true }).click()
  }
  await expect(page).toHaveURL(/\/login\?redirect=\/courses/)
  await expect(page.getByText('登录状态已失效，请重新登录')).toHaveCount(1)
  expect(await page.evaluate(() => sessionStorage.getItem('studypilot_token'))).toBeNull()
  await page.getByPlaceholder('name@university.edu').fill(identity.email)
  await page.getByPlaceholder('请输入密码').fill(identity.password)
  await page.getByRole('button', { name: '登录 StudyPilot' }).click()
  await expect(page).toHaveURL(/\/courses$/)
})

test('concurrent desktop 401 responses share one invalidation flow', async ({ page, request, consoleAudit }) => {
  test.skip((page.viewportSize()?.width || 0) < 900, 'desktop-only concurrency path')
  consoleAudit.allow(/401.*courses|courses.*401|Failed to load resource.*401/)
  const { token } = await registerAndLogin(request)
  await authenticatePage(page, token)
  await page.goto('/settings')
  await expect(page.locator('.el-loading-mask')).toBeHidden()
  await page.evaluate(() => sessionStorage.setItem('studypilot_token', 'invalid-round17-token'))
  let rejected = 0
  await page.route('**/api/v1/courses**', async (route) => {
    rejected += 1
    await new Promise((resolve) => setTimeout(resolve, 1_000))
    await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"INVALID_TOKEN"}' })
  })
  let loginNavigations = 0
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame() && new URL(frame.url()).pathname === '/login') loginNavigations += 1
  })
  await page.evaluate(() => {
    const search = document.querySelector<HTMLElement>('[aria-label="打开全局快捷搜索"]')
    const course = [...document.querySelectorAll<HTMLElement>('.sidebar-menu *')]
      .find((element) => element.textContent?.trim() === '课程管理')
    search?.click()
    course?.closest<HTMLElement>('.el-menu-item')?.click()
  })
  await expect(page).toHaveURL(/\/login/)
  expect(rejected).toBeGreaterThanOrEqual(2)
  expect(loginNavigations).toBe(1)
  await expect(page.getByText('登录状态已失效，请重新登录')).toHaveCount(1)
})

test('a stale 401 after manual logout does not show a false expiry warning', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/401.*courses|courses.*401|Failed to load resource.*401/)
  const { token } = await registerAndLogin(request)
  await authenticatePage(page, token)
  await page.goto('/dashboard')
  await page.route('**/api/v1/courses**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2_000))
    await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"STALE_TOKEN"}' })
  })
  await openSearch(page)
  await page.keyboard.press('Escape')
  await logout(page)
  await page.waitForTimeout(2_200)
  await expect(page.getByText('登录状态已失效，请重新登录')).toHaveCount(0)
})

test('quick-search keyboard highlight stays inside the scroll viewport', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  for (let index = 0; index < 8; index += 1) {
    await createCourse(request, token, `Scrollable Course ${String(index).padStart(2, '0')}`)
  }
  await authenticatePage(page, token)
  await page.goto('/dashboard')
  await openSearch(page)
  await expect(page.getByText('Scrollable Course 00', { exact: true })).toBeVisible()
  for (let index = 0; index < 20; index += 1) await page.keyboard.press('ArrowDown')
  const visible = await page.locator('.result-list').evaluate((container) => {
    const active = container.querySelector<HTMLElement>('[role="option"][aria-selected="true"]')
    if (!active) return false
    const listRect = container.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    return activeRect.top >= listRect.top && activeRect.bottom <= listRect.bottom
  })
  expect(visible).toBe(true)
  await page.keyboard.press('Escape')
})

test('one browser A/B/A switch never leaks quick-search course cache', async ({ page, request }) => {
  const userA = await registerAndLogin(request, randomIdentity('search-a'))
  const userB = await registerAndLogin(request, randomIdentity('search-b'))
  const courseA = await createCourse(request, userA.token, `A private ${Date.now()}`)
  const courseB = await createCourse(request, userB.token, `B private ${Date.now()}`)
  await authenticatePage(page, userA.token)
  await page.goto('/dashboard')
  await openSearch(page)
  await expect(page.getByText(courseA.name, { exact: true })).toBeVisible()
  await expect(page.getByText(courseB.name, { exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await logout(page)
  await login(page, userB.identity.email, userB.identity.password)
  await openSearch(page)
  await expect(page.getByText(courseB.name, { exact: true })).toBeVisible()
  await expect(page.getByText(courseA.name, { exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await logout(page)
  await login(page, userA.identity.email, userA.identity.password)
  await openSearch(page)
  await expect(page.getByText(courseA.name, { exact: true })).toBeVisible()
  await expect(page.getByText(courseB.name, { exact: true })).toHaveCount(0)
})
