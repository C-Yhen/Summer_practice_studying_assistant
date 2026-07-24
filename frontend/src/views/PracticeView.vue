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
  WrongBookEntry,
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
const wrongItems = ref<WrongBookEntry[]>([])
const wrongSummary = ref({ pending: 0, mastered: 0, repeated_wrong: 0 })
const wrongStatus = ref<'all' | 'pending' | 'mastered'>('all')
const wrongQuery = ref('')
const wrongUpdating = ref(false)
const expandedWrongId = ref<number | null>(null)
let requestVersion = 0

const activeTab = computed<'practice' | 'wrong'>(() => route.query.tab === 'wrong' ? 'wrong' : 'practice')
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
        query: {
          courseId: String(resolvedCourseId),
          tab: activeTab.value,
          ...(activeTab.value === 'practice' ? { mode: mode.value } : {}),
        },
      })
      return
    }

    if (activeTab.value === 'wrong') {
      expandedWrongId.value = null
      const data = await practiceApi.wrongBook(resolvedCourseId, wrongStatus.value, wrongQuery.value.trim())
      if (version !== requestVersion || resolvedCourseId !== courseId.value) return
      wrongItems.value = data.items
      wrongSummary.value = data.summary
    } else {
      questions.value = []
      summary.value = null
      resetAnswer(false)
      const data = await practiceApi.questions(resolvedCourseId, mode.value)
      if (version !== requestVersion || resolvedCourseId !== courseId.value) return
      questions.value = data.items
      summary.value = data.summary
      index.value = 0
      resetAnswer(true)
    }
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
  if (submitting.value || wrongUpdating.value) return
  pendingSubmission.value = null
  void router.replace({
    query: {
      courseId: String(nextCourseId),
      tab: activeTab.value,
      ...(activeTab.value === 'practice' ? { mode: mode.value } : {}),
    },
  })
}

function switchTab(next: string | number | boolean | undefined) {
  if (submitting.value || wrongUpdating.value) return
  const tab = next === 'wrong' ? 'wrong' : 'practice'
  void router.replace({
    query: {
      ...(courseId.value ? { courseId: String(courseId.value) } : {}),
      tab,
      ...(tab === 'practice' ? { mode: mode.value } : {}),
    },
  })
}

function switchMode(next: string | number | boolean | undefined) {
  if (submitting.value) return
  const nextMode = next === 'wrong' ? 'wrong' : 'all'
  void router.replace({
    query: {
      ...(courseId.value ? { courseId: String(courseId.value) } : {}),
      tab: 'practice',
      mode: nextMode,
    },
  })
}

async function updateWrong(entryId: number, next: 'mastered' | 'removed') {
  if (!courseId.value || wrongUpdating.value) return
  const currentCourseId = courseId.value
  wrongUpdating.value = true
  try {
    await practiceApi.updateWrong(currentCourseId, entryId, next)
    ElMessage.success(next === 'mastered' ? '已标记为掌握' : '已从错题清单移除')
    if (courseId.value === currentCourseId) await load()
  } catch (updateError) {
    ElMessage.error(getApiErrorMessage(updateError, '操作失败'))
  } finally {
    wrongUpdating.value = false
  }
}

function reviewWrongQuestions() {
  if (!wrongSummary.value.pending) return
  void router.replace({
    query: {
      ...(courseId.value ? { courseId: String(courseId.value) } : {}),
      tab: 'practice',
      mode: 'wrong',
    },
  })
}

watch(
  () => [route.query.courseId, route.query.tab, route.query.mode],
  () => {
    if (!submitting.value && !wrongUpdating.value) void load()
  },
)
onMounted(load)
</script>

<template>
  <div>
    <PageHeader
      title="练习与错题"
      eyebrow="SMART PRACTICE"
      description="完成练习、查看即时解析，并把错题转化为下一轮复习。"
    >
      <el-select
        v-model="courseId"
        class="course-select"
        :disabled="submitting || wrongUpdating || loading"
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

    <section class="practice-tabs content-card">
      <el-tabs :model-value="activeTab" @tab-change="switchTab">
        <el-tab-pane label="开始练习" name="practice">
          <div class="tab-body">
            <el-alert v-if="error" :title="error" type="error" show-icon />
            <div v-else v-loading="loading">
              <el-empty v-if="!courseId" description="还没有课程，请先创建课程并上传资料">
                <el-button type="primary" @click="router.push('/courses')">去创建课程</el-button>
              </el-empty>

              <template v-else>
                <div class="practice-toolbar">
                  <div>
                    <h2>{{ mode === 'wrong' ? '错题复习' : '课程练习' }}</h2>
                    <p>
                      {{ mode === 'wrong'
                        ? '只练习尚未掌握的错题，答对后继续巩固。'
                        : '根据当前课程知识点进行自测，错误题目会自动进入错题清单。' }}
                    </p>
                  </div>
                  <el-segmented
                    :model-value="mode"
                    :options="[
                      { label: '课程练习', value: 'all' },
                      { label: '错题复习', value: 'wrong' },
                    ]"
                    :disabled="submitting"
                    @change="switchMode"
                  />
                </div>

                <div class="summary-strip">
                  <div><span>累计答题</span><b>{{ summary?.total_attempts || 0 }}</b></div>
                  <div><span>当前正确率</span><b>{{ Math.round((summary?.accuracy || 0) * 100) }}%</b></div>
                  <div><span>待复习错题</span><b>{{ summary?.pending_wrong_count || 0 }}</b></div>
                </div>

                <el-empty
                  v-if="!questions.length"
                  :description="mode === 'wrong' ? '太棒了，当前没有待复习错题' : '当前课程还没有可练习题目'"
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
                  <el-button v-else @click="switchMode('all')">返回课程练习</el-button>
                </el-empty>

                <section v-else class="question-card">
                  <div class="question-meta">
                    <span>第 {{ index + 1 }} / {{ questions.length }} 题</span>
                    <span>{{ question.knowledge_point || '综合知识点' }}</span>
                    <span>{{ question.difficulty === 'hard' ? '较难' : question.difficulty === 'easy' ? '基础' : '适中' }}</span>
                  </div>
                  <el-progress :percentage="progress" :show-text="false" />
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
                      <b>{{ option.key }}</b><span>{{ option.text }}</span>
                    </el-radio>
                  </el-radio-group>

                  <div v-if="result" class="result" :class="result.is_correct ? 'is-correct' : 'is-wrong'">
                    <div class="result-title">
                      {{ result.is_correct ? '回答正确' : `回答错误，正确答案是 ${result.correct_option}` }}
                    </div>
                    <p>{{ result.explanation }}</p>
                    <p class="result-note">
                      {{ result.knowledge_point || '综合知识点' }} · 掌握度
                      {{ result.mastery_score === null ? '暂未评估' : `${Math.round(result.mastery_score * 100)}%` }}
                    </p>
                    <el-button v-if="!result.is_correct" plain @click="switchTab('wrong')">
                      查看错题清单
                    </el-button>
                  </div>

                  <footer>
                    <el-button :disabled="index === 0 || submitting" @click="move(-1)">上一题</el-button>
                    <el-button
                      v-if="!result"
                      type="primary"
                      :loading="submitting"
                      :disabled="!selected || submitting"
                      @click="submit"
                    >
                      {{ submitting ? '正在提交' : '提交答案' }}
                    </el-button>
                    <el-button
                      v-else-if="index < questions.length - 1"
                      type="primary"
                      :disabled="submitting"
                      @click="move(1)"
                    >
                      下一题
                    </el-button>
                    <el-button v-else type="primary" @click="switchTab('wrong')">查看练习结果</el-button>
                  </footer>
                </section>
              </template>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane name="wrong">
          <template #label>
            <span>错题清单 <em v-if="wrongSummary.pending">{{ wrongSummary.pending }}</em></span>
          </template>
          <div class="tab-body">
            <el-alert v-if="error" :title="error" type="error" show-icon />
            <div v-else v-loading="loading || wrongUpdating">
              <el-empty v-if="!courseId" description="还没有课程，请先创建课程并上传资料">
                <el-button type="primary" @click="router.push('/courses')">去创建课程</el-button>
              </el-empty>

              <template v-else>
                <div class="wrong-hero">
                  <div>
                    <span class="section-kicker">复习闭环</span>
                    <h2>集中处理薄弱知识点</h2>
                    <p>按状态筛选错题，查看解析后可以标记掌握；需要巩固时直接进入错题复习。</p>
                  </div>
                  <el-button
                    type="primary"
                    :disabled="!wrongSummary.pending || wrongUpdating"
                    @click="reviewWrongQuestions"
                  >
                    复习 {{ wrongSummary.pending }} 道待掌握错题
                  </el-button>
                </div>

                <div class="summary-strip wrong-summary">
                  <div><span>待掌握</span><b>{{ wrongSummary.pending }}</b></div>
                  <div><span>重复答错</span><b>{{ wrongSummary.repeated_wrong }}</b></div>
                  <div><span>已掌握</span><b>{{ wrongSummary.mastered }}</b></div>
                </div>

                <div class="wrong-toolbar">
                  <el-radio-group v-model="wrongStatus" :disabled="wrongUpdating" @change="load">
                    <el-radio-button value="all">全部</el-radio-button>
                    <el-radio-button value="pending">待掌握</el-radio-button>
                    <el-radio-button value="mastered">已掌握</el-radio-button>
                  </el-radio-group>
                  <el-input
                    v-model="wrongQuery"
                    clearable
                    placeholder="搜索题干或知识点"
                    :disabled="wrongUpdating"
                    @change="load"
                    @clear="load"
                  />
                </div>

                <el-empty v-if="!wrongItems.length" description="没有符合当前条件的错题">
                  <el-button v-if="wrongStatus !== 'all' || wrongQuery" @click="wrongStatus = 'all'; wrongQuery = ''; load()">
                    查看全部错题
                  </el-button>
                  <el-button v-else type="primary" @click="switchTab('practice')">开始一次练习</el-button>
                </el-empty>

                <div v-else class="wrong-list">
                  <article v-for="item in wrongItems" :key="item.id" class="wrong-item">
                    <div class="wrong-item-top">
                      <div>
                        <div class="wrong-tags">
                          <span>{{ item.question.knowledge_point || '综合知识点' }}</span>
                          <span :class="item.status">{{ item.status === 'pending' ? '待掌握' : '已掌握' }}</span>
                          <span v-if="item.wrong_count > 1" class="danger">已错 {{ item.wrong_count }} 次</span>
                        </div>
                        <h3>{{ item.question.stem }}</h3>
                      </div>
                      <div class="wrong-answer">
                        <span>你的答案 <b>{{ item.last_selected_option }}</b></span>
                        <span>正确答案 <b>{{ item.question.correct_option }}</b></span>
                      </div>
                    </div>
                    <button class="explanation-toggle" type="button" @click="expandedWrongId = expandedWrongId === item.id ? null : item.id">
                      {{ expandedWrongId === item.id ? '收起解析' : '查看答案解析' }}
                    </button>
                    <div v-if="expandedWrongId === item.id" class="explanation-panel">
                      <b>为什么这样选？</b>
                      <p>{{ item.question.explanation || '当前题目暂未提供解析。' }}</p>
                      <small>
                        当前掌握度：{{ item.mastery_score === null ? '暂未评估' : `${Math.round(item.mastery_score * 100)}%` }}
                      </small>
                    </div>
                    <div class="wrong-actions">
                      <el-button
                        v-if="item.status === 'pending'"
                        type="primary"
                        plain
                        :disabled="wrongUpdating"
                        @click="updateWrong(item.id, 'mastered')"
                      >
                        标记已掌握
                      </el-button>
                      <el-button text type="danger" :disabled="wrongUpdating" @click="updateWrong(item.id, 'removed')">
                        移出清单
                      </el-button>
                    </div>
                  </article>
                </div>
              </template>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<style scoped>
.course-select { width: 220px; }
.practice-tabs { overflow: hidden; }
.practice-tabs :deep(.el-tabs__header) { margin: 0; padding: 0 24px; border-bottom: 1px solid #e9edf5; }
.practice-tabs :deep(.el-tabs__nav-wrap::after) { display: none; }
.practice-tabs :deep(.el-tabs__item) { height: 58px; font-weight: 700; color: #64748b; }
.practice-tabs :deep(.el-tabs__item.is-active) { color: #3157d8; }
.practice-tabs :deep(.el-tabs__active-bar) { height: 3px; border-radius: 3px; background: #3157d8; }
.practice-tabs :deep(.el-tabs__item em) { display: inline-grid; min-width: 21px; height: 21px; margin-left: 7px; padding: 0 6px; place-items: center; border-radius: 999px; background: #fee2e2; color: #c24141; font-size: 11px; font-style: normal; }
.tab-body { min-height: 520px; padding: 26px; }
.practice-toolbar, .wrong-hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 22px; }
.practice-toolbar h2, .wrong-hero h2 { margin: 0 0 6px; color: #16213e; font-size: 22px; }
.practice-toolbar p, .wrong-hero p { max-width: 700px; margin: 0; color: #6b7892; font-size: 13px; line-height: 1.7; }
.section-kicker { display: block; margin-bottom: 6px; color: #3157d8; font-size: 11px; font-weight: 800; letter-spacing: .08em; }
.summary-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 22px; }
.summary-strip div { display: flex; align-items: center; justify-content: space-between; min-height: 74px; padding: 15px 18px; border: 1px solid #e6ebf4; border-radius: 14px; background: #f9fbff; }
.summary-strip span { color: #6b7892; font-size: 12px; }
.summary-strip b { color: #192442; font-size: 24px; }
.question-card { max-width: 900px; margin: 0 auto; padding: 28px; border: 1px solid #e4e9f3; border-radius: 18px; background: #fff; box-shadow: 0 14px 36px rgba(30, 49, 94, .07); }
.question-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.question-meta span { padding: 5px 9px; border-radius: 999px; background: #f0f4ff; color: #526486; font-size: 11px; }
.question-card > h2 { margin: 26px 0 20px; color: #17213c; font-size: 20px; line-height: 1.65; }
.question-card .el-radio-group { display: grid; gap: 11px; margin: 0 0 20px; }
.question-card .el-radio-group :deep(.el-radio) { align-items: flex-start; height: auto; min-height: 48px; margin-right: 0; padding: 13px 15px; white-space: normal; border-radius: 12px; }
.question-card .el-radio-group :deep(.el-radio__input) { margin-top: 3px; }
.question-card .el-radio-group :deep(.el-radio__label) { display: inline-flex; gap: 12px; white-space: normal; color: #35415d; line-height: 1.6; }
.question-card .el-radio-group :deep(.el-radio__label b) { color: #3157d8; }
.result { margin: 20px 0; padding: 18px; border: 1px solid #dce5ff; border-radius: 14px; background: #f5f8ff; }
.result.is-correct { border-color: #ccebdd; background: #f2fbf7; }
.result.is-wrong { border-color: #f2d5d5; background: #fff7f7; }
.result-title { margin-bottom: 8px; color: #1f2d4d; font-weight: 800; }
.result p { margin: 6px 0; color: #53617b; font-size: 13px; line-height: 1.7; }
.result .result-note { color: #7c879d; font-size: 12px; }
footer { position: relative; z-index: 1; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; margin-top: 22px; }
.wrong-summary div:first-child b { color: #d25b5b; }
.wrong-summary div:nth-child(2) b { color: #d48a32; }
.wrong-summary div:last-child b { color: #2f8f68; }
.wrong-toolbar { display: flex; justify-content: space-between; gap: 14px; margin-bottom: 20px; }
.wrong-toolbar .el-input { max-width: 340px; }
.wrong-list { display: grid; gap: 14px; }
.wrong-item { padding: 20px; border: 1px solid #e5eaf3; border-radius: 16px; background: #fff; transition: border-color .2s, box-shadow .2s; }
.wrong-item:hover { border-color: #cad6f8; box-shadow: 0 10px 26px rgba(37, 58, 112, .07); }
.wrong-item-top { display: flex; justify-content: space-between; gap: 24px; }
.wrong-item-top > div:first-child { min-width: 0; flex: 1; }
.wrong-tags { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; }
.wrong-tags span { padding: 4px 8px; border-radius: 999px; background: #f0f4fb; color: #60708d; font-size: 10px; font-weight: 700; }
.wrong-tags .pending { background: #fff0e8; color: #b75a2c; }
.wrong-tags .mastered { background: #eaf8f1; color: #277c5a; }
.wrong-tags .danger { background: #feecec; color: #bd4545; }
.wrong-item h3 { margin: 0; color: #1e2944; font-size: 15px; line-height: 1.65; }
.wrong-answer { display: flex; flex-direction: column; align-items: flex-end; gap: 7px; min-width: 130px; color: #7b879c; font-size: 11px; }
.wrong-answer b { display: inline-grid; width: 24px; height: 24px; margin-left: 4px; place-items: center; border-radius: 7px; background: #edf2ff; color: #3157d8; font-size: 12px; }
.explanation-toggle { margin-top: 14px; padding: 0; border: 0; background: transparent; color: #3157d8; cursor: pointer; font-size: 12px; font-weight: 700; }
.explanation-panel { margin-top: 12px; padding: 15px 17px; border-radius: 12px; background: #f7f9fd; color: #55637c; font-size: 12px; line-height: 1.7; }
.explanation-panel b { color: #26334f; }
.explanation-panel p { margin: 5px 0; }
.explanation-panel small { color: #8490a5; }
.wrong-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; padding-top: 14px; border-top: 1px solid #eef1f6; }

@media (max-width: 760px) {
  .course-select { width: 100%; }
  .tab-body { padding: 18px; }
  .practice-toolbar, .wrong-hero, .wrong-item-top { align-items: stretch; flex-direction: column; }
  .summary-strip { grid-template-columns: 1fr; }
  .wrong-toolbar { flex-direction: column; }
  .wrong-toolbar .el-input { max-width: none; }
  .wrong-answer { align-items: flex-start; }
  .question-card { padding: 20px; }
}
</style>
