import { expect, test } from '../fixtures'
import { apiData, authenticatePage, randomIdentity, registerAndLogin } from '../helpers/api'

test('first-use onboarding can complete, persist, and replay from settings', async ({ page, request }) => {
  const { token } = await registerAndLogin(request, randomIdentity('onboarding-complete'))
  await authenticatePage(page, token)
  await page.goto('/dashboard')

  await expect(page.getByRole('dialog', { name: '欢迎使用 StudyPilot' })).toBeVisible()
  await page.getByRole('button', { name: '开始引导' }).click()
  for (let step = 1; step <= 4; step += 1) {
    await expect(page.getByText(`${step} / 5`, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '下一步' }).click()
  }
  await expect(page.getByText('5 / 5', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '完成' }).click()
  await expect(page.getByRole('dialog', { name: '新手引导完成' })).toBeVisible()
  await page.getByRole('button', { name: '进入首页' }).click()

  await page.reload()
  await expect(page.getByRole('dialog', { name: '欢迎使用 StudyPilot' })).toBeHidden()
  const saved = await apiData(request, token, 'get', '/users/me/profile') as { preferences: { onboarding_seen_version: number; onboarding_completed_at: string | null } }
  expect(saved.preferences.onboarding_seen_version).toBe(1)
  expect(saved.preferences.onboarding_completed_at).not.toBeNull()

  await page.goto('/settings')
  await page.getByRole('button', { name: '重新查看新手引导' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('dialog', { name: '欢迎使用 StudyPilot' })).toBeVisible()
  const afterReplay = await apiData(request, token, 'get', '/users/me/profile') as { preferences: { onboarding_seen_version: number; onboarding_completed_at: string | null } }
  expect(afterReplay.preferences).toEqual(saved.preferences)
  await page.getByRole('button', { name: '暂时跳过' }).click()
})

test('skipping onboarding is persisted and does not return after refresh', async ({ page, request }) => {
  const { token } = await registerAndLogin(request, randomIdentity('onboarding-skip'))
  await authenticatePage(page, token)
  await page.goto('/dashboard')
  await expect(page.getByRole('dialog', { name: '欢迎使用 StudyPilot' })).toBeVisible()
  await page.getByRole('button', { name: '暂时跳过' }).click()
  await page.reload()
  await expect(page.getByRole('dialog', { name: '欢迎使用 StudyPilot' })).toBeHidden()
  const saved = await apiData(request, token, 'get', '/users/me/profile') as { preferences: { onboarding_seen_version: number; onboarding_completed_at: string | null } }
  expect(saved.preferences.onboarding_seen_version).toBe(1)
  expect(saved.preferences.onboarding_completed_at).toBeNull()
})
