<script setup lang="ts">
import { Check, DataAnalysis, Document, MagicStick } from '@element-plus/icons-vue'
</script>

<template>
  <section class="auth-showcase">
    <div class="ambient a1"></div><div class="ambient a2"></div>
    <div class="showcase-copy">
      <span class="showcase-tag"><i></i> AI LEARNING COPILOT</span>
      <h1>把散落的资料，<br />变成你的学习路径。</h1>
      <p>理解你的目标、时间与薄弱点，让每一次学习都有依据，每一步进度都看得见。</p>
      <div class="feature-list">
        <div><span><el-icon><Document /></el-icon></span><p><b>可信资料问答</b><small>答案回溯到文档、页码与章节</small></p><el-icon class="check"><Check /></el-icon></div>
        <div><span><el-icon><MagicStick /></el-icon></span><p><b>个性化动态计划</b><small>根据学习效果自动调整下一步</small></p><el-icon class="check"><Check /></el-icon></div>
        <div><span><el-icon><DataAnalysis /></el-icon></span><p><b>可解释能力洞察</b><small>掌握度、推荐理由与趋势一目了然</small></p><el-icon class="check"><Check /></el-icon></div>
      </div>
      <div class="showcase-proof">
        <div><strong>可追踪</strong><span>知识点与学习进度</span></div>
        <i></i><div><strong>可回溯</strong><span>资料问答引用来源</span></div>
        <i></i><div><strong>可解释</strong><span>学习建议生成依据</span></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.auth-showcase{position:relative;overflow:hidden;display:flex;align-items:center;padding:72px clamp(42px,7vw,96px);background:linear-gradient(145deg,#0b1634 0%,#101d43 54%,#172557 100%);color:#fff;min-height:100vh}.auth-showcase::before{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:45px 45px;mask-image:linear-gradient(90deg,#000,transparent)}.ambient{position:absolute;border-radius:50%;filter:blur(3px)}.a1{width:360px;height:360px;right:-150px;top:-110px;background:rgba(95,104,239,.18);box-shadow:0 0 100px rgba(95,104,239,.2)}.a2{width:260px;height:260px;left:-120px;bottom:-90px;background:rgba(24,181,160,.11)}.showcase-copy{position:relative;z-index:1;max-width:560px}.showcase-tag{display:inline-flex;align-items:center;gap:9px;padding:7px 11px;border:1px solid rgba(151,164,255,.18);border-radius:999px;background:rgba(110,122,250,.1);color:#aeb8ff;font-size:10px;font-weight:800;letter-spacing:1.5px}.showcase-tag i{width:7px;height:7px;border-radius:50%;background:#7d89ff;box-shadow:0 0 0 4px rgba(125,137,255,.14)}h1{margin:28px 0 18px;font-size:clamp(36px,4.2vw,56px);line-height:1.15;letter-spacing:-2.1px;font-weight:760}.showcase-copy>p{max-width:470px;margin:0;color:#a5b0ce;font-size:15px;line-height:1.8}.feature-list{margin-top:42px;display:grid;gap:13px}.feature-list>div{display:flex;align-items:center;gap:14px;padding:14px 16px;border:1px solid rgba(255,255,255,.07);border-radius:14px;background:rgba(255,255,255,.035);backdrop-filter:blur(8px)}.feature-list>div>span{width:35px;height:35px;display:grid;place-items:center;border-radius:10px;background:rgba(111,126,255,.14);color:#aab4ff}.feature-list p{display:flex;flex:1;flex-direction:column;margin:0}.feature-list b{font-size:12px}.feature-list small{margin-top:5px;color:#7f8cae;font-size:10px}.check{color:#42c7aa}.showcase-proof{display:flex;align-items:center;gap:22px;margin-top:38px}.showcase-proof>i{width:1px;height:30px;background:rgba(255,255,255,.1)}.showcase-proof div{display:flex;flex-direction:column}.showcase-proof strong{font-size:19px}.showcase-proof span{margin-top:6px;color:#7582a3;font-size:9px}@media(max-width:950px){.auth-showcase{display:none}}
</style>
