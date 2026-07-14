<script setup lang="ts">
defineProps<{ label: string; value: string; hint: string; tone?: 'blue' | 'green' | 'orange' | 'purple'; icon?: string }>()
</script>

<template>
  <article class="metric-card" :class="`tone-${tone || 'blue'}`">
    <div class="metric-top"><span class="metric-icon">{{ icon }}</span><span class="metric-label">{{ label }}</span></div>
    <div class="metric-value">{{ value }}</div>
    <div class="metric-hint"><span class="trend-dot"></span>{{ hint }}</div>
  </article>
</template>

<style scoped>
.metric-card { position:relative; overflow:hidden; padding:19px 20px 18px; border:1px solid var(--line); border-radius:17px; background:var(--surface); box-shadow:var(--shadow-soft); }
.metric-card::after { content:""; position:absolute; right:-25px; top:-35px; width:92px; height:92px; border-radius:50%; background:var(--tone-bg); }
.metric-top { display:flex; align-items:center; gap:9px; color:var(--muted); font-size:12px; position:relative; z-index:1; }
.metric-icon { width:27px; height:27px; border-radius:9px; display:grid; place-items:center; background:var(--tone-bg); color:var(--tone); font-weight:800; }
.metric-value { margin-top:15px; color:var(--ink); font-size:27px; line-height:1; font-weight:780; letter-spacing:-.5px; }
.metric-hint { display:flex; align-items:center; gap:7px; margin-top:10px; color:#7a86a0; font-size:11px; }
.trend-dot { width:6px; height:6px; border-radius:50%; background:var(--tone); box-shadow:0 0 0 4px var(--tone-bg); }
.tone-blue{--tone:#5867ed;--tone-bg:#eef0ff}.tone-green{--tone:#0fa88f;--tone-bg:#e7f8f4}.tone-orange{--tone:#eb8a34;--tone-bg:#fff2e5}.tone-purple{--tone:#9a5ae7;--tone-bg:#f5edff}
</style>
