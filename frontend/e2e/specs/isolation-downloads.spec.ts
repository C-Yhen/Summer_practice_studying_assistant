import { expect, test, type Page } from '../fixtures'
import {
  apiData,
  authenticatePage,
  bootstrapPractice,
  createActivePlan,
  createCalendarEvent,
  createCourse,
  listTodayTasks,
  localDate,
  randomIdentity,
  registerAndLogin,
  submitPractice,
  uploadDocument,
} from '../helpers/api'
import { activateVisible } from '../helpers/ui'

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

test('one browser A/B/A story isolates every prepared visible resource', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/404.*(courses|documents|recommendations)|Failed to load resource.*404/)
  const userA = await registerAndLogin(request, randomIdentity('isolation-a'))
  const userB = await registerAndLogin(request, randomIdentity('isolation-b'))
  const courseA = await createCourse(request, userA.token, `A complete bundle ${Date.now()}`)
  const documentA = await uploadDocument(request, userA.token, courseA.id, 'a-private-document.txt')
  await createActivePlan(request, userA.token, courseA.id)
  const today = await listTodayTasks(request, userA.token, courseA.id)
  const taskA = today.items[0]
  await apiData(request, userA.token, 'post', `/study-tasks/${taskA.id}/complete`, { data: { actual_minutes: 12 } })
  const questions = await bootstrapPractice(request, userA.token, courseA.id)
  await submitPractice(request, userA.token, courseA.id, questions.items[0].id, 'B')
  const recommendations = await apiData(request, userA.token, 'get', `/courses/${courseA.id}/recommendations?limit=20&category=all`)
  await apiData(request, userA.token, 'post', `/courses/${courseA.id}/recommendations/feedback`, {
    data: { recommendation_key: recommendations.items[0].recommendation_key, action: 'saved' },
  })
  const reportA = await apiData(request, userA.token, 'post', '/async-tasks', {
    data: {
      task_type: 'weekly_report',
      input_data: { start_date: localDate(-6), end_date: localDate(), course_id: courseA.id },
    },
  })
  const calendarA = await createCalendarEvent(request, userA.token, {
    title: 'A private calendar event',
    start_at: `${localDate()}T01:00:00.000Z`,
    end_at: `${localDate()}T01:30:00.000Z`,
    idempotency_key: `a-private-${Date.now()}`,
    study_task_id: taskA.id,
  })

  await authenticatePage(page, userA.token)
  await page.goto('/courses')
  await expect(page.getByText(courseA.name, { exact: true })).toBeVisible()
  await page.goto(`/documents/tasks?courseId=${courseA.id}&documentId=${documentA.document.id}&taskId=${documentA.async_task_id}`)
  await expect(page.getByText('a-private-document', { exact: false }).first()).toBeVisible()
  await page.goto(`/today?date=${taskA.scheduled_date}&courseId=${courseA.id}`)
  await expect(page.getByText('实际 12 分钟')).toBeVisible()
  await page.goto(`/wrong-book?courseId=${courseA.id}`)
  await expect(page.locator('.item')).toHaveCount(1)
  await page.goto(`/recommendations?courseId=${courseA.id}`)
  await page.getByRole('button', { name: '推荐历史' }).click()
  await expect(page.getByText('有帮助 1')).toBeVisible()
  await page.getByRole('dialog', { name: '推荐历史' }).locator('.el-dialog__headerbtn').click()
  await page.goto(`/tasks?taskId=${reportA.task_id}`)
  await expect(page.getByText('学习周报', { exact: true }).first()).toBeVisible()
  await page.goto(`/calendar?courseId=${courseA.id}&eventId=${calendarA.event_id}`)
  await expect(page.getByText('A private calendar event', { exact: true })).toBeVisible()
  const eventDialog = page.getByRole('dialog', { name: '本地日历事件' })
  await expect(eventDialog).toBeVisible()
  await activateVisible(page, eventDialog.locator('.el-dialog__close'))

  await logout(page)
  await login(page, userB.identity.email, userB.identity.password)
  if ((page.viewportSize()?.width || 0) >= 900) {
    await expect(page.locator('.user-chip')).toContainText(userB.identity.email)
  } else {
    await expect(page.locator('.user-chip')).toBeVisible()
  }
  const userBCoursesResponse = page.waitForResponse((response) => (
    response.request().method() === 'GET'
    && new URL(response.url()).pathname === '/api/v1/courses'
  ))
  await page.goto('/courses')
  const userBCourseBody = await (await userBCoursesResponse).json()
  expect(userBCourseBody.data.items.map((item: { name: string }) => item.name)).not.toContain(courseA.name)
  await expect(page.locator('.course-card').filter({ hasText: courseA.name })).toHaveCount(0)
  await page.getByRole('button', { name: '打开全局快捷搜索' }).click()
  const quickSearch = page.getByRole('dialog').filter({ has: page.getByLabel('搜索功能或课程') })
  await expect(quickSearch.locator('.course-group').getByText(courseA.name, { exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await page.goto(`/courses/${courseA.id}`)
  await expect(page.getByText('课程不存在或无权访问', { exact: true })).toBeVisible()
  await page.goto(`/documents/tasks?courseId=${courseA.id}&documentId=${documentA.document.id}&taskId=${documentA.async_task_id}`)
  await expect(page.getByText(/不属于当前账号|无权|失败/).first()).toBeVisible()
  await page.goto(`/today?courseId=${courseA.id}&taskId=${taskA.id}`)
  await expect(page.getByText('URL 中的课程不属于当前账号或已归档')).toBeVisible()
  await page.goto(`/recommendations?courseId=${courseA.id}`)
  await expect(page.getByText('课程不存在、已归档或无权访问')).toBeVisible()
  await page.goto(`/tasks?taskId=${reportA.task_id}`)
  await expect(page.getByText('任务不存在或不属于当前账号')).toBeVisible()
  await page.goto(`/calendar?courseId=${courseA.id}&eventId=${calendarA.event_id}`)
  await expect(page.getByText('日历事件不存在或不属于当前账号')).toBeVisible()
  await expect(page.getByText('A private calendar event', { exact: true })).toHaveCount(0)
  expect(calendarA.event_id).toBeGreaterThan(0)

  await logout(page)
  await login(page, userA.identity.email, userA.identity.password)
  await page.goto('/courses')
  await expect(page.getByText(courseA.name, { exact: true })).toBeVisible()
  await page.goto(`/wrong-book?courseId=${courseA.id}`)
  await expect(page.locator('.item')).toHaveCount(1)
  await page.goto(`/calendar?courseId=${courseA.id}&eventId=${calendarA.event_id}`)
  await expect(page.getByText('A private calendar event', { exact: true })).toBeVisible()
  await expect(page.getByRole('dialog', { name: '本地日历事件' })).toBeVisible()
})
