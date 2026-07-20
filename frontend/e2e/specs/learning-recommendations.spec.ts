import { expect, test } from '../fixtures'
import {
  apiData,
  authenticatePage,
  bootstrapPractice,
  createActivePlan,
  createCourse,
  createLearningRecord,
  listTodayTasks,
  localDate,
  registerAndLogin,
  submitPractice,
  uploadDocument,
} from '../helpers/api'

test('today filters, URL task restore, completion lock, refresh persistence and idempotency are real', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/503.*study-tasks\/today|study-tasks\/today.*503|Failed to load resource.*503/)
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Today Flow ${Date.now()}`)
  await createActivePlan(request, token, course.id)
  const before = await listTodayTasks(request, token, course.id)
  expect(before.items.length).toBeGreaterThan(0)
  const task = before.items[0]
  await authenticatePage(page, token)
  await page.goto(`/today?date=${task.scheduled_date}&courseId=${course.id}&taskId=${task.id}`)
  const completionDialog = page.getByRole('dialog', { name: '完成学习任务' })
  await expect(completionDialog).toBeVisible()
  await expect(completionDialog.getByText(task.title, { exact: true })).toBeVisible()
  const actual = completionDialog.getByRole('spinbutton')
  let completions = 0
  page.on('request', (seen) => {
    if (seen.method() === 'POST' && seen.url().endsWith(`/study-tasks/${task.id}/complete`)) completions += 1
  })
  await actual.fill('')
  await completionDialog.getByRole('button', { name: '确认完成' }).click()
  await expect(page.locator('.el-message--warning')).toContainText('至少为 1 分钟')
  expect(completions).toBe(0)
  await actual.fill('17')
  await completionDialog.getByRole('button', { name: '确认完成' }).dblclick()
  await expect(page.getByText('已完成', { exact: true }).last()).toBeVisible()
  expect(completions).toBe(1)
  await page.reload()
  await expect(page.getByText('实际 17 分钟')).toBeVisible()
  const replay = await apiData(request, token, 'post', `/study-tasks/${task.id}/complete`, { data: { actual_minutes: 99 } })
  expect(replay.idempotent_replay).toBe(true)
  expect(replay.actual_minutes).toBe(17)

  await page.locator('.page-heading .el-select').click()
  await page.getByRole('option', { name: new RegExp(course.name) }).click()
  await expect(page).toHaveURL(new RegExp(`courseId=${course.id}`))
  await page.getByRole('button', { name: '刷新' }).click()
  await expect(page.getByText('已完成', { exact: true }).last()).toBeVisible()

  let listFailures = 1
  await page.route('**/api/v1/study-tasks/today?**', async (route) => {
    if (listFailures-- > 0) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"TODAY_TEMPORARY"}' })
    } else await route.continue()
  })
  await page.getByRole('button', { name: '刷新' }).click()
  await expect(page.getByText('TODAY_TEMPORARY')).toBeVisible()
  await page.getByRole('button', { name: '重新加载' }).click()
  await expect(page.getByText('TODAY_TEMPORARY')).toBeHidden()

  const dateInput = page.locator('.page-heading input[type="date"]')
  await dateInput.fill(localDate(30))
  await dateInput.press('Tab')
  await expect(page.getByText(/没有活动计划任务/)).toBeVisible()
  await dateInput.fill(task.scheduled_date)
  await dateInput.press('Tab')
  await expect(page.getByText('实际 17 分钟')).toBeVisible()

  await apiData(request, token, 'post', `/courses/${course.id}/study-plans/generate`, {
    data: {
      start_date: task.scheduled_date,
      end_date: task.scheduled_date,
      daily_availability: { default_minutes: 60 },
      session_minutes: 30,
      goal: 'candidate must remain hidden',
    },
  })
  const afterCandidate = await listTodayTasks(request, token, course.id, task.scheduled_date)
  expect(afterCandidate.items.every((item: { id: number }) => before.items.some((old: { id: number }) => old.id === item.id))).toBe(true)
})

test('practice retries the identical submission, shows results, and drives wrong-book and mastery UI', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/ERR_FAILED.*attempts|attempts.*ERR_FAILED|Failed to load resource.*attempts/)
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Practice Flow ${Date.now()}`)
  const other = await createCourse(request, token, `Practice Empty ${Date.now()}`)
  await createActivePlan(request, token, course.id)
  await createActivePlan(request, token, other.id)
  const questions = await bootstrapPractice(request, token, course.id)
  expect(questions.items.length).toBeGreaterThan(1)
  await authenticatePage(page, token)
  await page.goto(`/practice?courseId=${course.id}`)
  const firstOption = page.locator('.el-radio').filter({ hasText: 'B.' }).first()
  await firstOption.click()
  await page.locator('.el-radio').filter({ hasText: 'C.' }).first().click()
  await firstOption.click()

  const payloads: string[] = []
  let aborted = false
  await page.route(`**/api/v1/courses/${course.id}/practice/questions/*/attempts`, async (route) => {
    payloads.push(route.request().postData() || '')
    if (!aborted) {
      aborted = true
      await route.abort('failed')
    } else {
      await route.continue()
    }
  })
  await page.getByRole('button', { name: '提交答案' }).click()
  await expect(page.locator('.el-message--error')).toContainText(/提交失败|网络|无法连接后端/)
  await page.getByRole('button', { name: '提交答案' }).dblclick()
  await expect(page.getByText(/回答错误，正确答案：A/)).toBeVisible()
  expect(payloads).toHaveLength(2)
  expect(payloads[1]).toBe(payloads[0])
  await expect(page.getByText(/规则提示：关联知识点/)).toBeVisible()

  await page.getByRole('button', { name: '下一题' }).click()
  await page.locator('.el-radio').filter({ hasText: 'A.' }).first().click()
  await page.getByRole('button', { name: '提交答案' }).dblclick()
  await expect(page.getByText('回答正确', { exact: true })).toBeVisible()
  await page.locator('.page-heading .el-select').click()
  await page.getByRole('option', { name: other.name }).click()
  await expect(page.getByText('暂无题目；请先生成并确认学习计划以获得知识点')).toBeVisible()

  await page.goto(`/wrong-book?courseId=${course.id}`)
  await expect(page.getByText(/错误 1 次/)).toBeVisible()
  await page.getByRole('button', { name: '开始错题复习' }).click()
  await expect(page).toHaveURL(/mode=wrong/)
  await page.goBack()
  await expect(page.getByText(/错误 1 次/)).toBeVisible()
  await page.getByRole('button', { name: '查看解析' }).click()
  await expect(page.getByText(/错题解析：/)).toBeVisible()
  let wrongBookWrites = 0
  page.on('request', (seen) => {
    if (seen.method() === 'PATCH' && /\/wrong-book\//.test(seen.url())) wrongBookWrites += 1
  })
  await page.getByRole('button', { name: '标记已掌握' }).dblclick()
  await expect(page.locator('.summary')).toContainText('已掌握')
  expect(wrongBookWrites).toBe(1)
  await page.locator('.el-radio-button__inner').filter({ hasText: '已掌握' }).click()
  await expect(page.locator('.item')).toHaveCount(1)
  await page.getByPlaceholder('搜索题干或知识点').fill('不存在')
  await page.getByPlaceholder('搜索题干或知识点').press('Enter')
  await expect(page.getByText('没有符合条件的真实错题')).toBeVisible()
  await page.getByPlaceholder('搜索题干或知识点').fill('')
  await page.getByPlaceholder('搜索题干或知识点').press('Enter')
  await page.locator('.el-radio-button__inner').filter({ hasText: '全部' }).click()
  await page.getByRole('button', { name: '移除' }).dblclick()
  await expect(page.getByText('没有符合条件的真实错题')).toBeVisible()

  await page.goto(`/mastery?courseId=${course.id}`)
  await expect(page.getByText('已有记录')).toBeVisible()
  await expect(page.getByText(/\d+ 次尝试/).first()).toBeVisible()
  await page.getByRole('button', { name: '刷新' }).click()
  await page.locator('.page-heading .el-select').click()
  await page.getByRole('option', { name: other.name }).click()
  await expect(page.getByText('当前课程尚无真实掌握记录')).toBeVisible()
  await expect(page.getByText('尚无学习记录').first()).toBeVisible()
})

test('recommendation feedback locks are per card, history refreshes, and primary action is single-shot', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/503.*recommendations\/feedback|recommendations\/feedback.*503|Failed to load resource.*503/)
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Recommendation Flow ${Date.now()}`)
  await createActivePlan(request, token, course.id)
  await uploadDocument(request, token, course.id, 'recommendation-source.txt')
  await createLearningRecord(request, token, course.id)
  await authenticatePage(page, token)
  await page.goto(`/recommendations?courseId=${course.id}`)
  const cards = page.locator('.recommend-card')
  await expect.poll(() => cards.count()).toBeGreaterThanOrEqual(2)

  const writes: { key: string; action: string }[] = []
  await page.route(`**/api/v1/courses/${course.id}/recommendations/feedback`, async (route) => {
    const body = route.request().postDataJSON()
    writes.push(body)
    if (body.action === 'clicked') {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"FEEDBACK_TEMPORARY"}' })
      return
    }
    await new Promise((resolve) => setTimeout(resolve, body.action === 'saved' ? 250 : 400))
    await route.continue()
  })
  const first = cards.nth(0)
  const second = cards.nth(1)
  await first.getByRole('button', { name: '有帮助' }).dblclick()
  await second.getByRole('button', { name: '不感兴趣' }).dblclick()
  await expect(first.getByRole('button', { name: '已标记有帮助' })).toBeVisible()
  await expect(second.getByRole('button', { name: '已标记不感兴趣' })).toBeVisible()
  expect(writes.filter((item) => item.action === 'saved')).toHaveLength(1)
  expect(writes.filter((item) => item.action === 'skipped')).toHaveLength(1)

  await page.getByRole('button', { name: '推荐历史' }).click()
  await expect(page.getByRole('dialog', { name: '推荐历史' })).toBeVisible()
  await expect(page.getByText('有帮助 1')).toBeVisible()
  await expect(page.getByText('不感兴趣 1')).toBeVisible()
  await page.getByRole('button', { name: '刷新历史' }).click()
  await page.getByRole('dialog', { name: '推荐历史' }).locator('.el-dialog__headerbtn').click()

  const actionButton = first.locator('.card-actions .el-button--primary')
  const destination = await actionButton.textContent()
  await actionButton.dblclick()
  await expect(page).not.toHaveURL(/\/recommendations/)
  expect(writes.filter((item) => item.action === 'clicked')).toHaveLength(1)
  expect(destination).toBeTruthy()
})
