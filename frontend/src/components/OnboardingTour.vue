<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useOnboardingStore } from '@/stores/onboarding'

const router = useRouter()
const onboarding = useOnboardingStore()
const tourOpen = ref(false)
const currentStep = ref(0)

const steps = [
  { target: 'courses', title: '课程管理', description: '先创建一门课程。课程是资料、问答、学习计划和练习的统一学习空间。' },
  { target: 'documents', title: '课程资料', description: '上传 PDF、TXT 或 Markdown 资料。处理完成后，资料可用于问答和练习生成。' },
  { target: 'chat', title: '智能问答', description: '针对当前课程资料提出问题。系统会优先依据资料回答并显示引用来源。' },
  { target: 'plans', title: '学习计划', description: '根据学习目标和时间安排生成计划。确认后，相关内容会进入今日任务。' },
  { target: 'practice', title: '练习与反馈', description: '完成练习和任务后，可查看错题、掌握度、推荐内容和学习趋势。' },
]

const finishOpen = ref(false)

function targetFor(target: string) {
  return () => document.querySelector<HTMLElement>(`[data-onboarding-target~="${target}"]`)
}

async function skip() {
  const saved = await onboarding.recordSkip()
  if (!saved) return
  tourOpen.value = false
}

async function complete(showFinish = false) {
  const saved = await onboarding.recordCompletion()
  if (!saved) return
  tourOpen.value = false
  if (showFinish) finishOpen.value = true
  else ElMessage.success('新手引导已完成')
}

function startTour() {
  onboarding.closeWelcomeLocally()
  void nextTick(() => {
    currentStep.value = 0
    tourOpen.value = true
  })
}

function handleWelcomeModelChange(value: boolean) {
  if (!value && onboarding.welcomeOpen) void skip()
}

function handleTourClose(index: number) {
  if (index === steps.length - 1) void complete(true)
  else void skip()
}

function handleFinish() {
  void complete(true)
}

async function finishAndCreateCourse() {
  finishOpen.value = false
  await router.push('/courses')
}

async function finishToDashboard() {
  finishOpen.value = false
  await router.push('/dashboard')
}
</script>

<template>
  <el-dialog
    :model-value="onboarding.welcomeOpen"
    title="欢迎使用 StudyPilot"
    width="min(480px, calc(100vw - 32px))"
    class="onboarding-welcome"
    :close-on-click-modal="true"
    :close-on-press-escape="true"
    @update:model-value="handleWelcomeModelChange"
  >
    <p>StudyPilot 可以帮助你管理课程资料，进行带引用的智能问答、制定学习计划，并通过练习和统计跟踪学习进度。</p>
    <el-alert v-if="onboarding.error" type="error" :title="onboarding.error" :closable="false" show-icon />
    <template #footer>
      <div class="welcome-actions">
        <el-button :disabled="onboarding.saving" @click="skip">暂时跳过</el-button>
        <el-button type="primary" :loading="onboarding.saving" @click="startTour">开始引导</el-button>
      </div>
    </template>
  </el-dialog>

  <el-tour
    v-model="tourOpen"
    v-model:current="currentStep"
    :show-close="true"
    :close-on-press-escape="true"
    :target-area-clickable="true"
    @close="handleTourClose"
    @finish="handleFinish"
  >
    <el-tour-step
      v-for="(step, index) in steps"
      :key="step.target"
      :target="targetFor(step.target)"
      :title="step.title"
      :description="step.description"
      :next-button-props="{ children: index === steps.length - 1 ? '完成' : '下一步' }"
      :prev-button-props="{ children: '上一步' }"
      :scroll-into-view-options="{ block: 'center', inline: 'center' }"
    />
    <template #indicators="{ current, total }"><span class="tour-count">{{ current + 1 }} / {{ total }}</span></template>
  </el-tour>

  <div v-if="tourOpen" class="tour-skip"><el-button text type="primary" :disabled="onboarding.saving" @click="skip">跳过引导</el-button></div>

  <el-dialog v-model="finishOpen" title="新手引导完成" width="min(420px, calc(100vw - 32px))" class="onboarding-finish">
    <p>建议先创建第一门课程并上传资料。</p>
    <template #footer><div class="welcome-actions"><el-button @click="finishToDashboard">进入首页</el-button><el-button type="primary" @click="finishAndCreateCourse">创建课程</el-button></div></template>
  </el-dialog>
</template>

<style scoped>
.onboarding-welcome :deep(.el-dialog__body),.onboarding-finish :deep(.el-dialog__body){padding-top:8px}.onboarding-welcome p,.onboarding-finish p{margin:0;color:#536079;line-height:1.8}.welcome-actions{display:flex;justify-content:flex-end;gap:10px}.tour-count{color:#7c879d;font-size:12px;font-variant-numeric:tabular-nums}.tour-skip{position:fixed;right:22px;bottom:20px;z-index:2100}@media(max-width:700px){.welcome-actions{justify-content:stretch}.welcome-actions .el-button{flex:1}.tour-skip{right:12px;bottom:12px}.onboarding-welcome :deep(.el-dialog__footer),.onboarding-finish :deep(.el-dialog__footer){padding-top:12px}}
</style>
