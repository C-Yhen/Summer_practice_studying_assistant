import { expect, test } from '@playwright/test'
import { authenticatePage, createCourse, registerAndLogin } from '../helpers/api'

test('create course with visible form and navigate through quick search', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  await authenticatePage(page, token)
  await page.goto('/courses')
  await page.getByRole('button', { name: '创建课程', exact: true }).first().click()
  const courseName = `Visible Course ${Date.now()}`
  await page.getByLabel('课程名称（必填）').fill(courseName)
  await page.getByLabel('课程编号').fill('VISIBLE-17')
  await page.getByRole('button', { name: '创建课程', exact: true }).last().click()
  await expect(page).toHaveURL(/\/courses\/\d+$/)
  await expect(page.getByRole('heading', { name: courseName })).toBeVisible()

  await page.keyboard.press('Control+k')
  const search = page.getByLabel('搜索功能或课程')
  await expect(search).toBeVisible()
  await search.fill('学习日历')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/calendar$/)
  await expect(page.getByText('LEARNING CALENDAR', { exact: true })).toBeVisible()
})

test('business 401 clears session once and login returns to original URL', async ({ page, request }) => {
  const { token, identity } = await registerAndLogin(request)
  await authenticatePage(page, token)
  await page.goto('/settings')
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => sessionStorage.setItem('studypilot_token', 'invalid-round17-token'))
  if ((page.viewportSize()?.width || 0) < 900) {
    await page.getByRole('button', { name: '打开导航' }).click()
    await expect(page.locator('.drawer-menu')).toBeVisible()
    await page.locator('.drawer-menu').getByText('课程管理', { exact: true }).click()
  } else {
    await page.locator('.sidebar-menu').getByText('课程管理', { exact: true }).click()
  }
  await expect(page).toHaveURL(/\/login\?redirect=\/courses/)
  await expect(page.getByText('登录状态已失效，请重新登录')).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('studypilot_token'))).toBeNull()

  await page.getByPlaceholder('name@university.edu').fill(identity.email)
  await page.getByPlaceholder('请输入密码').fill(identity.password)
  await page.getByRole('button', { name: '登录 StudyPilot' }).click()
  await expect(page).toHaveURL(/\/courses$/)
})

test('quick-search keyboard highlight stays inside the scroll viewport', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  for (let index = 0; index < 8; index += 1) {
    await createCourse(request, token, `Scrollable Course ${String(index).padStart(2, '0')}`)
  }
  await authenticatePage(page, token)
  await page.goto('/dashboard')
  await page.getByRole('button', { name: '打开全局快捷搜索' }).click()
  await expect(page.getByLabel('搜索功能或课程')).toBeVisible()
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
  await expect(page.getByLabel('搜索功能或课程')).toBeHidden()
})
