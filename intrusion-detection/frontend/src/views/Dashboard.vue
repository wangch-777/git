<template>
  <section class="dash">
    <h2 class="page-title">分析总览</h2>
    <p class="page-sub">
      快速入口与三类指标分开展示。基础模型测试指标、实验验证指标、检测预测数量来源不同，不能混为一谈。
    </p>

    <!-- 快速开始：导入数据 → 训练模型 → 批量检测 → 查看结果 -->
    <div class="quickstart glass-card">
      <h3 class="card-title">快速开始</h3>
      <div class="steps">
        <router-link v-for="step in steps" :key="step.title" :to="step.to" class="step">
          <span class="step-index mono">{{ step.index }}</span>
          <div class="step-body">
            <div class="step-title">{{ step.title }}</div>
            <div class="step-desc">{{ step.desc }}</div>
          </div>
          <svg class="step-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6" /></svg>
        </router-link>
      </div>
    </div>

    <!-- 1. 基础模型测试指标（来源：测试集） -->
    <article class="glass-card section" v-loading="baselineLoading">
      <header class="section-head">
        <h3 class="card-title">基础模型测试指标</h3>
        <span class="source-badge">来源：测试集（UNSW-NB15 原划分）</span>
      </header>

      <div v-if="baselineError" class="state-error">
        <el-alert :title="baselineError" type="error" :closable="false" show-icon />
        <el-button size="small" @click="loadBaseline">重试</el-button>
      </div>

      <div v-else-if="!baselineReady" class="empty">
        <div class="empty-mark mono">&gt;_</div>
        <h3>尚未训练基础模型</h3>
        <p class="empty-hint">在项目根目录运行以下命令，生成基线模型与测试指标：</p>
        <code class="empty-cmd mono">python -m ml.cli baseline</code>
      </div>

      <template v-else-if="summary">
        <div class="stats">
          <div class="stat-card" v-tilt="6">
            <div class="stat-label">攻击召回率</div>
            <div class="stat-value mono">{{ percent(summary.metrics.test.recall) }}</div>
          </div>
          <div class="stat-card" v-tilt="6">
            <div class="stat-label">正常流量误报率</div>
            <div class="stat-value mono warn">{{ percent(summary.metrics.test.fpr) }}</div>
          </div>
          <div class="stat-card" v-tilt="6">
            <div class="stat-label">F1 分数</div>
            <div class="stat-value gradient-text">{{ summary.metrics.test.f1.toFixed(3) }}</div>
          </div>
          <div class="stat-card" v-tilt="6">
            <div class="stat-label">测试样本</div>
            <div class="stat-value mono">{{ summary.test_rows.toLocaleString() }}</div>
          </div>
        </div>
        <p class="hint">以上为<strong>测试集</strong>实测指标（带真实标签），与验证指标、检测预测数量口径不同。完整混淆矩阵与曲线见「评估分析」。</p>
      </template>
    </article>

    <!-- 2. 实验验证指标（来源：验证集） -->
    <article class="glass-card section" v-loading="experimentsLoading">
      <header class="section-head">
        <h3 class="card-title">最近训练实验（验证指标）</h3>
        <span class="source-badge accent2">来源：训练时留出的验证集</span>
      </header>

      <div v-if="experimentsError" class="state-error">
        <el-alert :title="experimentsError" type="error" :closable="false" show-icon />
        <el-button size="small" @click="loadExperiments">重试</el-button>
      </div>

      <div v-else-if="!experiments.length" class="empty small">
        <div class="empty-mark mono">≋</div>
        <h3>还没有训练实验</h3>
        <p class="empty-hint">到「模型实验」里训练逻辑回归、决策树或随机森林后，这里会显示验证指标。</p>
        <el-button @click="router.push('/experiments')">去训练模型</el-button>
      </div>

      <el-table v-else :data="recentExperiments" stripe>
        <el-table-column prop="id" label="编号" width="70" />
        <el-table-column prop="name" label="实验名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="algorithm_name" label="算法" width="95" />
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="statusTagType(row.status)" size="small">{{ experimentStatus(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="验证指标（准确率 / 攻击召回率 / F1 / 误报率）" min-width="270">
          <template #default="{ row }">
            <span v-if="row.status === 'succeeded' && row.metrics" class="mono metric-cell">
              {{ fmtPct(row.metrics.accuracy) }} / {{ fmtPct(row.metrics.recall) }} / {{ fmtPct(row.metrics.f1) }} / {{ fmtPct(row.metrics.fpr) }}
            </span>
            <span v-else class="muted">—（训练完成或成功后显示）</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110"><template #default="{ row }"><el-button link type="primary" @click="router.push('/experiments')">查看</el-button></template></el-table-column>
      </el-table>
    </article>

    <!-- 3. 检测预测数量（来源：检测任务统计，非真实标签） -->
    <article class="glass-card section" v-loading="detectionsLoading">
      <header class="section-head">
        <h3 class="card-title">最近检测任务（预测数量）</h3>
        <span class="source-badge accent3">来源：检测预测统计，非真实标签，不含准确率</span>
      </header>

      <div v-if="detectionsError" class="state-error">
        <el-alert :title="detectionsError" type="error" :closable="false" show-icon />
        <el-button size="small" @click="loadDetections">重试</el-button>
      </div>

      <div v-else-if="!detections.length" class="empty small">
        <div class="empty-mark mono">⊘</div>
        <h3>还没有检测任务</h3>
        <p class="empty-hint">导入数据并选择模型后，在「批量检测」里创建检测任务。</p>
        <el-button @click="router.push('/detections')">去批量检测</el-button>
      </div>

      <el-table v-else :data="recentDetections" stripe>
        <el-table-column prop="id" label="任务" width="80" />
        <el-table-column label="数据文件" min-width="160"><template #default="{ row }">{{ datasetName(row.dataset_id) }}</template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="statusTagType(row.status)" size="small">{{ detectionStatus(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="预测行数" min-width="140"><template #default="{ row }"><span class="mono">{{ row.processed_rows }} / {{ row.total_rows }}</span></template></el-table-column>
        <el-table-column label="操作" width="110"><template #default="{ row }"><el-button link type="primary" @click="router.push(`/detections/${row.id}`)">查看结果</el-button></template></el-table-column>
      </el-table>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { http, errorText, type Dataset, type DetectionTask } from '../api/client'
import { statusName } from '../api/status'

const router = useRouter()

interface Summary {
  algorithm: string; feature_count: number; train_rows: number; validation_rows: number;
  test_rows: number; train_seconds: number; limitations: string;
  metrics: { test: { recall: number; fpr: number; f1: number } };
}
interface Experiment {
  id: number; name: string; algorithm_name: string; status: string;
  metrics: Record<string, number> | null; created_at: string;
}

/* —— 快速开始四个入口 —— */
const steps = computed(() => [
  { index: '01', title: '导入数据', desc: '上传流量特征 CSV 或使用示例', to: '/data' },
  { index: '02', title: '训练模型', desc: '逻辑回归 / 决策树 / 随机森林', to: '/experiments' },
  { index: '03', title: '批量检测', desc: '选择数据与模型，后台运行', to: '/detections' },
  { index: '04', title: '查看结果', desc: '筛选、统计与下载预测结果', to: resultTarget.value },
])
const resultTarget = computed(() => {
  const done = detections.value.find(t => t.status === 'succeeded')
  return done ? `/detections/${done.id}` : '/detections'
})

const percent = (v: number) => (v * 100).toFixed(2) + '%'
const fmtPct = (v: number | undefined) => v === undefined || v === null ? '—' : (v * 100).toFixed(2) + '%'

/* —— 基础模型测试指标 —— */
const baselineLoading = ref(true)
const baselineError = ref('')
const baselineReady = ref(false)
const summary = ref<Summary | null>(null)
async function loadBaseline() {
  baselineLoading.value = true; baselineError.value = ''
  try {
    const response = await http.get('/baseline')
    baselineReady.value = response.data.ready
    summary.value = response.data.summary
  } catch (e) {
    baselineReady.value = false
    summary.value = null
    baselineError.value = errorText(e)
  } finally { baselineLoading.value = false }
}

/* —— 实验（验证指标）—— */
const experimentsLoading = ref(true)
const experimentsError = ref('')
const experiments = ref<Experiment[]>([])
async function loadExperiments() {
  experimentsLoading.value = true; experimentsError.value = ''
  try {
    const response = await http.get<Experiment[]>('/experiments')
    experiments.value = response.data
  } catch (e) { experimentsError.value = errorText(e) } finally { experimentsLoading.value = false }
}
const recentExperiments = computed(() => experiments.value.slice(0, 6))

/* —— 检测（预测数量）—— */
const detectionsLoading = ref(true)
const detectionsError = ref('')
const detections = ref<DetectionTask[]>([])
const datasets = ref<Dataset[]>([])
async function loadDetections() {
  detectionsLoading.value = true; detectionsError.value = ''
  try {
    const response = await http.get<DetectionTask[]>('/detections')
    detections.value = response.data
  } catch (e) { detectionsError.value = errorText(e) } finally { detectionsLoading.value = false }
}
async function loadDatasets() {
  try { datasets.value = (await http.get<Dataset[]>('/datasets')).data } catch { /* 名称回退为编号，无需中断整页 */ }
}
const recentDetections = computed(() => detections.value.slice(0, 6))
const datasetName = (id: number) => datasets.value.find(d => d.id === id)?.name ?? `数据 #${id}`

const experimentStatus = (s: string) => ({ queued: '排队中', running: '训练中', succeeded: '成功', failed: '失败', interrupted: '已中断' }[s] ?? s)
const detectionStatus = (s: string) => statusName(s)
const statusTagType = (s: string) => ({ succeeded: 'success', running: 'primary', queued: 'warning', failed: 'danger', interrupted: 'danger' }[s] ?? 'info')

onMounted(() => { loadBaseline(); loadExperiments(); loadDetections(); loadDatasets() })
</script>

<style scoped>
.dash { max-width: 1180px; }

/* —— 快速开始 —— */
.quickstart { padding: 24px; margin-bottom: 20px; }
.card-title { margin: 0 0 16px; font-size: 16px; font-weight: 650; }
.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.step {
  position: relative;
  display: flex; align-items: center; gap: 12px;
  padding: 16px 14px;
  border: 1px solid var(--id-border);
  border-radius: var(--id-radius-sm);
  background: var(--id-surface-strong);
  color: var(--id-text);
  text-decoration: none;
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
.step:hover { transform: translateY(-2px); border-color: var(--id-border-strong); box-shadow: 0 10px 28px -16px rgba(45,212,191,.35); }
.step-index {
  flex: none; width: 34px; height: 34px;
  display: grid; place-items: center;
  border-radius: 9px; background: var(--id-gradient); color: #05110f;
  font-size: 13px; font-weight: 700;
}
.step-title { font-size: 14px; font-weight: 600; }
.step-desc { font-size: 12px; color: var(--id-text-dim); margin-top: 3px; line-height: 1.5; }
.step-arrow { width: 16px; height: 16px; margin-left: auto; color: var(--id-text-faint); flex: none; }

/* —— 指标分区 —— */
.section { padding: 24px; margin-bottom: 20px; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }
.section-head .card-title { margin: 0; }
.source-badge {
  font-size: 12px; color: var(--id-text-dim);
  border: 1px solid var(--id-border); border-radius: 999px; padding: 4px 12px;
  background: color-mix(in srgb, var(--id-accent) 8%, transparent);
}
.source-badge.accent2 { background: color-mix(in srgb, var(--id-accent-2) 10%, transparent); }
.source-badge.accent3 { background: color-mix(in srgb, var(--id-warn) 10%, transparent); }

/* —— 状态块 —— */
.state-error { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.state-error .el-alert { flex: 1; }
.empty { padding: 36px 20px; text-align: center; }
.empty.small { padding: 24px 20px; }
.empty-mark {
  font-size: 25px; color: var(--id-accent);
  width: 56px; height: 56px; margin: 0 auto 14px;
  display: grid; place-items: center;
  border: 1px solid var(--id-border); border-radius: 13px;
  background: var(--id-gradient-soft);
  box-shadow: 0 0 24px -6px rgba(45,212,191,.5);
}
.empty h3 { margin: 0 0 8px; font-size: 16px; }
.empty-hint { color: var(--id-text-dim); margin: 0 0 14px; }
.empty-cmd {
  display: inline-block; padding: 9px 16px;
  border-radius: 10px; border: 1px solid var(--id-border);
  background: var(--id-surface-strong); color: var(--id-accent); font-size: 14px;
}
.hint { color: var(--id-text-dim); line-height: 1.7; margin: 14px 0 0; }
.muted { color: var(--id-text-faint); }
.metric-cell { color: var(--id-text); }

/* —— 指标卡（沿用现有设计系统）—— */
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }

/* —— 响应式 —— */
@media (max-width: 1000px) {
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .steps { grid-template-columns: 1fr; }
  .stats { grid-template-columns: 1fr; }
  .section-head { flex-direction: column; align-items: flex-start; }
}
</style>