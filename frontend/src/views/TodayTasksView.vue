<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Clock, CoffeeCup, DArrowRight, VideoPlay } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { todayTasks } from '@/data/mock'

const tasks = ref(todayTasks.map((item) => ({ ...item })))
const delayVisible = ref(false)
const activeTask = ref(tasks.value.find((item) => item.status === 'doing') || tasks.value[0])
const completed = computed(() => tasks.value.filter((item) => item.status === 'done').length)
const minutesDone = computed(() => tasks.value.filter((item) => item.status === 'done').reduce((sum, item) => sum + item.duration, 0))
function complete(task: (typeof tasks.value)[number]) { task.status = 'done'; ElMessage.success(`已完成「${task.title}」，掌握度将在后台更新`) }
function postpone() { delayVisible.value = false; ElMessage.success('任务已延期，明日计划调整建议将在生成后请你确认') }
</script>

<template>
  <div>
    <PageHeader title="今日任务" eyebrow="DAILY FOCUS" description="2026 年 7 月 14 日 · 冲刺第 3 天 · 今日预算 120 分钟">
      <el-button plain><el-icon><CoffeeCup /></el-icon>进入休息模式</el-button><el-button type="primary"><el-icon><VideoPlay /></el-icon>继续专注</el-button>
    </PageHeader>
    <section class="daily-hero">
      <div class="ring"><strong>{{ Math.round(completed / tasks.length * 100) }}<small>%</small></strong><span>任务进度</span></div>
      <div class="daily-copy"><span>今日学习节奏</span><h2>{{ completed === tasks.length ? '今日目标已全部完成！' : '再完成 3 项，离目标更近一步' }}</h2><p>已专注 {{ minutesDone }} 分钟 · 剩余 {{ tasks.reduce((s,t)=>s+t.duration,0)-minutesDone }} 分钟 · 当前连续学习 12 天</p><el-progress :percentage="completed / tasks.length * 100" :show-text="false" :stroke-width="7" color="#78d9c6" /></div>
      <div class="daily-stat"><strong>+8%</strong><span>本周掌握度提升</span></div><div class="daily-stat"><strong>18 min</strong><span>领先原计划</span></div>
    </section>

    <section class="today-layout">
      <article class="content-card card-pad">
        <div class="card-header"><div><h2>任务清单</h2><p>按学习收益与前置依赖排序</p></div><span class="soft-tag brand">{{ completed }}/{{ tasks.length }} 已完成</span></div>
        <div class="task-cards"><article v-for="(task,index) in tasks" :key="task.id" :class="task.status"><button class="task-check" @click="complete(task)"><el-icon v-if="task.status === 'done'"><Check /></el-icon><span v-else>{{ index + 1 }}</span></button><div class="task-content"><div><span class="soft-tag" :class="task.type === '练习' ? 'orange' : 'brand'">{{ task.type }}</span><em>{{ task.priority }}优先级</em></div><h3>{{ task.title }}</h3><p>{{ task.course }} · 知识点：{{ task.knowledge }}</p><div class="task-bottom"><span><el-icon><Clock /></el-icon>{{ task.duration }} 分钟</span><span v-if="task.status === 'done'" class="done-label">完成于 09:48</span><template v-else><button @click="activeTask=task">开始学习</button><button class="delay" @click="delayVisible=true">延期</button></template></div></div></article></div>
      </article>

      <aside>
        <article class="focus-card">
          <span class="soft-tag green">正在进行</span><h2>{{ activeTask.title }}</h2><p>{{ activeTask.course }} · {{ activeTask.knowledge }}</p>
          <div class="timer"><strong>18:42</strong><span>剩余 / 25:00</span></div>
          <el-progress :percentage="25" :show-text="false" :stroke-width="7" color="#72d7c3" />
          <div class="timer-actions"><button><el-icon><VideoPlay /></el-icon></button><button><el-icon><DArrowRight /></el-icon></button></div>
          <small>离开页面不会中断计时</small>
        </article>
        <article class="content-card card-pad reason-card"><div class="card-header"><div><h2>为什么先做这项？</h2><p>个性化排序理由</p></div></div><ul><li><span>1</span>“函数依赖”是第三范式的前置知识</li><li><span>2</span>该知识点掌握度仅 52%</li><li><span>3</span>在期末考试中预计占 12 分</li></ul><div class="confidence">推荐置信度 <b>87%</b></div></article>
      </aside>
    </section>

    <el-dialog v-model="delayVisible" title="延期这项学习任务？" width="min(460px, 92vw)"><p class="dialog-note">系统会根据剩余时间、任务优先级与知识依赖重新计算明日计划。调整方案生成后仍需你确认，不会自动写入日历。</p><el-form label-position="top"><el-form-item label="延期原因"><el-select model-value="今天临时有事" style="width:100%"><el-option label="今天临时有事" value="今天临时有事" /><el-option label="当前内容太难" value="当前内容太难" /><el-option label="身体不适" value="身体不适" /></el-select></el-form-item><el-form-item label="希望安排到"><el-radio-group model-value="明天"><el-radio value="明天">明天</el-radio><el-radio value="本周内">本周内</el-radio><el-radio value="自动安排">自动安排</el-radio></el-radio-group></el-form-item></el-form><template #footer><el-button @click="delayVisible=false">取消</el-button><el-button type="primary" @click="postpone">确认延期并生成建议</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.daily-hero{display:flex;align-items:center;gap:24px;padding:22px 27px;margin-bottom:18px;border-radius:18px;background:linear-gradient(110deg,#19284f,#203a68);color:white}.ring{width:76px;height:76px;display:flex;align-items:center;justify-content:center;flex-direction:column;flex:none;border:6px solid rgba(255,255,255,.13);border-top-color:#76d7c4;border-right-color:#76d7c4;border-radius:50%;transform:rotate(18deg)}.ring>*{transform:rotate(-18deg)}.ring strong{font-size:20px}.ring strong small{font-size:9px}.ring span{color:#91a0bd;font-size:7px}.daily-copy{flex:1}.daily-copy>span{color:#7dd9c6;font-size:8px;font-weight:700}.daily-copy h2{margin:6px 0;font-size:16px}.daily-copy p{margin:0 0 11px;color:#aab5cc;font-size:8px}.daily-stat{display:flex;flex-direction:column;padding-left:20px;border-left:1px solid rgba(255,255,255,.1)}.daily-stat strong{font-size:16px}.daily-stat span{margin-top:5px;color:#8e9bb5;font-size:8px}.today-layout{display:grid;grid-template-columns:minmax(0,1fr) 315px;gap:18px}.task-cards{display:grid;gap:10px}.task-cards>article{display:flex;gap:12px;padding:14px;border:1px solid #e5e9f1;border-radius:13px;background:#fff}.task-cards>article.doing{border-color:#99a3ef;background:#fafaff;box-shadow:0 7px 18px rgba(86,102,222,.07)}.task-cards>article.done{opacity:.66;background:#f8faf9}.task-check{width:28px;height:28px;display:grid;place-items:center;flex:none;border:1px solid #d9deea;border-radius:9px;background:white;color:#7d879b;font-size:9px;cursor:pointer}.done .task-check{border-color:#18a88c;background:#18a88c;color:white}.task-content{flex:1;min-width:0}.task-content>div:first-child{display:flex;align-items:center}.task-content em{margin-left:7px;color:#e17d43;font-size:8px;font-style:normal}.task-content h3{margin:8px 0 5px;color:#3f4a65;font-size:12px}.done h3{text-decoration:line-through}.task-content p{margin:0;color:#929bad;font-size:8px}.task-bottom{display:flex;align-items:center;gap:8px;margin-top:11px}.task-bottom>span{display:flex;align-items:center;gap:5px;color:#8993a6;font-size:8px}.task-bottom button{margin-left:auto;padding:5px 9px;border:0;border-radius:7px;background:#5e6de8;color:white;font-size:8px;cursor:pointer}.task-bottom button.delay{margin-left:0;background:#f1f3f7;color:#778198}.task-bottom .done-label{margin-left:auto;color:#168e77}.focus-card{padding:21px;margin-bottom:14px;border-radius:17px;background:linear-gradient(145deg,#5a68e3,#816de5);color:white;box-shadow:0 15px 32px rgba(91,104,224,.2)}.focus-card h2{margin:14px 0 6px;font-size:14px}.focus-card>p{margin:0;color:#d8dcff;font-size:8px}.timer{text-align:center;margin:25px 0 13px}.timer strong{display:block;font:36px "SFMono-Regular",Consolas,monospace;letter-spacing:2px}.timer span{color:#d5d8fc;font-size:8px}.timer-actions{display:flex;justify-content:center;gap:9px;margin-top:18px}.timer-actions button{width:36px;height:36px;display:grid;place-items:center;border:1px solid rgba(255,255,255,.24);border-radius:11px;background:rgba(255,255,255,.13);color:white;cursor:pointer}.focus-card>small{display:block;text-align:center;margin-top:11px;color:#ccd1f8;font-size:7px}.reason-card ul{display:grid;gap:10px;padding:0;margin:0;list-style:none}.reason-card li{display:flex;align-items:center;gap:8px;color:#667188;font-size:9px}.reason-card li span{width:20px;height:20px;display:grid;place-items:center;border-radius:7px;background:#eef0ff;color:#5f6ee3;font-size:8px}.confidence{margin-top:14px;padding-top:11px;border-top:1px solid #edf0f4;color:#8a94a8;font-size:8px}.confidence b{float:right;color:#16a087}.dialog-note{padding:12px;margin:0 0 17px;border-radius:10px;background:#f3f5fb;color:#738097;font-size:9px;line-height:1.6}@media(max-width:900px){.today-layout{grid-template-columns:1fr}.today-layout aside{display:grid;grid-template-columns:1fr 1fr;gap:14px}.daily-stat{display:none}}@media(max-width:650px){.daily-hero{align-items:flex-start;flex-direction:column}.ring{display:none}.today-layout aside{grid-template-columns:1fr}}
</style>
