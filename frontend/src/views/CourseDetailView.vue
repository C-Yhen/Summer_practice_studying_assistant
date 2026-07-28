<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ChatDotRound, Delete, Edit, Refresh, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import EChart from '@/components/EChart.vue'
import StatusPill from '@/components/StatusPill.vue'
import { ApiEnvelopeError, getApiErrorMessage, isApiError, isUnauthorizedError } from '@/api/client'
import { dashboardApi } from '@/api/dashboard'
import { courseApi, documentApi, learningApi } from '@/api/services'
import type {
  BackendDocument,
  CourseListItem,
  DashboardOverview,
  KnowledgeMasteryItem,
  LearningRecordItem,
} from '@/types'

type ViewState = 'loading' | 'ready' | 'invalid-id' | 'not-found' | 'error'

const route = useRoute()
const router = useRouter()
const tab = ref('overview')
const state = ref<ViewState>('loading')
const pageError = ref('')
const course = ref<CourseListItem | null>(null)
const overview = ref<DashboardOverview | null>(null)
const overviewLoading = ref(false)
const overviewError = ref('')
const documents = ref<BackendDocument[]>([])
const documentsLoading = ref(false)
const documentsError = ref('')
const mastery = ref<KnowledgeMasteryItem[]>([])
const masteryLoading = ref(false)
const masteryError = ref('')
const records = ref<LearningRecordItem[]>([])
const recordsLoading = ref(false)
const recordsError = ref('')
const editVisible = ref(false)
const saving = ref(false)
const archiving = ref(false)
const reparsingId = ref<number | null>(null)
const resolvingTaskId = ref<number | null>(null)
let loadVersion = 0

const editForm = reactive({
  name: '',
  code: '',
  description: '',
  examDate: '',
  targetScore: 85,
  color: '#5b6cf9',
})

function localDate() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function routeCourseId(): number | null {
  const raw = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id
  if (typeof raw !== 'string' || !/^[1-9]\d*$/.test(raw)) return null
  const id = Number(raw)
  return Number.isSafeInteger(id) ? id : null
}

function errorMessage(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

function isNotFound(error: unknown) {
  return isApiError(error, 404)
    || (error instanceof ApiEnvelopeError && error.code === 404)
}

async function loadOverview(courseId: number, version = loadVersion) {
  overviewLoading.value = true
  overviewError.value = ''
  try {
    const result = await dashboardApi.getOverview({ target_date: localDate(), days: 7, course_id: courseId })
    if (version === loadVersion && course.value?.id === courseId) overview.value = result
  } catch (error) {
    if (version === loadVersion && course.value?.id === courseId) {
      overview.value = null
      overviewError.value = errorMessage(error, '课程概览加载失败')
    }
  } finally {
    if (version === loadVersion && course.value?.id === courseId) overviewLoading.value = false
  }
}

async function loadDocuments(courseId: number, version = loadVersion) {
  documentsLoading.value = true
  documentsError.value = ''
  try {
    const result = await documentApi.list(courseId)
    if (version === loadVersion && course.value?.id === courseId) documents.value = result.items
  } catch (error) {
    if (version === loadVersion && course.value?.id === courseId) {
      documents.value = []
      documentsError.value = errorMessage(error, '课程资料加载失败')
    }
  } finally {
    if (version === loadVersion && course.value?.id === courseId) documentsLoading.value = false
  }
}

async function loadMastery(courseId: number, version = loadVersion) {
  masteryLoading.value = true
  masteryError.value = ''
  try {
    const result = await learningApi.getMastery(courseId)
    if (version === loadVersion && course.value?.id === courseId) mastery.value = result.items
  } catch (error) {
    if (version === loadVersion && course.value?.id === courseId) {
      mastery.value = []
      masteryError.value = errorMessage(error, '掌握度加载失败')
    }
  } finally {
    if (version === loadVersion && course.value?.id === courseId) masteryLoading.value = false
  }
}

async function loadRecords(courseId: number, version = loadVersion) {
  recordsLoading.value = true
  recordsError.value = ''
  try {
    const result = await learningApi.getRecords(courseId)
    if (version === loadVersion && course.value?.id === courseId) records.value = result.items
  } catch (error) {
    if (version === loadVersion && course.value?.id === courseId) {
      records.value = []
      recordsError.value = errorMessage(error, '学习记录加载失败')
    }
  } finally {
    if (version === loadVersion && course.value?.id === courseId) recordsLoading.value = false
  }
}

async function loadCourse() {
  const version = ++loadVersion
  state.value = 'loading'
  pageError.value = ''
  course.value = null
  overview.value = null
  documents.value = []
  mastery.value = []
  records.value = []
  overviewError.value = documentsError.value = masteryError.value = recordsError.value = ''
  const courseId = routeCourseId()
  if (courseId === null) {
    state.value = 'invalid-id'
    return
  }
  try {
    const result = await courseApi.get(courseId)
    if (version !== loadVersion) return
    course.value = result
    state.value = 'ready'
    await Promise.all([
      loadOverview(courseId, version),
      loadDocuments(courseId, version),
      loadMastery(courseId, version),
      loadRecords(courseId, version),
    ])
  } catch (error) {
    if (version !== loadVersion) return
    state.value = isNotFound(error) ? 'not-found' : 'error'
    pageError.value = isNotFound(error)
      ? '课程不存在或无权访问'
      : errorMessage(error, '课程详情加载失败')
  }
}

const sortedMastery = computed(() => [...mastery.value].sort((left, right) => {
  if (!left.has_record && right.has_record) return 1
  if (left.has_record && !right.has_record) return -1
  return (left.score ?? 1) - (right.score ?? 1)
}))
const completionPercent = computed(() => Math.round((overview.value?.today.completion_rate ?? 0) * 100))
const trendOption = computed<EChartsOption>(() => ({
  color: ['#6675ed', '#17a78c'],
  tooltip: { trigger: 'axis' },
  grid: { top: 24, right: 18, bottom: 8, left: 10, containLabel: true },
  xAxis: { type: 'category', data: overview.value?.trend.map((item) => item.label) ?? [] },
  yAxis: [
    { type: 'value', min: 0, axisLabel: { formatter: '{value}m' } },
    { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
  ],
  series: [
    { name: '学习时长', type: 'bar', data: overview.value?.trend.map((item) => item.learning_minutes) ?? [] },
    { name: '任务完成率', type: 'line', yAxisIndex: 1, smooth: true, data: overview.value?.trend.map((item) => Math.round(item.completion_rate * 100)) ?? [] },
  ],
}))

function examSummary() {
  if (!course.value?.examDate) return '尚未设置考试日期'
  const exam = new Date(`${course.value.examDate}T00:00:00`)
  const today = new Date(`${localDate()}T00:00:00`)
  const days = Math.round((exam.getTime() - today.getTime()) / 86400000)
  if (days > 0) return `距离考试还有 ${days} 天`
  if (days === 0) return '考试日期为今天'
  return '考试日期已过'
}

function contextRoute(path: string) {
  return course.value ? { path, query: { courseId: String(course.value.id) } } : path
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function openEdit() {
  if (!course.value) return
  editForm.name = course.value.name
  editForm.code = course.value.code || ''
  editForm.description = course.value.description || ''
  editForm.examDate = course.value.examDate || ''
  editForm.targetScore = course.value.targetScore
  editForm.color = course.value.color
  editVisible.value = true
}

async function saveCourse() {
  if (!course.value || saving.value) return
  const name = editForm.name.trim()
  if (!name) return ElMessage.warning('课程名称不能为空')
  saving.value = true
  try {
    course.value = await courseApi.update(course.value.id, {
      name,
      code: editForm.code.trim() || null,
      description: editForm.description.trim() || null,
      exam_date: editForm.examDate || null,
      target_score: editForm.targetScore,
      color: editForm.color || null,
    })
    editVisible.value = false
    ElMessage.success('课程信息已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '课程修改失败'))
  } finally {
    saving.value = false
  }
}

async function archiveCourse() {
  if (!course.value || archiving.value) return
  try {
    await ElMessageBox.confirm(
      '归档后，该课程不会出现在默认课程列表中。本轮不提供归档恢复页面。',
      '归档课程',
      { confirmButtonText: '确认归档', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  archiving.value = true
  try {
    await courseApi.archive(course.value.id)
    ElMessage.success('课程已归档')
    await router.replace('/courses')
  } catch (error) {
    ElMessage.error(errorMessage(error, '课程归档失败'))
  } finally {
    archiving.value = false
  }
}

async function viewDocumentStatus(document: BackendDocument) {
  if (!course.value || resolvingTaskId.value !== null) return
  resolvingTaskId.value = document.id
  try {
    const task = await documentApi.getLatestTask(document.id)
    await router.push({
      name: 'document-tasks',
      query: { courseId: String(course.value.id), documentId: String(document.id), taskId: task.task_id },
    })
  } catch (error) {
    ElMessage.error(errorMessage(error, '找不到该文档的处理任务'))
  } finally {
    resolvingTaskId.value = null
  }
}

async function reparseDocument(document: BackendDocument) {
  if (!course.value || reparsingId.value !== null) return
  try {
    await ElMessageBox.confirm(
      `将为“${document.title}”创建新版本并重新解析，是否继续？`,
      '重新解析资料',
      { confirmButtonText: '重新解析', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  reparsingId.value = document.id
  try {
    const result = await documentApi.reparse(document.id)
    await router.push({
      name: 'document-tasks',
      query: {
        courseId: String(course.value.id),
        documentId: String(document.id),
        taskId: result.async_task_id,
      },
    })
  } catch (error) {
    ElMessage.error(errorMessage(error, '重新解析失败'))
  } finally {
    reparsingId.value = null
  }
}

watch(() => route.params.id, () => void loadCourse(), { immediate: true })
</script>

<template>
  <div>
    <PageHeader :title="course?.name || '课程详情'" eyebrow="课程空间" description="集中查看这门课程的资料、计划、掌握情况和学习记录。">
      <el-button plain @click="router.push('/courses')"><el-icon><ArrowLeft /></el-icon>返回课程</el-button>
    </PageHeader>

    <div v-if="state === 'loading'" v-loading="true" class="page-loading"></div>
    <el-result v-else-if="state === 'invalid-id'" icon="warning" title="无效的课程地址" sub-title="课程 ID 必须是正整数。"><template #extra><el-button type="primary" @click="router.push('/courses')">返回课程列表</el-button></template></el-result>
    <el-result v-else-if="state === 'not-found'" icon="error" title="课程不存在或无权访问" sub-title="该课程可能不存在、已归档，或不属于当前账号。"><template #extra><el-button type="primary" @click="router.push('/courses')">返回课程列表</el-button></template></el-result>
    <el-result v-else-if="state === 'error'" icon="error" title="课程详情加载失败" :sub-title="pageError"><template #extra><el-button type="primary" @click="loadCourse">重新加载</el-button></template></el-result>

    <template v-else-if="course">
      <section class="course-hero" :style="{ '--course-color': course.color }">
        <div class="course-identity"><span>{{ course.name.slice(0, 1) }}</span><div><small>{{ course.code || '未设置课程编号' }}</small><h1>{{ course.name }}</h1><p>{{ course.description || '暂无课程说明' }}</p></div></div>
        <div class="hero-stat"><strong>{{ course.targetScore }}</strong><span>目标成绩</span></div>
        <div class="hero-stat"><strong>{{ overview?.ready_document_count ?? '--' }}</strong><span>就绪资料</span></div>
        <div class="hero-stat"><strong>{{ overview?.metrics.average_mastery === null || !overview ? '--' : `${Math.round(overview.metrics.average_mastery * 100)}%` }}</strong><span>平均掌握度</span></div>
        <div class="exam-date"><small>考试日期</small><strong>{{ course.examDate || '未设置' }}</strong><span>{{ examSummary() }}</span></div>
      </section>

      <div class="action-row">
        <span>更新于 {{ formatDate(course.updatedAt) }}</span>
        <el-button @click="openEdit"><el-icon><Edit /></el-icon>编辑课程</el-button>
        <el-button @click="router.push(contextRoute('/upload'))"><el-icon><UploadFilled /></el-icon>上传资料</el-button>
        <el-button type="primary" @click="router.push(contextRoute('/chat'))"><el-icon><ChatDotRound /></el-icon>智能问答</el-button>
        <el-button type="danger" plain :loading="archiving" @click="archiveCourse"><el-icon><Delete /></el-icon>归档课程</el-button>
      </div>

      <section class="content-card course-content">
        <el-tabs v-model="tab">
          <el-tab-pane label="课程概览" name="overview">
            <el-alert v-if="overviewError" :title="overviewError" type="error" :closable="false" show-icon><template #default><el-button size="small" @click="loadOverview(course.id)">重试概览</el-button></template></el-alert>
            <div v-if="overviewLoading" v-loading="true" class="module-loading"></div>
            <div v-else-if="overview" class="overview-grid">
              <article class="overview-stats">
                <div><span>今日任务</span><strong>{{ overview.today.completed_count }}/{{ overview.today.total_count }}</strong><small>完成率 {{ completionPercent }}%</small></div>
                <div><span>今日计划</span><strong>{{ overview.today.planned_minutes }} 分钟</strong><small>实际 {{ overview.today.actual_minutes }} 分钟</small></div>
                <div><span>活动计划</span><strong>{{ overview.focus_course?.has_active_plan ? '已生效' : '暂无' }}</strong><small>{{ overview.metrics.study_days_in_range }} 个学习日</small></div>
              </article>
              <article class="trend-card"><div class="card-header"><div><h2>近 7 天学习趋势</h2><p>无数据日期按 0 展示</p></div></div><EChart :option="trendOption" height="260px" /></article>
              <article class="next-card"><span>规则生成的下一步</span><h2>{{ overview.next_action.title }}</h2><p>{{ overview.next_action.reason }}</p><el-button type="primary" @click="router.push(overview.next_action.route)">立即前往</el-button></article>
              <article class="context-card"><div class="card-header"><div><h2>当前课程入口</h2><p>跳转时保留课程 #{{ course.id }}</p></div></div><div><el-button @click="router.push(contextRoute('/plan'))">学习计划</el-button><el-button @click="router.push(contextRoute('/today'))">今日任务</el-button><el-button @click="router.push(contextRoute('/mastery'))">掌握度</el-button><el-button @click="router.push(contextRoute('/upload'))">上传资料</el-button></div></article>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="`课程资料 ${documents.length}`" name="documents">
            <div class="tab-toolbar"><span>只展示当前课程的真实资料</span><el-button :loading="documentsLoading" @click="loadDocuments(course.id)"><el-icon><Refresh /></el-icon>刷新</el-button></div>
            <el-alert v-if="documentsError" :title="documentsError" type="error" :closable="false" show-icon><template #default><el-button size="small" @click="loadDocuments(course.id)">重新加载</el-button></template></el-alert>
            <el-table v-else v-loading="documentsLoading" :data="documents" empty-text="尚未上传课程资料">
              <el-table-column label="资料名称" min-width="220"><template #default="scope"><b>{{ scope.row.title }}</b><small class="cell-sub">{{ scope.row.file_type.toUpperCase() }} · v{{ scope.row.current_version }}</small></template></el-table-column>
              <el-table-column label="状态" width="110"><template #default="scope"><StatusPill :status="scope.row.status" /></template></el-table-column>
              <el-table-column label="页数" width="80"><template #default="scope">{{ scope.row.page_count ?? '—' }}</template></el-table-column>
              <el-table-column label="更新时间" min-width="160"><template #default="scope">{{ formatDate(scope.row.updated_at) }}</template></el-table-column>
              <el-table-column label="错误信息" min-width="170"><template #default="scope">{{ scope.row.error_message || '—' }}</template></el-table-column>
              <el-table-column label="操作" width="190"><template #default="scope"><el-button link type="primary" :loading="resolvingTaskId === scope.row.id" @click="viewDocumentStatus(scope.row)">处理状态</el-button><el-button link :loading="reparsingId === scope.row.id" :disabled="reparsingId !== null" @click="reparseDocument(scope.row)">重新解析</el-button></template></el-table-column>
            </el-table>
            <el-empty v-if="!documentsLoading && !documentsError && !documents.length" description="尚未上传课程资料"><el-button type="primary" @click="router.push(contextRoute('/upload'))">上传资料</el-button></el-empty>
          </el-tab-pane>

          <el-tab-pane :label="`掌握度 ${mastery.length}`" name="mastery">
            <div class="tab-toolbar"><span>未产生学习记录的知识点不显示默认分数</span><el-button :loading="masteryLoading" @click="loadMastery(course.id)"><el-icon><Refresh /></el-icon>刷新</el-button></div>
            <el-alert v-if="masteryError" :title="masteryError" type="error" :closable="false" show-icon><template #default><el-button size="small" @click="loadMastery(course.id)">重新加载</el-button></template></el-alert>
            <el-table v-else v-loading="masteryLoading" :data="sortedMastery" empty-text="当前课程暂无知识点">
              <el-table-column prop="knowledge_point" label="知识点" min-width="180" />
              <el-table-column label="掌握度" min-width="180"><template #default="scope"><template v-if="scope.row.has_record"><el-progress :percentage="Math.round(scope.row.score * 100)" :stroke-width="7" /><small class="cell-sub">置信度 {{ Math.round(scope.row.confidence * 100) }}%</small></template><span v-else>--</span></template></el-table-column>
              <el-table-column label="练习次数" width="120"><template #default="scope">{{ scope.row.attempts || '尚无学习记录' }}</template></el-table-column>
              <el-table-column label="趋势" width="120"><template #default="scope">{{ scope.row.trend || '暂无趋势' }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="`学习记录 ${records.length}`" name="records">
            <div class="tab-toolbar"><span>真实学习时长与关联任务</span><el-button :loading="recordsLoading" @click="loadRecords(course.id)"><el-icon><Refresh /></el-icon>刷新</el-button></div>
            <el-alert v-if="recordsError" :title="recordsError" type="error" :closable="false" show-icon><template #default><el-button size="small" @click="loadRecords(course.id)">重新加载</el-button></template></el-alert>
            <el-table v-else v-loading="recordsLoading" :data="records" empty-text="当前课程暂无学习记录">
              <el-table-column prop="record_type" label="类型" width="120" />
              <el-table-column label="实际时长" width="120"><template #default="scope">{{ Math.round(scope.row.duration_seconds / 60) }} 分钟</template></el-table-column>
              <el-table-column label="关联任务" min-width="190"><template #default="scope">{{ scope.row.task_title || (scope.row.task_id ? `任务 #${scope.row.task_id}` : '—') }}</template></el-table-column>
              <el-table-column label="知识点" min-width="150"><template #default="scope">{{ scope.row.knowledge_point || '—' }}</template></el-table-column>
              <el-table-column label="状态" width="100"><template #default="scope">{{ scope.row.completed ? '已完成' : '未完成' }}</template></el-table-column>
              <el-table-column label="发生时间" min-width="170"><template #default="scope">{{ formatDate(scope.row.occurred_at) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </section>

      <el-dialog v-model="editVisible" title="编辑课程" width="min(560px, 92vw)" :close-on-click-modal="!saving">
        <el-form label-position="top">
          <el-form-item label="课程名称（必填）"><el-input v-model="editForm.name" maxlength="160" /></el-form-item>
          <div class="form-grid"><el-form-item label="课程编号"><el-input v-model="editForm.code" maxlength="50" /></el-form-item><el-form-item label="目标成绩"><el-input-number v-model="editForm.targetScore" :min="0" :max="100" style="width:100%" /></el-form-item></div>
          <el-form-item label="课程说明"><el-input v-model="editForm.description" type="textarea" :rows="3" maxlength="5000" /></el-form-item>
          <div class="form-grid"><el-form-item label="考试日期"><el-date-picker v-model="editForm.examDate" type="date" value-format="YYYY-MM-DD" clearable style="width:100%" /></el-form-item><el-form-item label="课程颜色"><el-color-picker v-model="editForm.color" /></el-form-item></div>
        </el-form>
        <template #footer><el-button :disabled="saving" @click="editVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveCourse">保存修改</el-button></template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
.page-loading{min-height:440px}.course-hero{--course-color:#5b6cf9;display:flex;align-items:center;gap:26px;padding:25px 28px;border-radius:19px;background:linear-gradient(115deg,#111f45,color-mix(in srgb,var(--course-color),#111f45 62%));color:white}.course-identity{display:flex;align-items:center;gap:16px;min-width:300px;margin-right:auto}.course-identity>span{width:58px;height:58px;display:grid;place-items:center;flex:none;border-radius:17px;background:var(--course-color);font-size:24px;font-weight:750}.course-identity small,.exam-date small{color:#aab4cb;font-size:9px}.course-identity h1{margin:5px 0;font-size:20px}.course-identity p{max-width:420px;margin:0;color:#aeb8cf;font-size:9px;line-height:1.6}.hero-stat{display:flex;flex-direction:column;padding-left:20px;border-left:1px solid rgba(255,255,255,.12)}.hero-stat strong{font-size:20px}.hero-stat span{margin-top:5px;color:#a2adc5;font-size:9px}.exam-date{display:flex;flex-direction:column;padding:11px 14px;border:1px solid rgba(255,255,255,.12);border-radius:12px}.exam-date strong{margin:4px 0;font-size:11px}.exam-date span{color:#8edccb;font-size:8px}.action-row{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin:14px 0 18px}.action-row>span{margin-right:auto;color:#8993a7;font-size:9px}.course-content{padding:4px 22px 22px}.module-loading{min-height:300px}.overview-grid{display:grid;grid-template-columns:1.3fr .7fr;gap:16px}.overview-grid>article{padding:18px;border:1px solid #edf0f5;border-radius:14px}.overview-stats{grid-column:span 2;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.overview-stats div{display:flex;flex-direction:column;padding:14px;border-radius:12px;background:#f7f8fc}.overview-stats span{color:#8993a7;font-size:9px}.overview-stats strong{margin:7px 0;color:#34405c;font-size:18px}.overview-stats small{color:#8b95aa;font-size:8px}.trend-card{min-width:0}.next-card{background:#f7f8ff}.next-card>span{color:#6574e8;font-size:9px;font-weight:750}.next-card h2{margin:16px 0 9px;color:#3e4964;font-size:17px}.next-card p{color:#7e889e;font-size:10px;line-height:1.7}.next-card .el-button{width:100%;margin-top:15px}.context-card{grid-column:span 2}.context-card>div:last-child{display:flex;flex-wrap:wrap;gap:8px}.tab-toolbar{display:flex;align-items:center;justify-content:space-between;margin:8px 0 14px;color:#8791a5;font-size:9px}.cell-sub{display:block;margin-top:5px;color:#929bad;font-size:8px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:1100px){.course-hero{flex-wrap:wrap}.course-identity{width:100%}.hero-stat{padding:0;border:0}.overview-grid{grid-template-columns:1fr}.overview-stats,.context-card{grid-column:auto}}@media(max-width:700px){.course-identity{min-width:0}.action-row{align-items:stretch;flex-direction:column}.action-row>span{margin:0}.overview-stats{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr}}
</style>
