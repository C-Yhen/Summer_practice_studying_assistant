import { expect, test } from '@playwright/test'
import { authenticatePage, createCourse, registerAndLogin } from '../helpers/api'

const routes = [
  ['/dashboard', '学习首页'],
  ['/courses', '课程管理'],
  ['/upload', '资料上传'],
  ['/documents/tasks', '文档处理进度'],
  ['/chat', '智能问答'],
  ['/plan', '学习计划'],
  ['/today', '今日任务'],
  ['/recommendations', '推荐中心'],
  ['/practice', '练习答题'],
  ['/wrong-book', '错题本'],
  ['/mastery', '知识点掌握度'],
  ['/statistics', '学习统计'],
  ['/tasks', '长时任务中心'],
  ['/calendar', '学习日历'],
  ['/settings', '个人设置'],
] as const

test('all production pages render their honest page title', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  await authenticatePage(page, token)
  for (const [path, title] of routes) {
    await page.goto(path)
    await expect(page).toHaveTitle(new RegExp(title))
    await expect(page.locator('.page-content')).toBeVisible()
  }
})

test('recommendation errors recover through visible retry and filter controls', async ({ page, request }) => {
  const { token } = await registerAndLogin(request)
  const course = await createCourse(request, token)
  await authenticatePage(page, token)
  let failures = 1
  await page.route('**/api/v1/courses/*/recommendations?**', async (route) => {
    if (failures > 0) {
      failures -= 1
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"temporary"}' })
    } else {
      await route.continue()
    }
  })
  await page.goto(`/recommendations?courseId=${course.id}`)
  await expect(page.getByText('temporary')).toBeVisible()
  await page.getByRole('button', { name: '重新加载推荐' }).click()
  await expect(page.getByText('temporary')).toBeHidden()
  await expect(page.getByText(course.name, { exact: true }).first()).toBeVisible()

  await page.locator('.el-radio-button__inner', { hasText: '学习计划' }).click()
  await expect(page).toHaveURL(/category=plan/)
  await expect(page.getByRole('button', { name: /刷新推荐/ })).toBeEnabled()
})
