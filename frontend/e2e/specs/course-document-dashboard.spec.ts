import { expect, test } from '../fixtures'
import {
  authenticatePage,
  createCourse,
  registerAndLogin,
  uploadDocument,
} from '../helpers/api'

test('dashboard empty state, retry, and every visible shortcut preserve real course context', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/503.*dashboard\/overview|dashboard\/overview.*503|Failed to load resource.*503/)
  const { token } = await registerAndLogin(request)
  await authenticatePage(page, token)
  let dashboardFailures = 1
  await page.route('**/api/v1/dashboard/overview?**', async (route) => {
    if (dashboardFailures-- > 0) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"DASHBOARD_TEMPORARY"}' })
    } else await route.continue()
  })
  await page.goto('/dashboard')
  await expect(page.getByText('DASHBOARD_TEMPORARY')).toBeVisible()
  await page.getByRole('button', { name: '重新加载' }).click()
  await page.getByRole('button', { name: '创建课程' }).click()
  await expect(page).toHaveURL(/\/courses$/)

  const course = await createCourse(request, token, `Dashboard Links ${Date.now()}`)
  const checks = [
    ['课程问答', '/chat'],
    ['今日学习', '/today'],
    ['上传资料', '/upload'],
    ['课程问答', '/chat'],
    ['学习计划', '/plan'],
    ['今日任务', '/today'],
    ['能力图谱 →', '/mastery'],
    ['任务中心 →', '/tasks'],
  ] as const
  for (const [label, path] of checks) {
    await page.goto('/dashboard')
    const control = page.getByRole('button', { name: label }).last()
    await expect(control).toBeVisible()
    await control.click()
    await expect(page).toHaveURL(new RegExp(`${path.replace('/', '\\/')}.*${path === '/tasks' ? '' : `courseId=${course.id}`}`))
  }
})

test('course edit cancel save normalization and archive confirmation are persistent', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Editable ${Date.now()}`)
  await authenticatePage(page, token)
  await page.goto(`/courses/${course.id}`)
  await page.getByRole('button', { name: '编辑课程' }).click()
  const name = page.getByLabel('课程名称（必填）')
  await name.fill('Cancelled name')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByRole('heading', { name: course.name }).first()).toBeVisible()

  await page.getByRole('button', { name: '编辑课程' }).click()
  const savedName = `Saved ${Date.now()}`
  await name.fill(`  ${savedName}  `)
  await page.getByLabel('课程说明').fill('  persisted description  ')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByText('课程信息已保存')).toBeVisible()
  await expect(page.getByRole('heading', { name: savedName }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: savedName }).first()).toBeVisible()

  await page.getByRole('button', { name: '归档课程' }).click()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByRole('heading', { name: savedName }).first()).toBeVisible()
  await page.getByRole('button', { name: '归档课程' }).click()
  await page.getByRole('button', { name: '确认归档' }).click()
  await expect(page).toHaveURL(/\/courses$/)
  await expect(page.getByText(savedName, { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '打开全局快捷搜索' }).click()
  await expect(page.getByText(savedName, { exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await page.goto(`/courses/${course.id}`)
  await expect(page.getByText('课程不存在或无权访问', { exact: true })).toBeVisible()
})

test('upload validation, server size failure, duplicate lock and legal recovery are visible', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/413.*documents|documents.*413|Failed to load resource.*413/)
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Upload Validation ${Date.now()}`)
  await authenticatePage(page, token)
  await page.goto(`/upload?courseId=${course.id}`)
  const input = page.locator('input[type="file"]')
  const upload = page.getByRole('button', { name: '上传并开始解析' })
  await expect(upload).toBeDisabled()

  await input.setInputFiles({ name: 'empty.txt', mimeType: 'text/plain', buffer: Buffer.alloc(0) })
  await expect(page.getByText('不能上传空文件')).toBeVisible()
  await expect(upload).toBeDisabled()
  await input.setInputFiles({ name: 'bad.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('bad') })
  await expect(page.getByText('仅支持 PDF、TXT、MD 或 Markdown 文件')).toBeVisible()
  await expect(upload).toBeDisabled()

  await input.setInputFiles({
    name: 'too-large.txt',
    mimeType: 'text/plain',
    buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 65),
  })
  await upload.click()
  await expect(page.locator('.el-message--error').last()).toContainText(/FILE_TOO_LARGE|超过后端限制|413|文档上传失败/)
  await expect(upload).toBeEnabled()

  await input.setInputFiles({
    name: 'legal-round17.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('合法资料：数据库事务、索引和查询优化。'),
  })
  let uploads = 0
  page.on('request', (seen) => {
    if (seen.method() === 'POST' && /\/courses\/\d+\/documents$/.test(new URL(seen.url()).pathname)) uploads += 1
  })
  await upload.dblclick()
  await expect(page).toHaveURL(/\/documents\/tasks\?.*documentId=.*taskId=/)
  expect(uploads).toBe(1)
  await expect(page.getByText('legal-round17', { exact: false }).first()).toBeVisible()
})

test('document task refresh reparse and URL ownership errors recover without stale detail', async ({ page, request, consoleAudit }) => {
  consoleAudit.allow(/404.*documents|documents.*404|Failed to load resource.*404/)
  const { token } = await registerAndLogin(request)
  const courseA = await createCourse(request, token, `Document A ${Date.now()}`)
  const courseB = await createCourse(request, token, `Document B ${Date.now()}`)
  const uploadA = await uploadDocument(request, token, courseA.id, 'document-a.txt')
  const uploadB = await uploadDocument(request, token, courseB.id, 'document-b.txt')
  await authenticatePage(page, token)

  await page.goto(`/documents/tasks?courseId=${courseA.id}&documentId=${uploadA.document.id}&taskId=${uploadB.async_task_id}`)
  await expect(page.getByText('任务不存在或不属于当前文档')).toBeVisible()
  await expect(page.getByText(uploadB.async_task_id, { exact: true })).toHaveCount(0)
  let taskReads = 0
  const ownedTaskPattern = `**/api/v1/documents/${uploadA.document.id}/tasks/${uploadA.async_task_id}`
  await page.route(ownedTaskPattern, async (route) => {
    taskReads += 1
    if (taskReads === 1) {
      const response = await route.fetch()
      const body = await response.json()
      body.data.status = 'processing'
      body.data.progress = 50
      body.data.current_step = 'embedding'
      await route.fulfill({ response, body: JSON.stringify(body) })
    } else await route.continue()
  })
  await page.goto(`/documents/tasks?courseId=${courseA.id}&documentId=${uploadA.document.id}`)
  await expect(page).toHaveURL(new RegExp(`taskId=${uploadA.async_task_id}`))
  await expect(page.getByText(uploadA.async_task_id, { exact: true })).toBeVisible()
  await expect.poll(() => taskReads, { timeout: 5_000 }).toBeGreaterThanOrEqual(2)
  await page.unroute(ownedTaskPattern)
  await page.getByRole('button', { name: '刷新状态' }).click()
  await page.getByRole('button', { name: '刷新列表' }).click()
  await page.locator('.selector-card .el-select').click()
  await page.getByRole('option', { name: new RegExp(courseB.name) }).click()
  await expect(page).toHaveURL(new RegExp(`courseId=${courseB.id}`))
  await expect(page.getByText('document-b', { exact: false }).first()).toBeVisible()
  await page.getByRole('button', { name: '查看状态' }).click()
  await expect(page).toHaveURL(new RegExp(`documentId=${uploadB.document.id}`))

  await page.goto(`/courses/${courseA.id}`)
  await page.getByRole('tab', { name: /课程资料/ }).click()
  const row = page.getByRole('row', { name: /document-a/ })
  let reparses = 0
  page.on('request', (seen) => {
    if (seen.method() === 'POST' && seen.url().endsWith(`/documents/${uploadA.document.id}/reparse`)) reparses += 1
  })
  await row.getByRole('button', { name: '重新解析' }).click()
  await page.getByRole('button', { name: '重新解析', exact: true }).last().dblclick()
  await expect(page).toHaveURL(/\/documents\/tasks\?.*taskId=/)
  expect(reparses).toBe(1)
  await expect(page.getByText('处理完成', { exact: true }).first()).toBeVisible()

  await page.goto('/documents/tasks?courseId=bad')
  await expect(page.getByText('URL 中的课程地址无效')).toBeVisible()
  await page.goto(`/documents/tasks?courseId=${courseA.id}&documentId=bad`)
  await expect(page.getByText('URL 中的文档地址无效')).toBeVisible()
  await page.goto(`/documents/tasks?courseId=${courseA.id}&documentId=${uploadA.document.id}&taskId=bad`)
  await expect(page.getByText('任务不存在或不属于当前文档')).toBeVisible()
  await page.goto(`/documents/tasks?courseId=${courseA.id}&documentId=${uploadB.document.id}`)
  await expect(page.getByText('URL 中的课程与文档不匹配')).toBeVisible()
  await page.goto(`/documents/tasks?courseId=${courseB.id}&documentId=${uploadB.document.id}`)
  await expect(page.getByText('document-b', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('document-a', { exact: false })).toHaveCount(0)
})
