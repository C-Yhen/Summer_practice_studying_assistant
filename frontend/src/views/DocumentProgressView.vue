<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Clock, Document, RefreshRight, VideoPause } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'
import { subscribeTaskProgress } from '@/api/taskSocket'

const progress = ref(72)
const stepIndex = computed(() => progress.value < 15 ? 0 : progress.value < 32 ? 1 : progress.value < 50 ? 2 : progress.value < 78 ? 3 : 4)
const stages = ['解析文档结构', '文本清洗与切块', '生成 Embedding', '写入 pgvector', '建立索引并收尾']
let timer: number | undefined
let unsubscribe: () => void = () => {}
onMounted(() => {
  timer = window.setInterval(() => { if (progress.value < 88) progress.value += 1 }, 1800)
  unsubscribe = subscribeTaskProgress('tsk_20260714_a81f', (message) => { progress.value = message.progress })
})
onBeforeUnmount(() => { if (timer) window.clearInterval(timer); unsubscribe() })
const rows = [
  { name: '数据库系统概论（第6版）.pdf', version: 'v2', size: '18.6 MB', status: 'processing', progress: 72, chunks: '865 / 1,204', updated: '刚刚' },
  { name: '数据库课程讲义-范式.pptx', version: 'v1', size: '8.2 MB', status: 'success', progress: 100, chunks: '186', updated: '昨天 21:20' },
  { name: '期末复习重点.md', version: 'v3', size: '126 KB', status: 'success', progress: 100, chunks: '48', updated: '昨天 19:12' },
  { name: '事务与并发控制.docx', version: 'v1', size: '3.4 MB', status: 'queued', progress: 0, chunks: '—', updated: '排队 2 分钟' },
]
</script>

<template>
  <div>
    <PageHeader title="文档处理进度" eyebrow="RAG PIPELINE" description="实时查看资料从上传到进入向量知识库的每一步。">
      <span class="socket-state"><i></i>WebSocket 已连接</span><el-button plain :icon="RefreshRight">刷新状态</el-button>
    </PageHeader>
    <section class="active-task">
      <div class="active-top"><div class="file-icon"><el-icon><Document /></el-icon></div><div class="active-info"><span>正在处理 · 数据库系统</span><h2>数据库系统概论（第6版）.pdf</h2><p class="mono">task_id: tsk_20260714_a81f · Celery worker-02</p></div><strong>{{ progress }}<small>%</small></strong></div>
      <el-progress :percentage="progress" :show-text="false" :stroke-width="9" color="#6675ed" />
      <div class="stage-list"><div v-for="(stage,index) in stages" :key="stage" :class="{ done: index < stepIndex, active: index === stepIndex }"><span><el-icon v-if="index < stepIndex"><Check /></el-icon><i v-else></i></span><b>{{ stage }}</b><small>{{ index < stepIndex ? '已完成' : index === stepIndex ? '处理中' : '等待中' }}</small></div></div>
      <div class="task-detail"><span><el-icon><Clock /></el-icon>已用时 1分42秒</span><span>当前步骤：生成向量并写入 pgvector（865 / 1,204）</span><button @click="ElMessage.info('已请求安全取消，当前批次完成后停止')"><el-icon><VideoPause /></el-icon>取消任务</button></div>
    </section>

    <section class="content-card card-pad table-card">
      <div class="card-header"><div><h2>课程资料</h2><p>数据库系统 · 共 12 份</p></div><el-select model-value="全部状态" size="small" style="width:110px"><el-option label="全部状态" value="全部状态" /></el-select></div>
      <el-table :data="rows">
        <el-table-column label="文档" min-width="270"><template #default="scope"><div class="document-cell"><span>{{ scope.row.name.split('.').pop()?.toUpperCase() }}</span><div><b>{{ scope.row.name }}</b><small>{{ scope.row.version }} · {{ scope.row.size }}</small></div></div></template></el-table-column>
        <el-table-column label="状态" width="115"><template #default="scope"><StatusPill :status="scope.row.status" /></template></el-table-column>
        <el-table-column label="进度" min-width="170"><template #default="scope"><div class="row-progress"><el-progress :percentage="scope.row.progress" :show-text="false" :stroke-width="6" /><span>{{ scope.row.progress }}%</span></div></template></el-table-column>
        <el-table-column prop="chunks" label="文本块" width="110" /><el-table-column prop="updated" label="更新时间" width="130" />
        <el-table-column label="操作" width="130"><template #default="scope"><el-button link type="primary">详情</el-button><el-button v-if="scope.row.status === 'success'" link>重新解析</el-button></template></el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.socket-state{display:flex;align-items:center;gap:7px;padding:8px 11px;border-radius:999px;background:#eaf8f4;color:#158e78;font-size:9px;font-weight:700}.socket-state i{width:7px;height:7px;border-radius:50%;background:#19ae8e;box-shadow:0 0 0 4px #d5f0e9}.active-task{padding:25px 27px;margin-bottom:18px;border:1px solid #dfe3f5;border-radius:19px;background:linear-gradient(145deg,#fff,#f8f9ff);box-shadow:var(--shadow-soft)}.active-top{display:flex;align-items:center;gap:13px;margin-bottom:20px}.file-icon{width:45px;height:49px;display:grid;place-items:center;border-radius:12px;background:#eef0ff;color:#6472e9;font-size:20px}.active-info{flex:1}.active-info>span{color:#6674df;font-size:9px;font-weight:700}.active-info h2{margin:5px 0;color:#36415d;font-size:15px}.active-info p{margin:0;color:#9aa3b4;font-size:8px}.active-top>strong{color:#5362de;font-size:30px}.active-top>strong small{font-size:13px}.stage-list{display:grid;grid-template-columns:repeat(5,1fr);margin:23px 0 19px}.stage-list>div{position:relative;display:flex;align-items:center;flex-direction:column;color:#a0a8b8}.stage-list>div::after{content:"";position:absolute;left:60%;right:-40%;top:12px;height:2px;background:#e5e8ef}.stage-list>div:last-child::after{display:none}.stage-list span{position:relative;z-index:1;width:25px;height:25px;display:grid;place-items:center;border:2px solid #dfe3eb;border-radius:50%;background:#fff;font-size:10px}.stage-list span i{width:5px;height:5px;border-radius:50%;background:#b3bac8}.stage-list b{margin-top:8px;font-size:9px}.stage-list small{margin-top:4px;font-size:8px}.stage-list .done span{color:#fff;border-color:#16a98d;background:#16a98d}.stage-list .done::after{background:#6fd2c0}.stage-list .active span{border-color:#6574eb;box-shadow:0 0 0 5px #edf0ff}.stage-list .active span i{background:#6271e8}.stage-list .active b{color:#5362dd}.stage-list .active small{color:#6976dd}.task-detail{display:flex;align-items:center;gap:24px;padding:10px 13px;border-radius:10px;background:#f3f5fb;color:#7d879b;font-size:9px}.task-detail span{display:flex;align-items:center;gap:5px}.task-detail button{display:flex;align-items:center;gap:5px;margin-left:auto;border:0;background:transparent;color:#dc676c;font-size:9px;cursor:pointer}.document-cell{display:flex;align-items:center;gap:10px}.document-cell>span{width:34px;height:38px;display:grid;place-items:center;border-radius:8px;background:#fff0ed;color:#d96857;font-size:7px;font-weight:800}.document-cell>div{display:flex;flex-direction:column}.document-cell b{font-size:10px;color:#424d67}.document-cell small{margin-top:4px;color:#979faf;font-size:8px}.row-progress{display:flex;align-items:center;gap:8px}.row-progress .el-progress{flex:1}.row-progress span{width:28px;color:#7c869b;font-size:9px}@media(max-width:800px){.stage-list{grid-template-columns:1fr}.stage-list>div{align-items:flex-start;flex-direction:row;gap:8px;padding:6px 0}.stage-list>div::after{display:none}.stage-list b,.stage-list small{margin:5px 0}.task-detail{align-items:flex-start;flex-direction:column;gap:8px}.task-detail button{margin-left:0}.active-info p{display:none}.active-top>strong{font-size:22px}}
</style>
