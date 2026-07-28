import { readFile } from 'node:fs/promises'
import { expect, test } from '../fixtures'
import {
  apiData,
  authenticatePage,
  createActivePlan,
  createCalendarEvent,
  createCourse,
  createLearningRecord,
  localDate,
  registerAndLogin,
} from '../helpers/api'
import { seedScenario } from '../helpers/seed'
import { activateVisible, activateVisibleTwice } from '../helpers/ui'

test('statistics filters retain data and real CSV download has BOM, headers and expected rows', async ({ page, request, consoleAudit }, testInfo) => {
  consoleAudit.allow(/503.*statistics\/export|statistics\/export.*503|Failed to load resource.*503/)
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Statistics CSV ${Date.now()}`)
  await createLearningRecord(request, token, course.id, 1800)
  await authenticatePage(page, token)
  await page.goto('/statistics?days=7')
  await expect(page.getByText('总学习时长')).toBeVisible()
  await expect(page.locator('.heatmap span')).toHaveCount(49)
  await expect(page.locator('.trend')).toContainText('学习时长趋势')

  await page.locator('.page-heading .el-select').first().click()
  await page.getByRole('option', { name: '最近 30 天' }).click()
  await expect(page).toHaveURL(/days=30/)
  await page.locator('.page-heading .el-select').nth(1).click()
  await page.getByRole('option', { name: course.name }).click()
  await expect(page).toHaveURL(new RegExp(`courseId=${course.id}`))
  await page.reload()
  await expect(page.locator('.page-heading .el-select').first()).toContainText('最近 30 天')

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出统计' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/\.csv$/)
  const csvPath = testInfo.outputPath('downloads', download.suggestedFilename())
  await download.saveAs(csvPath)
  const csv = await readFile(csvPath)
  expect([...csv.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf])
  const text = csv.toString('utf8').replace(/^\ufeff/, '')
  expect(text).toContain('日期')
  expect(text).toContain('实际学习')
  expect(text.trim().split(/\r?\n/).length).toBe(31)

  let failOnce = true
  await page.route('**/api/v1/statistics/export.csv**', async (route) => {
    if (failOnce) {
      failOnce = false
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"CSV_TEMPORARY"}' })
    } else await route.continue()
  })
  await page.getByRole('button', { name: '导出统计' }).click()
  await expect(page.locator('.el-alert').filter({ hasText: /统计导出失败|CSV|请求失败/ })).toBeVisible()
  await expect(page.getByText('总学习时长')).toBeVisible()
})

test('async task filters, cancel, retry, report validation and Markdown download use visible controls', async ({ page, request }, testInfo) => {
  const { token, identity } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Async Reports ${Date.now()}`)
  await createLearningRecord(request, token, course.id, 600)
  const states = seedScenario('async-states', identity.email, course.id)
  const legacy = seedScenario('legacy-report', identity.email, course.id)
  await authenticatePage(page, token)
  await page.goto(`/tasks?taskId=${states.queued}`)
  await expect(page.getByText(states.queued, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '取消任务' }).click()
  await page.getByRole('button', { name: '确定' }).click()
  await expect(page.locator('.detail .status-pill')).toHaveText(/已取消/)

  await page.goto(`/tasks?taskId=${states.failed}`)
  await expect(page.getByText('E2E_RETRYABLE_FAILURE')).toBeVisible()
  await page.getByRole('button', { name: '立即重试' }).click()
  await page.getByRole('button', { name: '确定' }).click()
  await expect(page.locator('.detail .status-pill')).toHaveText(/已完成/)

  await page.getByRole('button', { name: '生成学习周报' }).click()
  const dialog = page.getByRole('dialog', { name: '生成学习周报' })
  const inputs = dialog.locator('input')
  await inputs.nth(0).fill('')
  await dialog.locator('.el-dialog__header').click()
  await page.getByRole('button', { name: '创建任务' }).click()
  await expect(dialog.getByText('请选择开始和结束日期')).toBeVisible()
  await inputs.nth(0).fill(localDate())
  await inputs.nth(1).fill(localDate(-1))
  await dialog.locator('.el-dialog__header').click()
  await page.getByRole('button', { name: '创建任务' }).click()
  await expect(dialog.getByText(/结束日期不得早于开始日期/)).toBeVisible()
  await inputs.nth(0).fill(localDate(-32))
  await inputs.nth(1).fill(localDate())
  await dialog.locator('.el-dialog__header').click()
  await page.getByRole('button', { name: '创建任务' }).click()
  await expect(dialog.getByText(/周期最长为 31 天/)).toBeVisible()
  await inputs.nth(0).fill(localDate())
  await inputs.nth(1).fill(localDate())
  await dialog.locator('.el-dialog__header').click()
  await dialog.locator('.el-select').click()
  await page.getByRole('option', { name: new RegExp(course.name) }).click()
  let reportCreates = 0
  page.on('request', (seen) => {
    if (seen.method() === 'POST' && seen.url().endsWith('/api/v1/async-tasks')) reportCreates += 1
  })
  await page.getByRole('button', { name: '创建任务' }).dblclick()
  await expect(dialog).toBeHidden()
  expect(reportCreates).toBe(1)
  await expect(page.getByText('学习周报', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('每日学习')).toBeVisible()
  await expect(page.getByText('课程分布')).toBeVisible()
  await expect(page.getByText('当前周期没有生效计划任务', { exact: true })).toBeVisible()

  const markdownPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 Markdown' }).click()
  const markdown = await markdownPromise
  expect(markdown.suggestedFilename()).toMatch(/\.md$/)
  const markdownPath = testInfo.outputPath('downloads', markdown.suggestedFilename())
  await markdown.saveAs(markdownPath)
  const report = await readFile(markdownPath, 'utf8')
  expect(report).toContain('# StudyPilot 学习周报')
  expect(report).toContain('周期')
  expect(report).toContain('时区')
  expect(report).toContain('| 日期 |')

  await page.route('**/api/v1/async-tasks/*/report.md', (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: '{"detail":"REPORT_DOWNLOAD_TEMPORARY"}',
  }))
  await page.getByRole('button', { name: '下载 Markdown' }).click()
  await expect(page.locator('.report .el-alert')).toBeVisible()
  await expect(page.getByText('每日学习')).toBeVisible()
  await page.unroute('**/api/v1/async-tasks/*/report.md')

  await page.goto(`/tasks?taskId=${legacy.task_id}`)
  await expect(page.getByText('旧结构周报兼容内容')).toBeVisible()
  await expect(page.locator('.report .el-alert')).toHaveCount(0)
  const legacyDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 Markdown' }).click()
  expect((await legacyDownload).suggestedFilename()).toMatch(/\.md$/)

  await page.locator('.list header .el-select').first().click()
  await page.getByRole('option', { name: '成功' }).click()
  await page.locator('.list header .el-select').nth(1).click()
  await page.getByRole('option', { name: '学习周报' }).click()
  await expect(page.locator('.entry').first()).toBeVisible()
  await page.getByRole('button', { name: '刷新' }).click()
})

test('calendar navigation, plan sync, update, delete and real ICS download are persistent', async ({ page, request }, testInfo) => {
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Calendar Flow ${Date.now()}`)
  await createActivePlan(request, token, course.id)
  const candidate = await apiData(request, token, 'post', `/courses/${course.id}/study-plans/generate`, {
    data: {
      start_date: localDate(),
      end_date: localDate(),
      daily_availability: { default_minutes: 120 },
      session_minutes: 30,
      goal: 'calendar conflict fixture',
    },
  })
  const fixtureTaskId = candidate.candidate_version.tasks[0].id
  const startAt = `${localDate()}T12:00:00.000Z`
  const endAt = `${localDate()}T12:30:00.000Z`
  await createCalendarEvent(request, token, {
    title: 'Round17 conflict event',
    start_at: startAt,
    end_at: endAt,
    idempotency_key: `round17-conflict-${Date.now()}`,
    study_task_id: fixtureTaskId,
  })
  await authenticatePage(page, token)
  await page.goto(`/calendar?courseId=${course.id}`)
  await expect(page).toHaveURL(/weekStart=/)
  const originalUrl = page.url()
  await page.getByRole('button', { name: '下一周' }).click()
  const nextUrl = page.url()
  expect(nextUrl).not.toBe(originalUrl)
  await page.goBack()
  await expect(page).toHaveURL(originalUrl)
  await page.goForward()
  await expect(page).toHaveURL(nextUrl)
  await page.getByRole('button', { name: '今天' }).click()
  await expect(page.locator('.days > div')).toHaveCount(7)

  await page.getByRole('button', { name: '同步学习计划' }).click()
  const sync = page.getByRole('dialog', { name: '同步学习计划到本地日历' })
  const startTime = sync.locator('.el-form-item').filter({ hasText: '每日开始时间' }).locator('.el-select__wrapper')
  await activateVisible(page, startTime)
  const lateOption = page.getByRole('option', { name: '23:30' })
  await lateOption.click()
  await expect(lateOption).toBeHidden()
  await expect(startTime).toContainText('23:30')
  const latePreviewResponse = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/api/v1/calendar/plan-sync/preview'))
  await activateVisible(page, sync.getByRole('button', { name: '生成真实预览' }))
  await latePreviewResponse
  await expect(sync.getByText(/跨日 [1-9]/)).toBeVisible()
  await activateVisible(page, startTime)
  const regularOption = page.getByRole('option', { name: '20:00' })
  await regularOption.click()
  await expect(regularOption).toBeHidden()
  await expect(startTime).toContainText('20:00')
  const regularPreviewResponse = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/api/v1/calendar/plan-sync/preview'))
  await activateVisible(page, sync.getByRole('button', { name: '生成真实预览' }))
  await regularPreviewResponse
  await expect(sync.getByText(/可创建 [1-9]/)).toBeVisible()
  let confirms = 0
  page.on('request', (seen) => {
    if (seen.method() === 'POST' && seen.url().endsWith('/calendar/plan-sync/confirm')) confirms += 1
  })
  await activateVisibleTwice(page, sync.getByRole('button', { name: '确认创建' }))
  await expect(sync).toBeHidden()
  expect(confirms).toBe(1)
  await expect(page.locator('.event').first()).toBeVisible()

  await page.getByRole('button', { name: '同步学习计划' }).click()
  await activateVisible(page, sync.getByRole('button', { name: '生成真实预览' }))
  await expect(sync.getByText(/已同步 [1-9]/)).toBeVisible()
  await activateVisible(page, sync.getByRole('button', { name: '取消', exact: true }))

  const icsPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 ICS' }).click()
  const icsDownload = await icsPromise
  expect(icsDownload.suggestedFilename()).toMatch(/\.ics$/)
  const icsPath = testInfo.outputPath('downloads', icsDownload.suggestedFilename())
  await icsDownload.saveAs(icsPath)
  const ics = await readFile(icsPath, 'utf8')
  expect(ics).toContain('BEGIN:VCALENDAR')
  expect(ics).toContain('END:VCALENDAR')
  expect(ics).toContain('DTSTART')
  expect(ics).toContain('DTEND')

  const event = page.locator('.event').filter({ hasText: course.name }).first()
  await event.click()
  const detail = page.getByRole('dialog', { name: '本地日历事件' })
  const title = detail.getByLabel('标题')
  const previousTitle = await title.inputValue()
  await title.fill(`已修改 ${previousTitle}`)
  await activateVisible(page, detail.getByRole('button', { name: '预览修改' }))
  await expect(detail.getByText('修改预览已生成，请确认写入。')).toBeVisible()
  await activateVisible(page, detail.getByRole('button', { name: '确认修改' }))
  await expect(detail).toBeHidden()
  await expect(page.getByText(`已修改 ${previousTitle}`, { exact: true })).toBeVisible()

  await page.getByText(`已修改 ${previousTitle}`, { exact: true }).click()
  await activateVisible(page, detail.getByRole('button', { name: '预览删除' }))
  await expect(detail.getByText(/将删除事件/)).toBeVisible()
  await activateVisible(page, detail.getByRole('button', { name: '关闭', exact: true }))
  await expect(page.getByText(`已修改 ${previousTitle}`, { exact: true })).toBeVisible()
  await page.getByText(`已修改 ${previousTitle}`, { exact: true }).click()
  await activateVisible(page, detail.getByRole('button', { name: '预览删除' }))
  await activateVisible(page, detail.getByRole('button', { name: '确认删除' }))
  await expect(detail).toBeHidden()
  await expect(page.getByText(`已修改 ${previousTitle}`, { exact: true })).toHaveCount(0)
  const tasksAfterDelete = await apiData(request, token, 'get', `/study-tasks/today?target_date=${localDate()}&course_id=${course.id}`)
  expect(tasksAfterDelete.items.length).toBeGreaterThan(0)
  const afterDeleteDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 ICS' }).click()
  const afterDelete = await afterDeleteDownload
  const afterDeletePath = testInfo.outputPath('downloads', `after-delete-${afterDelete.suggestedFilename()}`)
  await afterDelete.saveAs(afterDeletePath)
  expect(await readFile(afterDeletePath, 'utf8')).not.toContain(`已修改 ${previousTitle}`)
  await expect(page.getByText(/已注册 \d+ 个日历工具/)).toBeVisible()
  await expect(page.getByText(/暂无 MCP 日历调用记录|success/)).toBeVisible()
})
