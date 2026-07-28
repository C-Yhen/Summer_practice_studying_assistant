import { expect, test, type Page } from '../fixtures'
import { randomIdentity, registerAndLogin } from '../helpers/api'

async function fillRegistration(page: Page, identity: ReturnType<typeof randomIdentity>) {
  await page.getByPlaceholder('AI 将这样称呼你').fill(identity.displayName)
  await page.getByPlaceholder('name@university.edu').fill(identity.email)
  await page.getByPlaceholder('至少 8 位').fill(identity.password)
  await page.getByPlaceholder('请再次输入密码').fill(identity.password)
}

test('registration agreement, password visibility, duplicate lock and session flow are real', async ({ page }) => {
  const identity = randomIdentity('auth')
  let registrations = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/auth/register')) registrations += 1
  })
  await page.goto('/register')
  await fillRegistration(page, identity)
  await expect(page.getByPlaceholder('至少 8 位')).toHaveAttribute('type', 'password')
  await page.getByPlaceholder('至少 8 位').locator('..').locator('.el-input__password').click()
  await expect(page.getByPlaceholder('至少 8 位')).toHaveAttribute('type', 'text')
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await expect(page.getByText('请先阅读并同意服务条款和隐私政策')).toBeVisible()
  expect(registrations).toBe(0)

  await page.locator('.agreement').click()
  await expect(page.getByRole('checkbox')).toBeChecked()
  await page.getByRole('button', { name: '创建账号', exact: true }).dblclick()
  await expect(page).toHaveURL(/\/dashboard$/)
  expect(registrations).toBe(1)
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
})

test('duplicate email is shown by the registration form and can recover', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/409.*auth\/register|auth\/register.*409|Failed to load resource.*409/)
  const { identity } = await registerAndLogin(request, randomIdentity('duplicate'))
  const replacement = randomIdentity('replacement')
  let registrations = 0
  page.on('request', (seen) => {
    if (seen.method() === 'POST' && seen.url().endsWith('/api/v1/auth/register')) registrations += 1
  })
  await page.goto('/register')
  await fillRegistration(page, identity)
  await page.locator('.agreement').click()
  await expect(page.getByRole('checkbox')).toBeChecked()
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await expect(page.getByText('该邮箱已注册')).toBeVisible()
  await expect(page.getByPlaceholder('name@university.edu')).toHaveValue(identity.email)
  await expect(page.getByRole('button', { name: '创建账号', exact: true })).toBeEnabled()
  expect(registrations).toBe(1)

  await page.getByPlaceholder('name@university.edu').fill(replacement.email)
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  expect(registrations).toBe(2)
})

test('login validation and wrong password remain local to login', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/401.*auth\/login|auth\/login.*401|Failed to load resource.*401/)
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
