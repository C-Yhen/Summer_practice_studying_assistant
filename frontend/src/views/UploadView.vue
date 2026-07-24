<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import JSZip from 'jszip'
import { ElMessage, type UploadFile, type UploadFiles, type UploadUserFile } from 'element-plus'
import {
  Check,
  CircleCheck,
  Close,
  Document,
  DocumentAdd,
  FolderOpened,
  Lock,
  Refresh,
  UploadFilled,
} from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi, documentApi } from '@/api/services'
import type { CourseListItem } from '@/types'

const ACCEPTED_EXTENSIONS = new Set(['pdf', 'txt', 'md', 'markdown'])
const MAX_FILE_BYTES = 10 * 1024 * 1024

type QueueStatus = 'waiting' | 'uploading' | 'success' | 'failed'

interface UploadQueueItem {
  id: string
  file: File
  displayName: string
  source: 'file' | 'zip'
  status: QueueStatus
  progress: number
  error: string
  documentId?: number
  taskId?: string
}

const route = useRoute()
const router = useRouter()
const courseId = ref<number | null>(null)
const courses = ref<CourseListItem[]>([])
const coursesLoading = ref(false)
const coursesError = ref('')
const pickerFiles = ref<UploadUserFile[]>([])
const queue = ref<UploadQueueItem[]>([])
const preparing = ref(false)
const uploading = ref(false)

const selectedCourse = computed(() => courses.value.find((course) => course.id === courseId.value) ?? null)
const pendingItems = computed(() => queue.value.filter((item) => item.status === 'waiting' || item.status === 'failed'))
const successItems = computed(() => queue.value.filter((item) => item.status === 'success'))
const failedItems = computed(() => queue.value.filter((item) => item.status === 'failed'))
const zipItems = computed(() => queue.value.filter((item) => item.source === 'zip').length)
const totalSize = computed(() => queue.value.reduce((sum, item) => sum + item.file.size, 0))
const overallProgress = computed(() => {
  if (!queue.value.length) return 0
  return Math.round(queue.value.reduce((sum, item) => sum + item.progress, 0) / queue.value.length)
})
const canSubmit = computed(() => (
  courseId.value !== null
  && pendingItems.value.length > 0
  && !coursesLoading.value
  && !preparing.value
  && !uploading.value
))

function queryId(value: unknown): { present: boolean; id: number | null } {
  if (value === undefined) return { present: false, id: null }
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return { present: true, id: Number.isInteger(parsed) && parsed > 0 ? parsed : null }
}

function uploadErrorMessage(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

function extensionOf(name: string) {
  return name.split('.').pop()?.toLowerCase() || ''
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function makeQueueId(file: File, displayName: string) {
  return `${displayName}:${file.size}:${file.lastModified}`
}

function validateDocument(file: File): string | null {
  if (!ACCEPTED_EXTENSIONS.has(extensionOf(file.name))) return '格式不受支持'
  if (file.size === 0) return '文件为空'
  if (file.size > MAX_FILE_BYTES) return '超过单文件 10 MB 限制'
  return null
}

function addDocument(file: File, displayName = file.name, source: UploadQueueItem['source'] = 'file') {
  const validationError = validateDocument(file)
  if (validationError) return { added: false, reason: `${displayName}：${validationError}` }
  const id = makeQueueId(file, displayName)
  if (queue.value.some((item) => item.id === id)) return { added: false, reason: `${displayName}：已在队列中` }
  queue.value.push({ id, file, displayName, source, status: 'waiting', progress: 0, error: '' })
  return { added: true, reason: '' }
}

async function extractZip(file: File) {
  const zip = await JSZip.loadAsync(file)
  const entries = Object.values(zip.files).filter((entry) => !entry.dir && ACCEPTED_EXTENSIONS.has(extensionOf(entry.name)))
  let added = 0
  const skipped: string[] = []

  for (const entry of entries) {
    const blob = await entry.async('blob')
    const name = entry.name.split('/').pop() || entry.name
    const extracted = new File([blob], name, { type: blob.type, lastModified: file.lastModified })
    const result = addDocument(extracted, entry.name, 'zip')
    if (result.added) added += 1
    else skipped.push(result.reason)
  }

  if (!entries.length) throw new Error('压缩包中没有 PDF、TXT 或 Markdown 文件')
  return { added, skipped }
}

async function addFiles(files: File[]) {
  if (!files.length) return
  preparing.value = true
  let added = 0
  const skipped: string[] = []
  try {
    for (const file of files) {
      if (extensionOf(file.name) === 'zip') {
        try {
          const result = await extractZip(file)
          added += result.added
          skipped.push(...result.skipped)
        } catch (error) {
          skipped.push(`${file.name}：${error instanceof Error ? error.message : '无法读取压缩包'}`)
        }
      } else {
        const result = addDocument(file)
        if (result.added) added += 1
        else skipped.push(result.reason)
      }
    }
    if (added) ElMessage.success(`已加入 ${added} 个文档`)
    if (skipped.length) ElMessage.warning(skipped.length === 1 ? skipped[0] : `有 ${skipped.length} 个文件未加入队列`)
  } finally {
    pickerFiles.value = []
    preparing.value = false
  }
}

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = ''
  try {
    const result = await courseApi.list()
    courses.value = result.items.filter((course) => !course.archived)
    const requested = queryId(route.query.courseId)
    if (requested.present && (requested.id === null || !courses.value.some((course) => course.id === requested.id))) {
      courseId.value = null
      coursesError.value = 'URL 中的课程不存在、不属于当前账号或已归档'
      return
    }
    if (requested.id) courseId.value = requested.id
    else if (!requested.present) courseId.value = null
    else if (courseId.value && !courses.value.some((course) => course.id === courseId.value)) courseId.value = null
  } catch (error) {
    courses.value = []
    courseId.value = null
    coursesError.value = uploadErrorMessage(error, '课程加载失败')
  } finally {
    coursesLoading.value = false
  }
}

async function handleChange(_file: UploadFile, files: UploadFiles) {
  const rawFiles = files.flatMap((item) => item.raw ? [item.raw] : [])
  await addFiles(rawFiles)
}

function removeItem(id: string) {
  if (uploading.value) return
  queue.value = queue.value.filter((item) => item.id !== id)
}

function clearCompleted() {
  queue.value = queue.value.filter((item) => item.status !== 'success')
}

function retryItem(item: UploadQueueItem) {
  item.status = 'waiting'
  item.progress = 0
  item.error = ''
}

async function startUpload() {
  if (uploading.value) return
  if (courseId.value === null) return ElMessage.warning('请先选择资料归属课程')
  if (!pendingItems.value.length) return ElMessage.warning('请先添加文档或压缩包')

  uploading.value = true
  const targets = [...pendingItems.value]
  for (const item of targets) {
    item.status = 'uploading'
    item.progress = 20
    item.error = ''
    try {
      const result = await documentApi.upload(courseId.value, item.file, item.displayName)
      item.status = 'success'
      item.progress = 100
      item.documentId = result.document.id
      item.taskId = result.async_task_id
    } catch (error) {
      item.status = 'failed'
      item.progress = 0
      item.error = uploadErrorMessage(error, '上传失败')
    }
  }
  uploading.value = false

  if (failedItems.value.length) ElMessage.warning(`上传完成：${successItems.value.length} 个成功，${failedItems.value.length} 个失败`)
  else ElMessage.success(`${successItems.value.length} 个文档已提交解析`)
}

function openTask(item: UploadQueueItem) {
  if (!item.documentId || !item.taskId) return
  router.push({
    name: 'document-tasks',
    query: { courseId: String(courseId.value), documentId: String(item.documentId), taskId: item.taskId },
  })
}

function openProgress() {
  router.push({ name: 'document-tasks', query: courseId.value ? { courseId: String(courseId.value) } : {} })
}

async function selectCourse(value: number) {
  await router.replace({ name: 'upload', query: { courseId: String(value) } })
}

watch(() => route.query.courseId, () => void loadCourses(), { immediate: true })
</script>

<template>
  <div>
    <PageHeader title="添加课程资料" description="一次添加多份讲义、笔记或 ZIP 资料包，系统会逐份解析并纳入所选课程。">
      <el-button plain @click="openProgress">查看全部处理记录</el-button>
    </PageHeader>

    <section class="upload-layout">
      <article class="content-card upload-main">
        <div class="section-head">
          <div>
            <span class="step-label">步骤 1</span>
            <h2>选择归属课程</h2>
            <p>后续问答、练习与学习计划都会使用这门课的资料。</p>
          </div>
          <div v-if="selectedCourse" class="course-chip" :style="{ '--course-color': selectedCourse.color }">
            <span></span>{{ selectedCourse.name }}
          </div>
        </div>

        <div class="section-body course-section">
          <el-alert v-if="coursesError" :title="coursesError" type="error" :closable="false" show-icon class="state-alert">
            <template #default><el-button size="small" @click="loadCourses">重新加载</el-button></template>
          </el-alert>
          <el-empty v-else-if="!coursesLoading && !courses.length" description="还没有可用课程" class="course-empty">
            <el-button type="primary" @click="router.push('/courses')">先创建课程</el-button>
          </el-empty>
          <el-select
            v-else
            :model-value="courseId"
            :loading="coursesLoading"
            placeholder="选择一门课程"
            :disabled="uploading"
            class="course-select"
            @change="selectCourse"
          >
            <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" />
          </el-select>
        </div>

        <div class="section-divider"></div>

        <div class="section-head">
          <div>
            <span class="step-label">步骤 2</span>
            <h2>添加文档或资料包</h2>
            <p>可多选文件；ZIP 会在本地展开，仅加入其中支持的文档。</p>
          </div>
          <el-tag effect="plain" type="info">单个文档 ≤ 10 MB</el-tag>
        </div>

        <div class="section-body">
          <el-upload
            v-model:file-list="pickerFiles"
            drag
            multiple
            :auto-upload="false"
            :show-file-list="false"
            :disabled="uploading || preparing"
            accept=".pdf,.txt,.md,.markdown,.zip"
            :on-change="handleChange"
            class="upload-zone"
          >
            <div class="upload-illustration"><el-icon><UploadFilled /></el-icon></div>
            <h3>{{ preparing ? '正在读取资料包…' : '拖拽文件到这里' }}</h3>
            <p>或点击选择多份 PDF、TXT、Markdown 与 ZIP 文件</p>
            <el-button type="primary" plain :loading="preparing">选择本地文件</el-button>
          </el-upload>

          <div v-if="queue.length" class="queue-block">
            <div class="queue-head">
              <div>
                <h3>待处理资料</h3>
                <p>{{ queue.length }} 个文档 · {{ formatBytes(totalSize) }}<span v-if="zipItems"> · {{ zipItems }} 个来自 ZIP</span></p>
              </div>
              <el-button v-if="successItems.length && !uploading" text @click="clearCompleted">清除已完成</el-button>
            </div>

            <div class="queue-list">
              <div v-for="item in queue" :key="item.id" class="queue-item" :class="`is-${item.status}`">
                <span class="file-icon"><el-icon><Document /></el-icon></span>
                <div class="file-main">
                  <div class="file-title">
                    <b :title="item.displayName">{{ item.displayName }}</b>
                    <span v-if="item.source === 'zip'" class="source-mark"><el-icon><FolderOpened /></el-icon>ZIP</span>
                  </div>
                  <p>
                    {{ extensionOf(item.file.name).toUpperCase() }} · {{ formatBytes(item.file.size) }}
                    <template v-if="item.status === 'waiting'"> · 等待上传</template>
                    <template v-else-if="item.status === 'uploading'"> · 正在提交解析任务</template>
                    <template v-else-if="item.status === 'success'"> · 已提交，后台解析中</template>
                    <template v-else> · {{ item.error }}</template>
                  </p>
                  <el-progress v-if="item.status === 'uploading'" :percentage="item.progress" :show-text="false" :stroke-width="4" />
                </div>
                <div class="file-actions">
                  <span v-if="item.status === 'success'" class="success-state"><el-icon><CircleCheck /></el-icon>已提交</span>
                  <el-button v-if="item.status === 'success'" size="small" text @click="openTask(item)">查看</el-button>
                  <el-button v-else-if="item.status === 'failed'" size="small" text @click="retryItem(item)"><el-icon><Refresh /></el-icon>重试</el-button>
                  <el-button v-if="item.status !== 'uploading' && item.status !== 'success'" circle text :icon="Close" aria-label="移除文件" @click="removeItem(item.id)" />
                </div>
              </div>
            </div>
          </div>

          <div v-else class="queue-empty">
            <el-icon><DocumentAdd /></el-icon>
            <span>添加后可在这里核对每一份文档</span>
          </div>
        </div>

        <footer class="submit-row">
          <div>
            <p><el-icon><Lock /></el-icon>资料仅归属于当前账号与所选课程</p>
            <el-progress v-if="uploading" :percentage="overallProgress" :stroke-width="5" :show-text="false" />
          </div>
          <el-button type="primary" size="large" :loading="uploading" :disabled="!canSubmit" @click="startUpload">
            <el-icon><DocumentAdd /></el-icon>{{ failedItems.length ? '重试失败项' : `上传 ${pendingItems.length || ''} 份资料` }}
          </el-button>
        </footer>
      </article>

      <aside class="upload-aside">
        <article class="content-card card-pad context-card">
          <span class="aside-label">上传后可以</span>
          <h2>围绕课程资料持续学习</h2>
          <div class="benefit-list">
            <div><span>1</span><p><b>让 AI 有据可查</b><small>回答会优先检索已解析的课程资料。</small></p></div>
            <div><span>2</span><p><b>生成针对性练习</b><small>从真实知识点与薄弱项组织题目。</small></p></div>
            <div><span>3</span><p><b>更新学习计划</b><small>新资料会进入后续计划生成上下文。</small></p></div>
          </div>
        </article>

        <article class="content-card card-pad pipeline-card">
          <div class="card-header"><div><h2>系统处理流程</h2><p>每份文档都有独立状态</p></div></div>
          <div class="pipeline">
            <div v-for="(step,index) in ['权限与文件校验','提取和清洗文本','按语义生成片段','建立课程检索索引']" :key="step">
              <span><el-icon><Check /></el-icon></span>
              <p><b>{{ step }}</b><small>{{ ['确认课程归属、格式和大小','读取 PDF 页或文本内容','保留可引用的来源边界','供问答、练习与计划调用'][index] }}</small></p>
            </div>
          </div>
        </article>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.upload-layout{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:20px;align-items:start}.upload-main{overflow:hidden}.section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:24px 26px 0}.section-head h2{margin:6px 0 5px;color:#26324a;font-size:17px}.section-head p{margin:0;color:#7c879b;font-size:11px;line-height:1.65}.step-label,.aside-label{color:#5c6cec;font-size:9px;font-weight:800}.section-body{padding:18px 26px 26px}.course-section{padding-top:14px}.section-divider{height:1px;margin:0 26px;background:#edf0f4}.course-select{width:100%}.course-chip{display:flex;align-items:center;gap:7px;min-width:0;padding:7px 10px;border:1px solid #e5e9f0;border-radius:7px;color:#59657c;background:#fff;font-size:10px;font-weight:700}.course-chip span{width:8px;height:8px;flex:none;border-radius:2px;background:var(--course-color,#5c6cec)}.state-alert{margin-bottom:4px}.state-alert :deep(.el-alert__content){width:100%}.state-alert :deep(.el-alert__description){display:flex;justify-content:flex-end;margin:0}.course-empty{min-height:180px}.upload-zone{width:100%}:deep(.el-upload){width:100%}:deep(.el-upload-dragger){width:100%;padding:30px 20px;border:1.5px dashed #cbd3e2;border-radius:8px;background:#fafbfe}:deep(.el-upload-dragger:hover){border-color:#7885ed;background:#f8f8ff}.upload-illustration{width:46px;height:46px;display:grid;place-items:center;margin:0 auto 11px;border-radius:8px;background:#ecefff;color:#6170e9;font-size:21px}.upload-zone h3{margin:0;color:#3f4b63;font-size:13px}.upload-zone p{margin:7px 0 14px;color:#8d97a9;font-size:9px}.queue-block{margin-top:18px;border:1px solid #e7eaf0;border-radius:8px;overflow:hidden}.queue-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 15px;background:#fafbfc;border-bottom:1px solid #edf0f4}.queue-head h3{margin:0;color:#39455d;font-size:11px}.queue-head p{margin:4px 0 0;color:#8d97a9;font-size:9px}.queue-list{max-height:330px;overflow:auto}.queue-item{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:11px;min-height:66px;padding:11px 13px;border-bottom:1px solid #edf0f4}.queue-item:last-child{border-bottom:0}.queue-item.is-failed{background:#fffafa}.file-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:7px;background:#f0f2f8;color:#68758c;font-size:16px}.is-success .file-icon{background:#eaf8f4;color:#15977e}.is-failed .file-icon{background:#fff0f0;color:#d65f66}.file-main{min-width:0}.file-title{display:flex;align-items:center;gap:8px;min-width:0}.file-title b{overflow:hidden;color:#46526a;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.source-mark{display:inline-flex;align-items:center;gap:3px;flex:none;color:#6e79cc;font-size:8px;font-weight:800}.file-main p{overflow:hidden;margin:4px 0 0;color:#919bad;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.file-main :deep(.el-progress){margin-top:8px}.file-actions{display:flex;align-items:center;gap:4px}.success-state{display:inline-flex;align-items:center;gap:4px;color:#15977e;font-size:9px;font-weight:700}.queue-empty{display:flex;align-items:center;justify-content:center;gap:7px;height:52px;margin-top:14px;border:1px dashed #e1e5ec;border-radius:8px;color:#9aa3b3;font-size:9px}.submit-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 26px;background:#fafbfc;border-top:1px solid #edf0f4}.submit-row>div{min-width:180px}.submit-row p{display:flex;align-items:center;gap:6px;margin:0;color:#828da1;font-size:9px}.submit-row :deep(.el-progress){margin-top:9px}.upload-aside{display:grid;gap:16px}.context-card{background:#2d374d;border-color:#2d374d;color:#fff}.context-card .aside-label{color:#aeb8ff}.context-card h2{margin:8px 0 20px;font-size:16px}.benefit-list{display:grid;gap:17px}.benefit-list>div{display:flex;gap:11px}.benefit-list>div>span{width:24px;height:24px;display:grid;place-items:center;flex:none;border:1px solid #59657d;border-radius:6px;color:#b8c0ff;font-size:9px;font-weight:800}.benefit-list p{display:flex;flex-direction:column;margin:0}.benefit-list b{font-size:10px}.benefit-list small{margin-top:4px;color:#b9c1d1;font-size:8px;line-height:1.55}.pipeline{display:grid;gap:14px}.pipeline>div{display:flex;gap:10px}.pipeline>div>span{width:25px;height:25px;display:grid;place-items:center;flex:none;border-radius:6px;background:#ebf8f5;color:#14a187;font-size:11px}.pipeline p{display:flex;flex-direction:column;margin:0}.pipeline b{color:#4b5670;font-size:10px}.pipeline small{margin-top:4px;color:#959daf;font-size:8px;line-height:1.4}@media(max-width:1000px){.upload-layout{grid-template-columns:1fr}.upload-aside{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.section-head{padding:20px 18px 0}.section-body{padding:16px 18px 22px}.section-divider{margin:0 18px}.section-head{flex-direction:column}.course-chip{max-width:100%}.queue-item{grid-template-columns:34px minmax(0,1fr)}.file-actions{grid-column:2;justify-content:flex-start}.submit-row{align-items:stretch;flex-direction:column;padding:17px 18px}.submit-row .el-button{width:100%}.upload-aside{grid-template-columns:1fr}}
</style>