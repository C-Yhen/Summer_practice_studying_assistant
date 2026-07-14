<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Calendar, ChatDotRound, Document, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import EChart from '@/components/EChart.vue'
import StatusPill from '@/components/StatusPill.vue'
import { courses } from '@/data/mock'

const route = useRoute()
const router = useRouter()
const tab = ref('overview')
const course = computed(() => courses.find((item) => item.id === Number(route.params.id)) || courses[0])
const chartOption: EChartsOption = {
  color: ['#5b6cf0'], grid: { top: 15, right: 10, bottom: 10, left: 10, containLabel: true },
  xAxis: { type: 'category', data: ['关系模型', 'SQL', '函数依赖', '范式', '事务', '索引'], axisLine: { lineStyle: { color: '#e7eaf1' } }, axisTick: { show: false }, axisLabel: { color: '#8993a8', fontSize: 9 } },
  yAxis: { type: 'value', max: 100, axisLabel: { color: '#a0a8ba', fontSize: 9 }, splitLine: { lineStyle: { color: '#edf0f5', type: 'dashed' } } },
  series: [{ type: 'bar', data: [84, 78, 52, 46, 58, 71], barWidth: 18, itemStyle: { borderRadius: [6, 6, 0, 0], color: { type: 'linear', x: 0, y: 1, x2: 0, y2: 0, colorStops: [{ offset: 0, color: '#aab2ff' }, { offset: 1, color: '#5969ea' }] } } }],
}
const documents = [
  { name: '数据库系统概论（第6版）.pdf', type: 'PDF', version: 'v2', chunks: 1204, status: 'success', date: '07-14 09:42' },
  { name: '数据库课程讲义-范式.pptx', type: 'PPT', version: 'v1', chunks: 186, status: 'success', date: '07-13 21:16' },
  { name: '期末复习重点.md', type: 'MD', version: 'v3', chunks: 48, status: 'success', date: '07-13 19:08' },
]
</script>

<template>
  <div>
    <PageHeader :title="course.name" eyebrow="COURSE DETAIL" :description="`${course.code} · ${course.teacher} · 目标 ${course.targetScore} 分`">
      <el-button plain @click="router.push('/courses')"><el-icon><ArrowLeft /></el-icon>返回</el-button>
      <el-button @click="router.push('/upload')"><el-icon><UploadFilled /></el-icon>上传资料</el-button>
      <el-button type="primary" @click="router.push('/chat')"><el-icon><ChatDotRound /></el-icon>进入问答</el-button>
    </PageHeader>

    <section class="course-hero">
      <div class="course-identity"><span>{{ course.name.slice(0,1) }}</span><div><small>当前主课程</small><h2>{{ course.name }}</h2><p>距离考试还有 7 天 · 今日建议学习 120 分钟</p></div></div>
      <div class="hero-stat"><strong>{{ course.progress }}%</strong><span>学习进度</span></div>
      <div class="hero-stat"><strong>{{ course.documentCount }}</strong><span>已入库资料</span></div>
      <div class="hero-stat"><strong>64%</strong><span>平均掌握度</span></div>
      <div class="exam-date"><el-icon><Calendar /></el-icon><div><small>考试日期</small><strong>{{ course.examDate }}</strong></div></div>
    </section>

    <section class="content-card course-content">
      <el-tabs v-model="tab">
        <el-tab-pane label="课程概览" name="overview">
          <div class="overview-grid">
            <article><div class="card-header"><div><h2>知识点掌握概览</h2><p>最近一次更新：今天 10:20</p></div><button class="card-link" @click="router.push('/mastery')">查看详情 →</button></div><EChart :option="chartOption" height="270px" /></article>
            <article class="next-card"><span class="soft-tag brand">下一步建议</span><h2>补齐函数依赖前置概念</h2><p>最近 5 道范式题中有 3 道因候选码判断错误而失分。完成下面两个任务后再进入第三范式练习，预计正确率可提升 12%。</p><div class="next-task"><i>1</i><span><b>阅读：函数依赖与属性闭包</b><small>35 分钟 · 讲义第 32–39 页</small></span></div><div class="next-task"><i>2</i><span><b>候选码判断基础练习</b><small>10 题 · 约 20 分钟</small></span></div><el-button type="primary" @click="router.push('/today')">加入今日任务</el-button></article>
          </div>
        </el-tab-pane>
        <el-tab-pane label="课程资料 12" name="documents">
          <el-table :data="documents" style="width:100%"><el-table-column label="资料名称" min-width="260"><template #default="scope"><div class="doc-name"><span><el-icon><Document /></el-icon></span><div><b>{{ scope.row.name }}</b><small>{{ scope.row.type }} · {{ scope.row.version }}</small></div></div></template></el-table-column><el-table-column prop="chunks" label="文本块" width="110" /><el-table-column label="状态" width="110"><template #default="scope"><StatusPill :status="scope.row.status" /></template></el-table-column><el-table-column prop="date" label="更新时间" width="140" /><el-table-column label="操作" width="130"><template #default><el-button link type="primary">查看</el-button><el-button link>重建</el-button></template></el-table-column></el-table>
        </el-tab-pane>
        <el-tab-pane label="知识点 36" name="knowledge"><div class="knowledge-cloud"><button v-for="item in ['关系模型','关系代数','SQL 查询','连接查询','函数依赖','属性闭包','候选码','第二范式','第三范式','BCNF','事务 ACID','并发控制','封锁协议','B+ 树索引']" :key="item">{{ item }}<small>{{ ['函数依赖','第三范式'].includes(item) ? '待加强' : '学习中' }}</small></button></div></el-tab-pane>
        <el-tab-pane label="学习记录" name="records"><div class="record-list"><div v-for="(item,index) in ['完成范式判断练习，正确率 70%','阅读《函数依赖：从定义到闭包》35 分钟','向 AI 提问「什么是第三范式」','完成 SQL 连接查询练习，正确率 90%']" :key="item"><span>{{ index + 1 }}</span><p><b>{{ item }}</b><small>{{ index === 0 ? '今天 10:20' : `${index} 天前` }}</small></p></div></div></el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<style scoped>
.course-hero{display:flex;align-items:center;gap:30px;padding:24px 28px;margin-bottom:18px;border-radius:19px;background:linear-gradient(115deg,#111f45,#1b2d5d);color:white;box-shadow:0 15px 38px rgba(17,31,69,.16)}.course-identity{display:flex;align-items:center;gap:16px;min-width:290px;margin-right:auto}.course-identity>span{width:57px;height:57px;display:grid;place-items:center;border-radius:17px;background:linear-gradient(145deg,#6474f0,#9b6be7);font-size:24px;font-weight:750}.course-identity small,.exam-date small{color:#8f9bb9;font-size:9px}.course-identity h2{margin:5px 0 4px;font-size:19px}.course-identity p{margin:0;color:#a6b1cb;font-size:9px}.hero-stat{display:flex;flex-direction:column;padding-left:24px;border-left:1px solid rgba(255,255,255,.1)}.hero-stat strong{font-size:20px}.hero-stat span{margin-top:5px;color:#8996b5;font-size:9px}.exam-date{display:flex;align-items:center;gap:10px;padding:11px 14px;border:1px solid rgba(255,255,255,.1);border-radius:12px;background:rgba(255,255,255,.045)}.exam-date div{display:flex;flex-direction:column}.exam-date strong{margin-top:4px;font-size:11px}.course-content{padding:4px 22px 22px}.overview-grid{display:grid;grid-template-columns:1.35fr .65fr;gap:18px}.overview-grid>article{padding:10px}.next-card{padding:19px!important;border-radius:15px;background:#f7f8ff}.next-card h2{margin:14px 0 9px;font-size:16px}.next-card>p{margin:0 0 16px;color:#78829a;font-size:10px;line-height:1.7}.next-task{display:flex;gap:10px;padding:11px 0;border-top:1px solid #e5e8f3}.next-task i{width:22px;height:22px;display:grid;place-items:center;flex:none;border-radius:7px;background:#e7eaff;color:#5d6beb;font-style:normal;font-size:9px;font-weight:800}.next-task span{display:flex;flex-direction:column}.next-task b{font-size:10px;color:#48536d}.next-task small{margin-top:5px;color:#929baf;font-size:8px}.next-card .el-button{width:100%;margin-top:13px}.doc-name{display:flex;align-items:center;gap:11px}.doc-name>span{width:31px;height:35px;display:grid;place-items:center;border-radius:8px;background:#fff0ed;color:#dc6b5a}.doc-name>div{display:flex;flex-direction:column}.doc-name b{color:#3f4a65;font-size:11px}.doc-name small{margin-top:4px;color:#98a1b3;font-size:8px}.knowledge-cloud{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:12px 0}.knowledge-cloud button{display:flex;justify-content:space-between;padding:16px;border:1px solid #e5e9f1;border-radius:12px;background:#fafbfc;color:#4b5670;cursor:pointer}.knowledge-cloud button:hover{border-color:#aeb6f3;background:#f8f8ff}.knowledge-cloud small{color:#919bad;font-size:8px}.record-list{padding:10px}.record-list>div{display:flex;gap:12px;padding:13px 0;border-bottom:1px solid #edf0f4}.record-list>div>span{width:24px;height:24px;display:grid;place-items:center;border-radius:50%;background:#eef0ff;color:#5b6ae8;font-size:9px}.record-list p{display:flex;flex-direction:column;margin:0}.record-list b{font-size:11px}.record-list small{margin-top:5px;color:#969fb1;font-size:9px}@media(max-width:1100px){.course-hero{flex-wrap:wrap}.course-identity{width:100%}.hero-stat{padding:0;border:0}.overview-grid{grid-template-columns:1fr}}@media(max-width:700px){.course-hero{gap:18px}.course-identity{min-width:0}.hero-stat{width:25%}.exam-date{width:100%}.knowledge-cloud{grid-template-columns:1fr 1fr}}
</style>
