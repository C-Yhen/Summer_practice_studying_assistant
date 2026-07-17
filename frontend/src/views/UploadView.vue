<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type UploadFile, type UploadFiles, type UploadUserFile } from 'element-plus'
import { Check, DocumentAdd, Lock, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi, documentApi } from '@/api/services'
import type { CourseListItem } from '@/types'

const ACCEPTED_EXTENSIONS = new Set(['pdf', 'txt', 'md', 'markdown'])
const route = useRoute()
const router = useRouter()
const courseId = ref<number | null>(null)
const courses = ref<CourseListItem[]>([])
const coursesLoading = ref(false)
const coursesError = ref('')
const fileList = ref<UploadUserFile[]>([])
const selectedFile = ref<File | null>(null)
const uploading = ref(false)

const canSubmit = computed(() => (
  courseId.value !== null
  && selectedFile.value !== null
  && !coursesLoading.value
  && !uploading.value
))

function queryId(value: unknown): { present: boolean; id: number | null } {
  if (value === undefined) return { present: false, id: null }
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return { present: true, id: Number.isInteger(parsed) && parsed > 0 ? parsed : null }
}

function uploadErrorMessage(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = ''
  try {
    const result = await courseApi.list()
    courses.value = result.items.filter((course) => !course.archived)
    const requested = queryId(route.query.courseId)
    if (requested.present && (requested.id === null || !courses.value.some((course) => course.id === requested.id))) {
      courseId.value = null
      coursesError.value = 'URL 中的课程不存在、不属于当前账号或已归档'
      return
    }
    if (requested.id) {
      courseId.value = requested.id
    } else if (!requested.present) {
      courseId.value = null
    } else if (courseId.value && !courses.value.some((course) => course.id === courseId.value)) {
      courseId.value = null
    }
  } catch (error) {
    courses.value = []
    courseId.value = null
    coursesError.value = uploadErrorMessage(error, '课程加载失败')
  } finally {
    coursesLoading.value = false
  }
}

function validateFile(file: File): string | null {
  const extension = file.name.split('.').pop()?.toLowerCase() || ''
  if (!ACCEPTED_EXTENSIONS.has(extension)) return '仅支持 PDF、TXT、MD 或 Markdown 文件'
  if (file.size === 0) return '不能上传空文件'
  return null
}

function handleChange(file: UploadFile, _files: UploadFiles) {
  if (!file.raw) {
    fileList.value = []
    selectedFile.value = null
    return
  }
  const validationError = validateFile(file.raw)
  if (validationError) {
    ElMessage.error(validationError)
    fileList.value = []
    selectedFile.value = null
    return
  }
  fileList.value = [file]
  selectedFile.value = file.raw
}

function handleRemove() {
  fileList.value = []
  selectedFile.value = null
}

async function startUpload() {
  if (uploading.value) return
  if (courseId.value === null) return ElMessage.warning('请选择归属课程')
  if (!selectedFile.value) return ElMessage.warning('请选择一个文件')
  const validationError = validateFile(selectedFile.value)
  if (validationError) return ElMessage.error(validationError)

  uploading.value = true
  try {
    const result = await documentApi.upload(courseId.value, selectedFile.value)
    fileList.value = []
    selectedFile.value = null
    ElMessage.success('上传成功，正在读取文档处理状态')
    await router.push({
      name: 'document-tasks',
      query: {
        courseId: String(courseId.value),
        documentId: String(result.document.id),
        taskId: result.async_task_id,
      },
    })
  } catch (error) {
    ElMessage.error(uploadErrorMessage(error, '文档上传失败'))
  } finally {
    uploading.value = false
  }
}

function openProgress() {
  router.push({
    name: 'document-tasks',
    query: courseId.value ? { courseId: String(courseId.value) } : {},
  })
}

async function selectCourse(value: number) {
  await router.replace({ name: 'upload', query: { courseId: String(value) } })
}

watch(() => route.query.courseId, () => void loadCourses(), { immediate: true })
</script>

<template>
  <div>
    <PageHeader title="资料上传" eyebrow="KNOWLEDGE INGESTION" description="上传 PDF、TXT 或 Markdown 资料，并跟踪真实解析状态。">
      <el-button plain @click="openProgress">查看处理进度</el-button>
    </PageHeader>

    <section class="upload-layout">
      <article class="content-card card-pad upload-main">
        <div class="step-indicator"><div class="active"><span>1</span><b>选择资料</b></div><i></i><div><span>2</span><b>后台解析</b></div><i></i><div><span>3</span><b>处理完成</b></div></div>

        <el-alert v-if="coursesError" :title="coursesError" type="error" :closable="false" show-icon class="state-alert">
          <template #default><el-button size="small" @click="loadCourses">重新加载课程</el-button></template>
        </el-alert>

        <el-empty v-else-if="!coursesLoading && !courses.length" description="还没有可用于上传的课程" class="course-empty">
          <el-button type="primary" @click="router.push('/courses')">前往课程管理</el-button>
        </el-empty>

        <el-form v-else v-loading="coursesLoading" label-position="top">
          <el-form-item label="归属课程（必选）">
            <el-select :model-value="courseId" placeholder="请选择当前账号的课程" :disabled="uploading" style="width:100%" @change="selectCourse">
              <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="选择文件（单文件）">
            <el-upload
              v-model:file-list="fileList"
              drag
              :auto-upload="false"
              :disabled="uploading"
              accept=".pdf,.txt,.md,.markdown"
              :on-change="handleChange"
              :on-remove="handleRemove"
              class="upload-zone"
            >
              <div class="upload-illustration"><el-icon><UploadFilled /></el-icon></div>
              <h3>拖拽一个文件到这里，或点击选择文件</h3>
              <p>支持 PDF、TXT、MD、Markdown；后端当前限制单个文件最大 10 MB</p>
              <el-button type="primary" plain :disabled="uploading">选择本地文件</el-button>
            </el-upload>
          </el-form-item>
        </el-form>

        <div v-if="uploading" class="uploading"><b>正在上传文件并创建解析任务，请勿重复提交…</b></div>
        <div class="submit-row">
          <p><el-icon><Lock /></el-icon>文件只会保存到当前账号拥有的课程中</p>
          <el-button type="primary" size="large" :loading="uploading" :disabled="!canSubmit" @click="startUpload"><el-icon><DocumentAdd /></el-icon>上传并开始解析</el-button>
        </div>
      </article>

      <aside>
        <article class="content-card card-pad pipeline-card">
          <div class="card-header"><div><h2>实际处理流程</h2><p>上传后可在处理页自动读取状态</p></div></div>
          <div class="pipeline">
            <div v-for="(step,index) in ['文件安全校验','提取文本','清洗与切块','生成 Embedding','保存文档状态']" :key="step"><span><el-icon><Check /></el-icon></span><p><b>{{ step }}</b><small>{{ ['校验类型、大小和课程权限','读取 PDF 页或文本内容','按语义边界生成文本块','使用当前配置的向量提供方','写入页数、块数与任务结果'][index] }}</small></p></div>
          </div>
        </article>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.upload-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:18px}.step-indicator{display:flex;align-items:center;justify-content:center;margin:4px 0 30px}.step-indicator div{display:flex;align-items:center;gap:7px;color:#9aa3b5;font-size:10px}.step-indicator span{width:24px;height:24px;display:grid;place-items:center;border-radius:50%;background:#eef0f4;color:#8a94a8;font-size:9px;font-weight:800}.step-indicator .active{color:#5262de}.step-indicator .active span{background:#5c6cec;color:white;box-shadow:0 0 0 5px #edf0ff}.step-indicator i{width:70px;height:1px;margin:0 12px;background:#dfe4ed}.state-alert{margin-bottom:18px}.state-alert :deep(.el-alert__content){width:100%}.state-alert :deep(.el-alert__description){display:flex;justify-content:flex-end;margin:0}.course-empty{min-height:260px}.upload-zone{width:100%}:deep(.el-upload){width:100%}:deep(.el-upload-dragger){width:100%;padding:36px 20px;border:1.5px dashed #cbd3e2;border-radius:15px;background:#fafbfe}:deep(.el-upload-dragger:hover){border-color:#7885ed;background:#f8f8ff}.upload-illustration{width:52px;height:52px;display:grid;place-items:center;margin:0 auto 13px;border-radius:15px;background:#ecefff;color:#6170e9;font-size:23px}.upload-zone h3{margin:0;color:#46516b;font-size:13px}.upload-zone p{margin:8px 0 15px;color:#949daf;font-size:9px}.uploading{margin:15px 0;padding:14px;border-radius:11px;background:#f5f7ff;color:#6572d7;font-size:10px}.submit-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding-top:18px;border-top:1px solid #edf0f4}.submit-row p{display:flex;align-items:center;gap:6px;margin:0;color:#8d96a9;font-size:9px}.pipeline-card{margin-bottom:14px}.pipeline{display:grid;gap:14px}.pipeline>div{display:flex;gap:10px}.pipeline>div>span{width:25px;height:25px;display:grid;place-items:center;flex:none;border-radius:8px;background:#ebf8f5;color:#14a187;font-size:11px}.pipeline p{display:flex;flex-direction:column;margin:0}.pipeline b{color:#4b5670;font-size:10px}.pipeline small{margin-top:4px;color:#959daf;font-size:8px;line-height:1.4}@media(max-width:1000px){.upload-layout{grid-template-columns:1fr}}@media(max-width:700px){.step-indicator i{width:22px}.step-indicator b{display:none}.submit-row{align-items:stretch;flex-direction:column}.submit-row .el-button{width:100%}}
</style>
