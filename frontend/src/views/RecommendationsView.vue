<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Clock, Document, MagicStick, Reading, Star, View } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'

const activeTab = ref('all')
const resources = [
  { id: 1, kind: '资料', icon: 'PDF', title: '函数依赖：从定义到属性闭包', source: '数据库课程讲义 · 第 32–39 页', duration: '35 分钟', match: 96, level: '基础', reason: '你的“函数依赖”掌握度仅 52%，它是第三范式的前置知识。', evidence: ['薄弱点匹配', '计划任务需要', '内容难度适合'], color: 'red' },
  { id: 2, kind: '练习', icon: '10题', title: '第三范式专项练习', source: 'AI 基于近 3 次错题生成', duration: '18 分钟', match: 92, level: '中等', reason: '最近 5 道范式题中有 3 道因传递依赖判断错误而失分。', evidence: ['错题相似度 89%', '考试高频', '预计提升 12%'], color: 'purple' },
  { id: 3, kind: '资料', icon: 'PPT', title: '事务隔离级别图解', source: '数据库课程讲义 · 第 8 章', duration: '22 分钟', match: 87, level: '基础', reason: '事务并发掌握度 58%，且该内容将在 3 天后的模拟测验中出现。', evidence: ['掌握度偏低', '近期计划', '章节关联'], color: 'orange' },
  { id: 4, kind: '练习', icon: '8题', title: '候选码与属性闭包强化', source: '题库精选 · 动态难度', duration: '15 分钟', match: 85, level: '进阶', reason: '完成这组练习将补齐范式判断的关键前置能力。', evidence: ['知识依赖', '错误模式匹配', '短时高收益'], color: 'green' },
  { id: 5, kind: '资料', icon: 'MD', title: '索引优化期末速记', source: '期末复习重点 · 第 4 节', duration: '12 分钟', match: 78, level: '复习', reason: '你的索引掌握度较好，适合在考前用短时间完成一次巩固。', evidence: ['间隔复习到期', '时间适配', '高频考点'], color: 'blue' },
  { id: 6, kind: '练习', icon: '20题', title: '数据库综合模拟卷一', source: '历年题型重组', duration: '60 分钟', match: 74, level: '综合', reason: '建议完成基础补弱后用于检验整体复习成效。', evidence: ['目标 90 分', '覆盖面广', '考前 7 天'], color: 'purple' },
]
function feedback(type: string) { ElMessage.success(type === 'like' ? '已记录：这个推荐对你有帮助' : '已减少相似内容推荐') }
</script>

<template>
  <div>
    <PageHeader title="推荐中心" eyebrow="EXPLAINABLE RECOMMENDATION" description="不只告诉你学什么，也说明为什么现在值得学。">
      <el-button plain><el-icon><Star /></el-icon>推荐历史</el-button><el-button type="primary"><el-icon><MagicStick /></el-icon>刷新推荐</el-button>
    </PageHeader>
    <section class="recommend-hero">
      <div><span>今日推荐策略</span><h2>优先补齐「函数依赖」→ 再进入第三范式练习</h2><p>综合知识点掌握度、近 18 次答题、考试剩余 7 天与今日 72 分钟可用时间生成。</p><div><span>掌握度权重 35%</span><span>考试紧迫度 25%</span><span>错题相似度 25%</span><span>时间适配 15%</span></div></div>
      <strong>87<small>%</small><em>策略置信度</em></strong>
    </section>
    <div class="filters"><el-radio-group v-model="activeTab" size="large"><el-radio-button value="all">全部推荐</el-radio-button><el-radio-button value="resource">学习资料</el-radio-button><el-radio-button value="practice">练习题</el-radio-button></el-radio-group><div><el-select model-value="数据库系统" style="width:150px"><el-option label="数据库系统" value="数据库系统" /></el-select><el-select model-value="推荐度排序" style="width:130px"><el-option label="推荐度排序" value="推荐度排序" /></el-select></div></div>
    <section class="recommend-grid">
      <article v-for="item in resources.filter(i => activeTab === 'all' || (activeTab === 'resource' ? i.kind === '资料' : i.kind === '练习'))" :key="item.id" class="recommend-card content-card">
        <div class="card-top"><span class="type-icon" :class="item.color">{{ item.icon }}</span><div class="match"><strong>{{ item.match }}%</strong><span>推荐匹配</span></div></div>
        <span class="kind">{{ item.kind }} · {{ item.level }}</span><h2>{{ item.title }}</h2><p class="source">{{ item.source }}</p>
        <div class="resource-meta"><span><el-icon><Clock /></el-icon>{{ item.duration }}</span><span><el-icon><View /></el-icon>1.2k 学习</span><span><el-icon><Star /></el-icon>4.8</span></div>
        <div class="reason"><div><el-icon><MagicStick /></el-icon><b>为什么推荐给你</b></div><p>{{ item.reason }}</p><div class="evidence"><span v-for="tag in item.evidence" :key="tag">{{ tag }}</span></div></div>
        <div class="card-actions"><el-button type="primary"><el-icon><component :is="item.kind === '资料' ? Document : Reading" /></el-icon>{{ item.kind === '资料' ? '开始阅读' : '开始练习' }}</el-button><el-dropdown><el-button plain>反馈 ···</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="feedback('like')">推荐准确</el-dropdown-item><el-dropdown-item @click="feedback('dislike')">不感兴趣</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.recommend-hero{display:flex;align-items:center;gap:30px;padding:23px 28px;margin-bottom:18px;border-radius:18px;background:linear-gradient(110deg,#17264e,#293d78);color:white}.recommend-hero>div{flex:1}.recommend-hero>div>span{color:#8f9cf7;font-size:8px;font-weight:750}.recommend-hero h2{margin:7px 0;font-size:17px}.recommend-hero p{margin:0;color:#aab5ce;font-size:9px}.recommend-hero>div>div{display:flex;gap:7px;margin-top:14px}.recommend-hero>div>div span{padding:5px 8px;border-radius:6px;background:rgba(255,255,255,.07);color:#bec6dc;font-size:7px}.recommend-hero>strong{display:flex;align-items:center;justify-content:center;flex-direction:column;width:90px;height:90px;border:7px solid rgba(255,255,255,.13);border-top-color:#7dd9c5;border-radius:50%;font-size:24px}.recommend-hero>strong small{font-size:10px}.recommend-hero>strong em{margin-top:3px;color:#93a0ba;font-size:7px;font-style:normal}.filters{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.filters>div{display:flex;gap:8px}.recommend-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.recommend-card{padding:19px}.card-top{display:flex;align-items:flex-start;justify-content:space-between}.type-icon{width:46px;height:50px;display:grid;place-items:center;border-radius:12px;font-size:10px;font-weight:800}.type-icon.red{background:#fff0ed;color:#dc6956}.type-icon.purple{background:#eff1ff;color:#6271e6}.type-icon.orange{background:#fff3e6;color:#da8332}.type-icon.green{background:#eaf8f4;color:#16947c}.type-icon.blue{background:#ebf4ff;color:#4783c8}.match{display:flex;align-items:flex-end;flex-direction:column}.match strong{color:#15a087;font-size:16px}.match span{margin-top:4px;color:#98a1b3;font-size:7px}.kind{display:block;margin-top:15px;color:#6472dd;font-size:8px;font-weight:750}.recommend-card>h2{margin:6px 0;color:#3c4762;font-size:14px}.source{margin:0;color:#8d97aa;font-size:8px}.resource-meta{display:flex;gap:13px;padding:12px 0;border-bottom:1px solid #edf0f5}.resource-meta span{display:flex;align-items:center;gap:4px;color:#8e97aa;font-size:8px}.reason{padding:12px;margin:13px 0;border-radius:11px;background:#f7f8fc}.reason>div:first-child{display:flex;align-items:center;gap:6px;color:#5d6be0;font-size:9px}.reason p{margin:7px 0;color:#68738b;font-size:8px;line-height:1.6}.evidence{display:flex;flex-wrap:wrap;gap:5px}.evidence span{padding:3px 5px;border-radius:5px;background:#e9ecff;color:#6472dc;font-size:7px}.card-actions{display:flex;gap:7px}.card-actions>.el-button:first-child{flex:1}@media(max-width:1100px){.recommend-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.recommend-grid{grid-template-columns:1fr}.filters{align-items:flex-start;gap:12px;flex-direction:column}.recommend-hero>strong{display:none}.recommend-hero>div>div{flex-wrap:wrap}}
</style>
