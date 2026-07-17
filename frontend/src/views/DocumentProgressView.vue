<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Document, RefreshRight, Upload } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'
import { getApiErrorMessage, isApiError, isUnauthorizedError } from '@/api/client'
import { courseApi, documentApi } from '@/api/services'
import type { BackendAsyncTask, BackendDocument, CourseListItem } from '@/types'

const POLL_INTERVAL_MS = 1500
const MAX_POLL_FAILURES = 3
const TERMINAL_STATUSES = new Set(['success', 'failed', 'cancelled'])
const STEP_LABELS: Record<string, string> = {
  queued: '等待处理',
  worker_started: '任务已开始',
  extracting: '提取文本',
  chunking: '清洗与切块',
  embedding: '生成向量',
  completed: '处理完成',
  cancelled_by_user: '用户已取消',
}
const PIPELINE_STAGES = [
  { key: 'queued', label: '等待处理' },
  { key: 'worker_started', label: '任务启动' },
  { key: 'extracting', label: '提取文本' },
  { key: 'chunking', label: '清洗与切块' },
  { key: 'embedding', label: '生成向量' },
  { key: 'completed', label: '处理完成' },
]

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const selectedCourseId = ref<number | null>(null)
const coursesLoading = ref(false)
const coursesError = ref('')
const documents = ref<BackendDocument[]>([])
const documentsLoading = ref(false)
const documentsError = ref('')
const activeDocument = ref<BackendDocument | null>(null)
const documentError = ref('')
const task = ref<BackendAsyncTask | null>(null)
const activeTaskId = ref('')
const taskError = ref('')
const polling = ref(false)
let pollTimer: number | undefined
let pollFailures = 0
let initializationVersion = 0

const selectedCourse = computed(() => courses.value.find((course) => course.id === selectedCourseId.value) || null)
const progress = computed(() => Math.min(100, Math.max(0, Math.round(task.value?.progress || 0))))
const chunkCount = computed(() => {
  const value = task.value?.result_data?.chunk_count
  return typeof value === 'number' ? value : null
})
const currentStepLabel = computed(() => {
  const step = task.value?.current_step
  return step ? STEP_LABELS[step] || step : '暂无步骤信息'
})
const currentStageIndex = computed(() => {
  if (!task.value) return -1
  if (task.value.status === 'success') return PIPELINE_STAGES.length - 1
  return PIPELINE_STAGES.findIndex((stage) => stage.key === task.value?.current_step)
})
const refreshLabel = computed(() => {
  if (taskError.value) return '状态读取失败'
  if (task.value && TERMINAL_STATUSES.has(task.value.status)) return '处理已停止'
  return polling.value ? '自动刷新中' : '未启动自动刷新'
})

function parsePositiveId(value: unknown): number | null {
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function parseTaskId(value: unknown): string {
  const raw = Array.isArray(value) ? value[0] : value
  return typeof raw === 'string' ? raw.trim() : ''
}

function documentErrorMessage(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

function stopPolling() {
  if (pollTimer !== undefined) window.clearTimeout(pollTimer)
  pollTimer = undefined
  polling.value = false
}

function isCurrentTask(documentId: number, taskId: string) {
  return activeDocument.value?.id === documentId && activeTaskId.value === taskId
}

function schedulePoll(documentId: number, taskId: string) {
  stopPolling()
  if (!task.value || TERMINAL_STATUSES.has(task.value.status) || !isCurrentTask(documentId, taskId)) return
  polling.value = true
  pollTimer = window.setTimeout(() => void readTask(documentId, taskId, true), POLL_INTERVAL_MS)
}

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = ''
  try {
    const result = await courseApi.list()
    courses.value = result.items.filter((course) => !course.archived)
  } catch (error) {
    courses.value = []
    coursesError.value = documentErrorMessage(error, '课程列表加载失败')
  } finally {
    coursesLoading.value = false
  }
}

async function loadDocuments(courseId: number) {
  documentsLoading.value = true
  documentsError.value = ''
  try {
    const result = await documentApi.list(courseId)
    if (selectedCourseId.value === courseId) documents.value = result.items
  } catch (error) {
    if (selectedCourseId.value === courseId) {
      documents.value = []
      documentsError.value = documentErrorMessage(error, '文档列表加载失败')
    }
  } finally {
    if (selectedCourseId.value === courseId) documentsLoading.value = false
  }
}

async function refreshActiveDocument(documentId: number) {
  documentError.value = ''
  try {
    const result = await documentApi.get(documentId)
    if (activeDocument.value?.id === documentId || activeDocument.value === null) activeDocument.value = result
  } catch (error) {
    documentError.value = documentErrorMessage(error, '文档详情读取失败')
  }
}

async function readTask(documentId: number, taskId: string, isPoll = false) {
  try {
    const result = await documentApi.getTask(documentId, taskId)
    if (!isCurrentTask(documentId, taskId)) return
    task.value = result
    taskError.value = ''
    pollFailures = 0
    if (TERMINAL_STATUSES.has(result.status)) {
      stopPolling()
      if (activeDocument.value?.id === documentId) void refreshActiveDocument(documentId)
      if (selectedCourseId.value) void loadDocuments(selectedCourseId.value)
    } else {
      schedulePoll(documentId, taskId)
    }
  } catch (error) {
    if (!isCurrentTask(documentId, taskId)) return
    pollFailures += 1
    taskError.value = isApiError(error, 404, 'TASK_NOT_FOUND')
      ? '任务不存在或不属于当前文档'
      : documentErrorMessage(error, '任务状态读取失败')
    if (pollFailures >= MAX_POLL_FAILURES || !isPoll) {
      stopPolling()
    } else {
      schedulePoll(documentId, taskId)
    }
  }
}

async function resolveTask(documentId: number, requestedTaskId: string) {
  let taskId = requestedTaskId
  if (!taskId) {
    try {
      taskId = (await documentApi.getLatestTask(documentId)).task_id
    } catch (error) {
      taskError.value = documentErrorMessage(error, '该文档暂无处理任务')
      return
    }
  }
  activeTaskId.value = taskId
  await readTask(documentId, taskId)

  if (!requestedTaskId && isCurrentTask(documentId, taskId) && !taskError.value) {
    void router.replace({
      name: 'document-tasks',
      query: { courseId: String(selectedCourseId.value), documentId: String(documentId), taskId },
    })
  }
}

async function initialize() {
  const version = ++initializationVersion
  stopPolling()
  pollFailures = 0
  selectedCourseId.value = null
  documents.value = []
  activeDocument.value = null
  activeTaskId.value = ''
  task.value = null
  documentsError.value = ''
  documentError.value = ''
  taskError.value = ''

  await loadCourses()
  if (version !== initializationVersion || coursesError.value) return

  const requestedCourseId = parsePositiveId(route.query.courseId)
  const requestedDocumentId = parsePositiveId(route.query.documentId)
  const requestedTaskId = parseTaskId(route.query.taskId)
  if (route.query.courseId !== undefined && requestedCourseId === null) {
    coursesError.value = 'URL 中的课程地址无效'
    return
  }
  if (route.query.documentId !== undefined && requestedDocumentId === null) {
    documentError.value = 'URL 中的文档地址无效'
    return
  }

  if (requestedCourseId) {
    if (!courses.value.some((course) => course.id === requestedCourseId)) {
      coursesError.value = 'URL 中的课程不属于当前账号或已归档'
      return
    }
    selectedCourseId.value = requestedCourseId
  }

  if (requestedDocumentId) {
    try {
      const document = await documentApi.get(requestedDocumentId)
      if (version !== initializationVersion) return
      if (!courses.value.some((course) => course.id === document.course_id)) {
        documentError.value = '文档所属课程不在当前账号的课程列表中'
        return
      }
      if (selectedCourseId.value && selectedCourseId.value !== document.course_id) {
        documentError.value = 'URL 中的课程与文档不匹配'
        return
      }
      activeDocument.value = document
      selectedCourseId.value = document.course_id
    } catch (error) {
      documentError.value = documentErrorMessage(error, '文档详情读取失败')
      return
    }
  }

  if (selectedCourseId.value) await loadDocuments(selectedCourseId.value)
  if (version !== initializationVersion) return
  if (requestedDocumentId) await resolveTask(requestedDocumentId, requestedTaskId)
}

function selectCourse(courseId: number) {
  router.replace({ name: 'document-tasks', query: { courseId: String(courseId) } })
}

function selectDocument(document: BackendDocument) {
  router.replace({
    name: 'document-tasks',
    query: { courseId: String(document.course_id), documentId: String(document.id) },
  })
}

async function refreshAll() {
  if (selectedCourseId.value) await loadDocuments(selectedCourseId.value)
  if (activeDocument.value) await refreshActiveDocument(activeDocument.value.id)
  if (activeTaskId.value) {
    stopPolling()
    pollFailures = 0
    if (activeDocument.value) await readTask(activeDocument.value.id, activeTaskId.value)
  }
}

function retryTaskStatus() {
  stopPolling()
  pollFailures = 0
  taskError.value = ''
  if (activeTaskId.value) {
    if (activeDocument.value) void readTask(activeDocument.value.id, activeTaskId.value)
  } else if (activeDocument.value) {
    void resolveTask(activeDocument.value.id, '')
  }
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

watch(() => route.fullPath, () => void initialize(), { immediate: true })
onBeforeUnmount(() => {
  initializationVersion += 1
  stopPolling()
})
</script>

<template>
  <div>
    <PageHeader title="文档处理进度" eyebrow="RAG PIPELINE" description="通过 REST 自动刷新真实文档与解析任务状态。">
      <span class="refresh-state" :class="{ error: taskError }"><i></i>{{ refreshLabel }}</span>
      <el-button plain :icon="RefreshRight" @click="refreshAll">刷新状态</el-button>
    </PageHeader>

    <section class="content-card card-pad selector-card">
      <div>
        <b>课程</b>
        <el-select :model-value="selectedCourseId" placeholder="选择课程查看资料" :loading="coursesLoading" style="width:min(360px,100%)" @change="selectCourse">
          <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" />
        </el-select>
      </div>
      <el-button type="primary" plain :icon="Upload" :disabled="!selectedCourseId" @click="router.push({ name: 'upload', query: selectedCourseId ? { courseId: String(selectedCourseId) } : {} })">上传新资料</el-button>
    </section>

    <el-alert v-if="coursesError" :title="coursesError" type="error" :closable="false" show-icon class="state-alert">
      <template #default><el-button size="small" @click="initialize">重新加载</el-button></template>
    </el-alert>
    <el-empty v-else-if="!coursesLoading && !courses.length" description="当前账号还没有课程">
      <el-button type="primary" @click="router.push('/courses')">前往课程管理</el-button>
    </el-empty>

    <el-alert v-if="documentError" :title="documentError" type="error" :closable="false" show-icon class="state-alert" />
    <section v-if="activeDocument" class="active-task">
      <div class="active-top">
        <div class="file-icon"><el-icon><Document /></el-icon></div>
        <div class="active-info"><span>{{ selectedCourse?.name || '当前课程' }}</span><h2>{{ activeDocument.title }}</h2><p>{{ activeDocument.file_type.toUpperCase() }} · v{{ activeDocument.current_version }} · 文档状态：{{ activeDocument.status }}</p></div>
        <strong v-if="task">{{ progress }}<small>%</small></strong>
      </div>

      <template v-if="task">
        <el-progress :percentage="progress" :show-text="false" :stroke-width="9" color="#6675ed" />
        <div class="stage-list">
          <div v-for="(stage,index) in PIPELINE_STAGES" :key="stage.key" :class="{ done: index < currentStageIndex || task.status === 'success', active: index === currentStageIndex && task.status !== 'success' }"><span><i></i></span><b>{{ stage.label }}</b></div>
        </div>
        <div class="task-detail-grid">
          <p><span>任务 ID</span><b class="mono">{{ task.task_id }}</b></p>
          <p><span>任务状态</span><StatusPill :status="task.status" /></p>
          <p><span>当前步骤</span><b>{{ currentStepLabel }}</b></p>
          <p><span>文档页数</span><b>{{ activeDocument.page_count ?? '待生成' }}</b></p>
          <p><span>文本块数</span><b>{{ chunkCount ?? '待生成' }}</b></p>
          <p><span>创建时间</span><b>{{ formatDate(task.created_at) }}</b></p>
        </div>
        <el-alert v-if="task.error_message" :title="task.error_message" type="error" :closable="false" show-icon class="inner-alert" />
        <el-alert v-if="taskError" :title="taskError" type="error" :closable="false" show-icon class="inner-alert"><template #default><el-button size="small" @click="retryTaskStatus">重试读取状态</el-button></template></el-alert>
      </template>
      <el-alert v-else-if="taskError" :title="taskError" type="warning" :closable="false" show-icon><template #default><el-button size="small" @click="retryTaskStatus">重试读取状态</el-button></template></el-alert>
      <el-empty v-else description="该文档暂无处理任务" />
    </section>

    <section v-if="selectedCourseId" class="content-card card-pad table-card">
      <div class="card-header"><div><h2>课程资料</h2><p>{{ selectedCourse?.name }} · {{ documents.length }} 份真实文档</p></div><el-button :icon="RefreshRight" :loading="documentsLoading" @click="loadDocuments(selectedCourseId)">刷新列表</el-button></div>
      <el-alert v-if="documentsError" :title="documentsError" type="error" :closable="false" show-icon class="state-alert"><template #default><el-button size="small" @click="loadDocuments(selectedCourseId)">重新加载</el-button></template></el-alert>
      <el-table v-else v-loading="documentsLoading" :data="documents" empty-text="该课程还没有文档">
        <el-table-column label="文档" min-width="250"><template #default="scope"><div class="document-cell"><span>{{ scope.row.file_type.toUpperCase() }}</span><div><b>{{ scope.row.title }}</b><small>版本 v{{ scope.row.current_version }}</small></div></div></template></el-table-column>
        <el-table-column label="状态" width="115"><template #default="scope"><StatusPill :status="scope.row.status" /></template></el-table-column>
        <el-table-column label="页数" width="85"><template #default="scope">{{ scope.row.page_count ?? '—' }}</template></el-table-column>
        <el-table-column label="更新时间" min-width="150"><template #default="scope">{{ formatDate(scope.row.updated_at) }}</template></el-table-column>
        <el-table-column label="失败原因" min-width="180"><template #default="scope">{{ scope.row.error_message || '—' }}</template></el-table-column>
        <el-table-column label="操作" width="110"><template #default="scope"><el-button link type="primary" @click="selectDocument(scope.row)">查看状态</el-button></template></el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.refresh-state{display:flex;align-items:center;gap:7px;padding:8px 11px;border-radius:999px;background:#eef1ff;color:#5868de;font-size:9px;font-weight:700}.refresh-state i{width:7px;height:7px;border-radius:50%;background:currentColor}.refresh-state.error{background:#ffeded;color:#dc5f5f}.selector-card{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:18px}.selector-card>div{display:flex;flex:1;flex-direction:column;gap:8px;color:#4b5670;font-size:10px}.state-alert{margin-bottom:18px}.state-alert :deep(.el-alert__content),.inner-alert :deep(.el-alert__content){width:100%}.state-alert :deep(.el-alert__description),.inner-alert :deep(.el-alert__description){display:flex;justify-content:flex-end;margin:0}.active-task{padding:25px 27px;margin-bottom:18px;border:1px solid #dfe3f5;border-radius:19px;background:linear-gradient(145deg,#fff,#f8f9ff);box-shadow:var(--shadow-soft)}.active-top{display:flex;align-items:center;gap:13px;margin-bottom:20px}.file-icon{width:45px;height:49px;display:grid;place-items:center;border-radius:12px;background:#eef0ff;color:#6472e9;font-size:20px}.active-info{flex:1}.active-info>span{color:#6674df;font-size:9px;font-weight:700}.active-info h2{margin:5px 0;color:#36415d;font-size:15px}.active-info p{margin:0;color:#8c96aa;font-size:9px}.active-top>strong{color:#5362de;font-size:30px}.active-top>strong small{font-size:13px}.stage-list{display:grid;grid-template-columns:repeat(6,1fr);margin:23px 0 19px}.stage-list>div{position:relative;display:flex;align-items:center;flex-direction:column;color:#a0a8b8}.stage-list>div::after{content:"";position:absolute;left:60%;right:-40%;top:12px;height:2px;background:#e5e8ef}.stage-list>div:last-child::after{display:none}.stage-list span{position:relative;z-index:1;width:25px;height:25px;display:grid;place-items:center;border:2px solid #dfe3eb;border-radius:50%;background:#fff}.stage-list span i{width:5px;height:5px;border-radius:50%;background:#b3bac8}.stage-list b{margin-top:8px;font-size:9px}.stage-list .done span{border-color:#16a98d;background:#16a98d}.stage-list .done span i{background:white}.stage-list .done::after{background:#6fd2c0}.stage-list .active span{border-color:#6574eb;box-shadow:0 0 0 5px #edf0ff}.stage-list .active span i{background:#6271e8}.stage-list .active b{color:#5362dd}.task-detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:13px;border-radius:12px;background:#f3f5fb}.task-detail-grid p{display:flex;min-width:0;flex-direction:column;gap:5px;margin:0;color:#8b95a9;font-size:9px}.task-detail-grid b{overflow-wrap:anywhere;color:#4d5872;font-size:10px}.inner-alert{margin-top:14px}.table-card{margin-top:18px}.document-cell{display:flex;align-items:center;gap:10px}.document-cell>span{width:34px;height:38px;display:grid;place-items:center;border-radius:8px;background:#fff0ed;color:#d96857;font-size:7px;font-weight:800}.document-cell>div{display:flex;flex-direction:column}.document-cell b{font-size:10px;color:#424d67}.document-cell small{margin-top:4px;color:#979faf;font-size:8px}@media(max-width:800px){.selector-card{align-items:stretch;flex-direction:column}.stage-list{grid-template-columns:repeat(3,1fr);gap:12px}.stage-list>div::after{display:none}.task-detail-grid{grid-template-columns:1fr 1fr}.active-info p{display:none}.active-top>strong{font-size:22px}}@media(max-width:520px){.stage-list,.task-detail-grid{grid-template-columns:1fr}.stage-list>div{align-items:flex-start}.active-task{padding:18px}}
</style>
