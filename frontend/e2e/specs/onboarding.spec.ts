import { expect, test } from '../fixtures'
import { apiData, authenticatePage, createActivePlan, createCourse, listTodayTasks, randomIdentity, registerAndLogin, uploadDocument } from '../helpers/api'

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
  await page.getByRole('button', { name: '完成', exact: true }).click()
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

test('real onboarding checklist uses server progress and safe course-aware navigation', async ({ page, request }) => {
  const { token } = await registerAndLogin(request, randomIdentity('checklist'))
  await authenticatePage(page, token)
  await page.goto('/dashboard')
  await page.getByRole('button', { name: '暂时跳过' }).click()
  await expect(page.getByRole('heading', { name: '开始使用 StudyPilot' })).toBeVisible()
  await expect(page.getByText('0 / 5', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /创建第一门课程/ }).click()
  await expect(page).toHaveURL(/\/courses$/)

  const course = await createCourse(request, token, `Checklist ${Date.now()}`)
  await uploadDocument(request, token, course.id, 'checklist-ready.txt')
  await page.goto('/dashboard')
  await expect(page.getByText('2 / 5', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /创建第一门课程/ })).toHaveClass(/completed/)
  await expect(page.getByRole('button', { name: /上传第一份学习资料/ })).toHaveClass(/completed/)
  await page.getByRole('button', { name: /提出第一个课程问题/ }).click()
  await expect(page).toHaveURL(new RegExp(`/chat\\?courseId=${course.id}`))
})

test('onboarding tour keeps course and material targets distinct', async ({ page, request }, testInfo) => {
  const { token } = await registerAndLogin(request, randomIdentity('target-audit'))
  await authenticatePage(page, token)
  await page.goto('/dashboard')
  await expect(page.locator('[data-onboarding-target~="documents"]')).toHaveCount(1)
  if (testInfo.project.name === 'desktop-chrome') {
    await expect(page.locator('[data-onboarding-target~="courses"]')).toHaveCount(1)
    const courseTarget = await page.locator('[data-onboarding-target~="courses"]').evaluate((element) => element.getAttribute('data-onboarding-target'))
    const documentTarget = await page.locator('[data-onboarding-target~="documents"]').evaluate((element) => element.getAttribute('data-onboarding-target'))
    expect(courseTarget).not.toBe(documentTarget)
    return
  }

  // The collapsed mobile sidebar deliberately has no course target.  The
  // Element Plus Tour must fall back to its centered card and still advance.
  await expect(page.locator('[data-onboarding-target~="courses"]')).toHaveCount(0)
  await page.getByRole('button', { name: '开始引导' }).click()
  await expect(page.getByText('1 / 5', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('2 / 5', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '跳过引导' }).click()
})

test('checklist completion and progress remain isolated between users', async ({ page, request }) => {
  const userA = await registerAndLogin(request, randomIdentity('checklist-a'))
  const userB = await registerAndLogin(request, randomIdentity('checklist-b'))
  const course = await createCourse(request, userA.token, `Checklist complete ${Date.now()}`)
  const document = await uploadDocument(request, userA.token, course.id, 'checklist-complete.txt')
  const session = await apiData(request, userA.token, 'post', `/courses/${course.id}/chat-sessions`, {
    data: { title: 'Checklist session', mode: 'strict', document_ids: [document.document.id] },
  }) as { session_id: string }
  await apiData(request, userA.token, 'post', `/chat-sessions/${session.session_id}/messages`, {
    data: { question: '请帮我复习资料', mode: 'strict', document_ids: [document.document.id] },
  })
  await createActivePlan(request, userA.token, course.id)
  const today = await listTodayTasks(request, userA.token, course.id)
  await apiData(request, userA.token, 'post', `/study-tasks/${today.items[0].id}/complete`, { data: { actual_minutes: 10 } })

  await authenticatePage(page, userA.token)
  await page.goto('/dashboard')
  await page.getByRole('button', { name: '暂时跳过' }).click()
  await expect(page.getByRole('heading', { name: '新手任务已完成' })).toBeVisible()
  await expect(page.getByText('5 / 5', { exact: true })).toBeVisible()

  await authenticatePage(page, userB.token)
  await page.goto('/dashboard')
  await page.getByRole('button', { name: '暂时跳过' }).click()
  await expect(page.getByRole('heading', { name: '开始使用 StudyPilot' })).toBeVisible()
  await expect(page.getByText('0 / 5', { exact: true })).toBeVisible()
})
