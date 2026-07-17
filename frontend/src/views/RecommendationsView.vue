<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, Refresh, Star } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi, recommendationApi } from '@/api/services'
import type { CourseListItem, CourseRecommendationItem, CourseRecommendationsResponse, RecommendationFeedbackAction, RecommendationHistoryResponse, RecommendationType } from '@/types'

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const courseId = ref<number | null>(null)
const result = ref<CourseRecommendationsResponse | null>(null)
const loading = ref(false)
const coursesLoading = ref(false)
const error = ref('')
const filter = ref<'all' | RecommendationType>('all')
const feedbackBusy = ref<string | null>(null)
const feedbackState = ref<Record<string, 'saved' | 'skipped'>>({})
const historyVisible = ref(false)
const history = ref<RecommendationHistoryResponse | null>(null)
let requestVersion = 0

const selectedCourse = computed(() => courses.value.find((course) => course.id === courseId.value) || null)
const items = computed(() => (result.value?.items || []).filter((item) => filter.value === 'all' || item.item_type === filter.value))

function pageError(value: unknown, fallback: string) {
  return isUnauthorizedError(value) ? '登录状态已失效，请重新登录' : getApiErrorMessage(value, fallback)
}
function requestedCourseId(): { present: boolean; value: number | null } {
  const raw = Array.isArray(route.query.courseId) ? route.query.courseId[0] : route.query.courseId
  if (raw === undefined) return { present: false, value: null }
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return { present: true, value: Number.isInteger(parsed) && parsed > 0 ? parsed : null }
}
async function loadCourses() {
  coursesLoading.value = true
  try { courses.value = (await courseApi.list()).items.filter((course) => !course.archived) }
  catch (value) { error.value = pageError(value, '课程列表加载失败') }
  finally { coursesLoading.value = false }
}
async function loadRecommendations() {
  const id = courseId.value
  result.value = null; error.value = ''
  if (id === null) return
  const version = ++requestVersion
  loading.value = true
  try {
    const loaded = await recommendationApi.list(id)
    if (version === requestVersion) result.value = loaded
  } catch (value) {
    if (version === requestVersion) error.value = pageError(value, '推荐加载失败')
  } finally { if (version === requestVersion) loading.value = false }
}
async function selectCourse(id: number | null) {
  await router.replace({ name: 'recommendations', query: id === null ? {} : { courseId: String(id) } })
}
function routeFor(item: CourseRecommendationItem) {
  const query = { courseId: String(item.course_id) }
  const map: Record<string, { name: string; query?: Record<string, string> }> = {
    open_today_tasks: { name: 'today', query: { ...query, taskId: String(item.item_id) } },
    open_mastery: { name: 'mastery', query }, open_chat: { name: 'chat', query },
    open_plan: { name: 'plan', query }, open_upload: { name: 'upload', query }, open_async_tasks: { name: 'tasks' },
  }
  return map[item.action.type] || null
}
async function act(item: CourseRecommendationItem) {
  const destination = routeFor(item)
  if (!destination) return
  try { await recommendationApi.feedback(item.course_id, { recommendation_key: item.recommendation_key, action: 'clicked' }) }
  catch (value) { ElMessage.warning(pageError(value, '点击反馈未保存，仍可继续跳转')) }
  await router.push(destination)
}
async function feedback(item: CourseRecommendationItem, action: RecommendationFeedbackAction) {
  feedbackBusy.value = item.recommendation_key
  try { await recommendationApi.feedback(item.course_id, { recommendation_key: item.recommendation_key, action }); if (action !== 'clicked') feedbackState.value = { ...feedbackState.value, [item.recommendation_key]: action }; if (historyVisible.value) await openHistory(); ElMessage.success(action === 'saved' ? '已记录：这个推荐有帮助' : '已记录：不感兴趣') }
  catch (value) { ElMessage.error(pageError(value, '反馈保存失败')) }
  finally { feedbackBusy.value = null }
}
async function openHistory() {
  if (courseId.value === null) return
  historyVisible.value = true
  try { history.value = await recommendationApi.history(courseId.value) }
  catch (value) { ElMessage.error(pageError(value, '推荐历史加载失败')) }
}
async function initialize() {
  feedbackState.value = {}; history.value = null; historyVisible.value = false
  await loadCourses()
  if (error.value) return
  const requested = requestedCourseId()
  if (requested.present) {
    if (requested.value === null || !courses.value.some((course) => course.id === requested.value)) { courseId.value = null; result.value = null; error.value = '课程不存在、已归档或无权访问'; return }
    courseId.value = requested.value
  } else if (courses.value[0]) {
    courseId.value = courses.value[0].id
    await router.replace({ name: 'recommendations', query: { courseId: String(courseId.value) } })
  } else courseId.value = null
  await loadRecommendations()
}
watch(() => route.query.courseId, initialize)
onMounted(initialize)
</script>

<template>
  <div>
    <PageHeader title="推荐中心" eyebrow="EXPLAINABLE RECOMMENDATION" description="基于当前课程真实学习数据生成可执行建议。">
      <el-button plain :disabled="courseId === null" @click="openHistory"><el-icon><Star /></el-icon>推荐历史</el-button>
      <el-button type="primary" :loading="loading" :disabled="courseId === null" @click="loadRecommendations"><el-icon><Refresh /></el-icon>刷新推荐</el-button>
    </PageHeader>
    <el-alert v-if="error" type="error" show-icon :closable="false" :title="error" class="page-alert"><template #default><el-button text @click="initialize">重试</el-button></template></el-alert>
    <el-empty v-else-if="!coursesLoading && !courses.length" description="请先创建课程"><el-button type="primary" @click="router.push({ name: 'courses' })">前往课程列表</el-button></el-empty>
    <template v-else>
      <div class="toolbar"><el-select :model-value="courseId" placeholder="选择课程" :loading="coursesLoading" @update:model-value="selectCourse"><el-option v-for="course in courses" :key="course.id" :label="course.name" :value="course.id" /></el-select><el-radio-group v-model="filter"><el-radio-button value="all">全部</el-radio-button><el-radio-button value="study_task">任务</el-radio-button><el-radio-button value="mastery_review">掌握度</el-radio-button><el-radio-button value="course_chat">资料与问答</el-radio-button><el-radio-button value="create_plan">计划</el-radio-button><el-radio-button value="weekly_report">周报</el-radio-button></el-radio-group></div>
      <section v-if="result" class="recommend-hero"><div><span>{{ result.algorithm_version }}</span><h2>{{ selectedCourse?.name }}</h2><p>{{ result.strategy_summary }}</p></div><strong>{{ result.items.length }}<small>条推荐</small></strong></section>
      <div v-if="loading" class="loading"><el-skeleton :rows="6" animated /></div>
      <el-empty v-else-if="result && !items.length" description="当前筛选下没有推荐" />
      <section v-else-if="result" class="recommend-grid"><article v-for="item in items" :key="item.recommendation_key" class="recommend-card content-card"><div class="card-top"><span>{{ item.item_type }}</span><b>{{ item.score.toFixed(1) }} 分</b></div><h2>{{ item.title }}</h2><p>{{ item.subtitle }}</p><div class="reason"><b>推荐依据</b><p>{{ item.reason }}</p><div><el-tag v-for="signal in item.signals" :key="signal.code" size="small">{{ signal.label }} +{{ signal.contribution.toFixed(1) }}</el-tag></div></div><div class="card-actions"><el-button v-if="routeFor(item)" type="primary" @click="act(item)">{{ item.action.label }}</el-button><el-button :type="feedbackState[item.recommendation_key] === 'saved' ? 'success' : 'default'" :loading="feedbackBusy === item.recommendation_key" :disabled="feedbackBusy === item.recommendation_key" @click="feedback(item, 'saved')">{{ feedbackState[item.recommendation_key] === 'saved' ? '已标记有帮助' : '有帮助' }}</el-button><el-button :type="feedbackState[item.recommendation_key] === 'skipped' ? 'warning' : 'default'" :loading="feedbackBusy === item.recommendation_key" :disabled="feedbackBusy === item.recommendation_key" @click="feedback(item, 'skipped')">{{ feedbackState[item.recommendation_key] === 'skipped' ? '已标记不感兴趣' : '不感兴趣' }}</el-button></div></article></section>
    </template>
    <el-dialog v-model="historyVisible" title="推荐历史" width="620px"><div v-if="history" class="history-metrics"><el-tag>点击 {{ history.metrics.clicked }}</el-tag><el-tag>有帮助 {{ history.metrics.saved }}</el-tag><el-tag>不感兴趣 {{ history.metrics.skipped }}</el-tag></div><el-empty v-if="history && !history.items.length" description="暂无真实反馈历史" /><el-timeline v-else><el-timeline-item v-for="item in history?.items || []" :key="item.record_id" :timestamp="item.created_at"><b>{{ item.title }}</b> · {{ item.feedback_action }}<p>{{ item.reason }}</p></el-timeline-item></el-timeline></el-dialog>
  </div>
</template>

<style scoped>
.page-alert { margin-bottom: 16px; }
.toolbar { display: flex; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.toolbar .el-select { width: 220px; }
.recommend-hero { display: flex; justify-content: space-between; align-items: center; padding: 22px 28px; margin-bottom: 18px; border-radius: 18px; background: linear-gradient(110deg, #17264e, #293d78); color: #fff; }
.recommend-hero span { color: #aab5ce; font-size: 12px; }
.recommend-hero h2 { margin: 6px 0; font-size: 20px; }
.recommend-hero p { margin: 0; color: #d3d8e8; }
.recommend-hero strong { font-size: 28px; text-align: center; }
.recommend-hero small { display: block; font-size: 12px; font-weight: 400; }
.recommend-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.recommend-card { padding: 18px; }
.card-top { display: flex; justify-content: space-between; color: #6372e8; }
.card-top b { color: #15977f; }
.recommend-card h2 { font-size: 16px; }
.recommend-card > p { color: #818ba0; font-size: 13px; }
.reason { padding: 12px; border-radius: 10px; background: #f7f8fc; font-size: 13px; }
.reason p { line-height: 1.55; }
.reason div, .card-actions, .history-metrics { display: flex; gap: 6px; flex-wrap: wrap; }
.card-actions { margin-top: 14px; }
.history-metrics { margin-bottom: 15px; }
@media (max-width: 900px) { .recommend-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px) { .toolbar { align-items: stretch; flex-direction: column; } .toolbar .el-select { width: 100%; } .recommend-grid { grid-template-columns: 1fr; } }
</style>
