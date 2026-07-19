<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import { courseApi, practiceApi } from '@/api/services'
import { getApiErrorMessage } from '@/api/client'
import type { CourseListItem, WrongBookEntry } from '@/types'

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const courseId = ref<number | null>(null)
const items = ref<WrongBookEntry[]>([])
const summary = ref({ pending: 0, mastered: 0, repeated_wrong: 0 })
const status = ref<'all' | 'pending' | 'mastered'>('all')
const q = ref('')
const loading = ref(false)
const updating = ref(false)
const error = ref('')
const expanded = ref<number | null>(null)
let requestVersion = 0

async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  items.value = []
  expanded.value = null
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
      await router.replace({ query: { courseId: String(resolvedCourseId) } })
      return
    }
    const data = await practiceApi.wrongBook(resolvedCourseId, status.value, q.value)
    if (version !== requestVersion || resolvedCourseId !== courseId.value) return
    items.value = data.items
    summary.value = data.summary
  } catch (loadError) {
    if (version === requestVersion) {
      error.value = getApiErrorMessage(loadError, '错题本加载失败')
    }
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

async function update(entryId: number, next: 'mastered' | 'removed') {
  if (!courseId.value || updating.value) return
  const currentCourseId = courseId.value
  updating.value = true
  try {
    await practiceApi.updateWrong(currentCourseId, entryId, next)
    if (courseId.value === currentCourseId) await load()
  } catch (updateError) {
    ElMessage.error(getApiErrorMessage(updateError, '操作失败'))
  } finally {
    updating.value = false
  }
}

function changeCourse(nextCourseId: number) {
  if (updating.value) return
  items.value = []
  summary.value = { pending: 0, mastered: 0, repeated_wrong: 0 }
  void router.replace({ query: { courseId: String(nextCourseId) } })
}

watch(() => route.query.courseId, () => void load())
onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="错题本" eyebrow="ERROR REVIEW" description="真实错题、掌握度和规则复习提示。">
      <el-select
        v-model="courseId"
        style="width: 200px"
        :disabled="loading || updating"
        @change="changeCourse"
      >
        <el-option
          v-for="course in courses"
          :key="course.id"
          :value="course.id"
          :label="course.name"
        />
      </el-select>
      <el-button
        type="primary"
        :disabled="!summary.pending || loading || updating"
        @click="router.push({ name: 'practice', query: { courseId, mode: 'wrong' } })"
      >
        开始错题复习
      </el-button>
    </PageHeader>

    <el-alert v-if="error" :title="error" type="error" />
    <div v-else v-loading="loading">
      <section class="summary">
        <div>待掌握 <b>{{ summary.pending }}</b></div>
        <div>重复错误 <b>{{ summary.repeated_wrong }}</b></div>
        <div>已掌握 <b>{{ summary.mastered }}</b></div>
      </section>
      <div class="toolbar">
        <el-radio-group v-model="status" :disabled="updating" @change="load">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="pending">待掌握</el-radio-button>
          <el-radio-button value="mastered">已掌握</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="q"
          placeholder="搜索题干或知识点"
          :disabled="updating"
          @change="load"
        />
      </div>
      <el-empty v-if="!items.length" description="没有符合条件的真实错题" />
      <article v-for="item in items" :key="item.id" class="content-card item">
        <h2>{{ item.question.stem }}</h2>
        <p>
          {{ item.question.knowledge_point || '未关联知识点' }} · 错误
          {{ item.wrong_count }} 次 · 你的答案 {{ item.last_selected_option }} →
          正确答案 {{ item.question.correct_option }}
        </p>
        <el-button text @click="expanded = expanded === item.id ? null : item.id">
          查看解析
        </el-button>
        <p v-if="expanded === item.id" class="explain">
          错题解析：{{ item.question.explanation }}
        </p>
        <el-button
          v-if="item.status === 'pending'"
          :disabled="updating"
          @click="update(item.id, 'mastered')"
        >
          标记已掌握
        </el-button>
        <el-button text type="danger" :disabled="updating" @click="update(item.id, 'removed')">
          移除
        </el-button>
      </article>
    </div>
  </div>
</template>

<style scoped>
.summary { display: flex; gap: 14px; margin-bottom: 15px; }
.summary div, .item { padding: 16px; }
.summary div { flex: 1; background: #fff; border-radius: 10px; }
.summary b { font-size: 20px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 14px; }
.item { margin-bottom: 10px; }
.item h2 { font-size: 13px; }
.item p, .explain { font-size: 10px; color: #65728a; }
</style>
