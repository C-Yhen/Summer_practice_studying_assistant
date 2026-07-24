<script setup lang="ts">
defineProps<{ label: string; value: string; hint: string; tone?: 'blue' | 'green' | 'orange' | 'purple'; icon?: string }>()
</script>

<template>
  <article class="metric-card" :class="`tone-${tone || 'blue'}`">
    <div class="metric-top"><span class="metric-label">{{ label }}</span><span class="metric-icon">{{ icon }}</span></div>
    <div class="metric-value">{{ value }}</div>
    <div class="metric-hint">{{ hint }}</div>
    <span class="metric-accent"></span>
  </article>
</template>

<style scoped>
.metric-card { position:relative; overflow:hidden; min-height:136px; padding:19px 20px; border:1px solid var(--line); border-radius:18px; background:var(--surface); box-shadow:var(--shadow-soft); }
.metric-card::after { content:""; position:absolute; right:-42px; bottom:-50px; width:112px; height:112px; border:24px solid var(--tone-bg); border-radius:50%; opacity:.72; }
.metric-top { position:relative; z-index:1; display:flex; align-items:center; justify-content:space-between; gap:10px; color:var(--muted); font-size:11px; font-weight:750; letter-spacing:.3px; }
.metric-icon { width:31px; height:31px; display:grid; place-items:center; border-radius:10px; background:var(--tone-bg); color:var(--tone); font-size:14px; font-weight:850; }
.metric-value { position:relative; z-index:1; margin-top:15px; color:var(--ink); font-size:26px; line-height:1; font-weight:820; letter-spacing:-.65px; }
.metric-hint { position:relative; z-index:1; max-width:82%; margin-top:10px; color:#7a86a0; font-size:11px; line-height:1.45; }
.metric-accent { position:absolute; inset:0 auto 0 0; width:3px; background:var(--tone); }
.tone-blue{--tone:#5867ed;--tone-bg:#eef0ff}.tone-green{--tone:#0fa88f;--tone-bg:#e7f8f4}.tone-orange{--tone:#eb8a34;--tone-bg:#fff2e5}.tone-purple{--tone:#9a5ae7;--tone-bg:#f5edff}
</style>
