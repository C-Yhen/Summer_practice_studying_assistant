<script setup lang="ts">
defineProps<{ collapsed?: boolean; light?: boolean }>()
</script>

<template>
  <div class="app-logo" :class="{ collapsed, light }">
    <span class="logo-mark"><span></span><i></i></span>
    <div v-if="!collapsed" class="logo-copy">
      <strong>StudyPilot</strong>
      <small>智能学习助手</small>
    </div>
  </div>
</template>

<style scoped>
.app-logo { display:flex; align-items:center; gap:13px; color:#f8fbff; min-width:0; }
.logo-mark { width:40px; height:40px; flex:none; position:relative; border-radius:13px; background:linear-gradient(145deg,#8a7cff,#5a4bf2); box-shadow:0 10px 26px rgba(91,76,244,.38); overflow:hidden; }
.logo-mark::before,.logo-mark::after,.logo-mark span,.logo-mark i { content:""; position:absolute; height:4px; border-radius:4px; background:#fff; transform:rotate(-36deg); transform-origin:left center; }
.logo-mark::before { width:17px; left:9px; top:14px; }
.logo-mark::after { width:13px; left:15px; top:24px; opacity:.68; }
.logo-mark span { width:8px; left:8px; top:22px; opacity:.76; }
.logo-mark i { width:9px; left:22px; top:13px; opacity:.5; }
.logo-copy { display:flex; flex-direction:column; line-height:1; }
.logo-copy strong { font-size:19px; letter-spacing:-.45px; }
.logo-copy small { margin-top:7px; color:#8995b1; font-size:10px; letter-spacing:2px; }
.light { color:#152143; }
.light .logo-copy small { color:#7a86a6; }
.collapsed { justify-content:center; }
</style>
