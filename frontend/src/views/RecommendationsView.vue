<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Star } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi, recommendationApi } from '@/api/services'
import type {
  CourseListItem,
  CourseRecommendationItem,
  CourseRecommendationsResponse,
  RecommendationCategory,
  RecommendationFeedbackAction,
  RecommendationHistoryResponse,
} from '@/types'

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const courseId = ref<number | null>(null)
const category = ref<RecommendationCategory>('all')
const result = ref<CourseRecommendationsResponse | null>(null)
const loading = ref(false)
const coursesLoading = ref(false)
const courseLoadError = ref('')
const recommendationError = ref('')
const routeError = ref('')
const feedbackBusyKeys = ref<Set<string>>(new Set())
const actionBusyKey = ref<string | null>(null)
const feedbackState = ref<Record<string, 'saved' | 'skipped'>>({})
const historyVisible = ref(false)
const history = ref<RecommendationHistoryResponse | null>(null)
const historyLoading = ref(false)
const historyRefreshing = ref(false)
let requestVersion = 0
let historyRequestVersion = 0
let viewActive = true

const categoryOptions: { value: RecommendationCategory; label: string; empty: string }[] = [
  { value: 'all', label: '综合', empty: '当前没有可执行的下一步建议' },
  { value: 'task', label: '学习任务', empty: '当前没有待完成的近期学习任务' },
  { value: 'mastery', label: '薄弱点复习', empty: '暂无有真实学习记录的薄弱知识点' },
  { value: 'resource', label: '资料与问答', empty: '当前没有资料或问答相关建议' },
  { value: 'plan', label: '学习计划', empty: '当前已有生效计划，无需再次创建' },
  { value: 'report', label: '学习复盘', empty: '最近 7 天暂无学习记录，暂不建议生成周报' },
]
const selectedCourse = computed(() => courses.value.find((course) => course.id === courseId.value) || null)
const selectedCategory = computed(() => categoryOptions.find((item) => item.value === category.value) || categoryOptions[0])
const items = computed(() => result.value?.items || [])

function pageError(value: unknown, fallback: string) {
  return isUnauthorizedError(value) ? '登录状态已失效，请重新登录' : getApiErrorMessage(value, fallback)
}

function queryValue(key: 'courseId' | 'category') {
  const raw = route.query[key]
  return Array.isArray(raw) ? raw[0] : raw
}

function requestedCourseId(): { present: boolean; value: number | null } {
  const raw = queryValue('courseId')
  if (raw === undefined) return { present: false, value: null }
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return { present: true, value: Number.isInteger(parsed) && parsed > 0 ? parsed : null }
}

function requestedCategory(): { value: RecommendationCategory; valid: boolean } {
  const raw = queryValue('category')
  if (raw === undefined) return { value: 'all', valid: true }
  return categoryOptions.some((item) => item.value === raw)
    ? { value: raw as RecommendationCategory, valid: true }
    : { value: 'all', valid: false }
}

function recommendationQuery(id: number | null, nextCategory: RecommendationCategory) {
  const query: Record<string, string> = {}
  if (id !== null) query.courseId = String(id)
  if (nextCategory !== 'all') query.category = nextCategory
  return query
}

async function loadCourses() {
  courseLoadError.value = ''
  coursesLoading.value = true
  try {
    courses.value = (await courseApi.list()).items.filter((course) => !course.archived)
  } catch (value) {
    courseLoadError.value = pageError(value, '课程列表加载失败')
  } finally {
    coursesLoading.value = false
  }
}

async function loadRecommendations() {
  const id = courseId.value
  const requestedCategory = category.value
  const version = ++requestVersion
  result.value = null
  recommendationError.value = ''
  if (id === null) return
  loading.value = true
  try {
    const loaded = await recommendationApi.list(id, { category: requestedCategory, limit: 6 })
    if (version === requestVersion && courseId.value === id && category.value === requestedCategory) result.value = loaded
  } catch (value) {
    if (version === requestVersion) recommendationError.value = pageError(value, '推荐加载失败')
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

async function synchronizeRoute() {
  if (coursesLoading.value) return
  const requestedCourse = requestedCourseId()
  const requestedFilter = requestedCategory()
  let nextCourse: number | null = null

  if (requestedCourse.present) {
    if (requestedCourse.value === null || !courses.value.some((course) => course.id === requestedCourse.value)) {
      courseId.value = null
      result.value = null
      recommendationError.value = ''
      routeError.value = '课程不存在、已归档或无权访问'
      return
    }
    nextCourse = requestedCourse.value
  } else if (courses.value[0]) {
    nextCourse = courses.value[0].id
  }

  const desiredQuery = recommendationQuery(nextCourse, requestedFilter.value)
  const routeHasDesiredCourse = queryValue('courseId') === desiredQuery.courseId
  const routeHasDesiredCategory = (queryValue('category') || undefined) === desiredQuery.category
  if (!requestedFilter.valid || !routeHasDesiredCourse || !routeHasDesiredCategory) {
    await router.replace({ name: 'recommendations', query: desiredQuery })
    return
  }

  const courseChanged = courseId.value !== nextCourse
  courseId.value = nextCourse
  category.value = requestedFilter.value
  routeError.value = ''
  if (courseChanged) {
    feedbackState.value = {}
    feedbackBusyKeys.value = new Set()
    actionBusyKey.value = null
    history.value = null
    historyVisible.value = false
    historyLoading.value = false
    historyRefreshing.value = false
    historyRequestVersion += 1
  }
  await loadRecommendations()
}

async function retryCourses() {
  await loadCourses()
  if (!courseLoadError.value) await synchronizeRoute()
}

async function retryRecommendations() {
  if (courseId.value !== null) await loadRecommendations()
}

function clearRecommendationState() {
  requestVersion += 1
  result.value = null
  recommendationError.value = ''
}

async function selectCourse(id: number | null) {
  clearRecommendationState()
  await router.replace({ name: 'recommendations', query: recommendationQuery(id, category.value) })
}

async function selectCategory(nextCategory: RecommendationCategory) {
  if (courseId.value === null) return
  clearRecommendationState()
  await router.replace({ name: 'recommendations', query: recommendationQuery(courseId.value, nextCategory) })
}

function routeFor(item: CourseRecommendationItem) {
  const courseQuery = { courseId: String(item.course_id) }
  const map: Record<string, { name: string; query?: Record<string, string> }> = {
    open_today_tasks: { name: 'today', query: { ...courseQuery, taskId: String(item.item_id) } },
    open_mastery: { name: 'mastery', query: courseQuery },
    open_chat: { name: 'chat', query: courseQuery },
    open_plan: { name: 'plan', query: courseQuery },
    open_upload: { name: 'upload', query: courseQuery },
    open_async_tasks: { name: 'tasks' },
  }
  return map[item.action.type] || null
}

async function refreshHistory(initial = false) {
  if (courseId.value === null) return
  if (historyLoading.value || historyRefreshing.value) return
  const id = courseId.value
  const version = ++historyRequestVersion
  if (initial) historyLoading.value = true
  else historyRefreshing.value = true
  try {
    const loaded = await recommendationApi.history(id)
    if (viewActive && version === historyRequestVersion && courseId.value === id) history.value = loaded
  } catch (value) {
    if (viewActive && version === historyRequestVersion) ElMessage.error(pageError(value, '推荐历史加载失败'))
  } finally {
    if (version === historyRequestVersion) {
      if (initial) historyLoading.value = false
      else historyRefreshing.value = false
    }
  }
}

async function act(item: CourseRecommendationItem) {
  const destination = routeFor(item)
  if (!destination || actionBusyKey.value !== null) return
  const key = item.recommendation_key
  const sourceCourseId = item.course_id
  const sourceRequestVersion = requestVersion
  actionBusyKey.value = key
  try {
    try {
      await recommendationApi.feedback(sourceCourseId, { recommendation_key: key, action: 'clicked' })
    } catch (value) {
      if (
        viewActive
        && requestVersion === sourceRequestVersion
        && courseId.value === sourceCourseId
        && actionBusyKey.value === key
      ) {
        ElMessage.warning(pageError(value, '点击反馈未保存，仍可继续跳转'))
      }
    }
    if (
      !viewActive
      || requestVersion !== sourceRequestVersion
      || courseId.value !== sourceCourseId
      || actionBusyKey.value !== key
    ) {
      return
    }
    if (viewActive && historyVisible.value) void refreshHistory()
    await router.push(destination)
  } finally {
    if (actionBusyKey.value === key) actionBusyKey.value = null
  }
}

async function feedback(item: CourseRecommendationItem, action: RecommendationFeedbackAction) {
  const key = item.recommendation_key
  if (feedbackBusyKeys.value.has(key)) return
  feedbackBusyKeys.value = new Set(feedbackBusyKeys.value).add(key)
  try {
    await recommendationApi.feedback(item.course_id, { recommendation_key: item.recommendation_key, action })
    if (viewActive && courseId.value === item.course_id) {
      feedbackState.value = { ...feedbackState.value, [item.recommendation_key]: action as 'saved' | 'skipped' }
      if (historyVisible.value) void refreshHistory()
      ElMessage.success(action === 'saved' ? '已记录：这个推荐有帮助' : '已记录：不感兴趣')
    }
  } catch (value) {
    if (viewActive && courseId.value === item.course_id) ElMessage.error(pageError(value, '反馈保存失败'))
  } finally {
    const next = new Set(feedbackBusyKeys.value)
    next.delete(key)
    feedbackBusyKeys.value = next
  }
}

async function openHistory() {
  if (courseId.value === null || historyVisible.value || historyLoading.value) return
  historyVisible.value = true
  history.value = null
  await refreshHistory(true)
}

function priorityLabel(score: number) {
  if (score >= 75) return '优先处理'
  if (score >= 50) return '建议安排'
  return '可选建议'
}

function feedbackLabel(action: RecommendationFeedbackAction | null) {
  return { clicked: '已点击', saved: '有帮助', skipped: '不感兴趣' }[action || 'clicked']
}

onMounted(async () => {
  await loadCourses()
  await synchronizeRoute()
})
watch([() => route.query.courseId, () => route.query.category], () => { void synchronizeRoute() })
onBeforeUnmount(() => {
  viewActive = false
  requestVersion += 1
  historyRequestVersion += 1
  feedbackBusyKeys.value = new Set()
  actionBusyKey.value = null
})
</script>

<template>
  <div>
    <PageHeader title="下一步建议" eyebrow="个性化推荐" description="综合任务、掌握情况、课程资料和近期学习记录，帮你判断此刻最值得做什么。">
      <el-button plain :loading="historyLoading" :disabled="courseId === null || historyLoading" @click="openHistory"><el-icon><Star /></el-icon>推荐历史</el-button>
      <el-button type="primary" :loading="loading" :disabled="loading || courseId === null" @click="loadRecommendations"><el-icon><Refresh /></el-icon>刷新推荐</el-button>
    </PageHeader>
    <div v-if="coursesLoading && !courses.length" class="loading"><el-skeleton :rows="4" animated /></div>
    <el-alert v-else-if="courseLoadError" type="error" show-icon :closable="false" :title="courseLoadError" class="page-alert"><template #default><el-button text :loading="coursesLoading" :disabled="coursesLoading" @click="retryCourses">重新加载课程</el-button></template></el-alert>
    <el-alert v-else-if="routeError && !courses.length" type="error" show-icon :closable="false" :title="routeError" class="page-alert" />
    <el-empty v-else-if="!courses.length" description="请先创建课程"><el-button type="primary" @click="router.push({ name: 'courses' })">前往课程列表</el-button></el-empty>
    <template v-else>
      <div class="toolbar">
        <el-select :model-value="courseId" placeholder="选择课程" :loading="coursesLoading" @update:model-value="selectCourse"><el-option v-for="course in courses" :key="course.id" :label="course.name" :value="course.id" /></el-select>
        <el-radio-group :model-value="category" class="category-tabs" @update:model-value="selectCategory">
          <el-radio-button v-for="option in categoryOptions" :key="option.value" :value="option.value">
            {{ option.label }}<small v-if="result"> {{ result.category_counts[option.value] }}</small>
          </el-radio-button>
        </el-radio-group>
      </div>
      <el-alert v-if="routeError" type="error" show-icon :closable="false" :title="routeError" class="page-alert"><template #default><el-button text @click="selectCourse(courses[0]?.id || null)">切换到可用课程</el-button></template></el-alert>
      <el-alert v-if="recommendationError" type="error" show-icon :closable="false" :title="recommendationError" class="page-alert"><template #default><el-button text :loading="loading" :disabled="loading" @click="retryRecommendations">重新加载推荐</el-button></template></el-alert>
      <section v-if="result" class="recommend-hero"><div><span>当前课程</span><h2>{{ selectedCourse?.name }}</h2><p>{{ result.strategy_summary }}</p></div><strong>为你筛选 {{ result.selection.returned }} 条<small>从 {{ result.selection.candidate_total }} 个可执行动作中排序</small></strong></section>
      <div v-if="loading" class="loading"><el-skeleton :rows="6" animated /></div>
      <el-empty v-else-if="!routeError && !recommendationError && result && !items.length" :description="selectedCategory.empty" />
      <section v-else-if="result" class="recommend-grid"><article v-for="(item, index) in items" :key="item.recommendation_key" class="recommend-card content-card"><div class="card-top"><span>{{ index === 0 && category === 'all' ? '首要建议' : item.category_label }}</span><b :class="{ urgent: item.score >= 75 }">{{ priorityLabel(item.score) }}</b></div><h2>{{ item.title }}</h2><p>{{ item.subtitle }}</p><div class="reason"><b>为什么推荐给你</b><p>{{ item.reason }}</p><details v-if="item.signals.length"><summary>查看判断信号</summary><div><el-tag v-for="signal in item.signals" :key="signal.code" size="small">{{ signal.label }} · {{ signal.contribution.toFixed(1) }}</el-tag></div></details></div><div class="card-actions"><el-button v-if="routeFor(item)" type="primary" :loading="actionBusyKey === item.recommendation_key" :disabled="actionBusyKey !== null" @click="act(item)">{{ item.action.label }}</el-button><el-button :type="feedbackState[item.recommendation_key] === 'saved' ? 'success' : 'default'" :loading="feedbackBusyKeys.has(item.recommendation_key)" :disabled="feedbackBusyKeys.has(item.recommendation_key)" @click="feedback(item, 'saved')">{{ feedbackState[item.recommendation_key] === 'saved' ? '已标记有帮助' : '有帮助' }}</el-button><el-button :type="feedbackState[item.recommendation_key] === 'skipped' ? 'warning' : 'default'" :loading="feedbackBusyKeys.has(item.recommendation_key)" :disabled="feedbackBusyKeys.has(item.recommendation_key)" @click="feedback(item, 'skipped')">{{ feedbackState[item.recommendation_key] === 'skipped' ? '已标记不感兴趣' : '不感兴趣' }}</el-button></div></article></section>
      <p v-if="result" class="rules-note">建议来自你的真实学习记录与可执行状态 · 推荐模型版本 {{ result.algorithm_version }}</p>
    </template>
    <el-dialog v-model="historyVisible" title="推荐历史" width="620px"><div v-loading="historyLoading"><div v-if="history" class="history-metrics"><el-tag>点击 {{ history.metrics.clicked }}</el-tag><el-tag>有帮助 {{ history.metrics.saved }}</el-tag><el-tag>不感兴趣 {{ history.metrics.skipped }}</el-tag><el-button size="small" :loading="historyRefreshing" :disabled="historyRefreshing" @click="refreshHistory()">刷新历史</el-button></div><el-empty v-if="history && !history.items.length" description="暂无真实反馈历史" /><el-timeline v-else><el-timeline-item v-for="item in history?.items || []" :key="item.record_id" :timestamp="item.created_at"><b>{{ item.title }}</b> · {{ item.category_label }} · {{ feedbackLabel(item.feedback_action) }}<p>{{ item.reason }}</p></el-timeline-item></el-timeline></div></el-dialog>
  </div>
</template>

<style scoped>
.page-alert{margin-bottom:16px}.toolbar{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:16px}.toolbar .el-select{width:220px}.category-tabs{display:flex;flex-wrap:wrap;justify-content:flex-end}.category-tabs small{margin-left:3px;color:#74809a}.recommend-hero{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:25px 30px;margin-bottom:18px;border-radius:18px;background:linear-gradient(115deg,#17264e,#394a94);color:#fff;box-shadow:0 15px 34px rgba(25,40,83,.16)}.recommend-hero span{color:#aeb9e9;font-size:11px;font-weight:750}.recommend-hero h2{margin:5px 0 7px;font-size:22px}.recommend-hero p{max-width:680px;margin:0;color:#dce1f0;font-size:13px;line-height:1.6}.recommend-hero strong{font-size:19px;text-align:right}.recommend-hero small{display:block;margin-top:5px;color:#c7cfe8;font-size:11px;font-weight:400}.recommend-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.recommend-card{display:flex;min-height:280px;flex-direction:column;padding:20px}.card-top{display:flex;justify-content:space-between;color:#5267dd;font-size:12px;font-weight:750}.card-top b{color:#53806c}.card-top b.urgent{color:#d5683d}.recommend-card h2{margin:16px 0 8px;color:#34415b;font-size:17px}.recommend-card>p{min-height:40px;margin:0 0 14px;color:#758096;font-size:12px;line-height:1.6}.reason{padding:14px;border:1px solid #e9ecf4;border-radius:11px;background:#f8f9fc;font-size:12px}.reason>b{color:#45516c}.reason summary{margin-top:10px;color:#6572d4;cursor:pointer;font-weight:700}.reason p{margin:7px 0 0;color:#69758d;line-height:1.6}.reason div,.card-actions,.history-metrics{display:flex;gap:6px;flex-wrap:wrap}.reason details div{margin-top:9px}.card-actions{margin-top:auto;padding-top:16px}.history-metrics{margin-bottom:15px}.rules-note{margin:20px 0 0;color:#7f8aa1;font-size:11px;text-align:right}@media(max-width:900px){.toolbar{align-items:stretch;flex-direction:column}.toolbar .el-select{width:100%}.category-tabs{justify-content:flex-start}.recommend-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.recommend-hero{align-items:flex-start;flex-direction:column}.recommend-hero strong{text-align:left}.recommend-grid{grid-template-columns:1fr}}
</style>
