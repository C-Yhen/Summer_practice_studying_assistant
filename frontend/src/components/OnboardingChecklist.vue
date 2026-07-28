<script setup lang="ts">
import { ArrowRight, Check } from '@element-plus/icons-vue'
import type { DashboardOnboardingProgress } from '@/types'

type ChecklistItemKey = keyof DashboardOnboardingProgress['items']
const props = defineProps<{ progress: DashboardOnboardingProgress | null; loading?: boolean }>()
const emit = defineEmits<{ navigate: [key: ChecklistItemKey] }>()
const tasks: Array<{ key: ChecklistItemKey; title: string; description: string }> = [
  { key: 'course_created', title: '创建第一门课程', description: '设置学习目标与课程信息' },
  { key: 'document_ready', title: '上传第一份学习资料', description: '处理完成后可用于问答与练习' },
  { key: 'question_asked', title: '提出第一个课程问题', description: '基于课程资料开始提问' },
  { key: 'plan_activated', title: '生成并确认第一份学习计划', description: '确认后会进入今日学习安排' },
  { key: 'task_completed', title: '完成第一个学习任务', description: '记录真实学习完成情况' },
]
function completed(key: ChecklistItemKey) { return Boolean(props.progress?.items[key]) }
function navigate(key: ChecklistItemKey) { if (!props.loading && props.progress) emit('navigate', key) }
</script>

<template>
  <section class="onboarding-checklist" :aria-busy="loading || undefined">
    <template v-if="loading">
      <div class="checklist-heading"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-count"></div></div>
      <div class="skeleton skeleton-progress"></div>
      <div class="skeleton-rows"><div v-for="index in 5" :key="index" class="skeleton skeleton-row"></div></div>
    </template>
    <template v-else-if="progress">
      <header class="checklist-heading"><div><span>新手任务</span><h2>{{ progress.is_complete ? '新手任务已完成' : '开始使用 StudyPilot' }}</h2></div><strong>{{ progress.completed_count }} / {{ progress.total_count }}</strong></header>
      <el-progress :percentage="Math.round((progress.completed_count / progress.total_count) * 100)" :show-text="false" :stroke-width="7" color="#5f54e8" />
      <p v-if="progress.is_complete" class="completion-copy">你已经走完 StudyPilot 的基础学习流程，可以继续使用练习、错题、掌握度和推荐等功能。</p>
      <div v-else class="checklist-copy">完成这些真实学习步骤，后续功能会自然衔接。</div>
      <div class="checklist-tasks"><button v-for="task in tasks" :key="task.key" type="button" :class="{ completed: completed(task.key) }" @click="navigate(task.key)"><span class="task-mark"><el-icon v-if="completed(task.key)"><Check /></el-icon></span><span class="task-text"><b>{{ task.title }}</b><small>{{ task.description }}</small></span><el-icon class="task-arrow"><ArrowRight /></el-icon></button></div>
    </template>
  </section>
</template>

<style scoped>
.onboarding-checklist{margin-bottom:22px;padding:22px 24px;border:1px solid #dfe5f0;border-radius:16px;background:#fff;box-shadow:0 10px 28px rgba(28,39,69,.05)}.checklist-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.checklist-heading span{color:var(--brand);font-size:11px;font-weight:800}.checklist-heading h2{margin:5px 0 14px;color:var(--ink);font-size:20px}.checklist-heading strong{padding-top:7px;color:#4e43ce;font-size:15px;font-variant-numeric:tabular-nums}.checklist-copy,.completion-copy{margin:12px 0 14px;color:var(--muted);font-size:12px;line-height:1.65}.completion-copy{color:#35786b}.checklist-tasks{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.checklist-tasks button{display:flex;align-items:center;gap:9px;min-width:0;padding:12px 10px;border:1px solid #e5e9f1;border-radius:10px;background:#fafbfc;text-align:left;cursor:pointer;transition:.15s ease}.checklist-tasks button:hover{border-color:#cfcafa;background:#f8f7ff}.task-mark{display:grid;place-items:center;width:24px;height:24px;flex:none;border:1.5px solid #c9cfdd;border-radius:50%;color:transparent}.task-mark .el-icon{font-size:13px}.task-text{display:flex;min-width:0;flex:1;flex-direction:column}.task-text b,.task-text small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.task-text b{color:#39445b;font-size:11px}.task-text small{margin-top:4px;color:#8b95a9;font-size:9px}.task-arrow{color:#a1a9b8;font-size:11px}.checklist-tasks button.completed{border-color:#dbece7;background:#f5fbf9}.checklist-tasks button.completed .task-mark{border-color:#15987e;background:#15987e;color:#fff}.checklist-tasks button.completed .task-text b{color:#34796b}.skeleton{border-radius:6px;background:linear-gradient(90deg,#f1f3f7 25%,#fafbfc 37%,#f1f3f7 63%);background-size:400% 100%;animation:shimmer 1.2s ease infinite}.skeleton-title{width:160px;height:22px}.skeleton-count{width:40px;height:20px}.skeleton-progress{width:100%;height:7px;margin:16px 0}.skeleton-rows{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.skeleton-row{height:58px}@keyframes shimmer{to{background-position:-100% 0}}@media(max-width:1100px){.checklist-tasks,.skeleton-rows{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.onboarding-checklist{padding:18px}.checklist-tasks,.skeleton-rows{grid-template-columns:1fr}.checklist-tasks button{min-height:56px}.task-text small{white-space:normal}.checklist-heading h2{font-size:18px}}
</style>
