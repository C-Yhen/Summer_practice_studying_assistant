<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import { courseApi, practiceApi } from '@/api/services'
import { getApiErrorMessage } from '@/api/client'
import type {
  CourseListItem,
  PracticeAttemptRequest,
  PracticeAttemptResult,
  PracticeQuestion,
  PracticeSummary,
} from '@/types'

interface PendingSubmission {
  courseId: number
  mode: 'all' | 'wrong'
  questionId: number
  payload: PracticeAttemptRequest
}

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const courseId = ref<number | null>(null)
const questions = ref<PracticeQuestion[]>([])
const summary = ref<PracticeSummary | null>(null)
const index = ref(0)
const selected = ref('')
const result = ref<PracticeAttemptResult | null>(null)
const pendingSubmission = ref<PendingSubmission | null>(null)
const loading = ref(false)
const booting = ref(false)
const submitting = ref(false)
const error = ref('')
const started = ref<number | null>(null)
let requestVersion = 0

const mode = computed<'all' | 'wrong'>(() => route.query.mode === 'wrong' ? 'wrong' : 'all')
const question = computed(() => questions.value[index.value])
const progress = computed(() => questions.value.length
  ? Math.round((index.value + 1) / questions.value.length * 100)
  : 0)

function resetAnswer(startTimer = true) {
  selected.value = ''
  result.value = null
  pendingSubmission.value = null
  started.value = startTimer && question.value ? Date.now() : null
}

async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  questions.value = []
  summary.value = null
  resetAnswer(false)
  try {
    const availableCourses = (await courseApi.list()).items.filter((item) => !item.archived)
    if (version !== requestVersion) return
    courses.value = availableCourses
    const routeCourseId = Number(route.query.courseId)
    const resolvedCourseId = availableCourses.some((item) => item.id === routeCourseId)
      ? routeCourseId
      : (availableCourses[0]?.id ?? null)
    courseId.value = resolvedCourseId
    if (!resolvedCourseId) return
    if (String(resolvedCourseId) !== route.query.courseId) {
      await router.replace({
        query: { ...route.query, courseId: String(resolvedCourseId), mode: mode.value },
      })
      return
    }
    const data = await practiceApi.questions(resolvedCourseId, mode.value)
    if (version !== requestVersion || resolvedCourseId !== courseId.value) return
    questions.value = data.items
    summary.value = data.summary
    index.value = 0
    resetAnswer(true)
  } catch (loadError) {
    if (version === requestVersion) {
      error.value = getApiErrorMessage(loadError, '练习加载失败')
    }
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

async function bootstrap() {
  if (!courseId.value || submitting.value) return
  booting.value = true
  try {
    await practiceApi.bootstrap(courseId.value)
    await load()
  } catch (bootstrapError) {
    ElMessage.error(getApiErrorMessage(bootstrapError, '生成基础自测题失败'))
  } finally {
    booting.value = false
  }
}

function chooseAnswer() {
  if (!submitting.value) pendingSubmission.value = null
}

async function submit() {
  const currentCourseId = courseId.value
  const currentQuestion = question.value
  if (!currentCourseId || !currentQuestion || !selected.value || submitting.value) return

  let pending = pendingSubmission.value
  if (
    !pending
    || pending.courseId !== currentCourseId
    || pending.mode !== mode.value
    || pending.questionId !== currentQuestion.id
    || pending.payload.selected_option !== selected.value
  ) {
    pending = {
      courseId: currentCourseId,
      mode: mode.value,
      questionId: currentQuestion.id,
      payload: {
        submission_id: crypto.randomUUID(),
        selected_option: selected.value,
        elapsed_seconds: Math.max(0, Math.round((Date.now() - (started.value ?? Date.now())) / 1000)),
      },
    }
    pendingSubmission.value = pending
  }

  submitting.value = true
  try {
    const response = await practiceApi.submit(
      pending.courseId,
      pending.questionId,
      pending.payload,
    )
    result.value = response
    summary.value = response.summary
    pendingSubmission.value = null
  } catch (submitError) {
    ElMessage.error(getApiErrorMessage(submitError, '提交失败，请使用原提交重试'))
  } finally {
    submitting.value = false
  }
}

function move(step: number) {
  if (submitting.value) return
  index.value = Math.max(0, Math.min(questions.value.length - 1, index.value + step))
  resetAnswer(true)
}

function changeCourse(nextCourseId: number) {
  if (submitting.value) return
  pendingSubmission.value = null
  void router.replace({ query: { courseId: String(nextCourseId), mode: mode.value } })
}

watch(
  () => [route.query.courseId, route.query.mode],
  () => {
    if (!submitting.value) void load()
  },
)
onMounted(load)
</script>

<template>
  <div>
    <PageHeader
      :title="mode === 'wrong' ? '错题复习' : '练习答题'"
      eyebrow="SMART PRACTICE"
      :description="question ? `当前课程：${courses.find((item) => item.id === courseId)?.name}` : '选择真实课程并完成基础自测'"
    >
      <el-select
        v-model="courseId"
        style="width: 200px"
        :disabled="submitting || loading"
        @change="changeCourse"
      >
        <el-option
          v-for="course in courses"
          :key="course.id"
          :label="course.name"
          :value="course.id"
        />
      </el-select>
    </PageHeader>

    <el-alert v-if="error" :title="error" type="error" />
    <div v-else v-loading="loading">
      <el-empty v-if="!courseId" description="暂无真实课程" />
      <el-empty
        v-else-if="!questions.length"
        :description="mode === 'wrong' ? '没有待复习错题' : '暂无题目；请先生成并确认学习计划以获得知识点'"
      >
        <el-button
          v-if="mode === 'all'"
          type="primary"
          :loading="booting"
          :disabled="submitting"
          @click="bootstrap"
        >
          生成基础自测题
        </el-button>
      </el-empty>

      <section v-else class="content-card card-pad">
        <el-progress :percentage="progress" />
        <p>
          {{ index + 1 }} / {{ questions.length }} · 当前正确率
          {{ Math.round((summary?.accuracy || 0) * 100) }}%
        </p>
        <h2>{{ question.stem }}</h2>
        <el-radio-group
          v-model="selected"
          :disabled="Boolean(result) || submitting"
          @change="chooseAnswer"
        >
          <el-radio
            v-for="option in question.options"
            :key="option.key"
            :value="option.key"
            border
          >
            {{ option.key }}. {{ option.text }}
          </el-radio>
        </el-radio-group>

        <div v-if="result" class="result">
          <b>{{ result.is_correct ? '回答正确' : `回答错误，正确答案：${result.correct_option}` }}</b>
          <p>{{ result.explanation }}</p>
          <p>
            规则提示：关联知识点 {{ result.knowledge_point || '未关联' }}；当前掌握度
            {{ result.mastery_score === null ? '暂无' : `${Math.round(result.mastery_score * 100)}%` }}
          </p>
          <el-button
            v-if="!result.is_correct"
            @click="router.push({ name: 'wrong-book', query: { courseId } })"
          >
            查看错题本
          </el-button>
        </div>

        <footer>
          <el-button :disabled="index === 0 || submitting" @click="move(-1)">
            上一题
          </el-button>
          <el-button
            v-if="!result"
            type="primary"
            :loading="submitting"
            :disabled="!selected || submitting"
            @click="submit"
          >
            {{ submitting ? '提交中' : '提交答案' }}
          </el-button>
          <el-button
            v-else
            type="primary"
            :disabled="index === questions.length - 1 || submitting"
            @click="move(1)"
          >
            下一题
          </el-button>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.card-pad { padding: 24px; }
.el-radio-group { display: grid; gap: 10px; margin: 20px 0; }
.result { margin: 18px 0; padding: 14px; background: #f5f8ff; border-radius: 10px; }
footer { display: flex; justify-content: space-between; }
</style>
