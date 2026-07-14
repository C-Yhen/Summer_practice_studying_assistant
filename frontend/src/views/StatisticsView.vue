<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { Calendar, Download } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import EChart from '@/components/EChart.vue'
import MetricCard from '@/components/MetricCard.vue'
import { trendData } from '@/data/mock'

const range = ref('最近 7 天')
const trendOption = computed<EChartsOption>(() => ({ color: ['#5e6de7','#17aa90'], tooltip:{trigger:'axis'},grid:{top:25,left:10,right:20,bottom:5,containLabel:true},legend:{top:0,right:0,itemWidth:8,itemHeight:8,textStyle:{fontSize:9,color:'#7d879b'}},xAxis:{type:'category',data:trendData.map(i=>i.day),axisLine:{lineStyle:{color:'#e5e9f0'}},axisTick:{show:false},axisLabel:{fontSize:9,color:'#8d96a8'}},yAxis:{type:'value',axisLabel:{fontSize:8,color:'#9aa2b3',formatter:'{value} min'},splitLine:{lineStyle:{color:'#edf0f5',type:'dashed'}}},series:[{name:'实际时长',type:'line',smooth:true,symbolSize:6,data:trendData.map(i=>i.minutes),areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(94,109,231,.25)'},{offset:1,color:'rgba(94,109,231,0)'}]}}},{name:'计划时长',type:'line',smooth:true,symbol:'none',lineStyle:{type:'dashed',width:1.5},data:[120,120,90,120,120,140,120]}] }))
const subjectOption: EChartsOption={tooltip:{trigger:'item'},legend:{bottom:0,itemWidth:8,itemHeight:8,textStyle:{fontSize:9,color:'#7d879b'}},series:[{type:'pie',radius:['48%','70%'],center:['50%','43%'],label:{show:false},data:[{name:'数据库系统',value:438,itemStyle:{color:'#5e6de7'}},{name:'计算机网络',value:205,itemStyle:{color:'#16aa90'}},{name:'操作系统',value:128,itemStyle:{color:'#ee994d'}},{name:'其他',value:49,itemStyle:{color:'#c8cfdd'}}]}]}
const activity=[0,1,0,2,3,1,0,1,2,4,3,1,0,0,2,3,4,2,1,0,1,3,4,5,3,1,0,0,2,4,5,4,2,1,0,1,3,5,4,3,2,0,1,2,4,5,3,2,0]
</script>

<template>
  <div>
    <PageHeader title="学习统计" eyebrow="LEARNING ANALYTICS" description="用数据回看投入、成效与节奏，找到真正有效的学习方式。"><el-select v-model="range" style="width:130px"><el-option label="最近 7 天" value="最近 7 天" /><el-option label="最近 30 天" value="最近 30 天" /></el-select><el-button plain><el-icon><Download /></el-icon>导出周报</el-button></PageHeader>
    <section class="metric-grid"><MetricCard label="总学习时长" value="13h 40m" hint="较上周 +2h 18m" icon="⌁" tone="blue" /><MetricCard label="完成任务" value="26 项" hint="完成率 82%" icon="✓" tone="green" /><MetricCard label="练习正确率" value="76%" hint="较上周 +8%" icon="◎" tone="purple" /><MetricCard label="高效时段" value="20–22 点" hint="平均正确率 84%" icon="↗" tone="orange" /></section>
    <section class="stats-grid">
      <article class="content-card card-pad trend"><div class="card-header"><div><h2>学习时长趋势</h2><p>实际投入与计划预算对比</p></div><span class="soft-tag green">计划达成 91%</span></div><EChart :option="trendOption" height="280px" /></article>
      <article class="content-card card-pad subject"><div class="card-header"><div><h2>课程时间分布</h2><p>共 820 分钟</p></div></div><EChart :option="subjectOption" height="230px" /><div class="subject-main"><strong>53%</strong><span>数据库系统</span></div></article>
      <article class="content-card card-pad activity"><div class="card-header"><div><h2>学习活跃热力图</h2><p>过去 7 周 · 颜色越深表示学习时长越长</p></div><span class="calendar"><el-icon><Calendar /></el-icon>连续 12 天</span></div><div class="heatmap"><span v-for="(value,index) in activity" :key="index" :class="`level-${value}`" :title="`${value*25} 分钟`"></span></div><div class="heat-label"><span>7 周前</span><span>今天</span></div></article>
      <article class="content-card card-pad insights"><div class="card-header"><div><h2>本周学习洞察</h2><p>基于学习行为与答题表现</p></div><span class="soft-tag brand">AI 生成</span></div><div class="insight-list"><div><span>01</span><p><b>晚间学习效率最高</b><small>20:00–22:00 的练习正确率比全天平均高 11%，建议把高难度任务放在这个时段。</small></p></div><div><span>02</span><p><b>阅读到练习间隔过长</b><small>你通常在阅读后 18 小时才练习。若缩短到 2 小时内，知识留存率预计提升 9%。</small></p></div><div><span>03</span><p><b>稳定性正在提升</b><small>连续学习 12 天，日均波动从 38 分钟降至 21 分钟，节奏更加稳定。</small></p></div></div></article>
    </section>
  </div>
</template>

<style scoped>
.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:17px;margin-bottom:17px}.stats-grid{display:grid;grid-template-columns:1.5fr .7fr;gap:17px}.trend,.subject{min-width:0}.subject{position:relative}.subject-main{position:absolute;left:50%;top:155px;display:flex;align-items:center;flex-direction:column;transform:translate(-50%,-50%)}.subject-main strong{font-size:18px}.subject-main span{margin-top:4px;color:#8d96a9;font-size:7px}.activity{grid-column:span 2}.calendar{display:flex;align-items:center;gap:5px;color:#16a088;font-size:8px}.heatmap{display:grid;grid-template-columns:repeat(7,1fr);gap:7px}.heatmap span{height:22px;border-radius:5px;background:#eef1f5}.heatmap .level-1{background:#dff3ee}.heatmap .level-2{background:#a9ded1}.heatmap .level-3{background:#64c6b1}.heatmap .level-4{background:#2baa92}.heatmap .level-5{background:#16836f}.heat-label{display:flex;justify-content:space-between;margin-top:7px;color:#9aa2b2;font-size:7px}.insights{grid-column:span 2}.insight-list{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}.insight-list>div{display:flex;gap:10px;padding:13px;border-radius:11px;background:#f7f8fc}.insight-list>div>span{color:#6977df;font:10px Consolas,monospace}.insight-list p{display:flex;flex-direction:column;margin:0}.insight-list b{font-size:9px;color:#46516b}.insight-list small{margin-top:6px;color:#7f899e;font-size:8px;line-height:1.6}@media(max-width:950px){.metric-grid{grid-template-columns:repeat(2,1fr)}.stats-grid{grid-template-columns:1fr}.activity,.insights{grid-column:auto}.insight-list{grid-template-columns:1fr}}@media(max-width:520px){.metric-grid{grid-template-columns:1fr}.heatmap{gap:4px}.heatmap span{height:14px}}
</style>
