<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Calendar, Check, Clock, Refresh, Warning } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi, planApi } from '@/api/services'
import type { CourseListItem, CurrentStudyPlanResponse, StudyPlanGenerateRequest, StudyPlanTask } from '@/types'

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const selectedCourseId = ref<number | null>(null)
const coursesLoading = ref(false)
const coursesError = ref('')
const plan = ref<CurrentStudyPlanResponse | null>(null)
const planLoading = ref(false)
const planError = ref('')
const generating = ref(false)
const confirming = ref(false)
const confirmVisible = ref(false)

function localDate(offset = 0) {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const form = reactive({
  goal: '完成课程复习并巩固重点知识',
  startDate: localDate(),
  endDate: localDate(6),
  dailyMinutes: 120,
  sessionMinutes: 45,
})

const selectedCourse = computed(() => courses.value.find((course) => course.id === selectedCourseId.value) || null)
const groupedTasks = computed(() => {
  const groups = new Map<string, StudyPlanTask[]>()
  for (const task of plan.value?.tasks || []) {
    const items = groups.get(task.scheduled_date) || []
    items.push(task)
    groups.set(task.scheduled_date, items)
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([date, tasks]) => ({ date, tasks }))
})
const totalMinutes = computed(() => (plan.value?.tasks || []).reduce((sum, task) => sum + task.estimated_minutes, 0))
const completedCount = computed(() => (plan.value?.tasks || []).filter((task) => task.status === 'completed').length)
const isCandidate = computed(() => plan.value?.status === 'candidate')

function pageError(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

function queryCourseId(): number | null {
  const raw = Array.isArray(route.query.courseId) ? route.query.courseId[0] : route.query.courseId
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

async function syncCourseQuery() {
  await router.replace({ name: 'plan', query: selectedCourseId.value ? { courseId: String(selectedCourseId.value) } : {} })
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

async function loadCurrentPlan() {
  if (!selectedCourseId.value) return
  const courseId = selectedCourseId.value
  planLoading.value = true
  planError.value = ''
  try {
    const result = await planApi.getCurrent(courseId)
    if (selectedCourseId.value === courseId) plan.value = result
  } catch (error) {
    if (selectedCourseId.value === courseId) {
      plan.value = null
      planError.value = pageError(error, '当前计划加载失败')
    }
  } finally {
    if (selectedCourseId.value === courseId) planLoading.value = false
  }
}

async function selectCourse(courseId: number) {
  selectedCourseId.value = courseId
  plan.value = null
  planError.value = ''
  confirmVisible.value = false
  await syncCourseQuery()
  await loadCurrentPlan()
}

async function initialize() {
  await loadCourses()
  if (coursesError.value || !courses.value.length) return
  const requested = queryCourseId()
  if (requested && !courses.value.some((course) => course.id === requested)) {
    coursesError.value = 'URL 中的课程不属于当前账号或已归档'
    return
  }
  selectedCourseId.value = requested || courses.value[0].id
  if (!requested) await syncCourseQuery()
  await loadCurrentPlan()
}

async function generatePlan() {
  if (generating.value || !selectedCourseId.value) return
  const goal = form.goal.trim()
  if (!goal) return ElMessage.warning('请填写学习目标')
  if (!form.startDate || !form.endDate) return ElMessage.warning('请选择计划起止日期')
  if (form.startDate > form.endDate) return ElMessage.warning('结束日期不能早于开始日期')
  if (form.sessionMinutes > form.dailyMinutes) return ElMessage.warning('单次学习时长不能超过每日预算')

  const payload: StudyPlanGenerateRequest = {
    goal,
    start_date: form.startDate,
    end_date: form.endDate,
    daily_availability: { default_minutes: form.dailyMinutes },
    session_minutes: form.sessionMinutes,
    unavailable_dates: [],
  }
  generating.value = true
  planError.value = ''
  try {
    const generated = await planApi.generate(selectedCourseId.value, payload)
    plan.value = {
      plan_id: generated.plan_id,
      course_id: generated.course_id,
      goal: generated.goal,
      start_date: generated.start_date,
      end_date: generated.end_date,
      active_version: 0,
      plan_status: 'draft',
      expected_base_version: generated.expected_base_version,
      confirmation_token: generated.confirmation_token,
      ...generated.candidate_version,
    }
    ElMessage.success('候选学习计划已生成，确认前不会进入今日任务')
  } catch (error) {
    planError.value = pageError(error, '学习计划生成失败')
  } finally {
    generating.value = false
  }
}

async function confirmPlan() {
  if (confirming.value || !plan.value || !isCandidate.value) return
  if (plan.value.expected_base_version === null || !plan.value.confirmation_token) {
    ElMessage.error('确认信息已失效，正在重新加载')
    confirmVisible.value = false
    await loadCurrentPlan()
    return
  }
  confirming.value = true
  try {
    await planApi.confirm(plan.value.plan_id, plan.value.version, {
      expected_base_version: plan.value.expected_base_version,
      confirmation_token: plan.value.confirmation_token,
    })
    confirmVisible.value = false
    await loadCurrentPlan()
    ElMessage.success('计划已确认，活动版本任务现已生效')
  } catch (error) {
    confirmVisible.value = false
    ElMessage.error(pageError(error, '计划确认失败'))
    await loadCurrentPlan()
  } finally {
    confirming.value = false
  }
}

function openTodayTasks() {
  router.push({ name: 'today', query: selectedCourseId.value ? { courseId: String(selectedCourseId.value) } : {} })
}

function formatDay(value: string) {
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', weekday: 'short' }).format(date)
}

onMounted(initialize)
</script>

<template>
  <div class="plan-page">
    <PageHeader title="学习计划" eyebrow="RULE-BASED PLANNING" description="基于课程目标、可用时间和掌握度生成规则计划，确认后任务才会生效。">
      <el-select :model-value="selectedCourseId" placeholder="选择课程" :loading="coursesLoading" style="width:240px" @change="selectCourse">
        <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" />
      </el-select>
      <el-button v-if="plan" plain :loading="planLoading" @click="loadCurrentPlan"><el-icon><Refresh /></el-icon>刷新计划</el-button>
      <el-button v-if="plan?.plan_status === 'active'" type="primary" @click="openTodayTasks">进入今日任务</el-button>
    </PageHeader>

    <el-alert v-if="coursesError" :title="coursesError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="initialize">重试</el-button></template></el-alert>
    <el-empty v-else-if="!coursesLoading && !courses.length" description="当前账号还没有课程"><el-button type="primary" @click="router.push('/courses')">前往课程管理</el-button></el-empty>

    <template v-else-if="selectedCourseId">
      <section class="content-card form-card">
        <div class="section-head"><div><span>计划参数</span><h2>{{ plan ? '生成新计划' : '生成学习计划' }}</h2><p>后端会再次校验日期与学习时长；重新生成会创建新的候选计划。</p></div><el-button type="primary" :loading="generating" :disabled="generating" @click="generatePlan">{{ generating ? '生成中…' : '生成候选计划' }}</el-button></div>
        <el-form label-position="top" class="plan-form">
          <el-form-item label="学习目标"><el-input v-model="form.goal" maxlength="500" show-word-limit /></el-form-item>
          <el-form-item label="开始日期"><el-input v-model="form.startDate" type="date" /></el-form-item>
          <el-form-item label="结束日期"><el-input v-model="form.endDate" type="date" /></el-form-item>
          <el-form-item label="每日学习分钟"><el-input-number v-model="form.dailyMinutes" :min="15" :max="720" /></el-form-item>
          <el-form-item label="单次学习分钟"><el-input-number v-model="form.sessionMinutes" :min="15" :max="180" /></el-form-item>
        </el-form>
      </section>

      <el-alert v-if="planError" :title="planError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="loadCurrentPlan">重新加载</el-button></template></el-alert>
      <div v-if="planLoading" v-loading="true" class="plan-loading"></div>
      <el-empty v-else-if="!plan" description="当前课程还没有学习计划，请先生成候选计划" />

      <template v-else>
        <section class="content-card status-card" :class="isCandidate ? 'candidate' : 'active'">
          <div><span>{{ isCandidate ? '候选版本，尚未生效' : '当前生效版本' }}</span><h2>{{ selectedCourse?.name }} · 版本 {{ plan.version }}</h2><p>{{ plan.goal }} · {{ plan.start_date }} 至 {{ plan.end_date }}</p></div>
          <el-button v-if="isCandidate" type="primary" :disabled="!plan.confirmation_token" @click="confirmVisible = true"><el-icon><Check /></el-icon>确认此计划</el-button>
          <el-button v-else type="primary" @click="openTodayTasks">查看今日任务</el-button>
        </section>

        <section class="summary-grid">
          <article><span>计划任务</span><strong>{{ plan.tasks.length }}</strong><small>已完成 {{ completedCount }} 项</small></article>
          <article><span>总预计时长</span><strong>{{ totalMinutes }}</strong><small>分钟</small></article>
          <article><span>涉及天数</span><strong>{{ groupedTasks.length }}</strong><small>个排期日</small></article>
          <article><span>版本状态</span><strong class="text-value">{{ plan.status }}</strong><small>{{ plan.summary || '暂无汇总' }}</small></article>
        </section>

        <section class="content-card risk-card"><div class="section-head"><div><span>计划风险</span><h2>真实排期检查</h2></div></div><p v-if="!plan.risks.length" class="no-risk">当前未检测到明显排期风险</p><ul v-else><li v-for="risk in plan.risks" :key="risk"><el-icon><Warning /></el-icon>{{ risk }}</li></ul></section>

        <el-empty v-if="!groupedTasks.length" description="当前候选计划没有可安排任务，请根据风险调整日期或预算" />
        <section v-else class="day-list">
          <article v-for="day in groupedTasks" :key="day.date" class="content-card day-card">
            <header><div><el-icon><Calendar /></el-icon><span>{{ formatDay(day.date) }}</span></div><small>{{ day.tasks.length }} 项 · {{ day.tasks.reduce((sum, task) => sum + task.estimated_minutes, 0) }} 分钟</small></header>
            <div class="tasks"><div v-for="task in day.tasks" :key="task.id" :class="{ completed: task.status === 'completed' }"><span class="type">{{ task.task_type }}</span><div><b>{{ task.title }}</b><small>难度 {{ task.difficulty }} · 优先级 {{ Math.round(task.priority * 100) }} · 状态 {{ task.status }}</small></div><em><el-icon><Clock /></el-icon>{{ task.estimated_minutes }} 分钟</em></div></div>
          </article>
        </section>
      </template>
    </template>

    <el-dialog v-model="confirmVisible" :title="`确认采用计划版本 ${plan?.version || ''}`" width="min(560px, 92vw)">
      <div v-if="plan" class="confirm-box"><el-icon><Warning /></el-icon><div><b>确认后活动版本任务才会进入今日任务</b><p>{{ plan.start_date }} 至 {{ plan.end_date }} · {{ plan.tasks.length }} 项任务 · 共 {{ totalMinutes }} 分钟</p><ul v-if="plan.risks.length"><li v-for="risk in plan.risks" :key="risk">{{ risk }}</li></ul><p v-else>当前未检测到明显排期风险。</p></div></div>
      <template #footer><el-button :disabled="confirming" @click="confirmVisible = false">再检查一下</el-button><el-button type="primary" :loading="confirming" :disabled="confirming" @click="confirmPlan">确认并生效</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-alert{margin-bottom:16px}.form-card{padding:18px;margin-bottom:16px}.section-head{display:flex;align-items:center;justify-content:space-between;gap:18px}.section-head span{color:#6371df;font-size:9px;font-weight:750}.section-head h2{margin:5px 0;color:#3f4962;font-size:15px}.section-head p{margin:0;color:#929bad;font-size:9px}.plan-form{display:grid;grid-template-columns:2fr repeat(4,1fr);gap:12px;margin-top:16px}.plan-form :deep(.el-form-item){margin:0}.plan-form :deep(.el-input-number){width:100%}.plan-loading{min-height:240px}.status-card{display:flex;align-items:center;justify-content:space-between;padding:20px 22px;margin-bottom:14px;border-left:4px solid}.status-card.candidate{border-left-color:#e49a42;background:#fffaf3}.status-card.active{border-left-color:#18a78b;background:#f4fbf9}.status-card span{font-size:9px;font-weight:800}.candidate span{color:#cf7d24}.active span{color:#168d77}.status-card h2{margin:6px 0;color:#3f4962;font-size:15px}.status-card p{margin:0;color:#858fa4;font-size:9px}.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:14px}.summary-grid article{display:flex;flex-direction:column;padding:17px;border:1px solid var(--line);border-radius:14px;background:white}.summary-grid span{color:#8f98aa;font-size:8px}.summary-grid strong{margin-top:7px;color:#42506d;font-size:20px}.summary-grid .text-value{font-size:14px}.summary-grid small{margin-top:5px;color:#9ca4b4;font-size:8px}.risk-card{padding:17px 20px;margin-bottom:14px}.risk-card ul,.confirm-box ul{display:grid;gap:7px;padding:0;margin:12px 0 0;list-style:none}.risk-card li{display:flex;align-items:center;gap:6px;color:#b96f2d;font-size:9px}.no-risk{margin:12px 0 0;color:#168d77;font-size:9px}.day-list{display:grid;gap:12px}.day-card{overflow:hidden}.day-card header{display:flex;align-items:center;justify-content:space-between;padding:13px 17px;border-bottom:1px solid #edf0f5;background:#fafbfc}.day-card header div{display:flex;align-items:center;gap:7px;color:#5362d7;font-size:10px;font-weight:750}.day-card header small{color:#8d96a8;font-size:8px}.tasks{display:grid}.tasks>div{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:12px;padding:13px 17px;border-bottom:1px solid #eff1f5}.tasks>div:last-child{border:0}.tasks>div.completed{opacity:.62;background:#f7faf9}.tasks .type{padding:4px 7px;border-radius:6px;background:#eef0ff;color:#5868dd;font-size:8px}.tasks b{display:block;color:#48536c;font-size:10px}.tasks small{display:block;margin-top:5px;color:#929bad;font-size:8px}.tasks em{display:flex;align-items:center;gap:4px;color:#768198;font-size:8px;font-style:normal}.confirm-box{display:flex;gap:12px;padding:15px;border-radius:12px;background:#fff7eb;color:#d9832d}.confirm-box>.el-icon{flex:none;font-size:20px}.confirm-box b{font-size:11px}.confirm-box p,.confirm-box li{color:#836a50;font-size:9px;line-height:1.6}@media(max-width:1050px){.plan-form{grid-template-columns:repeat(2,1fr)}.plan-form :first-child{grid-column:span 2}.summary-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){.plan-form,.summary-grid{grid-template-columns:1fr}.plan-form :first-child{grid-column:auto}.status-card{align-items:flex-start;gap:14px;flex-direction:column}.tasks>div{grid-template-columns:auto 1fr}.tasks em{grid-column:2}}
</style>
