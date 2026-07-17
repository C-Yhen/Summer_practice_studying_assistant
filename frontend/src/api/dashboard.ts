import { ApiEnvelopeError, apiClient, mockEnabled, unwrapApiResponse } from './client'
import { courseApi } from './services'
import type { CourseListItem, DashboardOverview } from '@/types'

export interface DashboardOverviewParams {
  target_date: string
  days?: number
  course_id?: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isInteger(value: unknown): value is number {
  return Number.isInteger(value)
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isRate(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

function parseDashboardOverview(value: unknown): DashboardOverview {
  if (
    !isRecord(value)
    || typeof value.target_date !== 'string'
    || typeof value.range_start !== 'string'
    || typeof value.range_end !== 'string'
    || typeof value.timezone !== 'string'
    || !isInteger(value.course_count)
    || !isInteger(value.ready_document_count)
    || !isRecord(value.today)
    || !isRecord(value.metrics)
    || !Array.isArray(value.trend)
    || !Array.isArray(value.weak_points)
    || !isRecord(value.next_action)
    || !Array.isArray(value.recent_async_tasks)
  ) {
    throw new ApiEnvelopeError('后端返回了无法识别的首页概览结构')
  }

  const focus = value.focus_course
  if (focus !== null && (
    !isRecord(focus)
    || !isInteger(focus.id)
    || typeof focus.name !== 'string'
    || !isNullableString(focus.code)
    || !isNullableString(focus.exam_date)
    || (focus.days_until_exam !== null && !isInteger(focus.days_until_exam))
    || typeof focus.has_active_plan !== 'boolean'
  )) throw new ApiEnvelopeError('后端返回的首页焦点课程不完整')

  const today = value.today
  if (
    !Array.isArray(today.items)
    || !today.items.every((item) => isRecord(item)
      && isInteger(item.id)
      && isInteger(item.course_id)
      && typeof item.title === 'string'
      && typeof item.task_type === 'string'
      && isInteger(item.estimated_minutes)
      && (item.actual_minutes === null || isInteger(item.actual_minutes))
      && typeof item.priority === 'number'
      && typeof item.difficulty === 'string'
      && typeof item.status === 'string'
      && typeof item.scheduled_date === 'string')
    || !isInteger(today.total_count)
    || !isInteger(today.completed_count)
    || !isInteger(today.pending_count)
    || !isInteger(today.planned_minutes)
    || !isInteger(today.actual_minutes)
    || !isRate(today.completion_rate)
  ) throw new ApiEnvelopeError('后端返回的今日任务概览不完整')

  const metrics = value.metrics
  if (
    !isInteger(metrics.today_focus_minutes)
    || !isRate(metrics.today_completion_rate)
    || (metrics.average_mastery !== null && !isRate(metrics.average_mastery))
    || !isInteger(metrics.active_course_count)
    || !isInteger(metrics.ready_document_count)
    || !isInteger(metrics.study_days_in_range)
  ) throw new ApiEnvelopeError('后端返回的首页指标不完整')

  if (!value.trend.every((point) => isRecord(point)
    && typeof point.date === 'string'
    && typeof point.label === 'string'
    && isInteger(point.learning_minutes)
    && isInteger(point.scheduled_tasks)
    && isInteger(point.completed_tasks)
    && isRate(point.completion_rate))) {
    throw new ApiEnvelopeError('后端返回的学习趋势不完整')
  }

  if (!value.weak_points.every((point) => isRecord(point)
    && isInteger(point.knowledge_point_id)
    && typeof point.knowledge_point === 'string'
    && isInteger(point.course_id)
    && typeof point.course_name === 'string'
    && isRate(point.score)
    && isInteger(point.attempts)
    && isRate(point.confidence))) {
    throw new ApiEnvelopeError('后端返回的薄弱知识点不完整')
  }

  const action = value.next_action
  if (
    typeof action.type !== 'string'
    || typeof action.title !== 'string'
    || typeof action.reason !== 'string'
    || typeof action.route !== 'string'
  ) throw new ApiEnvelopeError('后端返回的下一步建议不完整')

  if (!value.recent_async_tasks.every((task) => isRecord(task)
    && typeof task.task_id === 'string'
    && typeof task.task_type === 'string'
    && typeof task.status === 'string'
    && isInteger(task.progress)
    && isNullableString(task.current_step)
    && typeof task.created_at === 'string'
    && isNullableString(task.finished_at))) {
    throw new ApiEnvelopeError('后端返回的异步任务信息不完整')
  }

  return value as unknown as DashboardOverview
}

function shiftDate(source: string, offset: number): string {
  const [year, month, day] = source.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  date.setDate(date.getDate() + offset)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function mockOverview(
  params: DashboardOverviewParams,
  selectedCourse?: CourseListItem,
): DashboardOverview {
  const days = params.days ?? 7
  const rangeStart = shiftDate(params.target_date, -(days - 1))
  return {
    target_date: params.target_date,
    range_start: rangeStart,
    range_end: params.target_date,
    timezone: 'Asia/Shanghai',
    course_count: 1,
    ready_document_count: 1,
    focus_course: {
      id: selectedCourse?.id ?? 1,
      name: selectedCourse?.name ?? '演示课程',
      code: selectedCourse?.code ?? 'DEMO-101',
      exam_date: selectedCourse?.examDate ?? shiftDate(params.target_date, 7),
      days_until_exam: selectedCourse?.examDate
        ? Math.ceil(
          (new Date(`${selectedCourse.examDate}T00:00:00`).getTime()
            - new Date(`${params.target_date}T00:00:00`).getTime()) / 86400000,
        )
        : 7,
      has_active_plan: true,
    },
    today: {
      items: [{ id: 1, course_id: selectedCourse?.id ?? 1, title: '完成演示复习任务', task_type: 'review', estimated_minutes: 30, actual_minutes: null, priority: 0.9, difficulty: 'basic', status: 'todo', scheduled_date: params.target_date }],
      total_count: 1,
      completed_count: 0,
      pending_count: 1,
      planned_minutes: 30,
      actual_minutes: 0,
      completion_rate: 0,
    },
    metrics: { today_focus_minutes: 0, today_completion_rate: 0, average_mastery: 0.42, active_course_count: 1, ready_document_count: 1, study_days_in_range: 0 },
    trend: Array.from({ length: days }, (_, index) => ({ date: shiftDate(rangeStart, index), label: `第${index + 1}天`, learning_minutes: 0, scheduled_tasks: index === days - 1 ? 1 : 0, completed_tasks: 0, completion_rate: 0 })),
    weak_points: [{ knowledge_point_id: 1, knowledge_point: '演示知识点', course_id: selectedCourse?.id ?? 1, course_name: selectedCourse?.name ?? '演示课程', score: 0.42, attempts: 1, confidence: 0.5 }],
    next_action: { type: 'today_task', title: '继续完成：完成演示复习任务', reason: '这是今天优先级最高的未完成任务', route: `/today?courseId=${selectedCourse?.id ?? 1}` },
    recent_async_tasks: [],
  }
}

export const dashboardApi = {
  async getOverview(params: DashboardOverviewParams): Promise<DashboardOverview> {
    if (mockEnabled) {
      await new Promise((resolve) => window.setTimeout(resolve, 220))
      const selectedCourse = params.course_id === undefined
        ? undefined
        : await courseApi.get(params.course_id)
      return mockOverview(params, selectedCourse)
    }
    return parseDashboardOverview(
      unwrapApiResponse<unknown>(await apiClient.get('/dashboard/overview', { params })),
    )
  },
}
