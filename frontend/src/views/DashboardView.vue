<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useRouter } from 'vue-router'
import { ArrowRight, ChatDotRound, Clock, Reading, Refresh, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import MetricCard from '@/components/MetricCard.vue'
import EChart from '@/components/EChart.vue'
import StatusPill from '@/components/StatusPill.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { dashboardApi } from '@/api/dashboard'
import { useAuthStore } from '@/stores/auth'
import type { DashboardAsyncTask, DashboardOverview, DashboardTodayTask } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const overview = ref<DashboardOverview | null>(null)
const loading = ref(false)
const loadError = ref('')

function localDate(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

async function loadOverview() {
  loading.value = true
  loadError.value = ''
  try {
    overview.value = await dashboardApi.getOverview({ target_date: localDate(), days: 7 })
  } catch (error) {
    overview.value = null
    loadError.value = isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, '首页数据加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '上午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})
const focus = computed(() => overview.value?.focus_course ?? null)
const completionPercent = computed(() => Math.round((overview.value?.today.completion_rate ?? 0) * 100))
const averageMastery = computed(() => overview.value?.metrics.average_mastery ?? null)
const hasTrend = computed(() => overview.value?.trend.some((item) => item.learning_minutes > 0 || item.scheduled_tasks > 0) ?? false)
const trendOption = computed<EChartsOption>(() => ({
  color: ['#5a6aec', '#16ae94'], tooltip: { trigger: 'axis', backgroundColor: '#17213e', borderWidth: 0, textStyle: { color: '#fff', fontSize: 11 } },
  grid: { top: 25, left: 10, right: 12, bottom: 5, containLabel: true }, legend: { right: 0, top: 0, itemWidth: 8, itemHeight: 8, textStyle: { color: '#7a849b', fontSize: 10 }, data: ['学习时长', '完成率'] },
  xAxis: { type: 'category', data: overview.value?.trend.map((item) => item.label) ?? [], axisLine: { lineStyle: { color: '#e9edf4' } }, axisTick: { show: false }, axisLabel: { color: '#929bb0', fontSize: 10 } },
  yAxis: [
    { type: 'value', min: 0, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#a0a8ba', fontSize: 9, formatter: '{value}m' }, splitLine: { lineStyle: { color: '#edf0f5', type: 'dashed' } } },
    { type: 'value', min: 0, max: 100, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false } },
  ],
  series: [
    { name: '学习时长', data: overview.value?.trend.map((item) => item.learning_minutes) ?? [], type: 'bar', barWidth: 13, itemStyle: { borderRadius: [5, 5, 0, 0], color: '#e5e8ff' } },
    { name: '完成率', data: overview.value?.trend.map((item) => Math.round(item.completion_rate * 100)) ?? [], type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, lineStyle: { width: 3 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(22,174,148,.18)' }, { offset: 1, color: 'rgba(22,174,148,0)' }] } } },
  ],
}))

function withCourse(path: string) { return focus.value ? { path, query: { courseId: String(focus.value.id) } } : path }
function examSummary() {
  const days = focus.value?.days_until_exam
  if (days === null || days === undefined) return '尚未设置考试日期'
  if (days === 0) return '考试就在今天'
  return days > 0 ? `距离考试还有 ${days} 天` : `考试日期已过 ${Math.abs(days)} 天`
}
function taskTypeLabel(type: string) { return ({ review: '复习', practice: '练习', reading: '阅读', quiz: '测试', study: '学习' } as Record<string, string>)[type] || type }
function priorityLabel(task: DashboardTodayTask) { return task.priority >= 0.8 ? '高' : task.priority >= 0.5 ? '中' : '低' }
function asyncTaskName(task: DashboardAsyncTask) { return ({ document_parse: '文档解析', document_process: '文档处理', weekly_report: '学习周报', study_plan_generate: '学习计划生成', rag_answer: '问答处理' } as Record<string, string>)[task.task_type] || task.task_type }
onMounted(loadOverview)
</script>

<template>
  <div>
    <PageHeader :title="`${greeting}，${auth.user?.displayName || '学习者'} 👋`" eyebrow="LEARNING OVERVIEW" description="首页只汇总当前账号已保存的真实课程、计划、学习记录与处理任务。">
      <el-button plain @click="router.push(withCourse('/chat'))"><el-icon><ChatDotRound /></el-icon>课程问答</el-button>
      <el-button type="primary" @click="router.push(withCourse('/today'))"><el-icon><Reading /></el-icon>今日学习</el-button>
    </PageHeader>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="loadOverview"><el-icon><Refresh /></el-icon>重新加载</el-button></template></el-alert>
    <div v-if="loading" v-loading="true" class="dashboard-loading"></div>

    <template v-else-if="overview">
      <section v-if="focus" class="focus-banner">
        <div class="focus-copy"><span class="focus-badge"><i></i>{{ focus.name }}<template v-if="focus.code"> · {{ focus.code }}</template></span><h2>{{ examSummary() }}</h2><p>{{ focus.has_active_plan ? '已有生效学习计划' : '尚无生效学习计划' }} · 今日计划 {{ overview.today.planned_minutes }} 分钟 · 已完成 {{ overview.today.completed_count }}/{{ overview.today.total_count }} 项</p><div class="focus-progress"><span :style="{ width: `${completionPercent}%` }"></span></div></div>
        <div class="focus-orbit"><div class="orbit-ring"></div><strong>{{ completionPercent }}<small>%</small></strong><span>今日完成</span></div>
        <button class="focus-arrow" aria-label="查看学习计划" @click="router.push(withCourse('/plan'))"><el-icon><ArrowRight /></el-icon></button>
      </section>
      <section v-else class="content-card empty-focus"><div><span>还没有课程</span><h2>从创建第一门课程开始</h2><p>创建课程后，可以继续上传资料、确认计划并在这里查看学习进展。</p></div><el-button type="primary" @click="router.push('/courses')">创建课程</el-button></section>

      <section class="metrics-grid">
        <MetricCard label="今日专注" :value="`${overview.metrics.today_focus_minutes} min`" :hint="`已记录 ${overview.today.actual_minutes} 分钟任务学习`" icon="⌁" tone="blue" />
        <MetricCard label="今日完成率" :value="`${Math.round(overview.metrics.today_completion_rate * 100)}%`" :hint="`${overview.today.completed_count}/${overview.today.total_count} 项生效计划任务`" icon="✓" tone="green" />
        <MetricCard label="平均掌握度" :value="averageMastery === null ? '暂无' : `${Math.round(averageMastery * 100)}%`" :hint="averageMastery === null ? '完成关联知识点任务后生成' : `${overview.weak_points.length} 个薄弱点优先展示`" icon="◎" tone="purple" />
        <MetricCard label="学习概况" :value="`${overview.metrics.study_days_in_range} 天`" :hint="`${overview.metrics.active_course_count} 门课程 · ${overview.metrics.ready_document_count} 份就绪资料`" icon="↗" tone="orange" />
      </section>

      <section class="section-grid dashboard-grid">
        <article class="content-card card-pad trend-card"><div class="card-header"><div><h2>近 7 天学习趋势</h2><p>{{ overview.range_start }} 至 {{ overview.range_end }} · {{ overview.timezone }}</p></div></div><EChart v-if="hasTrend" :option="trendOption" height="244px" /><el-empty v-else description="近 7 天暂无学习时长或生效计划任务" :image-size="68" /></article>
        <article class="content-card card-pad today-card">
          <div class="card-header"><div><h2>今日任务</h2><p>{{ overview.today.completed_count }}/{{ overview.today.total_count }} 项已完成</p></div><button class="card-link" @click="router.push(withCourse('/today'))">查看全部 →</button></div>
          <div v-if="overview.today.items.length" class="task-list"><button v-for="task in overview.today.items" :key="task.id" class="task-row" :class="{ done: task.status === 'completed' }" @click="router.push({ path: '/today', query: { courseId: String(task.course_id) } })"><span class="check-box">✓</span><span class="task-info"><b>{{ task.title }}</b><small>{{ taskTypeLabel(task.task_type) }} · {{ task.status === 'completed' && task.actual_minutes ? `实际 ${task.actual_minutes}` : `预计 ${task.estimated_minutes}` }} 分钟</small></span><span class="priority" :class="priorityLabel(task)">{{ priorityLabel(task) }}</span></button></div>
          <el-empty v-else description="今天暂无生效计划任务" :image-size="62"><el-button size="small" @click="router.push(withCourse('/plan'))">查看计划</el-button></el-empty>
        </article>
        <article class="content-card card-pad mastery-card">
          <div class="card-header"><div><h2>薄弱知识点</h2><p>按当前真实掌握度从低到高</p></div><button class="card-link" @click="router.push(withCourse('/mastery'))">能力图谱 →</button></div>
          <div v-if="overview.weak_points.length" class="mastery-list"><div v-for="item in overview.weak_points" :key="item.knowledge_point_id"><div><b>{{ item.knowledge_point }}</b><span>{{ Math.round(item.score * 100) }}%</span></div><el-progress :percentage="Math.round(item.score * 100)" :show-text="false" :stroke-width="7" :color="item.score < 0.5 ? '#ee8b4a' : '#6978ef'" /><small>{{ item.course_name }} · 已练习 {{ item.attempts }} 次</small></div></div><el-empty v-else description="暂无掌握度记录" :image-size="62" />
        </article>
        <article class="content-card next-card"><div class="advice-label"><span>→</span> 下一步</div><h2>{{ overview.next_action.title }}</h2><p>{{ overview.next_action.reason }}</p><button @click="router.push(overview.next_action.route)">立即前往 <el-icon><ArrowRight /></el-icon></button></article>
        <article class="content-card card-pad shortcut-card"><div class="card-header"><div><h2>快捷入口</h2><p>继续当前课程的真实流程</p></div></div><div class="shortcut-grid"><button @click="router.push(withCourse('/upload'))"><el-icon><UploadFilled /></el-icon><span>上传资料</span></button><button @click="router.push(withCourse('/chat'))"><el-icon><ChatDotRound /></el-icon><span>课程问答</span></button><button @click="router.push(withCourse('/plan'))"><el-icon><Clock /></el-icon><span>学习计划</span></button><button @click="router.push(withCourse('/today'))"><el-icon><Reading /></el-icon><span>今日任务</span></button></div></article>
        <article class="content-card card-pad jobs-card">
          <div class="card-header"><div><h2>最近处理任务</h2><p>仅展示当前账号最近 3 项真实异步任务</p></div><button class="card-link" @click="router.push('/tasks')">任务中心 →</button></div>
          <div v-if="overview.recent_async_tasks.length" class="job-list"><button v-for="job in overview.recent_async_tasks" :key="job.task_id" class="job-row" @click="router.push({ name: 'tasks', query: { taskId: job.task_id } })"><span class="job-icon"><el-icon><Clock /></el-icon></span><div class="job-main"><b>{{ asyncTaskName(job) }}</b><small>{{ job.current_step || job.task_type }}</small><el-progress v-if="!['success', 'succeeded', 'failed', 'cancelled'].includes(job.status)" :percentage="job.progress" :show-text="false" :stroke-width="5" /></div><StatusPill :status="job.status" /></button></div><el-empty v-else description="暂无异步处理任务" :image-size="62" />
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dashboard-loading{min-height:420px}.empty-focus{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:28px 34px;margin-bottom:18px}.empty-focus span{color:#6876e8;font-size:10px;font-weight:750}.empty-focus h2{margin:8px 0;color:var(--ink);font-size:22px}.empty-focus p{margin:0;color:var(--muted);font-size:11px}.focus-banner{position:relative;min-height:174px;display:flex;align-items:center;gap:38px;overflow:hidden;padding:28px 34px;margin-bottom:18px;border-radius:22px;background:linear-gradient(112deg,#4655db 0%,#6672ed 54%,#8e69e9 100%);color:#fff;box-shadow:0 18px 42px rgba(77,91,219,.24)}.focus-banner::before{content:"";position:absolute;width:390px;height:390px;right:10%;top:-265px;border:80px solid rgba(255,255,255,.06);border-radius:50%}.focus-copy{position:relative;z-index:1;flex:1}.focus-badge{display:inline-flex;align-items:center;gap:8px;font-size:10px;font-weight:700;color:#e7e9ff}.focus-badge i{width:7px;height:7px;border-radius:50%;background:#72ead3;box-shadow:0 0 0 4px rgba(114,234,211,.17)}.focus-copy h2{margin:14px 0 8px;font-size:27px;letter-spacing:-.7px}.focus-copy p{margin:0;color:#dfe2ff;font-size:11px}.focus-progress{max-width:570px;height:5px;margin-top:19px;border-radius:5px;background:rgba(255,255,255,.2);overflow:hidden}.focus-progress span{display:block;height:100%;border-radius:5px;background:#fff}.focus-orbit{position:relative;z-index:1;width:104px;height:104px;display:flex;align-items:center;justify-content:center;flex-direction:column;flex:none}.orbit-ring{position:absolute;inset:0;border:7px solid rgba(255,255,255,.17);border-top-color:#fff;border-right-color:#fff;border-radius:50%;transform:rotate(20deg)}.focus-orbit strong{font-size:28px}.focus-orbit strong small{font-size:13px}.focus-orbit span{font-size:9px;color:#d6daff}.focus-arrow{position:relative;z-index:1;width:40px;height:40px;border:1px solid rgba(255,255,255,.25);border-radius:12px;background:rgba(255,255,255,.13);color:white;cursor:pointer}.metrics-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin-bottom:18px}.dashboard-grid>article{min-width:0}.trend-card{grid-column:span 8}.today-card{grid-column:span 4}.mastery-card,.next-card,.shortcut-card{grid-column:span 4}.jobs-card{grid-column:span 12}.task-list{display:grid;gap:8px}.task-row{width:100%;display:flex;align-items:center;gap:10px;padding:10px;border:0;border-radius:11px;background:#f8f9fc;text-align:left;cursor:pointer}.task-row:hover{background:#f2f4fb}.check-box{width:18px;height:18px;display:grid;place-items:center;flex:none;border:1.5px solid #cbd2e1;border-radius:6px;color:transparent;font-size:10px}.task-info{flex:1;min-width:0;display:flex;flex-direction:column}.task-info b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#3e4964;font-size:10px}.task-info small{margin-top:5px;color:#9ba4b6;font-size:9px}.priority{font-size:9px}.priority.高{color:#dc6969}.priority.中{color:#d28a44}.task-row.done{opacity:.65}.task-row.done .check-box{color:white;border-color:var(--teal);background:var(--teal)}.task-row.done b{text-decoration:line-through}.mastery-list{display:grid;gap:15px}.mastery-list>div>div{display:flex;justify-content:space-between;margin-bottom:7px;color:#48536d;font-size:10px}.mastery-list span{color:#7b859b}.mastery-list small{display:block;margin-top:6px;color:#98a1b4;font-size:8px}.next-card{position:relative;overflow:hidden;padding:22px;background:linear-gradient(145deg,#101e43,#162752);color:white}.next-card::after{content:"→";position:absolute;right:-8px;top:-35px;font-size:130px;color:rgba(255,255,255,.035)}.advice-label{display:flex;align-items:center;gap:8px;color:#a8b4ff;font-size:9px;font-weight:800;letter-spacing:1.3px}.next-card h2{margin:16px 0 10px;font-size:17px}.next-card>p{margin:0;color:#aab4cf;font-size:10px;line-height:1.75}.next-card button{display:flex;align-items:center;gap:5px;margin-top:24px;padding:0;border:0;background:transparent;color:#b6beff;font-size:10px;cursor:pointer}.shortcut-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.shortcut-grid button{display:flex;align-items:center;gap:8px;padding:13px;border:1px solid #edf0f5;border-radius:12px;background:#fafbfc;color:#58647f;cursor:pointer}.shortcut-grid button:hover{border-color:#cfd5ff;background:#f5f6ff;color:#5867ed}.job-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.job-row{display:flex;align-items:flex-start;gap:10px;padding:13px;border:1px solid #edf0f5;border-radius:12px;background:#fafbfc}.job-icon{width:28px;height:28px;display:grid;place-items:center;flex:none;border-radius:9px;background:#edf0ff;color:#6574e8}.job-main{display:flex;flex:1;min-width:0;flex-direction:column}.job-main b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#46516b;font-size:10px}.job-main small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:6px 0;color:#929bad;font-size:8px}@media(max-width:1200px){.metrics-grid{grid-template-columns:repeat(2,1fr)}.trend-card,.today-card{grid-column:span 12}.mastery-card,.next-card,.shortcut-card{grid-column:span 6}.job-list{grid-template-columns:1fr}}@media(max-width:700px){.focus-banner{padding:23px}.focus-orbit,.focus-arrow{display:none}.focus-copy h2{font-size:21px}.metrics-grid{grid-template-columns:1fr 1fr;gap:12px}.mastery-card,.next-card,.shortcut-card{grid-column:span 12}}@media(max-width:480px){.metrics-grid{grid-template-columns:1fr}.empty-focus{align-items:flex-start;flex-direction:column}}
</style>
