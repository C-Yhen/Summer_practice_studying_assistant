<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useRouter } from 'vue-router'
import { ArrowRight, ChatDotRound, Clock, Reading } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import MetricCard from '@/components/MetricCard.vue'
import EChart from '@/components/EChart.vue'
import StatusPill from '@/components/StatusPill.vue'
import { asyncTasks, knowledgeMastery, todayTasks as taskSource, trendData } from '@/data/mock'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const tasks = ref(taskSource.map((task) => ({ ...task })))
const doneCount = computed(() => tasks.value.filter((task) => task.status === 'done').length)
const trendOption = computed<EChartsOption>(() => ({
  color: ['#5a6aec', '#16ae94'],
  tooltip: { trigger: 'axis', backgroundColor: '#17213e', borderWidth: 0, textStyle: { color: '#fff', fontSize: 11 } },
  grid: { top: 25, left: 10, right: 12, bottom: 5, containLabel: true },
  legend: { right: 0, top: 0, itemWidth: 8, itemHeight: 8, textStyle: { color: '#7a849b', fontSize: 10 }, data: ['学习时长', '完成率'] },
  xAxis: { type: 'category', data: trendData.map((item) => item.day), axisLine: { lineStyle: { color: '#e9edf4' } }, axisTick: { show: false }, axisLabel: { color: '#929bb0', fontSize: 10 } },
  yAxis: [
    { type: 'value', min: 0, max: 160, interval: 40, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#a0a8ba', fontSize: 9, formatter: '{value}m' }, splitLine: { lineStyle: { color: '#edf0f5', type: 'dashed' } } },
    { type: 'value', min: 0, max: 100, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false } },
  ],
  series: [
    { name: '学习时长', data: trendData.map((item) => item.minutes), type: 'bar', barWidth: 13, itemStyle: { borderRadius: [5, 5, 0, 0], color: '#e5e8ff' } },
    { name: '完成率', data: trendData.map((item) => item.completion), type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, lineStyle: { width: 3 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(22,174,148,.18)' }, { offset: 1, color: 'rgba(22,174,148,0)' }] } } },
  ],
}))

function toggleTask(task: (typeof tasks.value)[number]) { task.status = task.status === 'done' ? 'todo' : 'done' }
</script>

<template>
  <div>
    <PageHeader :title="`上午好，${auth.user?.displayName || '学习者'} 👋`" eyebrow="LEARNING OVERVIEW" description="今天是冲刺第 3 天，保持节奏，你已经比计划领先 18 分钟。">
      <el-button plain @click="router.push('/chat')"><el-icon><ChatDotRound /></el-icon>问问 AI</el-button>
      <el-button type="primary" @click="router.push('/today')"><el-icon><Reading /></el-icon>开始今日学习</el-button>
    </PageHeader>

    <section class="focus-banner">
      <div class="focus-copy">
        <span class="focus-badge"><i></i>数据库系统 · 期末冲刺</span>
        <h2>距离考试还有 <em>7</em> 天</h2>
        <p>今日重点：函数依赖与第三范式 · 预计 2 小时 · 已完成 {{ doneCount }}/{{ tasks.length }} 项任务</p>
        <div class="focus-progress"><span :style="{ width: `${doneCount / tasks.length * 100}%` }"></span></div>
      </div>
      <div class="focus-orbit"><div class="orbit-ring"></div><strong>68<small>%</small></strong><span>课程进度</span></div>
      <button class="focus-arrow" aria-label="查看学习计划" @click="router.push('/plan')"><el-icon><ArrowRight /></el-icon></button>
    </section>

    <section class="metrics-grid">
      <MetricCard label="今日专注" value="48 min" hint="目标 120 分钟 · 还差 72 分钟" icon="⌁" tone="blue" />
      <MetricCard label="计划完成率" value="82%" hint="较上周提升 9%" icon="✓" tone="green" />
      <MetricCard label="平均掌握度" value="64%" hint="6 个知识点正在提升" icon="◎" tone="purple" />
      <MetricCard label="连续学习" value="12 天" hint="再坚持 2 天刷新纪录" icon="↗" tone="orange" />
    </section>

    <section class="section-grid dashboard-grid">
      <article class="content-card card-pad trend-card">
        <div class="card-header"><div><h2>本周学习趋势</h2><p>学习时长与任务完成率</p></div><el-select model-value="本周" size="small" style="width:86px"><el-option label="本周" value="本周" /></el-select></div>
        <EChart :option="trendOption" height="244px" />
      </article>

      <article class="content-card card-pad today-card">
        <div class="card-header"><div><h2>今日任务</h2><p>{{ doneCount }}/{{ tasks.length }} 项已完成</p></div><button class="card-link" @click="router.push('/today')">查看全部 →</button></div>
        <div class="task-list">
          <button v-for="task in tasks" :key="task.id" class="task-row" :class="{ done: task.status === 'done' }" @click="toggleTask(task)">
            <span class="check-box">✓</span><span class="task-info"><b>{{ task.title }}</b><small>{{ task.type }} · {{ task.duration }} 分钟</small></span><span class="priority" :class="task.priority">{{ task.priority }}</span>
          </button>
        </div>
      </article>

      <article class="content-card card-pad mastery-card">
        <div class="card-header"><div><h2>薄弱知识点</h2><p>优先级由掌握度与考试权重计算</p></div><button class="card-link" @click="router.push('/mastery')">能力图谱 →</button></div>
        <div class="mastery-list">
          <div v-for="item in knowledgeMastery.slice(2, 5)" :key="item.name"><div><b>{{ item.name }}</b><span>{{ item.value }}%</span></div><el-progress :percentage="item.value" :show-text="false" :stroke-width="7" :color="item.value < 50 ? '#ee8b4a' : '#6978ef'" /></div>
        </div>
        <div class="weak-tip"><span>!</span><p><b>建议先学「函数依赖」</b><small>它是理解第三范式的前置知识，预计 35 分钟可补齐。</small></p></div>
      </article>

      <article class="content-card card-pad recommend-card">
        <div class="card-header"><div><h2>为你推荐</h2><p>基于薄弱点与当前计划</p></div><button class="card-link" @click="router.push('/recommendations')">更多推荐 →</button></div>
        <div class="resource-item"><span class="resource-icon pdf">PDF</span><div><b>函数依赖：从定义到闭包</b><p>数据库讲义 · 第 32–39 页</p><small>匹配薄弱点「函数依赖」</small></div><strong>96%</strong></div>
        <div class="resource-item"><span class="resource-icon quiz">Q</span><div><b>第三范式专项练习 · 10 题</b><p>预计 18 分钟 · 中等难度</p><small>根据近 3 次错题生成</small></div><strong>92%</strong></div>
      </article>

      <article class="content-card advice-card">
        <div class="advice-label"><span>✦</span> AI 学习建议</div>
        <h2>先补基础，再攻范式判断</h2>
        <p>你对“函数依赖”的掌握度下降了 2%，但 SQL 基础稳定。建议把今晚的 30 分钟 SQL 练习调整为函数依赖复习，预计可将明日范式题正确率提升 12%。</p>
        <div><span class="soft-tag brand">依据：近 18 次答题</span><span class="soft-tag green">置信度 87%</span></div>
        <button @click="router.push('/plan')">查看调整方案 <el-icon><ArrowRight /></el-icon></button>
      </article>

      <article class="content-card card-pad jobs-card">
        <div class="card-header"><div><h2>最近长时任务</h2><p>Celery + Redis 实时进度</p></div><button class="card-link" @click="router.push('/tasks')">任务中心 →</button></div>
        <div class="job-list">
          <div v-for="job in asyncTasks.slice(0, 3)" :key="job.id" class="job-row">
            <span class="job-icon"><el-icon><Clock /></el-icon></span><div class="job-main"><b>{{ job.name }}</b><small>{{ job.step }}</small><el-progress v-if="job.status !== 'success'" :percentage="job.progress" :show-text="false" :stroke-width="5" /></div><StatusPill :status="job.status" />
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.focus-banner{position:relative;min-height:174px;display:flex;align-items:center;gap:38px;overflow:hidden;padding:28px 34px;margin-bottom:18px;border-radius:22px;background:linear-gradient(112deg,#4655db 0%,#6672ed 54%,#8e69e9 100%);color:#fff;box-shadow:0 18px 42px rgba(77,91,219,.24)}.focus-banner::before{content:"";position:absolute;width:390px;height:390px;right:10%;top:-265px;border:80px solid rgba(255,255,255,.06);border-radius:50%}.focus-copy{position:relative;z-index:1;flex:1}.focus-badge{display:inline-flex;align-items:center;gap:8px;font-size:10px;font-weight:700;color:#e7e9ff}.focus-badge i{width:7px;height:7px;border-radius:50%;background:#72ead3;box-shadow:0 0 0 4px rgba(114,234,211,.17)}.focus-copy h2{margin:14px 0 8px;font-size:27px;letter-spacing:-.7px}.focus-copy h2 em{font-size:38px;font-style:normal;color:#fff2bd}.focus-copy p{margin:0;color:#dfe2ff;font-size:11px}.focus-progress{max-width:570px;height:5px;margin-top:19px;border-radius:5px;background:rgba(255,255,255,.2);overflow:hidden}.focus-progress span{display:block;height:100%;border-radius:5px;background:#fff}.focus-orbit{position:relative;z-index:1;width:104px;height:104px;display:flex;align-items:center;justify-content:center;flex-direction:column;flex:none}.orbit-ring{position:absolute;inset:0;border:7px solid rgba(255,255,255,.17);border-top-color:#fff;border-right-color:#fff;border-radius:50%;transform:rotate(20deg)}.focus-orbit strong{font-size:28px}.focus-orbit strong small{font-size:13px}.focus-orbit span{font-size:9px;color:#d6daff}.focus-arrow{position:relative;z-index:1;width:40px;height:40px;border:1px solid rgba(255,255,255,.25);border-radius:12px;background:rgba(255,255,255,.13);color:white;cursor:pointer}.metrics-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin-bottom:18px}.dashboard-grid>article{min-width:0}.trend-card{grid-column:span 8}.today-card{grid-column:span 4}.mastery-card,.recommend-card,.advice-card{grid-column:span 4}.jobs-card{grid-column:span 12}.task-list{display:grid;gap:8px}.task-row{width:100%;display:flex;align-items:center;gap:10px;padding:10px;border:0;border-radius:11px;background:#f8f9fc;text-align:left;cursor:pointer}.task-row:hover{background:#f2f4fb}.check-box{width:18px;height:18px;display:grid;place-items:center;flex:none;border:1.5px solid #cbd2e1;border-radius:6px;color:transparent;font-size:10px}.task-info{flex:1;min-width:0;display:flex;flex-direction:column}.task-info b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#3e4964;font-size:10px}.task-info small{margin-top:5px;color:#9ba4b6;font-size:9px}.priority{font-size:9px}.priority.高{color:#dc6969}.priority.中{color:#d28a44}.task-row.done{opacity:.65}.task-row.done .check-box{color:white;border-color:var(--teal);background:var(--teal)}.task-row.done b{text-decoration:line-through}.mastery-list{display:grid;gap:15px}.mastery-list>div>div{display:flex;justify-content:space-between;margin-bottom:7px;color:#48536d;font-size:10px}.mastery-list span{color:#7b859b}.weak-tip{display:flex;gap:10px;margin-top:17px;padding:12px;border-radius:12px;background:#fff7ed}.weak-tip>span{width:23px;height:23px;display:grid;place-items:center;flex:none;border-radius:8px;background:#ffe5c6;color:#dc832b;font-weight:800}.weak-tip p{display:flex;flex-direction:column;margin:0}.weak-tip b{color:#705133;font-size:10px}.weak-tip small{margin-top:5px;color:#a17b54;font-size:9px;line-height:1.5}.resource-item{display:flex;align-items:center;gap:11px;padding:12px 0;border-bottom:1px solid #edf0f5}.resource-item:last-child{border-bottom:0}.resource-icon{width:37px;height:42px;display:grid;place-items:center;flex:none;border-radius:9px;font-size:9px;font-weight:800}.resource-icon.pdf{background:#fff0ed;color:#dd6654}.resource-icon.quiz{background:#eff1ff;color:#5e6dea}.resource-item div{display:flex;flex:1;min-width:0;flex-direction:column}.resource-item b{color:#3e4963;font-size:10px}.resource-item p{margin:5px 0;color:#8993a8;font-size:9px}.resource-item small{color:#6673df;font-size:8px}.resource-item>strong{color:#19a18a;font-size:10px}.advice-card{position:relative;overflow:hidden;padding:22px;background:linear-gradient(145deg,#101e43,#162752);color:white}.advice-card::after{content:"✦";position:absolute;right:-15px;top:-30px;font-size:130px;color:rgba(255,255,255,.035)}.advice-label{display:flex;align-items:center;gap:8px;color:#a8b4ff;font-size:9px;font-weight:800;letter-spacing:1.3px}.advice-label span{color:#8f9cff}.advice-card h2{margin:16px 0 10px;font-size:17px}.advice-card>p{margin:0;color:#aab4cf;font-size:10px;line-height:1.75}.advice-card>div:not(.advice-label){display:flex;flex-wrap:wrap;gap:7px;margin-top:15px}.advice-card button{display:flex;align-items:center;gap:5px;margin-top:17px;padding:0;border:0;background:transparent;color:#b6beff;font-size:10px;cursor:pointer}.job-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.job-row{display:flex;align-items:flex-start;gap:10px;padding:13px;border:1px solid #edf0f5;border-radius:12px;background:#fafbfc}.job-icon{width:28px;height:28px;display:grid;place-items:center;flex:none;border-radius:9px;background:#edf0ff;color:#6574e8}.job-main{display:flex;flex:1;min-width:0;flex-direction:column}.job-main b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#46516b;font-size:10px}.job-main small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:6px 0;color:#929bad;font-size:8px}@media(max-width:1200px){.metrics-grid{grid-template-columns:repeat(2,1fr)}.trend-card,.today-card{grid-column:span 12}.mastery-card,.recommend-card,.advice-card{grid-column:span 6}.advice-card{grid-column:span 12}.job-list{grid-template-columns:1fr}}@media(max-width:700px){.focus-banner{padding:23px}.focus-orbit,.focus-arrow{display:none}.focus-copy h2{font-size:21px}.metrics-grid{grid-template-columns:1fr 1fr;gap:12px}.mastery-card,.recommend-card,.advice-card{grid-column:span 12}}@media(max-width:480px){.metrics-grid{grid-template-columns:1fr}}
</style>
