import { expect, test } from '@playwright/test'
import { authenticatePage, createCourse, registerAndLogin } from '../helpers/api'

test('upload, offline course chat and plan confirmation form a real learning flow', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token, `Learning Flow ${Date.now()}`)
  await authenticatePage(page, token)

  await page.goto(`/upload?courseId=${course.id}`)
  await page.locator('input[type="file"]').setInputFiles({
    name: 'round17-notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('数据库事务具有原子性、一致性、隔离性和持久性。事务隔离用于控制并发可见性。'),
  })
  await page.getByRole('button', { name: '上传并开始解析' }).click()
  await expect(page).toHaveURL(/\/documents\/tasks\?.*documentId=.*taskId=/)
  await expect(page.getByText('round17-notes', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('已完成', { exact: true }).first()).toBeVisible()

  await page.goto(`/chat?courseId=${course.id}`)
  const composer = page.getByPlaceholder('向课程资料提问，Shift + Enter 换行…')
  await expect(composer).toBeVisible()
  await composer.fill('事务隔离解决什么问题？')
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.locator('.message.user')).toHaveCount(1)
  await expect(page.locator('.message.assistant')).toHaveCount(1)

  await page.goto(`/plan?courseId=${course.id}`)
  await page.getByRole('button', { name: '生成候选计划' }).click()
  await expect(page.getByRole('button', { name: '确认此计划' })).toBeVisible()
  await page.getByRole('button', { name: '确认此计划' }).click()
  await page.getByRole('button', { name: '确认并生效' }).click()
  await expect(page.getByText('当前生效版本', { exact: true })).toBeVisible()
})

test('profile, learning preferences and unavailable settings are honest', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  await authenticatePage(page, token)
  await page.goto('/settings')

  const nickname = page.getByLabel('昵称')
  await expect(nickname).toBeVisible()
  const updatedName = `Updated ${Date.now()}`
  await nickname.fill(`  ${updatedName}  `)
  await page.getByRole('button', { name: '保存个人资料' }).click()
  await expect(nickname).toHaveValue(updatedName)
  if ((page.viewportSize()?.width || 0) >= 900) {
    await expect(page.locator('.user-chip')).toContainText(updatedName)
  }

  await page.getByText('学习偏好', { exact: true }).first().click()
  await page.getByText('Markdown', { exact: true }).click()
  await page.getByRole('button', { name: '保存学习偏好' }).click()
  await expect(page.getByText('学习偏好已保存')).toBeVisible()

  await page.getByText('模型与服务', { exact: true }).first().click()
  await expect(page.getByRole('button', { name: '配置（后续开放）' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '工具权限（后续开放）' })).toBeDisabled()
  await page.getByText('账户与安全', { exact: true }).first().click()
  await expect(page.getByRole('button', { name: '修改密码（暂未开放）' })).toBeDisabled()
})
