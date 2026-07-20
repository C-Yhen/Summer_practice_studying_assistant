import { expect, test } from '@playwright/test'
import { randomIdentity, registerAndLogin } from '../helpers/api'

test('register, restore, logout and redirect login are real', async ({ page, request }) => {
  const identity = randomIdentity('auth')
  await page.goto('/register')
  await page.getByPlaceholder('AI 将这样称呼你').fill(identity.displayName)
  await page.getByPlaceholder('name@university.edu').fill(identity.email)
  await page.getByPlaceholder('至少 8 位').fill(identity.password)
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.reload()
  await expect(page).toHaveURL(/\/dashboard$/)

  await page.locator('.user-chip').click()
  await page.getByText('退出登录', { exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => sessionStorage.getItem('studypilot_token'))).toBeNull()
  await page.goBack()
  await expect(page).not.toHaveURL(/\/dashboard$/)

  await page.goto('/login?redirect=/settings')
  await page.getByPlaceholder('name@university.edu').fill(identity.email)
  await page.getByPlaceholder('请输入密码').fill(identity.password)
  await page.getByPlaceholder('请输入密码').press('Enter')
  await expect(page).toHaveURL(/\/settings$/)

  const duplicate = await request.post(`${process.env.E2E_API_ORIGIN}/api/v1/auth/register`, {
    data: { display_name: identity.displayName, email: identity.email, password: identity.password },
  })
  expect(duplicate.status()).toBe(409)
})

test('login validation and wrong password remain local to login', async ({ page, request }) => {
  const { identity } = await registerAndLogin(request)
  await page.goto('/login')
  await page.getByRole('button', { name: '登录 StudyPilot' }).click()
  await expect(page.getByText('请输入邮箱')).toBeVisible()
  await page.getByPlaceholder('name@university.edu').fill(identity.email)
  await page.getByPlaceholder('请输入密码').fill(`${identity.password}-wrong`)
  await page.getByRole('button', { name: '登录 StudyPilot' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText('邮箱或密码错误')).toBeVisible()
})
