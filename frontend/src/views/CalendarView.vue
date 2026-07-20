<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Calendar, Delete, Download, Edit } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import { calendarApi, courseApi, mcpApi } from '@/api/services'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type {
  CalendarEventItem,
  CalendarEventPreview,
  CalendarEventUpdateRequest,
  CalendarPlanSyncPreview,
  CourseListItem,
  MCPToolCallItem,
  MCPToolInfo,
} from '@/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const courses = ref<CourseListItem[]>([])
const events = ref<CalendarEventItem[]>([])
const tools = ref<MCPToolInfo[]>([])
const calls = ref<MCPToolCallItem[]>([])
const weekStart = ref('')
const courseId = ref<number | undefined>()
const timezone = computed(() => auth.user?.timezone || 'UTC')
const calendarError = ref('')
const toolError = ref('')
const auditError = ref('')
const exportError = ref('')
const loadingEvents = ref(false)
const previewingPlan = ref(false)
const confirmingPlan = ref(false)
const exportingIcs = ref(false)
const previewingUpdate = ref(false)
const updatingEvent = ref(false)
const previewingDelete = ref(false)
const deletingEvent = ref(false)
const syncVisible = ref(false)
const detailVisible = ref(false)
const selected = ref<CalendarEventItem | null>(null)
const planPreview = ref<CalendarPlanSyncPreview | null>(null)
const updatePreview = ref<CalendarEventPreview | null>(null)
const deletePreview = ref<CalendarEventPreview | null>(null)
const dailyStart = ref('20:00')
const gap = ref(10)
const editTitle = ref('')
const editStart = ref('')
const editEnd = ref('')
let internalNavigation = false
let requestVersion = 0

function parseDateOnly(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return match ? { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) } : null
}
function formatDateOnly(year: number, month: number, day: number) {
  return [year, month, day].map((value, index) => String(value).padStart(index ? 2 : 4, '0')).join('-')
}
function addDateDays(value: string, amount: number) {
  const parts = parseDateOnly(value)
  if (!parts) return value
  const date = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + amount))
  return formatDateOnly(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate())
}
function mondayOf(value: string) {
  const parts = parseDateOnly(value)
  if (!parts) return value
  const weekday = new Date(Date.UTC(parts.year, parts.month - 1, parts.day)).getUTCDay()
  return addDateDays(value, -((weekday + 6) % 7))
}
function zonedParts(value: Date) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone.value,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value)
  const get = (type: string) => Number(parts.find((item) => item.type === type)?.value || 0)
  return { year: get('year'), month: get('month'), day: get('day'), hour: get('hour'), minute: get('minute'), second: get('second') }
}
function todayInUserZone() {
  const parts = zonedParts(new Date())
  return formatDateOnly(parts.year, parts.month, parts.day)
}
function eventLocal(event: CalendarEventItem) {
  const start = zonedParts(new Date(event.start_at))
  const end = zonedParts(new Date(event.end_at))
  const startDate = formatDateOnly(start.year, start.month, start.day)
  const endDate = formatDateOnly(end.year, end.month, end.day)
  const startTime = `${String(start.hour).padStart(2, '0')}:${String(start.minute).padStart(2, '0')}`
  const endTime = `${String(end.hour).padStart(2, '0')}:${String(end.minute).padStart(2, '0')}`
  return { startDate, endDate, startTime, endTime, range: startDate === endDate ? `${startTime}–${endTime}` : `${startDate} ${startTime} – ${endDate} ${endTime}` }
}
function previewRange(startAt: string, endAt: string) {
  return eventLocal({ start_at: startAt, end_at: endAt } as CalendarEventItem).range
}
function localDateTimeToUtc(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value)
  if (!match) throw new Error('本地日期时间格式无效')
  const desired = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]))
  let guess = desired
  for (let index = 0; index < 4; index += 1) {
    const actual = zonedParts(new Date(guess))
    const represented = Date.UTC(actual.year, actual.month - 1, actual.day, actual.hour, actual.minute, actual.second)
    guess += desired - represented
  }
  const verified = zonedParts(new Date(guess))
  if (
    verified.year !== Number(match[1])
    || verified.month !== Number(match[2])
    || verified.day !== Number(match[3])
    || verified.hour !== Number(match[4])
    || verified.minute !== Number(match[5])
  ) throw new Error('该本地时间在当前时区不存在，请选择其他时间')
  return new Date(guess).toISOString()
}
function toLocalInput(value: string) {
  const parts = zonedParts(new Date(value))
  return `${formatDateOnly(parts.year, parts.month, parts.day)}T${String(parts.hour).padStart(2, '0')}:${String(parts.minute).padStart(2, '0')}`
}

const weekDays = computed(() => Array.from({ length: 7 }, (_, index) => addDateDays(weekStart.value, index)))
const calendarTools = computed(() => tools.value.filter((tool) => ['get_available_time', 'create_calendar_event', 'update_calendar_event', 'delete_calendar_event'].includes(tool.name)))
const operationBusy = computed(() => previewingUpdate.value || updatingEvent.value || previewingDelete.value || deletingEvent.value)

function clearRangeState() {
  events.value = []
  planPreview.value = null
  selected.value = null
  detailVisible.value = false
  updatePreview.value = null
  deletePreview.value = null
  calendarError.value = ''
}
async function initializeFromRoute() {
  if (!courses.value.length) courses.value = (await courseApi.list()).items.filter((course) => !course.archived)
  const rawWeek = String(route.query.weekStart || '')
  weekStart.value = parseDateOnly(rawWeek) ? mondayOf(rawWeek) : mondayOf(todayInUserZone())
  const rawCourse = Number(route.query.courseId)
  courseId.value = courses.value.some((course) => course.id === rawCourse) ? rawCourse : undefined
  const needsNormalize = rawWeek !== weekStart.value || (route.query.courseId && courseId.value === undefined)
  if (needsNormalize) {
    internalNavigation = true
    await router.replace({ query: { weekStart: weekStart.value, ...(courseId.value ? { courseId: String(courseId.value) } : {}) } })
    internalNavigation = false
  }
}
async function loadCalendarData() {
  const version = ++requestVersion
  clearRangeState()
  loadingEvents.value = true
  const params = { start_date: weekStart.value, end_date: weekDays.value[6], course_id: courseId.value }
  try {
    const data = await calendarApi.list(params)
    if (version === requestVersion) events.value = data.items
  } catch (error) {
    if (version === requestVersion) calendarError.value = getApiErrorMessage(error, '日历事件加载失败')
  } finally {
    if (version === requestVersion) loadingEvents.value = false
  }
  toolError.value = ''
  try { tools.value = (await mcpApi.listTools()).items } catch (error) { toolError.value = getApiErrorMessage(error, 'MCP 工具加载失败') }
  auditError.value = ''
  try { calls.value = (await mcpApi.listCalls({ calendar_only: true })).items } catch (error) { auditError.value = getApiErrorMessage(error, 'MCP 审计加载失败') }
}
async function updateRouteAndLoad(nextWeek: string, nextCourse: number | undefined) {
  clearRangeState()
  weekStart.value = nextWeek
  courseId.value = nextCourse
  internalNavigation = true
  await router.replace({ query: { weekStart: nextWeek, ...(nextCourse ? { courseId: String(nextCourse) } : {}) } })
  internalNavigation = false
  await loadCalendarData()
}
async function onCourseChange(value: number | undefined) { await updateRouteAndLoad(weekStart.value, value) }
async function changeWeek(amount: number) { await updateRouteAndLoad(addDateDays(weekStart.value, amount * 7), courseId.value) }
async function goToday() { await updateRouteAndLoad(mondayOf(todayInUserZone()), courseId.value) }
function invalidatePlanPreview() { planPreview.value = null }

async function previewPlan() {
  if (previewingPlan.value) return
  previewingPlan.value = true
  calendarError.value = ''
  try {
    planPreview.value = await calendarApi.previewPlanSync({ start_date: weekStart.value, end_date: weekDays.value[6], course_id: courseId.value, daily_start_time: dailyStart.value, gap_minutes: gap.value })
  } catch (error) { calendarError.value = getApiErrorMessage(error, '计划预览失败') }
  finally { previewingPlan.value = false }
}
async function confirmPlan() {
  if (!planPreview.value || confirmingPlan.value) return
  confirmingPlan.value = true
  try {
    const result = await calendarApi.confirmPlanSync(planPreview.value, planPreview.value.confirmation_token)
    ElMessage.success(`创建 ${result.created_count} 项，幂等重放 ${result.replayed_count} 项`)
    syncVisible.value = false
    planPreview.value = null
    await loadCalendarData()
  } catch (error) { calendarError.value = getApiErrorMessage(error, '计划确认失败，请重新预览') }
  finally { confirmingPlan.value = false }
}
async function exportIcs() {
  if (exportingIcs.value) return
  exportingIcs.value = true
  exportError.value = ''
  try {
    const file = await calendarApi.exportIcs({ start_date: weekStart.value, end_date: weekDays.value[6], course_id: courseId.value })
    const url = URL.createObjectURL(file.blob)
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = file.filename; anchor.click(); URL.revokeObjectURL(url)
  } catch (error) { exportError.value = getApiErrorMessage(error, 'ICS 导出失败') }
  finally { exportingIcs.value = false }
}
function openEvent(event: CalendarEventItem) {
  selected.value = event
  editTitle.value = event.title
  editStart.value = toLocalInput(event.start_at)
  editEnd.value = toLocalInput(event.end_at)
  updatePreview.value = null
  deletePreview.value = null
  detailVisible.value = true
}
function updatePayload(): CalendarEventUpdateRequest {
  return { title: editTitle.value.trim(), start_at: localDateTimeToUtc(editStart.value), end_at: localDateTimeToUtc(editEnd.value) }
}
async function previewUpdate() {
  if (!selected.value || previewingUpdate.value) return
  previewingUpdate.value = true
  calendarError.value = ''
  try { updatePreview.value = await calendarApi.previewUpdate(selected.value.id, updatePayload()) }
  catch (error) { calendarError.value = getApiErrorMessage(error, '修改预览失败') }
  finally { previewingUpdate.value = false }
}
async function confirmUpdate() {
  if (!selected.value || !updatePreview.value || updatingEvent.value) return
  updatingEvent.value = true
  try {
    await calendarApi.updateEvent(selected.value.id, updatePayload(), updatePreview.value.confirmation_token)
    detailVisible.value = false
    ElMessage.success('本地日历事件已更新')
    await loadCalendarData()
  } catch (error) { calendarError.value = getApiErrorMessage(error, '事件已变化或令牌过期，请重新预览') }
  finally { updatingEvent.value = false }
}
async function previewDelete() {
  if (!selected.value || previewingDelete.value) return
  previewingDelete.value = true
  try { deletePreview.value = await calendarApi.previewDelete(selected.value.id) }
  catch (error) { calendarError.value = getApiErrorMessage(error, '删除预览失败') }
  finally { previewingDelete.value = false }
}
async function confirmDelete() {
  if (!selected.value || !deletePreview.value || deletingEvent.value) return
  deletingEvent.value = true
  try {
    await calendarApi.deleteEvent(selected.value.id, deletePreview.value.confirmation_token)
    detailVisible.value = false
    ElMessage.success('本地日历事件已删除')
    await loadCalendarData()
  } catch (error) { calendarError.value = getApiErrorMessage(error, '事件已变化或令牌过期，请重新预览') }
  finally { deletingEvent.value = false }
}

watch([dailyStart, gap], invalidatePlanPreview)
watch(() => [route.query.weekStart, route.query.courseId], async () => {
  if (internalNavigation) return
  try { await initializeFromRoute(); await loadCalendarData() }
  catch (error) { calendarError.value = getApiErrorMessage(error, '日历初始化失败') }
})
onMounted(async () => {
  try { await initializeFromRoute(); await loadCalendarData() }
  catch (error) { calendarError.value = getApiErrorMessage(error, '日历初始化失败') }
})
</script>

<template>
  <div>
    <PageHeader title="学习日历" eyebrow="LEARNING CALENDAR" description="将当前活动学习计划同步到 StudyPilot 本地日历，并可导出 ICS 文件。">
      <el-select :model-value="courseId" clearable placeholder="全部课程" @change="onCourseChange"><el-option v-for="course in courses" :key="course.id" :label="course.name" :value="course.id"/></el-select>
      <el-button plain :loading="exportingIcs" :disabled="loadingEvents" @click="exportIcs"><el-icon><Download/></el-icon>导出 ICS</el-button>
      <el-button type="primary" :disabled="loadingEvents || !courses.length" @click="syncVisible=true"><el-icon><Calendar/></el-icon>同步学习计划</el-button>
    </PageHeader>
    <el-alert v-if="exportError" :title="exportError" type="error"/>
    <el-alert v-if="calendarError" :title="calendarError" type="error"/>
    <section class="layout">
      <main>
        <article class="content-card card-pad local-state"><b>StudyPilot 本地日历：可用</b><span>用户时区：{{ timezone }}</span><span>外部日历账户：未连接</span><span>ICS 可手动导入 Outlook、Google Calendar 等应用</span></article>
        <article class="content-card card-pad">
          <div class="head"><h2>自然周安排</h2><span>{{ weekStart }} 至 {{ weekDays[6] }}</span><el-button size="small" @click="changeWeek(-1)">上一周</el-button><el-button size="small" @click="goToday">今天</el-button><el-button size="small" @click="changeWeek(1)">下一周</el-button></div>
          <div v-if="loadingEvents" v-loading="true" class="loading"/>
          <el-empty v-else-if="!events.length" description="当前周暂无本地日历事件"/>
          <div v-else class="days"><div v-for="day in weekDays" :key="day"><h3>{{ day }}</h3><button v-for="event in events.filter(item=>eventLocal(item).startDate===day)" :key="event.id" class="event" @click="openEvent(event)"><b>{{ event.title }}</b><small>{{ eventLocal(event).range }}</small><small>{{ event.course_name || '本地事件' }} · {{ event.task_type || '手工事件' }}</small></button></div></div>
        </article>
      </main>
      <aside>
        <article class="content-card card-pad"><h2>MCP 日历工具</h2><el-alert v-if="toolError" :title="toolError" type="error"/><p v-else>已注册 {{ calendarTools.length }} 个日历工具；写操作需要二次确认。</p><div v-for="tool in calendarTools" :key="tool.name" class="line"><b>{{tool.name}}</b><small>{{tool.requires_confirmation?'写操作 · 需要确认':'只读'}}</small></div></article>
        <article class="content-card card-pad"><h2>最近 MCP 日历调用</h2><el-alert v-if="auditError" :title="auditError" type="error"/><el-empty v-else-if="!calls.length" description="暂无 MCP 日历调用记录" :image-size="55"/><div v-for="call in calls" :key="call.id" class="line"><b>{{call.tool_name}}</b><small>{{call.status}} · {{call.duration_ms}}ms</small></div></article>
      </aside>
    </section>
    <el-dialog v-model="syncVisible" title="同步学习计划到本地日历" width="min(720px,94vw)">
      <el-form label-position="top"><el-form-item label="每日开始时间"><el-time-select v-model="dailyStart" start="06:00" step="00:30" end="23:30"/></el-form-item><el-form-item label="任务间隔（分钟）"><el-input-number v-model="gap" :min="0" :max="120"/></el-form-item></el-form>
      <el-button :loading="previewingPlan" :disabled="confirmingPlan" @click="previewPlan">生成真实预览</el-button>
      <div v-if="planPreview" class="preview"><p>可创建 {{planPreview.ready_count}} 项；冲突 {{planPreview.conflict_count}} 项；已同步 {{planPreview.already_synced_count}} 项；跨日 {{planPreview.outside_day_count}} 项。</p><div v-for="item in planPreview.items" :key="item.task_id"><b>{{item.title}}</b><span>{{item.status}} · {{item.reason || previewRange(item.start_at,item.end_at)}}</span></div></div>
      <template #footer><el-button :disabled="confirmingPlan" @click="syncVisible=false">取消</el-button><el-button type="primary" :loading="confirmingPlan" :disabled="!planPreview?.ready_count || previewingPlan" @click="confirmPlan">确认创建</el-button></template>
    </el-dialog>
    <el-dialog v-model="detailVisible" title="本地日历事件" width="min(620px,94vw)">
      <template v-if="selected">
        <div class="details"><p><b>课程：</b>{{selected.course_name || '无关联课程'}}</p><p><b>任务类型：</b>{{selected.task_type || '手工事件'}}</p><p><b>来源：</b>{{selected.provider}} / {{selected.sync_status}}</p></div>
        <el-form label-position="top"><el-form-item label="标题"><el-input v-model="editTitle" @input="updatePreview=null"/></el-form-item><el-form-item label="本地开始时间"><el-input v-model="editStart" type="datetime-local" @input="updatePreview=null"/></el-form-item><el-form-item label="本地结束时间"><el-input v-model="editEnd" type="datetime-local" @input="updatePreview=null"/></el-form-item></el-form>
        <el-alert v-if="updatePreview" title="修改预览已生成，请确认写入。" type="warning"/><el-alert v-if="deletePreview" :title="'将删除事件：'+selected.title" type="warning"/>
      </template>
      <template #footer><el-button type="danger" :loading="previewingDelete || deletingEvent" :disabled="operationBusy && !previewingDelete && !deletingEvent" @click="deletePreview ? confirmDelete() : previewDelete()"><el-icon><Delete/></el-icon>{{deletePreview?'确认删除':'预览删除'}}</el-button><el-button :loading="previewingUpdate || updatingEvent" :disabled="operationBusy && !previewingUpdate && !updatingEvent" @click="updatePreview ? confirmUpdate() : previewUpdate()"><el-icon><Edit/></el-icon>{{updatePreview?'确认修改':'预览修改'}}</el-button><el-button :disabled="operationBusy" @click="detailVisible=false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px}.local-state{display:flex;gap:16px;color:#758096}.local-state b{color:#168f78}.head{display:flex;align-items:center;gap:8px}.head span{flex:1;color:#8791a4;font-size:9px}.days{display:grid;grid-template-columns:repeat(7,minmax(120px,1fr));gap:8px;overflow:auto}.days>div{min-height:170px;border:1px solid #e8ebf1;padding:8px;border-radius:8px}.days h3{font-size:9px}.event{display:flex;width:100%;flex-direction:column;gap:4px;margin:6px 0;padding:8px;border:0;border-left:3px solid #5e6de7;background:#eff1ff;text-align:left}.event b,.event small{font-size:8px}.event small{color:#7d879b}.loading{min-height:320px}.line{display:flex;flex-direction:column;gap:4px;padding:8px 0;border-bottom:1px solid #edf0f4}.line b{font:8px Consolas,monospace}.line small{color:#7d879b;font-size:7px}.preview{display:grid;gap:7px;margin-top:12px;padding:10px;background:#f5f7fb}.preview>div{display:flex;justify-content:space-between;font-size:9px}.details{display:flex;gap:14px;font-size:9px}@media(max-width:900px){.layout{grid-template-columns:1fr}.local-state{align-items:flex-start;flex-direction:column}}
</style>
