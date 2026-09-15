<template>
  <div class="shell">
    <div class="ambient" ref="ambient" aria-hidden="true"></div>
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark glow">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round">
            <path d="M12 3l7 3v5c0 4.6-3 7.6-7 9-4-1.4-7-4.4-7-9V6z" />
            <path d="M9.2 12l1.9 1.9 3.7-3.8" />
          </svg>
        </div>
        <div class="brand-text">
          <div class="brand-name">入侵检测系统</div>
          <div class="brand-sub mono">ML &nbsp;·&nbsp; IDS</div>
        </div>
      </div>

      <nav class="nav" @mouseleave="onNavLeave">
        <span class="nav-glow" :style="glowStyle" aria-hidden="true"></span>
        <router-link v-for="item in nav" :key="item.path" :to="item.path" class="nav-item" :class="{ active: isActive(item.path) }" v-magnet="0.22" @mouseenter="onNavEnter(item, $event)">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round">
            <template v-if="item.icon === 'dashboard'">
              <rect x="3" y="3" width="7" height="9" rx="1.6" /><rect x="14" y="3" width="7" height="5" rx="1.6" /><rect x="14" y="12" width="7" height="9" rx="1.6" /><rect x="3" y="16" width="7" height="5" rx="1.6" />
            </template>
            <template v-else-if="item.icon === 'data'">
              <ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" />
            </template>
            <template v-else-if="item.icon === 'experiment'">
              <path d="M9 3h6" /><path d="M10 3v6.3L4.6 17a2 2 0 0 0 1.8 3h11.2a2 2 0 0 0 1.8-3L14 9.3V3" /><path d="M7.5 15h9" />
            </template>
            <template v-else-if="item.icon === 'detect'">
              <path d="M12 3l7 3v5c0 4.6-3 7.6-7 9-4-1.4-7-4.4-7-9V6z" /><circle cx="12" cy="12" r="2.4" /><path d="M12 9.6v.1M14.4 12h-.1" />
            </template>
            <template v-else-if="item.icon === 'eval'">
              <path d="M4 20V8" /><path d="M9 20V4" /><path d="M14 20v-7" /><path d="M19 20v-9" /><path d="M2.5 20h19" />
            </template>
          </svg>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="side-foot">
        <span class="pulse" :class="online ? 'ok' : 'off'"></span>
        <span class="mono">{{ online ? '后台已连接' : '后台离线' }}</span>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="topbar-head">
          <h1 class="topbar-title">{{ title }}</h1>
          <p class="topbar-sub mono">Network Intrusion Detection &amp; Visualization System</p>
        </div>
        <div class="status-chip" :class="online ? 'ok' : 'off'">
          <span class="pulse" :class="online ? 'ok' : 'off'"></span>
          <span class="mono">{{ online ? 'LOCAL · READY' : 'LOCAL · DOWN' }}</span>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const nav = [
  { path: '/dashboard', label: '分析总览', icon: 'dashboard', accent: '#2dd4bf' },
  { path: '/data', label: '数据管理', icon: 'data', accent: '#4f8df9' },
  { path: '/experiments', label: '模型实验', icon: 'experiment', accent: '#8b7cff' },
  { path: '/detections', label: '批量检测', icon: 'detect', accent: '#fb7185' },
  { path: '/evaluation', label: '评估分析', icon: 'eval', accent: '#fbbf24' },
]

const route = useRoute()
const titles: Record<string, string> = {
  '/dashboard': '分析总览',
  '/data': '数据管理',
  '/experiments': '模型实验',
  '/detections': '批量检测',
  '/evaluation': '评估分析',
}
const title = computed(() => titles[route.path] ?? (route.path.startsWith('/detections') ? '检测任务详情' : '入侵检测系统'))
const isActive = (path: string) => path === '/detections' ? route.path.startsWith('/detections') : route.path === path

const online = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let stopped = false
async function check() {
  try { online.value = (await fetch('/health', { cache: 'no-store' })).ok }
  catch { online.value = false }
  if (!stopped) timer = setTimeout(check, 5000)
}

/* —— 导航高光：随指针在栏目间滑动，并按栏目变色 —— */
const glowStyle = ref<Record<string, string>>({ top: '0px', height: '44px', opacity: '0', '--glow': '#2dd4bf' })
function positionGlow(el: Element | null) {
  if (!el) { glowStyle.value.opacity = '0'; return }
  const box = el as HTMLElement
  glowStyle.value = { top: `${box.offsetTop}px`, height: `${box.offsetHeight}px`, opacity: '1', '--glow': glowStyle.value['--glow'] ?? '#2dd4bf' }
}
function onNavEnter(item: (typeof nav)[number], e: MouseEvent) {
  glowStyle.value['--glow'] = item.accent
  positionGlow(e.currentTarget as Element)
}
function onNavLeave() { syncActiveGlow() }
function syncActiveGlow() {
  nextTick(() => {
    const active = document.querySelector('.nav-item.active')
    if (active) positionGlow(active)
    else glowStyle.value.opacity = '0'
  })
}
watch(() => route.path, syncActiveGlow)

/* —— 全局氛围光：柔和光斑跟随指针，慢速 e-in-out 缓动 —— */
const ambient = ref<HTMLDivElement>()
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
let pointer = { x: 0.5, y: 0.5 }
let glow = { a: { x: 0.5, y: 0.5 }, b: { x: 0.5, y: 0.35 } }
let raf = 0
function onPointerMove(e: MouseEvent) {
  pointer.x = e.clientX / window.innerWidth
  pointer.y = e.clientY / window.innerHeight
}
function ambientLoop() {
  glow.a.x += (pointer.x - glow.a.x) * 0.05
  glow.a.y += (pointer.y - glow.a.y) * 0.05
  glow.b.x += (pointer.x - glow.b.x) * 0.028
  glow.b.y += (pointer.y - glow.b.y) * 0.028
  const w = window.innerWidth, h = window.innerHeight
  ambient.value?.style.setProperty('--ax', `${(glow.a.x * w).toFixed(1)}px`)
  ambient.value?.style.setProperty('--ay', `${(glow.a.y * h).toFixed(1)}px`)
  ambient.value?.style.setProperty('--bx', `${(glow.b.x * w).toFixed(1)}px`)
  ambient.value?.style.setProperty('--by', `${(glow.b.y * h).toFixed(1)}px`)
  raf = requestAnimationFrame(ambientLoop)
}

onMounted(() => {
  check()
  syncActiveGlow()
  window.addEventListener('mousemove', onPointerMove)
  if (!reduceMotion) raf = requestAnimationFrame(ambientLoop)
})
onBeforeUnmount(() => {
  stopped = true
  clearTimeout(timer)
  window.removeEventListener('mousemove', onPointerMove)
  cancelAnimationFrame(raf)
})
</script>

<style scoped>
.shell {
  position: relative;
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--id-bg);
  color: var(--id-text);
}

/* —— 全局氛围光：两团柔光跟随指针 —— */
.ambient {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.ambient::before,
.ambient::after {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  width: 48vmax;
  height: 48vmax;
  border-radius: 50%;
  filter: blur(70px);
  will-change: transform;
}
.ambient::before {
  transform: translate(-50%, -50%) translate(var(--ax, 50vw), var(--ay, 50vh));
  background: radial-gradient(circle, rgba(45, 212, 191, 0.14), transparent 62%);
}
.ambient::after {
  transform: translate(-50%, -50%) translate(var(--bx, 50vw), var(--by, 50vh));
  background: radial-gradient(circle, rgba(139, 124, 255, 0.14), transparent 62%);
}

.sidebar, .main { position: relative; z-index: 1; }

/* —— 侧边栏 —— */
.sidebar {
  width: 236px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: var(--id-bg-soft);
  border-right: 1px solid var(--id-border);
  padding: 18px 14px;
}
.brand { display: flex; align-items: center; gap: 12px; padding: 2px 6px 20px; }
.brand-mark {
  width: 38px; height: 38px; flex: none;
  display: grid; place-items: center;
  border-radius: 11px;
  background: var(--id-gradient);
  color: #05110f;
}
.brand-mark svg { width: 22px; height: 22px; }
.brand-name { font-weight: 700; font-size: 15px; letter-spacing: .01em; }
.brand-sub { font-size: 11px; color: var(--id-text-faint); margin-top: 2px; letter-spacing: .08em; }

.nav { position: relative; display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
.nav-glow {
  position: absolute;
  left: 6px;
  right: 6px;
  top: 0;
  height: 44px;
  border-radius: var(--id-radius-sm);
  background: linear-gradient(135deg, color-mix(in srgb, var(--glow, #2dd4bf) 18%, transparent), color-mix(in srgb, var(--glow, #2dd4bf) 4%, transparent));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--glow, #2dd4bf) 20%, transparent), 0 14px 34px -14px color-mix(in srgb, var(--glow, #2dd4bf) 55%, transparent);
  opacity: 0;
  transition: top .4s cubic-bezier(.22, 1, .36, 1), height .4s cubic-bezier(.22, 1, .36, 1), opacity .28s ease, background .3s ease, box-shadow .3s ease;
  pointer-events: none;
}
.nav-item {
  position: relative;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px;
  border-radius: var(--id-radius-sm);
  color: var(--id-text-dim);
  font-size: 14px;
  text-decoration: none;
  transition: background .16s ease, color .16s ease;
}
.nav-item:hover { background: var(--id-fill, rgba(148,163,184,.07)); color: var(--id-text); }
.nav-icon { width: 19px; height: 19px; flex: none; }
.nav-item.active {
  color: var(--id-accent);
  background: var(--id-gradient-soft);
}
.nav-item.active::before {
  content: '';
  position: absolute; left: 0; top: 8px; bottom: 8px;
  width: 3px; border-radius: 3px;
  background: var(--id-gradient);
  box-shadow: 0 0 12px rgba(45,212,191,.6);
}
.side-foot {
  margin-top: auto;
  display: flex; align-items: center; gap: 8px;
  padding: 12px 12px 4px;
  font-size: 12px; color: var(--id-text-dim);
  border-top: 1px solid var(--id-border);
}

/* —— 头部 —— */
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 28px;
  border-bottom: 1px solid var(--id-border);
  background: color-mix(in srgb, var(--id-bg) 82%, transparent);
  backdrop-filter: blur(10px);
}
.topbar-title { font-size: 19px; font-weight: 700; margin: 0; }
.topbar-sub { font-size: 11px; color: var(--id-text-faint); margin: 4px 0 0; letter-spacing: .03em; }
.status-chip {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid var(--id-border);
  font-size: 11px; letter-spacing: .06em;
}
.status-chip.ok { color: var(--id-ok); border-color: rgba(52,211,153,.35); }
.status-chip.off { color: var(--id-warn); border-color: rgba(251,191,36,.35); }

/* —— 状态脉冲点 —— */
.pulse { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.pulse.ok { background: var(--id-ok); box-shadow: 0 0 0 0 rgba(52,211,153,.5); animation: ping 2s infinite; }
.pulse.off { background: var(--id-warn); box-shadow: 0 0 0 0 rgba(251,191,36,.4); }
@keyframes ping {
  0% { box-shadow: 0 0 0 0 rgba(52,211,153,.5); }
  70% { box-shadow: 0 0 0 7px rgba(52,211,153,0); }
  100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); }
}

/* —— 内容区 —— */
.content {
  flex: 1; overflow-y: auto;
  padding: 28px;
  min-width: 0;
}

/* —— 响应式 —— */
@media (max-width: 760px) {
  .sidebar { width: 68px; padding: 18px 10px; }
  .brand-text, .nav-label, .side-foot span:not(.pulse) { display: none; }
  .brand { justify-content: center; padding-bottom: 16px; }
  .nav-item { justify-content: center; padding: 12px 0; }
  .side-foot { justify-content: center; padding: 12px 0 4px; }
  .topbar { padding: 14px 18px; }
  .topbar-sub { display: none; }
  .content { padding: 18px; }
}
</style>