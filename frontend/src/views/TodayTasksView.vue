<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Clock, Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi, studyTaskApi } from '@/api/services'
import type { CourseListItem, TodayTask } from '@/types'

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const selectedCourseId = ref<number | ''>('')
const targetDate = ref(localDate())
const coursesLoading = ref(false)
const coursesError = ref('')
const tasks = ref<TodayTask[]>([])
const tasksLoading = ref(false)
const tasksError = ref('')
const completeVisible = ref(false)
const activeTask = ref<TodayTask | null>(null)
const actualMinutes = ref(1)
const completingTaskId = ref<number | null>(null)

function localDate() {
  const date = new Date()
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const completedTasks = computed(() => tasks.value.filter((task) => task.status === 'completed'))
const completionRate = computed(() => tasks.value.length ? Math.round(completedTasks.value.length / tasks.value.length * 100) : 0)
const actualMinutesDone = computed(() => completedTasks.value.reduce((sum, task) => sum + (task.actual_minutes || 0), 0))
const remainingMinutes = computed(() => tasks.value.filter((task) => task.status !== 'completed').reduce((sum, task) => sum + task.estimated_minutes, 0))
const displayDate = computed(() => {
  const date = new Date(`${targetDate.value}T00:00:00`)
  return Number.isNaN(date.getTime()) ? targetDate.value : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(date)
})

function pageError(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

function queryCourseId(): number | null {
  const raw = Array.isArray(route.query.courseId) ? route.query.courseId[0] : route.query.courseId
  if (raw === undefined) return null
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : -1
}

function queryDate(): string {
  const raw = Array.isArray(route.query.date) ? route.query.date[0] : route.query.date
  return typeof raw === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : localDate()
}

function queryTaskId(): number | null {
  const raw = Array.isArray(route.query.taskId) ? route.query.taskId[0] : route.query.taskId
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function courseName(courseId: number) {
  const course = courses.value.find((item) => item.id === courseId)
  return course ? (course.code ? `${course.name} · ${course.code}` : course.name) : `课程 #${courseId}`
}

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = ''
  try {
    const result = await courseApi.list()
    courses.value = result.items.filter((course) => !course.archived)
  } catch (error) {
    courses.value = []
    coursesError.value = pageError(error, '课程列表加载失败')
  } finally {
    coursesLoading.value = false
  }
}

async function loadTasks() {
  tasksLoading.value = true
  tasksError.value = ''
  try {
    const result = await studyTaskApi.listToday({
      target_date: targetDate.value,
      ...(typeof selectedCourseId.value === 'number' ? { course_id: selectedCourseId.value } : {}),
    })
    tasks.value = result.items
  } catch (error) {
    tasks.value = []
    tasksError.value = pageError(error, '今日任务加载失败')
  } finally {
    tasksLoading.value = false
  }
}

async function changeCourse(value: number | '') {
  await router.replace({
    name: 'today',
    query: {
      date: targetDate.value,
      ...(typeof value === 'number' ? { courseId: String(value) } : {}),
    },
  })
}

async function changeDate() {
  await router.replace({
    name: 'today',
    query: {
      date: targetDate.value,
      ...(typeof selectedCourseId.value === 'number' ? { courseId: String(selectedCourseId.value) } : {}),
    },
  })
}

async function initialize() {
  selectedCourseId.value = ''
  targetDate.value = queryDate()
  tasks.value = []
  tasksError.value = ''
  await loadCourses()
  if (coursesError.value) return
  const requested = queryCourseId()
  if (requested === -1 || (requested && !courses.value.some((course) => course.id === requested))) {
    coursesError.value = 'URL 中的课程不属于当前账号或已归档'
    return
  }
  selectedCourseId.value = requested || ''
  await loadTasks()
  const requestedTaskId = queryTaskId()
  const requestedTask = requestedTaskId ? tasks.value.find((task) => task.id === requestedTaskId) : null
  if (requestedTask) openComplete(requestedTask, false)
}

function openComplete(task: TodayTask, syncUrl = true) {
  if (task.status === 'completed' || completingTaskId.value !== null) return
  activeTask.value = task
  actualMinutes.value = task.estimated_minutes
  completeVisible.value = true
  if (syncUrl) {
    void router.replace({
      name: 'today',
      query: {
        date: targetDate.value,
        courseId: String(task.course_id),
        taskId: String(task.id),
      },
    })
  }
}

function closeComplete() {
  completeVisible.value = false
  activeTask.value = null
  void router.replace({
    name: 'today',
    query: {
      date: targetDate.value,
      ...(typeof selectedCourseId.value === 'number' ? { courseId: String(selectedCourseId.value) } : {}),
    },
  })
}

async function completeTask() {
  const task = activeTask.value
  if (!task || completingTaskId.value !== null) return
  if (!Number.isInteger(actualMinutes.value) || actualMinutes.value < 1) return ElMessage.warning('实际学习时长至少为 1 分钟')
  completingTaskId.value = task.id
  try {
    const result = await studyTaskApi.complete(task.id, { actual_minutes: actualMinutes.value })
    completeVisible.value = false
    activeTask.value = null
    await router.replace({
      name: 'today',
      query: {
        date: targetDate.value,
        ...(typeof selectedCourseId.value === 'number' ? { courseId: String(selectedCourseId.value) } : {}),
      },
    })
    await loadTasks()
    const mastery = result.mastery_score === null ? '该任务没有关联知识点' : `掌握度更新为 ${Math.round(result.mastery_score * 100)}%`
    ElMessage.success(result.idempotent_replay ? `任务已经完成，${mastery}` : `任务已完成，${mastery}`)
  } catch (error) {
    ElMessage.error(pageError(error, '任务完成状态保存失败'))
  } finally {
    completingTaskId.value = null
  }
}

watch(() => [route.query.courseId, route.query.date], () => void initialize(), { immediate: true })
</script>

<template>
  <div class="today-page">
    <PageHeader title="今日任务" eyebrow="ACTIVE PLAN TASKS" :description="`${displayDate} · 仅展示当前生效计划版本中的真实任务`">
      <el-input v-model="targetDate" type="date" style="width:155px" :disabled="tasksLoading" @change="changeDate" />
      <el-select :model-value="selectedCourseId" placeholder="全部课程" :loading="coursesLoading" style="width:220px" @change="changeCourse">
        <el-option label="全部课程" value="" />
        <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" />
      </el-select>
      <el-button plain :loading="tasksLoading" @click="loadTasks"><el-icon><Refresh /></el-icon>刷新</el-button>
    </PageHeader>

    <el-alert v-if="coursesError" :title="coursesError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="initialize">重试</el-button></template></el-alert>
    <el-alert v-if="tasksError" :title="tasksError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="loadTasks">重新加载</el-button></template></el-alert>

    <section class="daily-hero">
      <div class="ring"><strong>{{ completionRate }}<small>%</small></strong><span>任务进度</span></div>
      <div><span>活动计划任务</span><h2>{{ tasks.length ? (completionRate === 100 ? '所选日期任务已全部完成' : `已完成 ${completedTasks.length} / ${tasks.length} 项`) : '所选日期暂无生效任务' }}</h2><p>实际已学习 {{ actualMinutesDone }} 分钟 · 剩余预计 {{ remainingMinutes }} 分钟</p><el-progress :percentage="completionRate" :show-text="false" :stroke-width="7" color="#78d9c6" /></div>
    </section>

    <div v-if="tasksLoading" v-loading="true" class="tasks-loading"></div>
    <el-empty v-else-if="!tasks.length && !tasksError" description="所选日期和课程没有活动计划任务；请确认计划或切换到实际排期日期"><el-button type="primary" @click="router.push({ name: 'plan', query: typeof selectedCourseId === 'number' ? { courseId: String(selectedCourseId) } : {} })">前往学习计划</el-button></el-empty>

    <section v-else class="content-card task-section">
      <div class="card-header"><div><h2>任务清单</h2><p>候选或已失效版本的任务不会出现在这里</p></div><span class="soft-tag brand">{{ completedTasks.length }}/{{ tasks.length }} 已完成</span></div>
      <div class="task-list">
        <article v-for="(task,index) in tasks" :key="task.id" :class="{ completed: task.status === 'completed' }">
          <span class="task-index"><el-icon v-if="task.status === 'completed'"><Check /></el-icon><template v-else>{{ index + 1 }}</template></span>
          <div class="task-copy"><div><span class="soft-tag brand">{{ task.task_type }}</span><em>优先级 {{ Math.round(task.priority * 100) }}</em></div><h3>{{ task.title }}</h3><p>{{ courseName(task.course_id) }} · 难度 {{ task.difficulty }} · {{ task.scheduled_date }}</p><div class="task-meta"><span><el-icon><Clock /></el-icon>预计 {{ task.estimated_minutes }} 分钟</span><span v-if="task.actual_minutes !== null">实际 {{ task.actual_minutes }} 分钟</span><span>状态 {{ task.status }}</span></div></div>
          <el-button v-if="task.status !== 'completed'" type="primary" size="small" :loading="completingTaskId === task.id" :disabled="completingTaskId !== null" @click="openComplete(task)">完成任务</el-button>
          <span v-else class="done-label"><el-icon><Check /></el-icon>已完成</span>
        </article>
      </div>
    </section>

    <el-dialog v-model="completeVisible" title="完成学习任务" width="min(450px, 92vw)">
      <div v-if="activeTask" class="complete-dialog"><b>{{ activeTask.title }}</b><p>预计 {{ activeTask.estimated_minutes }} 分钟。提交后将持久化学习记录，并更新关联知识点掌握度。</p><el-form label-position="top"><el-form-item label="实际学习分钟数"><el-input-number v-model="actualMinutes" :min="1" :max="1440" style="width:100%" /></el-form-item></el-form></div>
      <template #footer><el-button :disabled="completingTaskId !== null" @click="closeComplete">取消</el-button><el-button type="primary" :loading="completingTaskId !== null" :disabled="completingTaskId !== null" @click="completeTask">确认完成</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-alert{margin-bottom:14px}.daily-hero{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:24px;padding:22px 27px;margin-bottom:18px;border-radius:18px;background:linear-gradient(110deg,#19284f,#203a68);color:white}.ring{width:76px;height:76px;display:flex;align-items:center;justify-content:center;flex-direction:column;border:6px solid rgba(255,255,255,.13);border-top-color:#76d7c4;border-right-color:#76d7c4;border-radius:50%}.ring strong{font-size:20px}.ring strong small{font-size:9px}.ring span{color:#aab5cc;font-size:7px}.daily-hero>div:last-child>span{color:#7dd9c6;font-size:8px;font-weight:750}.daily-hero h2{margin:6px 0;font-size:16px}.daily-hero p{margin:0 0 11px;color:#aab5cc;font-size:9px}.tasks-loading{min-height:280px}.task-section{padding:20px}.task-list{display:grid;gap:10px;margin-top:14px}.task-list article{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:13px;padding:14px;border:1px solid #e5e9f1;border-radius:13px;background:#fff}.task-list article.completed{opacity:.7;background:#f6faf8}.task-index{width:29px;height:29px;display:grid;place-items:center;border:1px solid #dce1eb;border-radius:9px;color:#727e96;font-size:9px}.completed .task-index{border-color:#18a58a;background:#18a58a;color:white}.task-copy>div{display:flex;align-items:center;gap:8px}.task-copy em{color:#d27b3e;font-size:8px;font-style:normal}.task-copy h3{margin:8px 0 5px;color:#414d68;font-size:12px}.completed h3{text-decoration:line-through}.task-copy p{margin:0;color:#929bad;font-size:8px}.task-meta{display:flex!important;gap:12px!important;margin-top:9px}.task-meta span{display:flex;align-items:center;gap:4px;color:#7e899f;font-size:8px}.done-label{display:flex;align-items:center;gap:5px;color:#168d77;font-size:9px;font-weight:750}.complete-dialog>b{color:#414c66;font-size:12px}.complete-dialog>p{margin:8px 0 17px;color:#7f899e;font-size:9px;line-height:1.6}@media(max-width:650px){.daily-hero{grid-template-columns:1fr}.ring{display:none}.task-list article{grid-template-columns:auto 1fr}.task-list article>.el-button,.done-label{grid-column:2;justify-self:start}.task-meta{align-items:flex-start;flex-direction:column;gap:5px!important}}
</style>
