<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Document, RefreshRight, VideoPause } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { asyncTaskApi, courseApi, documentApi } from '@/api/services'
import type { BackendAsyncTask, CourseListItem, WeeklyReportRequest } from '@/types'

const route = useRoute()
const router = useRouter()
const POLL_INTERVAL_MS = 2000
const MAX_POLL_FAILURES = 3
const activeStatuses = new Set(['queued', 'processing', 'cancelling'])
const taskTypeLabels: Record<string, string> = { document_parse: '文档解析', weekly_report: '学习周报', plan_generation: '学习计划生成' }
const stepLabels: Record<string, string> = { queued: '等待处理', queued_for_retry: '等待重新入队', worker_started: '任务已启动', extracting: '提取文本', chunking: '清洗与切块', embedding: '生成向量', loading_learning_data: '读取学习数据', aggregating_tasks: '汇总学习任务', aggregating_mastery: '汇总掌握度', building_report: '生成周报', cancellation_requested: '正在取消', cancelled_before_start: '开始前已取消', cancelled_by_user: '已按用户请求取消', completed: '处理完成', dispatch_failed: '派发失败' }

const tasks = ref<BackendAsyncTask[]>([])
const total = ref(0)
const selected = ref<BackendAsyncTask | null>(null)
const statusFilter = ref('all')
const typeFilter = ref('all')
const loading = ref(false)
const loadError = ref('')
const actionLoading = ref(false)
const selectionError = ref('')
const courses = ref<CourseListItem[]>([])
const courseLoading = ref(false)
const showCreate = ref(false)
const createLoading = ref(false)
const createError = ref('')
const documentCourseId = ref<number | null>(null)
let pollTimer: number | undefined
let pollFailures = 0
let requestVersion = 0

const stats = computed(() => ({
  processing: tasks.value.filter((task) => task.status === 'processing' || task.status === 'cancelling').length,
  queued: tasks.value.filter((task) => task.status === 'queued').length,
  success: tasks.value.filter((task) => task.status === 'success').length,
  failed: tasks.value.filter((task) => task.status === 'failed' || task.status === 'cancelled').length,
}))
const hasActiveTasks = computed(() => tasks.value.some((task) => activeStatuses.has(task.status)))
const currentStep = computed(() => selected.value?.current_step ? stepLabels[selected.value.current_step] || selected.value.current_step : '暂无步骤信息')
const taskTypeName = (task: BackendAsyncTask) => taskTypeLabels[task.task_type] || task.task_type
const hasWeeklyReport = computed(() => selected.value?.task_type === 'weekly_report' && selected.value.result_data)
const hasDocumentResult = computed(() => selected.value?.task_type === 'document_parse' && selected.value.result_data)
const today = new Date()
const defaultEnd = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
const previous = new Date(today); previous.setDate(previous.getDate() - 6)
const reportForm = ref<WeeklyReportRequest>({ start_date: `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}-${String(previous.getDate()).padStart(2, '0')}`, end_date: defaultEnd, course_id: null })

function errorMessage(error: unknown, fallback: string) { return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback) }
function formatDate(value: string | null) { if (!value) return '暂无'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(date) }
function taskIcon(task: BackendAsyncTask) { return task.task_type === 'document_parse' ? Document : Clock }
function stopPolling() { if (pollTimer !== undefined) window.clearTimeout(pollTimer); pollTimer = undefined }
function schedulePolling() { stopPolling(); if (!hasActiveTasks.value || document.hidden) return; pollTimer = window.setTimeout(() => void loadTasks(true), POLL_INTERVAL_MS) }

async function resolveDocumentLink(task: BackendAsyncTask | null) {
  documentCourseId.value = null
  if (!task || task.task_type !== 'document_parse' || task.resource_type !== 'document') return
  const documentId = Number(task.resource_id)
  if (!Number.isInteger(documentId) || documentId <= 0) return
  try { documentCourseId.value = (await documentApi.get(documentId)).course_id } catch { documentCourseId.value = null }
}

async function loadTasks(isPoll = false) {
  const version = ++requestVersion
  if (!isPoll) loading.value = true
  if (!isPoll) loadError.value = ''
  try {
    const result = await asyncTaskApi.list({ status: statusFilter.value === 'all' ? undefined : statusFilter.value, task_type: typeFilter.value === 'all' ? undefined : typeFilter.value, limit: 100 })
    if (version !== requestVersion) return
    tasks.value = result.items
    total.value = result.total
    pollFailures = 0
    const requestedTaskId = typeof route.query.taskId === 'string' ? route.query.taskId : ''
    const requested = requestedTaskId ? result.items.find((task) => task.task_id === requestedTaskId) : undefined
    if (requested) {
      selected.value = requested
      selectionError.value = ''
    } else if (requestedTaskId) {
      selected.value = null
      selectionError.value = '任务不存在或不属于当前账号'
      void router.replace({ name: 'tasks', query: {} })
    } else if (selected.value) {
      selected.value = result.items.find((task) => task.task_id === selected.value?.task_id) || null
    }
    if (!selected.value && result.items.length && !requestedTaskId) selected.value = result.items[0]
    await resolveDocumentLink(selected.value)
  } catch (error) {
    if (version !== requestVersion) return
    pollFailures += 1
    loadError.value = errorMessage(error, '任务列表加载失败')
    if (pollFailures >= MAX_POLL_FAILURES) stopPolling()
  } finally {
    if (version === requestVersion) { loading.value = false; if (!loadError.value && pollFailures < MAX_POLL_FAILURES) schedulePolling() }
  }
}

function selectTask(task: BackendAsyncTask) { selected.value = task; selectionError.value = ''; void router.replace({ name: 'tasks', query: { taskId: task.task_id } }); void resolveDocumentLink(task) }
async function refresh() { pollFailures = 0; stopPolling(); await loadTasks() }

async function loadCourses() { courseLoading.value = true; try { courses.value = (await courseApi.list()).items.filter((course) => !course.archived) } catch (error) { createError.value = errorMessage(error, '课程列表加载失败') } finally { courseLoading.value = false } }
async function openCreate() { createError.value = ''; showCreate.value = true; if (!courses.value.length) await loadCourses() }
async function createWeeklyReport() {
  createLoading.value = true; createError.value = ''
  try {
    const task = await asyncTaskApi.createWeeklyReport(reportForm.value)
    showCreate.value = false; selectTask(task); await loadTasks(); ElMessage.success('学习周报任务已创建')
  } catch (error) { createError.value = errorMessage(error, '创建学习周报失败') } finally { createLoading.value = false }
}
async function cancelTask() {
  if (!selected.value) return
  await ElMessageBox.confirm('队列中的任务会立即取消；执行中的任务会在安全检查点停止。确认继续？', '取消长时任务', { type: 'warning' })
  actionLoading.value = true
  try { selected.value = await asyncTaskApi.cancel(selected.value.task_id); await loadTasks(); ElMessage.success('已提交取消请求') } catch (error) { ElMessage.error(errorMessage(error, '取消任务失败')) } finally { actionLoading.value = false }
}
async function retryTask() {
  if (!selected.value) return
  await ElMessageBox.confirm('将使用原始资源和输入重新入队。确认重试？', '重试长时任务', { type: 'warning' })
  actionLoading.value = true
  try { selected.value = await asyncTaskApi.retry(selected.value.task_id); await loadTasks(); ElMessage.success('任务已重新入队') } catch (error) { ElMessage.error(errorMessage(error, '重试任务失败')) } finally { actionLoading.value = false }
}
function onVisibilityChange() { if (document.hidden) stopPolling(); else void refresh() }
watch([statusFilter, typeFilter], () => { void router.replace({ name: 'tasks', query: {} }); void loadTasks() })
watch(() => route.query.taskId, () => void loadTasks())
onMounted(() => { document.addEventListener('visibilitychange', onVisibilityChange); void loadTasks() })
onBeforeUnmount(() => { requestVersion += 1; stopPolling(); document.removeEventListener('visibilitychange', onVisibilityChange) })
</script>

<template>
  <div>
    <PageHeader title="长时任务中心" eyebrow="ASYNC JOBS" description="查看当前账号真实的文档解析与学习周报任务。">
      <el-button plain :loading="loading" @click="refresh"><el-icon><RefreshRight /></el-icon>刷新</el-button>
      <el-button type="primary" @click="openCreate"><el-icon><Clock /></el-icon>生成学习周报</el-button>
    </PageHeader>
    <section class="task-stats"><div><span>进行中</span><strong>{{ stats.processing }}</strong></div><div><span>排队中</span><strong>{{ stats.queued }}</strong></div><div><span>成功</span><strong class="green">{{ stats.success }}</strong></div><div><span>失败或取消</span><strong class="danger">{{ stats.failed }}</strong></div></section>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="refresh">重试</el-button></template></el-alert>
    <el-alert v-if="selectionError" :title="selectionError" type="warning" :closable="false" show-icon class="page-alert" />
    <section class="tasks-layout">
      <article class="content-card task-list-card" v-loading="loading">
        <div class="list-head"><div><h2>任务列表</h2><p>共 {{ total }} 项真实任务</p></div><div class="filters"><el-select v-model="statusFilter" size="small"><el-option label="全部状态" value="all" /><el-option label="排队中" value="queued" /><el-option label="处理中" value="processing" /><el-option label="正在取消" value="cancelling" /><el-option label="已成功" value="success" /><el-option label="失败" value="failed" /><el-option label="已取消" value="cancelled" /></el-select><el-select v-model="typeFilter" size="small"><el-option label="全部类型" value="all" /><el-option label="文档解析" value="document_parse" /><el-option label="学习周报" value="weekly_report" /></el-select></div></div>
        <el-empty v-if="!loading && !tasks.length" description="暂无长时任务" :image-size="72" />
        <button v-for="task in tasks" :key="task.task_id" class="task-entry" :class="{ active:selected?.task_id===task.task_id }" @click="selectTask(task)"><span class="entry-icon"><el-icon><component :is="taskIcon(task)" /></el-icon></span><div class="entry-main"><div><b>{{ taskTypeName(task) }}</b><StatusPill :status="task.status" /></div><p>{{ stepLabels[task.current_step || ''] || task.current_step || task.task_type }}</p><el-progress v-if="task.status !== 'success'" :percentage="task.progress" :show-text="false" :stroke-width="6" /><small><span class="mono">{{ task.task_id }}</span><span>{{ formatDate(task.created_at) }}</span></small></div><strong v-if="task.status !== 'success'">{{ task.progress }}%</strong></button>
      </article>
      <aside class="content-card detail-panel" v-if="selected"><header><div><span>任务详情</span><StatusPill :status="selected.status" /></div><h2>{{ taskTypeName(selected) }}</h2><p class="mono">{{ selected.task_id }}</p></header><div class="detail-progress"><strong>{{ selected.progress }}<small>%</small></strong><el-progress :percentage="selected.progress" :show-text="false" :stroke-width="8" /><span>{{ currentStep }}</span></div><div class="detail-info"><p><span>资源</span><b>{{ selected.resource_type || '无' }}{{ selected.resource_id ? ` · ${selected.resource_id}` : '' }}</b></p><p><span>创建时间</span><b>{{ formatDate(selected.created_at) }}</b></p><p><span>开始时间</span><b>{{ formatDate(selected.started_at) }}</b></p><p><span>更新时间</span><b>{{ formatDate(selected.updated_at) }}</b></p><p><span>完成时间</span><b>{{ formatDate(selected.finished_at) }}</b></p><p><span>重试次数</span><b>{{ selected.retry_count }} / 3</b></p><p><span>取消请求</span><b>{{ selected.cancel_requested ? '已请求' : '未请求' }}</b></p></div><el-alert v-if="selected.error_message" :title="selected.error_message" type="error" :closable="false" show-icon class="result-card" />
        <div v-if="hasWeeklyReport" class="result-card"><h3>学习周报</h3><p>周期：{{ selected.result_data?.range_start }} 至 {{ selected.result_data?.range_end }}</p><p>学习：{{ selected.result_data?.total_learning_minutes }} 分钟，{{ selected.result_data?.study_days }} 天</p><p>任务：{{ selected.result_data?.completed_tasks }} / {{ selected.result_data?.scheduled_tasks }}（{{ Math.round(Number(selected.result_data?.completion_rate || 0) * 100) }}%）</p><p v-if="Array.isArray(selected.result_data?.weak_points) && selected.result_data?.weak_points.length">薄弱点：{{ (selected.result_data?.weak_points as Array<{ knowledge_point:string }>).map((item) => item.knowledge_point).join('、') }}</p><p>{{ selected.result_data?.summary }}</p></div>
        <div v-else-if="hasDocumentResult" class="result-card"><h3>文档处理结果</h3><p>文档：{{ selected.result_data?.document_id }} · 版本 {{ selected.result_data?.version }}</p><p>页数：{{ selected.result_data?.page_count ?? '暂无' }} · 文本块：{{ selected.result_data?.chunk_count ?? '暂无' }}</p><el-button v-if="documentCourseId !== null" size="small" plain @click="router.push({ name: 'document-tasks', query: { courseId: String(documentCourseId), documentId: String(selected.result_data?.document_id || selected.resource_id), taskId: selected.task_id } })">查看文档处理页</el-button></div>
        <details v-else-if="selected.result_data" class="result-card"><summary>查看任务结果</summary><pre>{{ JSON.stringify(selected.result_data, null, 2) }}</pre></details>
        <div class="detail-actions"><el-button v-if="selected.can_cancel" type="danger" plain :loading="actionLoading" @click="cancelTask"><el-icon><VideoPause /></el-icon>取消任务</el-button><el-button v-if="selected.can_retry" type="primary" :loading="actionLoading" @click="retryTask"><el-icon><RefreshRight /></el-icon>立即重试</el-button></div></aside>
      <aside v-else class="content-card empty-detail"><el-empty description="选择一项任务查看详情" :image-size="72" /></aside>
    </section>
    <el-dialog v-model="showCreate" title="生成学习周报" width="min(460px,92vw)"><el-form label-position="top"><el-form-item label="开始日期"><el-date-picker v-model="reportForm.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="结束日期"><el-date-picker v-model="reportForm.end_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="课程范围"><el-select v-model="reportForm.course_id" clearable placeholder="全部课程" :loading="courseLoading" style="width:100%"><el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" /></el-select></el-form-item></el-form><el-alert v-if="createError" :title="createError" type="error" :closable="false" show-icon /><template #footer><el-button @click="showCreate=false">取消</el-button><el-button type="primary" :loading="createLoading" @click="createWeeklyReport">创建任务</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.task-stats{display:grid;grid-template-columns:repeat(4,1fr);margin-bottom:17px;border:1px solid var(--line);border-radius:16px;background:#fff;overflow:hidden}.task-stats>div{padding:17px 19px;border-right:1px solid #e9ecf2}.task-stats>div:last-child{border:0}.task-stats span{display:block;color:#8e97aa;font-size:9px}.task-stats strong{display:block;margin-top:5px;color:#3e4963;font-size:20px}.task-stats .green{color:#15967f}.task-stats .danger{color:#ce6565}.page-alert{margin-bottom:16px}.tasks-layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:17px}.task-list-card{overflow:hidden}.list-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:17px 19px;border-bottom:1px solid #edf0f4}.list-head h2{margin:0;font-size:13px}.list-head p{margin:4px 0 0;color:#929bad;font-size:9px}.filters{display:flex;gap:8px}.filters .el-select{width:115px}.task-entry{width:100%;display:flex;align-items:flex-start;gap:11px;padding:14px 18px;border:0;border-bottom:1px solid #edf0f4;background:#fff;text-align:left;cursor:pointer}.task-entry:hover,.task-entry.active{background:#f8f9ff}.task-entry.active{box-shadow:3px 0 #6070e5 inset}.entry-icon{width:34px;height:34px;display:grid;place-items:center;flex:none;border-radius:10px;background:#eef0ff;color:#5f6ee4}.entry-main{display:flex;min-width:0;flex:1;flex-direction:column}.entry-main>div{display:flex;align-items:center;gap:8px}.entry-main b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#414c66;font-size:11px}.entry-main p{margin:6px 0;color:#8e97aa;font-size:9px}.entry-main small{display:flex;gap:12px;margin-top:6px;color:#9da5b5;font-size:8px}.task-entry>strong{color:#5d6be0;font-size:11px}.detail-panel{overflow:hidden}.detail-panel>header{padding:19px;border-bottom:1px solid #edf0f4;background:#fafbfc}.detail-panel header>div{display:flex;justify-content:space-between}.detail-panel header>div>span{color:#8e97aa;font-size:9px}.detail-panel h2{margin:10px 0 5px;color:#39445f;font-size:14px}.detail-panel header p{margin:0;color:#9aa2b3;font-size:8px}.detail-progress{padding:18px;text-align:center}.detail-progress strong{color:#5d6be1;font-size:28px}.detail-progress strong small{font-size:11px}.detail-progress .el-progress{margin:12px 0}.detail-progress>span{color:#7e899e;font-size:9px}.detail-info{padding:0 18px}.detail-info p{display:flex;justify-content:space-between;gap:12px;padding:8px 0;margin:0;border-bottom:1px solid #eff1f5;font-size:9px}.detail-info span{color:#9099ab}.detail-info b{max-width:60%;overflow-wrap:anywhere;color:#566178;text-align:right}.result-card{margin:16px 18px;padding:12px;border-radius:10px;background:#f6f8fd;color:#59647c;font-size:9px;line-height:1.7}.result-card h3{margin:0 0 7px;color:#3e4963;font-size:11px}.result-card p{margin:4px 0}.result-card pre{overflow:auto;font-size:8px;white-space:pre-wrap}.detail-actions{display:flex;gap:7px;padding:0 18px 18px}.detail-actions .el-button{flex:1;margin:0}.empty-detail{display:grid;place-items:center;min-height:300px}@media(max-width:1000px){.tasks-layout{grid-template-columns:1fr}.detail-panel,.empty-detail{display:none}}@media(max-width:600px){.task-stats{grid-template-columns:1fr 1fr}.list-head{align-items:flex-start;flex-direction:column}.filters{width:100%}.filters .el-select{flex:1}.entry-main small{display:none}}
</style>
