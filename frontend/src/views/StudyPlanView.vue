<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Clock, MagicStick, Refresh, Warning } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'

const version = ref('v3')
const confirmVisible = ref(false)
const days = [
  { day: '周一', date: '07/13', done: true, minutes: 120, tasks: [{ type: '阅读', title: '关系模型与关系代数', duration: 45, status: 'done' }, { type: '练习', title: 'SQL 基础查询 15 题', duration: 40, status: 'done' }] },
  { day: '周二', date: '07/14', today: true, minutes: 120, tasks: [{ type: '阅读', title: '函数依赖与属性闭包', duration: 35, status: 'done' }, { type: '练习', title: '第三范式专项练习', duration: 25, status: 'doing' }, { type: '复习', title: 'TCP 拥塞控制', duration: 30, status: 'todo' }] },
  { day: '周三', date: '07/15', minutes: 115, tasks: [{ type: '阅读', title: '第二范式与第三范式', duration: 45, status: 'todo' }, { type: '练习', title: '候选码判断 10 题', duration: 30, status: 'todo' }] },
  { day: '周四', date: '07/16', minutes: 125, tasks: [{ type: '阅读', title: 'BCNF 与模式分解', duration: 50, status: 'todo' }, { type: '测试', title: '范式综合小测', duration: 35, status: 'todo' }] },
  { day: '周五', date: '07/17', minutes: 110, tasks: [{ type: '阅读', title: '事务 ACID 与隔离级别', duration: 40, status: 'todo' }, { type: '练习', title: '事务并发异常', duration: 30, status: 'todo' }] },
  { day: '周六', date: '07/18', minutes: 140, tasks: [{ type: '复习', title: '全章知识点串联', duration: 60, status: 'todo' }, { type: '测试', title: '模拟卷一', duration: 60, status: 'todo' }] },
  { day: '周日', date: '07/19', minutes: 90, tasks: [{ type: '复习', title: '错题集中回顾', duration: 45, status: 'todo' }, { type: '练习', title: '薄弱点强化题', duration: 30, status: 'todo' }] },
]
const totalMinutes = computed(() => days.reduce((sum, day) => sum + day.minutes, 0))
function confirmPlan() { confirmVisible.value = false; ElMessage.success('计划 v3 已确认，后续调整将保留版本记录') }
</script>

<template>
  <div>
    <PageHeader title="7 天冲刺学习计划" eyebrow="ADAPTIVE PLANNING" description="计划会根据任务完成、答题表现与剩余时间动态调整，所有版本均可追溯。">
      <el-select v-model="version" style="width:130px"><el-option label="当前版本 v3" value="v3" /><el-option label="历史版本 v2" value="v2" /><el-option label="初始版本 v1" value="v1" /></el-select>
      <el-button plain><el-icon><Refresh /></el-icon>重新生成</el-button><el-button type="primary" @click="confirmVisible = true"><el-icon><Check /></el-icon>确认此计划</el-button>
    </PageHeader>
    <section class="plan-summary">
      <div class="plan-score"><span>计划可行性</span><strong>92<small>/100</small></strong><p>基于每日 2 小时空闲时间与目标 90 分</p></div>
      <div><span>总学习时长</span><strong>{{ Math.round(totalMinutes / 60) }}h 40m</strong><p>7 天 · 日均 115 分钟</p></div><div><span>计划任务</span><strong>16 项</strong><p>阅读 6 · 练习 7 · 测试 3</p></div><div><span>预计提升</span><strong>+18%</strong><p>平均掌握度 64% → 82%</p></div>
      <div class="plan-confidence"><span>AI 置信度 88%</span><i><em></em></i><small>数据：18 次答题 · 12 天记录</small></div>
    </section>

    <section class="adjustment-note">
      <div class="magic"><el-icon><MagicStick /></el-icon></div><div class="adjust-copy"><span>AI 动态调整建议 · v2 → v3</span><h3>将 30 分钟 SQL 练习替换为函数依赖复习</h3><p>原因：函数依赖掌握度下降 2%，并连续影响 3 道范式题；SQL 正确率已稳定在 88%。</p></div><div class="diff"><span><del>SQL 综合练习 · 30m</del></span><i>→</i><span><ins>函数依赖复习 · 35m</ins></span></div><button>查看完整差异</button>
    </section>

    <section class="week-board">
      <article v-for="day in days" :key="day.date" class="day-column" :class="{ today: day.today, done: day.done }">
        <header><div><span>{{ day.day }}</span><strong>{{ day.date }}</strong></div><em v-if="day.today">今天</em><em v-else-if="day.done" class="complete">已完成</em><small>{{ day.minutes }} min</small></header>
        <div class="day-tasks"><button v-for="(task,index) in day.tasks" :key="task.title" :class="task.status"><span>{{ index + 1 }}</span><div><em>{{ task.type }}</em><b>{{ task.title }}</b><small><el-icon><Clock /></el-icon>{{ task.duration }} 分钟</small></div></button></div>
        <footer><span>{{ day.tasks.filter(t => t.status === 'done').length }}/{{ day.tasks.length }} 完成</span><el-progress :percentage="day.tasks.filter(t => t.status === 'done').length / day.tasks.length * 100" :show-text="false" :stroke-width="5" /></footer>
      </article>
    </section>

    <el-dialog v-model="confirmVisible" title="确认采用学习计划 v3" width="min(520px, 92vw)">
      <div class="confirm-box"><el-icon><Warning /></el-icon><div><b>这是一次受控写操作</b><p>确认后将创建 16 项学习任务，并保存计划版本 v3。系统不会覆盖旧版本；同步到第三方日历仍需单独确认。</p></div></div>
      <div class="confirm-items"><p><span>生效日期</span><b>2026-07-14 至 2026-07-20</b></p><p><span>每日预算</span><b>最多 120 分钟</b></p><p><span>动态调整</span><b>开启（每次调整仍需确认）</b></p></div>
      <template #footer><el-button @click="confirmVisible = false">再检查一下</el-button><el-button type="primary" @click="confirmPlan">确认并创建任务</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.plan-summary{display:grid;grid-template-columns:1.3fr repeat(3,1fr) 1.25fr;gap:0;margin-bottom:16px;border:1px solid var(--line);border-radius:17px;background:white;box-shadow:var(--shadow-soft)}.plan-summary>div{display:flex;flex-direction:column;padding:19px 21px;border-right:1px solid #e9ecf2}.plan-summary>div:last-child{border:0}.plan-summary span{color:#8a94a8;font-size:9px}.plan-summary strong{margin-top:8px;color:#313c58;font-size:19px}.plan-summary strong small{font-size:9px;color:#8d96aa}.plan-summary p,.plan-summary small{margin:6px 0 0;color:#9aa2b3;font-size:8px}.plan-score{background:#f7f8ff}.plan-score strong{color:#5363df}.plan-confidence i{height:6px;margin-top:11px;border-radius:5px;background:#eceff5;overflow:hidden}.plan-confidence em{display:block;width:88%;height:100%;border-radius:5px;background:linear-gradient(90deg,#6372e8,#15b099)}.adjustment-note{display:flex;align-items:center;gap:14px;padding:15px 18px;margin-bottom:16px;border:1px solid #dddff8;border-radius:15px;background:linear-gradient(90deg,#f5f6ff,#faf9ff)}.magic{width:38px;height:38px;display:grid;place-items:center;flex:none;border-radius:12px;background:#e7eaff;color:#5e6de5;font-size:18px}.adjust-copy{flex:1}.adjust-copy>span{color:#6270dd;font-size:8px;font-weight:750}.adjust-copy h3{margin:5px 0 4px;color:#3f4963;font-size:11px}.adjust-copy p{margin:0;color:#8892a6;font-size:8px}.diff{display:flex;align-items:center;gap:8px}.diff span{padding:7px 9px;border-radius:7px;background:#fff;color:#8a94a7;font-size:8px}.diff del{color:#c27a7e}.diff ins{color:#168d77;text-decoration:none}.diff i{color:#818aa0;font-style:normal}.adjustment-note>button{border:0;background:transparent;color:#5d6be0;font-size:8px;cursor:pointer}.week-board{display:grid;grid-template-columns:repeat(7,minmax(145px,1fr));gap:10px;overflow-x:auto;padding-bottom:8px}.day-column{min-height:410px;display:flex;flex-direction:column;border:1px solid var(--line);border-radius:14px;background:white;box-shadow:var(--shadow-soft);overflow:hidden}.day-column.today{border-color:#7d89ec;box-shadow:0 8px 25px rgba(92,107,230,.13)}.day-column>header{display:flex;align-items:center;gap:7px;padding:12px;border-bottom:1px solid #edf0f5;background:#fafbfc}.day-column.today>header{background:#f1f3ff}.day-column header>div{display:flex;flex-direction:column}.day-column header span{font-size:10px;font-weight:700}.day-column header strong{margin-top:3px;color:#98a0b2;font-size:8px}.day-column header em{padding:3px 5px;border-radius:5px;background:#5e6de7;color:#fff;font-size:7px;font-style:normal}.day-column header em.complete{background:#e7f7f2;color:#178e77}.day-column header>small{margin-left:auto;color:#8e97aa;font-size:7px}.day-tasks{display:grid;gap:8px;padding:10px}.day-tasks button{display:flex;gap:8px;padding:10px 8px;border:1px solid #e7eaf1;border-radius:10px;background:#fff;text-align:left;cursor:pointer}.day-tasks button:hover{border-color:#aeb6ee}.day-tasks button>span{width:19px;height:19px;display:grid;place-items:center;flex:none;border-radius:6px;background:#eef0f5;color:#7c879b;font-size:7px}.day-tasks button>div{display:flex;min-width:0;flex-direction:column}.day-tasks em{color:#6573dc;font-size:7px;font-style:normal}.day-tasks b{margin-top:5px;color:#4c566f;font-size:9px;line-height:1.45}.day-tasks small{display:flex;align-items:center;gap:4px;margin-top:6px;color:#9aa2b3;font-size:7px}.day-tasks .done{opacity:.66;background:#f7faf9}.day-tasks .done>span{background:#1aa58a;color:white}.day-tasks .doing{border-color:#98a2ed;background:#f8f8ff}.day-tasks .doing>span{background:#6372e8;color:white}.day-column>footer{margin-top:auto;padding:11px;border-top:1px solid #edf0f5}.day-column footer span{display:block;margin-bottom:6px;color:#8b95a8;font-size:7px}.confirm-box{display:flex;gap:12px;padding:14px;border-radius:12px;background:#fff7eb;color:#dc882e}.confirm-box>.el-icon{font-size:20px}.confirm-box b{font-size:11px}.confirm-box p{margin:6px 0 0;color:#8f704d;font-size:9px;line-height:1.6}.confirm-items{margin-top:14px}.confirm-items p{display:flex;justify-content:space-between;padding:9px 0;margin:0;border-bottom:1px solid #edf0f4;font-size:10px}.confirm-items span{color:#8a94a8}.confirm-items b{color:#4a556e}@media(max-width:1100px){.plan-summary{grid-template-columns:repeat(2,1fr)}.plan-summary>div{border-bottom:1px solid #e9ecf2}.plan-confidence{grid-column:span 2}.adjustment-note{align-items:flex-start;flex-wrap:wrap}.diff{width:100%;margin-left:52px}}@media(max-width:600px){.plan-summary{grid-template-columns:1fr}.plan-confidence{grid-column:auto}.diff{margin-left:0;overflow:auto}.adjustment-note>button{margin-left:52px}.week-board{grid-template-columns:repeat(7,155px)}}
</style>
