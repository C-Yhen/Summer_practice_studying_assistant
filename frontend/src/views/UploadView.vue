<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type UploadFile, type UploadFiles, type UploadUserFile } from 'element-plus'
import { Check, DocumentAdd, InfoFilled, Lock, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const courseId = ref('1')
const fileList = ref<UploadUserFile[]>([])
const parsingMode = ref('balanced')
const uploadProgress = ref(0)
const uploading = ref(false)
const canSubmit = computed(() => fileList.value.length > 0 && !uploading.value)

function handleChange(_file: UploadFile, files: UploadFiles) { fileList.value = files }
function startUpload() {
  if (!canSubmit.value) return
  uploading.value = true
  const timer = window.setInterval(() => {
    uploadProgress.value += 14
    if (uploadProgress.value >= 100) {
      window.clearInterval(timer)
      uploadProgress.value = 100
      ElMessage.success('上传完成，文档解析任务已进入队列')
      window.setTimeout(() => router.push('/documents/tasks'), 500)
    }
  }, 120)
}
</script>

<template>
  <div>
    <PageHeader title="资料上传" eyebrow="KNOWLEDGE INGESTION" description="上传课程资料，系统将自动解析、切块并建立可追溯的 RAG 知识库。">
      <el-button plain @click="router.push('/documents/tasks')">查看处理进度</el-button>
    </PageHeader>
    <section class="upload-layout">
      <article class="content-card card-pad upload-main">
        <div class="step-indicator"><div class="active"><span>1</span><b>选择资料</b></div><i></i><div><span>2</span><b>解析建库</b></div><i></i><div><span>3</span><b>可用于问答</b></div></div>
        <el-form label-position="top">
          <el-form-item label="归属课程"><el-select v-model="courseId" style="width:100%"><el-option label="数据库系统 · CS-DB-2026" value="1" /><el-option label="计算机网络 · CS-NET-2026" value="2" /><el-option label="操作系统 · CS-OS-2026" value="3" /></el-select></el-form-item>
          <el-form-item label="选择文件">
            <el-upload v-model:file-list="fileList" drag multiple :auto-upload="false" accept=".pdf,.ppt,.pptx,.doc,.docx,.txt,.md" :on-change="handleChange" class="upload-zone">
              <div class="upload-illustration"><el-icon><UploadFilled /></el-icon></div><h3>拖拽资料到这里，或点击选择文件</h3><p>支持 PDF、PPT、Word、TXT、Markdown，单个文件最大 50 MB</p><el-button type="primary" plain>选择本地文件</el-button>
            </el-upload>
          </el-form-item>
          <el-form-item label="解析策略">
            <el-radio-group v-model="parsingMode" class="strategy-group">
              <el-radio value="fast"><span><b>快速解析</b><small>适合纯文本讲义，速度优先</small></span></el-radio>
              <el-radio value="balanced"><span><b>智能平衡</b><small>保留页码与章节，推荐</small></span><em>推荐</em></el-radio>
              <el-radio value="quality"><span><b>精细解析</b><small>复杂排版与表格，质量优先</small></span></el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <div v-if="uploading" class="uploading"><div><b>正在上传 {{ fileList.length }} 个文件</b><span>{{ uploadProgress }}%</span></div><el-progress :percentage="uploadProgress" :show-text="false" :stroke-width="8" /></div>
        <div class="submit-row"><p><el-icon><Lock /></el-icon>文件仅用于你的课程知识库，所有访问都经过权限校验</p><el-button type="primary" size="large" :disabled="!canSubmit" @click="startUpload"><el-icon><DocumentAdd /></el-icon>上传并开始解析</el-button></div>
      </article>

      <aside>
        <article class="content-card card-pad pipeline-card"><div class="card-header"><div><h2>解析流水线</h2><p>Celery 长时任务，进度可追踪</p></div></div><div class="pipeline"><div v-for="(step,index) in ['文件安全校验','提取文本与结构','清洗并智能切块','生成 Embedding','写入 pgvector','清理旧版本缓存']" :key="step"><span><el-icon><Check /></el-icon></span><p><b>{{ step }}</b><small>{{ ['校验类型、大小和访问权限','保留页码、章节与版本号','按语义边界生成文本块','批量调用向量模型','建立向量索引与过滤字段','保证问答不命中过期资料'][index] }}</small></p></div></div></article>
        <article class="version-note"><el-icon><InfoFilled /></el-icon><div><b>文档版本受控</b><p>同名资料更新后会生成新版本；旧版问答与检索缓存自动失效，历史版本仍可追溯。</p></div></article>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.upload-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px}.step-indicator{display:flex;align-items:center;justify-content:center;margin:4px 0 30px}.step-indicator div{display:flex;align-items:center;gap:7px;color:#9aa3b5;font-size:10px}.step-indicator span{width:24px;height:24px;display:grid;place-items:center;border-radius:50%;background:#eef0f4;color:#8a94a8;font-size:9px;font-weight:800}.step-indicator .active{color:#5262de}.step-indicator .active span{background:#5c6cec;color:white;box-shadow:0 0 0 5px #edf0ff}.step-indicator i{width:70px;height:1px;margin:0 12px;background:#dfe4ed}.upload-zone{width:100%}:deep(.el-upload){width:100%}:deep(.el-upload-dragger){width:100%;padding:36px 20px;border:1.5px dashed #cbd3e2;border-radius:15px;background:#fafbfe}:deep(.el-upload-dragger:hover){border-color:#7885ed;background:#f8f8ff}.upload-illustration{width:52px;height:52px;display:grid;place-items:center;margin:0 auto 13px;border-radius:15px;background:#ecefff;color:#6170e9;font-size:23px}.upload-zone h3{margin:0;color:#46516b;font-size:13px}.upload-zone p{margin:8px 0 15px;color:#949daf;font-size:9px}.strategy-group{width:100%;display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.strategy-group .el-radio{position:relative;height:auto;margin:0;padding:14px;border:1px solid #e2e6ef;border-radius:12px;background:#fafbfc}.strategy-group .el-radio.is-checked{border-color:#8792ed;background:#f7f7ff}:deep(.strategy-group .el-radio__label){flex:1}.strategy-group span{display:flex;flex-direction:column}.strategy-group b{font-size:10px}.strategy-group small{margin-top:5px;color:#929bad;font-size:8px}.strategy-group em{position:absolute;right:8px;top:7px;padding:2px 5px;border-radius:5px;background:#e9ecff;color:#5d6be5;font-size:7px;font-style:normal}.uploading{margin:15px 0;padding:13px;border-radius:11px;background:#f5f7ff}.uploading>div{display:flex;justify-content:space-between;margin-bottom:8px;color:#6572d7;font-size:10px}.submit-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding-top:18px;border-top:1px solid #edf0f4}.submit-row p{display:flex;align-items:center;gap:6px;margin:0;color:#8d96a9;font-size:9px}.pipeline-card{margin-bottom:14px}.pipeline{display:grid;gap:14px}.pipeline>div{display:flex;gap:10px}.pipeline>div>span{width:25px;height:25px;display:grid;place-items:center;flex:none;border-radius:8px;background:#ebf8f5;color:#14a187;font-size:11px}.pipeline p{display:flex;flex-direction:column;margin:0}.pipeline b{color:#4b5670;font-size:10px}.pipeline small{margin-top:4px;color:#959daf;font-size:8px;line-height:1.4}.version-note{display:flex;gap:11px;padding:16px;border:1px solid #f1e2cb;border-radius:14px;background:#fff9ef;color:#db852e}.version-note>div{display:flex;flex-direction:column}.version-note b{font-size:10px}.version-note p{margin:5px 0 0;color:#987552;font-size:8px;line-height:1.6}@media(max-width:1000px){.upload-layout{grid-template-columns:1fr}.upload-layout aside{display:grid;grid-template-columns:1fr 1fr;gap:14px}.version-note{height:max-content}}@media(max-width:700px){.step-indicator i{width:22px}.step-indicator b{display:none}.strategy-group{grid-template-columns:1fr}.submit-row{align-items:stretch;flex-direction:column}.submit-row .el-button{width:100%}.upload-layout aside{grid-template-columns:1fr}}
</style>
