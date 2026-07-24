<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useRouter } from 'vue-router'
import { ArrowRight, Calendar, ChatDotRound, Clock, DocumentAdd, Reading, Refresh, UploadFilled } from '@element-plus/icons-vue'
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
const onboardingSteps = computed(() => {
  const hasCourse = Boolean(focus.value)
  const hasDocument = (overview.value?.metrics.ready_document_count ?? 0) > 0
  const hasPlan = Boolean(focus.value?.has_active_plan)
  const hasLearning = (overview.value?.metrics.study_days_in_range ?? 0) > 0 || (overview.value?.today.completed_count ?? 0) > 0
  return [
    { title: '创建课程', description: '设置学习目标与考试日期', done: hasCourse, route: '/courses' },
    { title: '添加资料', description: '上传讲义、笔记或教材', done: hasDocument, route: withCourse('/upload') },
    { title: '生成计划', description: '由 AI 生成可确认的学习安排', done: hasPlan, route: withCourse('/plan') },
    { title: '开始学习', description: '完成任务、练习并获得反馈', done: hasLearning, route: withCourse('/today') },
  ]
})
const onboardingComplete = computed(() => onboardingSteps.value.every((step) => step.done))
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
function courseProgressSummary() {
  if (!focus.value?.has_active_plan) return '先创建计划，再开始清晰、可持续的学习节奏'
  if (overview.value?.today.total_count) {
    return `今天还有 ${Math.max(overview.value.today.total_count - overview.value.today.completed_count, 0)} 项任务，预计 ${Math.max(overview.value.today.planned_minutes - overview.value.today.actual_minutes, 0)} 分钟`
  }
  return '今天没有待办，可继续课程问答或补充学习资料'
}
function taskTypeLabel(type: string) { return ({ review: '复习', practice: '练习', reading: '阅读', quiz: '测试', study: '学习' } as Record<string, string>)[type] || type }
function priorityLabel(task: DashboardTodayTask) { return task.priority >= 0.8 ? '高' : task.priority >= 0.5 ? '中' : '低' }
function asyncTaskName(task: DashboardAsyncTask) { return ({ document_parse: '文档解析', document_process: '文档处理', weekly_report: '学习周报', study_plan_generate: '学习计划生成', rag_answer: '问答处理' } as Record<string, string>)[task.task_type] || task.task_type }
onMounted(loadOverview)
</script>

<template>
  <div>
    <PageHeader :title="`${greeting}，${auth.user?.displayName || '学习者'}`" eyebrow="学习首页" description="从当前课程继续学习，AI 会根据资料、计划与练习结果给出下一步建议。">
      <el-button plain @click="router.push(withCourse('/chat'))"><el-icon><ChatDotRound /></el-icon>课程问答</el-button>
      <el-button type="primary" @click="router.push(withCourse('/today'))"><el-icon><Reading /></el-icon>今日学习</el-button>
    </PageHeader>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="loadOverview"><el-icon><Refresh /></el-icon>重新加载</el-button></template></el-alert>
    <div v-if="loading" v-loading="true" class="dashboard-loading"></div>

    <template v-else-if="overview">
      <section v-if="!onboardingComplete" class="onboarding-panel">
        <div class="onboarding-copy">
          <span>首次使用指南</span>
          <h2>四步建立你的 AI 学习空间</h2>
          <p>先准备课程与资料，再让 AI 生成计划。每完成一步，后续能力会自动解锁。</p>
        </div>
        <div class="onboarding-steps">
          <button v-for="(step, index) in onboardingSteps" :key="step.title" :class="{ done: step.done }" @click="router.push(step.route)">
            <i>{{ step.done ? '✓' : index + 1 }}</i>
            <span><b>{{ step.title }}</b><small>{{ step.description }}</small></span>
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
      </section>

      <section class="primary-workspace">
        <article v-if="focus" class="command-deck">
          <div class="deck-main">
            <span class="focus-badge"><i></i>当前课程</span>
            <p class="course-kicker">{{ focus.name }}<template v-if="focus.code"> / {{ focus.code }}</template></p>
            <h2>{{ courseProgressSummary() }}</h2>
            <div class="course-meta"><span><el-icon><Calendar /></el-icon>{{ examSummary() }}</span><span>{{ focus.has_active_plan ? '计划运行中' : '等待创建计划' }}</span></div>
            <div class="focus-actions"><el-button class="continue-button" @click="router.push(withCourse('/today'))">继续今日学习 <el-icon><ArrowRight /></el-icon></el-button><button class="plan-link" aria-label="查看学习计划" @click="router.push(withCourse('/plan'))">查看学习计划</button></div>
          </div>
          <div class="deck-progress">
            <div class="progress-orbit"><div class="orbit-ring"></div><strong>{{ completionPercent }}<small>%</small></strong></div>
            <span>今日完成度</span>
            <div class="focus-progress"><i :style="{ width: `${completionPercent}%` }"></i></div>
            <small>{{ overview.today.completed_count }} / {{ overview.today.total_count }} 项已完成</small>
          </div>
        </article>
        <article v-else class="content-card empty-focus"><div><span>还没有课程</span><h2>从创建第一门课程开始</h2><p>创建课程后，可以继续上传资料、确认计划并在这里查看学习进展。</p></div><el-button type="primary" @click="router.push('/courses')">创建课程</el-button></article>

        <article class="content-card card-pad today-card">
          <div class="card-header"><div><span class="panel-index">今日安排</span><h2>今天要做什么</h2><p>按计划优先级依次推进</p></div><button class="card-link" @click="router.push(withCourse('/today'))">查看全部</button></div>
          <div class="today-summary"><div><b>{{ overview.today.completed_count }}</b><span>/ {{ overview.today.total_count }} 项</span></div><div><b>{{ overview.today.actual_minutes }}</b><span>/ {{ overview.today.planned_minutes }} 分钟</span></div></div>
          <div v-if="overview.today.items.length" class="task-list"><button v-for="task in overview.today.items" :key="task.id" class="task-row" :class="{ done: task.status === 'completed' }" @click="router.push({ path: '/today', query: { courseId: String(task.course_id) } })"><span class="check-box">✓</span><span class="task-info"><b>{{ task.title }}</b><small>{{ taskTypeLabel(task.task_type) }} · {{ task.status === 'completed' && task.actual_minutes ? `实际 ${task.actual_minutes}` : `预计 ${task.estimated_minutes}` }} 分钟</small></span><span class="priority" :class="priorityLabel(task)">{{ priorityLabel(task) }}</span></button></div>
          <el-empty v-else description="今天暂无生效计划任务" :image-size="62"><el-button size="small" @click="router.push(withCourse('/plan'))">查看计划</el-button></el-empty>
        </article>
      </section>

      <section class="section-grid dashboard-grid">
        <article class="metrics-panel"><div class="section-label"><div><span>近 7 天</span><h2>学习概览</h2></div><p>{{ overview.range_start }} 至 {{ overview.range_end }}</p></div><section class="metrics-grid"><MetricCard label="今日学习" :value="`${overview.metrics.today_focus_minutes} 分钟`" :hint="`已记录 ${overview.today.actual_minutes} 分钟任务学习`" icon="⌁" tone="blue" /><MetricCard label="任务完成率" :value="`${Math.round(overview.metrics.today_completion_rate * 100)}%`" :hint="`${overview.today.completed_count}/${overview.today.total_count} 项计划任务`" icon="✓" tone="green" /><MetricCard label="平均掌握度" :value="averageMastery === null ? '暂无' : `${Math.round(averageMastery * 100)}%`" :hint="averageMastery === null ? '完成练习后生成' : `${overview.weak_points.length} 个薄弱点待加强`" icon="◎" tone="purple" /><MetricCard label="学习概况" :value="`${overview.metrics.study_days_in_range} 天`" :hint="`${overview.metrics.active_course_count} 门课程 · ${overview.metrics.ready_document_count} 份可用资料`" icon="↗" tone="orange" /></section></article>
        <article class="content-card card-pad trend-card"><div class="card-header"><div><h2>近 7 天学习趋势</h2><p>{{ overview.timezone }} · 学习时长与任务完成率</p></div></div><EChart v-if="hasTrend" :option="trendOption" height="244px" /><el-empty v-else description="近 7 天暂无学习时长或生效计划任务" :image-size="68" /></article>
        <article class="content-card card-pad mastery-card">
          <div class="card-header"><div><h2>薄弱知识点</h2><p>按当前真实掌握度从低到高</p></div><button class="card-link" @click="router.push(withCourse('/mastery'))">能力图谱 →</button></div>
          <div v-if="overview.weak_points.length" class="mastery-list"><div v-for="item in overview.weak_points" :key="item.knowledge_point_id"><div><b>{{ item.knowledge_point }}</b><span>{{ Math.round(item.score * 100) }}%</span></div><el-progress :percentage="Math.round(item.score * 100)" :show-text="false" :stroke-width="7" :color="item.score < 0.5 ? '#ee8b4a' : '#6978ef'" /><small>{{ item.course_name }} · 已练习 {{ item.attempts }} 次</small></div></div><el-empty v-else description="暂无掌握度记录" :image-size="62" />
        </article>
        <article class="content-card next-card"><div class="advice-label"><span>AI</span> 下一步建议</div><h2>{{ overview.next_action.title }}</h2><p>{{ overview.next_action.reason }}</p><button @click="router.push(overview.next_action.route)">现在去做 <el-icon><ArrowRight /></el-icon></button></article>
        <article class="content-card card-pad shortcut-card"><div class="card-header"><div><h2>常用操作</h2><p>围绕当前课程继续学习</p></div></div><div class="shortcut-grid"><button @click="router.push(withCourse('/upload'))"><el-icon><UploadFilled /></el-icon><span>添加资料</span></button><button @click="router.push(withCourse('/chat'))"><el-icon><ChatDotRound /></el-icon><span>问 AI</span></button><button @click="router.push(withCourse('/practice'))"><el-icon><DocumentAdd /></el-icon><span>开始练习</span></button><button @click="router.push(withCourse('/plan'))"><el-icon><Clock /></el-icon><span>调整计划</span></button></div></article>
        <article class="content-card card-pad jobs-card">
          <div class="card-header"><div><h2>最近处理任务</h2><p>仅展示当前账号最近 3 项真实异步任务</p></div><button class="card-link" @click="router.push('/tasks')">任务中心 →</button></div>
          <div v-if="overview.recent_async_tasks.length" class="job-list"><button v-for="job in overview.recent_async_tasks" :key="job.task_id" class="job-row" @click="router.push({ name: 'tasks', query: { taskId: job.task_id } })"><span class="job-icon"><el-icon><Clock /></el-icon></span><div class="job-main"><b>{{ asyncTaskName(job) }}</b><small>{{ job.current_step || job.task_type }}</small><el-progress v-if="!['success', 'succeeded', 'failed', 'cancelled'].includes(job.status)" :percentage="job.progress" :show-text="false" :stroke-width="5" /></div><StatusPill :status="job.status" /></button></div><el-empty v-else description="暂无异步处理任务" :image-size="62" />
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page-alert{margin-bottom:20px}.dashboard-loading{min-height:420px}.onboarding-panel{display:grid;grid-template-columns:minmax(260px,.75fr) minmax(0,1.45fr);gap:24px;margin-bottom:22px;padding:24px;border:1px solid #dfe5f0;border-radius:16px;background:#fff;box-shadow:0 10px 28px rgba(28,39,69,.05)}.onboarding-copy>span{color:var(--brand);font-size:11px;font-weight:800}.onboarding-copy h2{margin:8px 0;color:var(--ink);font-size:20px}.onboarding-copy p{margin:0;color:var(--muted);font-size:12px;line-height:1.65}.onboarding-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.onboarding-steps button{display:flex;align-items:center;gap:9px;min-width:0;padding:13px 11px;border:1px solid #e5e9f1;border-radius:10px;background:#fafbfc;text-align:left;cursor:pointer}.onboarding-steps button:hover{border-color:#cfcafa;background:#f8f7ff}.onboarding-steps i{width:25px;height:25px;display:grid;place-items:center;flex:none;border-radius:50%;background:#e9e7ff;color:#5f54e8;font-style:normal;font-size:11px;font-weight:800}.onboarding-steps span{display:flex;min-width:0;flex:1;flex-direction:column}.onboarding-steps b{color:#39445b;font-size:11px}.onboarding-steps small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:4px;color:#8b95a9;font-size:9px}.onboarding-steps .el-icon{color:#a1a9b8;font-size:11px}.onboarding-steps button.done{border-color:#dbece7;background:#f5fbf9}.onboarding-steps button.done i{background:#d9f2eb;color:#15987e}.primary-workspace{display:grid;grid-template-columns:minmax(0,1.72fr) minmax(330px,.9fr);gap:20px;margin-bottom:34px}.empty-focus{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:30px 34px}.empty-focus span{color:var(--brand);font-size:11px;font-weight:800}.empty-focus h2{margin:9px 0;color:var(--ink);font-size:22px}.empty-focus p{margin:0;color:var(--muted);font-size:13px;line-height:1.65}.command-deck{position:relative;min-height:310px;display:grid;grid-template-columns:minmax(0,1fr) 190px;align-items:stretch;overflow:hidden;border-radius:18px;background:linear-gradient(125deg,#10192f 0%,#172343 53%,#30265e 100%);color:#fff;box-shadow:0 18px 42px rgba(23,28,66,.16)}.command-deck::before{content:"";position:absolute;width:330px;height:330px;right:10%;top:-235px;border:68px solid rgba(117,101,247,.13);border-radius:50%}.command-deck::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;background:linear-gradient(90deg,transparent,#6b5df5,#40d2b5,transparent)}.deck-main{position:relative;z-index:1;padding:34px 36px}.focus-badge{display:inline-flex;align-items:center;gap:10px;color:#aeb8d5;font-size:10px;font-weight:800;letter-spacing:1.1px}.focus-badge i{width:7px;height:7px;border-radius:50%;background:#55dbc2;box-shadow:0 0 0 5px rgba(85,219,194,.12)}.course-kicker{margin:24px 0 9px;color:#8f9bbb;font-size:12px;font-weight:700}.deck-main h2{max-width:610px;margin:0;color:#fff;font-size:28px;line-height:1.36;letter-spacing:-.75px}.course-meta{display:flex;flex-wrap:wrap;gap:9px 20px;margin-top:16px;color:#9eabc7;font-size:11px}.course-meta span{display:flex;align-items:center;gap:6px}.focus-actions{display:flex;align-items:center;gap:14px;margin-top:30px}.continue-button{height:42px!important;border-color:#7466f6!important;background:#7466f6!important;color:#fff!important;box-shadow:0 10px 24px rgba(65,51,190,.3)!important}.plan-link{padding:7px 3px;border:0;background:transparent;color:#aeb9d6;font-size:11px;font-weight:700;cursor:pointer}.deck-progress{position:relative;z-index:1;display:flex;align-items:center;justify-content:center;flex-direction:column;padding:28px 26px;border-left:1px solid rgba(255,255,255,.07);background:rgba(255,255,255,.025)}.progress-orbit{position:relative;width:112px;height:112px;display:grid;place-items:center}.orbit-ring{position:absolute;inset:0;border:8px solid rgba(255,255,255,.09);border-top-color:#7567f7;border-right-color:#4ed8bd;border-radius:50%;transform:rotate(22deg);box-shadow:inset 0 0 24px rgba(82,70,207,.08)}.progress-orbit strong{font-size:28px}.progress-orbit strong small{font-size:12px;color:#9eabc6}.deck-progress>span{margin-top:12px;color:#d8ddef;font-size:11px;font-weight:750}.focus-progress{width:100%;height:4px;margin-top:22px;border-radius:5px;background:rgba(255,255,255,.1);overflow:hidden}.focus-progress i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,#7265f4,#49d5bb)}.deck-progress>small{margin-top:9px;color:#7f8daa;font-size:10px}.today-card{min-width:0;min-height:310px;border-top:3px solid #675af1}.today-card .card-header{align-items:flex-start;margin-bottom:16px}.panel-index{display:block;margin-bottom:7px;color:var(--brand);font-size:9px;font-weight:850;letter-spacing:.6px}.today-summary{display:grid;grid-template-columns:1fr 1fr;gap:1px;overflow:hidden;margin-bottom:13px;border-radius:9px;background:#e8ebf2}.today-summary>div{display:flex;align-items:baseline;gap:4px;padding:11px 12px;background:#f6f7fa}.today-summary b{color:var(--ink);font-size:17px}.today-summary span{color:#8892a6;font-size:10px}.task-list{display:grid;gap:8px}.task-row{width:100%;display:flex;align-items:center;gap:10px;padding:11px 10px;border:1px solid transparent;border-radius:8px;background:#f7f8fb;text-align:left;cursor:pointer;transition:border-color .15s ease,transform .15s ease,background .15s ease}.task-row:hover{border-color:#dedafc;background:#f7f5ff;transform:translateX(2px)}.check-box{width:20px;height:20px;display:grid;place-items:center;flex:none;border:1.5px solid #c9cfdd;border-radius:5px;color:transparent;font-size:10px}.task-info{flex:1;min-width:0;display:flex;flex-direction:column}.task-info b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#354057;font-size:12px}.task-info small{margin-top:5px;color:#8e98ac;font-size:10px}.priority{padding:3px 6px;border-radius:4px;background:#eef0f4;color:#8b94a6;font-size:9px}.priority.高{background:#fff0f0;color:#d65f68}.priority.中{background:#fff5e8;color:#cf8335}.task-row.done{opacity:.6}.task-row.done .check-box{color:white;border-color:var(--teal);background:var(--teal)}.task-row.done b{text-decoration:line-through}.dashboard-grid>article{min-width:0}.metrics-panel{grid-column:span 12}.section-label{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:17px}.section-label span{color:var(--brand);font-size:9px;font-weight:850;letter-spacing:.5px}.section-label h2{margin:6px 0 0;color:var(--ink);font-size:20px;letter-spacing:-.35px}.section-label p{margin:0;color:var(--muted);font-size:10px}.metrics-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.trend-card{grid-column:span 8}.mastery-card{grid-column:span 4}.next-card{grid-column:span 4}.shortcut-card{grid-column:span 8}.jobs-card{grid-column:span 12}.trend-card,.mastery-card,.shortcut-card,.jobs-card{border-top:3px solid transparent}.trend-card{border-top-color:#6558f5}.mastery-card{border-top-color:#13b99a}.shortcut-card{border-top-color:#9a5ae7}.jobs-card{border-top-color:#e6e9f0}.mastery-list{display:grid;gap:17px}.mastery-list>div>div{display:flex;justify-content:space-between;margin-bottom:8px;color:#48536d;font-size:12px}.mastery-list span{color:#7b859b}.mastery-list small{display:block;margin-top:7px;color:#8f99ad;font-size:11px}.next-card{position:relative;overflow:hidden;padding:27px;background:linear-gradient(145deg,#5e50ea,#785ee8);color:white;box-shadow:0 14px 30px rgba(85,65,212,.16)}.next-card::before{content:"";position:absolute;width:145px;height:145px;right:-65px;bottom:-70px;border:28px solid rgba(255,255,255,.08);border-radius:50%}.advice-label{display:flex;align-items:center;gap:9px;color:#dfdcff;font-size:10px;font-weight:800;letter-spacing:.4px}.advice-label span{display:grid;place-items:center;width:25px;height:25px;border-radius:7px;background:rgba(255,255,255,.14);font-size:9px}.next-card h2{position:relative;margin:20px 0 11px;font-size:19px;line-height:1.4}.next-card>p{position:relative;margin:0;color:#e1dfff;font-size:12px;line-height:1.7}.next-card button{position:relative;display:flex;align-items:center;gap:6px;margin-top:27px;padding:0;border:0;background:transparent;color:#fff;font-size:11px;font-weight:800;cursor:pointer}.shortcut-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.shortcut-grid button{display:flex;align-items:center;gap:9px;padding:15px;border:1px solid #e9ecf2;border-radius:9px;background:#f8f9fb;color:#536078;font-size:12px;cursor:pointer;transition:.15s ease}.shortcut-grid button:hover{border-color:#d8d3ff;background:#f5f3ff;color:#6255ef;transform:translateY(-2px)}.job-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.job-row{display:flex;align-items:flex-start;gap:11px;padding:15px;border:1px solid #e9ecf2;border-radius:9px;background:#f8f9fb;text-align:left;cursor:pointer}.job-row:hover{border-color:#dcdff0;background:#f6f6fb}.job-icon{width:32px;height:32px;display:grid;place-items:center;flex:none;border-radius:8px;background:#eeecff;color:#6558f5}.job-main{display:flex;flex:1;min-width:0;flex-direction:column}.job-main b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#3e4960;font-size:12px}.job-main small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:6px 0;color:#8792a8;font-size:10px}@media(max-width:1280px){.onboarding-panel{grid-template-columns:1fr}.command-deck{grid-template-columns:minmax(0,1fr) 160px}.deck-main{padding:30px}.deck-main h2{font-size:24px}}@media(max-width:1100px){.onboarding-steps{grid-template-columns:repeat(2,1fr)}.primary-workspace{grid-template-columns:1fr}.command-deck{grid-template-columns:minmax(0,1fr) 190px}.metrics-grid{grid-template-columns:repeat(2,1fr)}.trend-card{grid-column:span 12}.mastery-card,.next-card,.shortcut-card{grid-column:span 6}.shortcut-grid{grid-template-columns:1fr 1fr}.job-list{grid-template-columns:1fr}}@media(max-width:700px){.onboarding-panel{padding:18px}.onboarding-steps{grid-template-columns:1fr}.primary-workspace{gap:14px;margin-bottom:26px}.command-deck{min-height:auto;grid-template-columns:1fr}.deck-main{padding:25px 22px}.deck-main h2{font-size:22px}.deck-progress{align-items:flex-start;padding:20px 22px;border-top:1px solid rgba(255,255,255,.07);border-left:0}.progress-orbit{display:none}.deck-progress>span{margin-top:0}.focus-actions{align-items:flex-start;flex-direction:column}.metrics-grid{grid-template-columns:1fr 1fr;gap:12px}.section-label{align-items:flex-start;flex-direction:column;gap:5px}.mastery-card,.next-card,.shortcut-card{grid-column:span 12}}@media(max-width:480px){.metrics-grid,.shortcut-grid{grid-template-columns:1fr}.empty-focus{align-items:flex-start;flex-direction:column}}
</style>
