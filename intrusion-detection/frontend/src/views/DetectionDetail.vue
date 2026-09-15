<template>
  <section>
    <el-button link type="primary" @click="router.push('/detections')">返回检测任务</el-button>
    <h2>检测任务 #{{ route.params.id }}</h2>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="task">
      <p>状态：{{ statusName(task.status) }}　模型版本：{{ task.model_id }}　处理行数：{{ task.processed_rows }} / {{ task.total_rows }}</p>
      <el-progress :percentage="progress" :status="task.status === 'succeeded' ? 'success' : undefined" />
      <p v-if="task.status === 'queued'">任务正在排队。如果长时间未开始，请确认启动了后台 Worker。</p>
      <el-alert v-if="task.error" :title="task.error" type="error" :closable="false" />
      <p v-if="['failed', 'interrupted'].includes(task.status)"><el-button type="primary" :loading="retrying" @click="retry">重试此任务</el-button></p>
      <template v-if="task.status === 'succeeded'">
        <h3>预测结果</h3>
        <p>下面的数量是模型预测统计，不是实际攻击数量。没有经过核验的真实标签时，不计算准确率或误报率。</p>
        <div class="filters">
          <label>预测类别
            <select v-model="label" aria-label="预测类别">
              <option value="">全部</option><option value="0">正常</option><option value="1">攻击</option>
            </select>
          </label>
          <a :href="downloadUrl">下载当前筛选结果 CSV</a>
        </div>
        <p v-if="stats">当前筛选：{{ stats.total }} 条，正常 {{ stats.normal }} 条，攻击 {{ stats.attack }} 条，预测攻击占比 {{ (stats.attack_ratio * 100).toFixed(2) }}%。</p>
        <Chart v-if="stats && stats.total" :option="distribution" label="当前筛选的预测类别分布；可点击类别筛选" @select="label = $event === '正常' ? '0' : '1'" />
        <el-table :data="items" stripe v-loading="loading" empty-text="当前筛选没有结果">
          <el-table-column prop="source_row_id" label="数据行序号（从0开始）" min-width="160" />
          <el-table-column prop="predicted_name" label="预测结果" min-width="100" />
          <el-table-column label="预测类别分数" min-width="140"><template #default="scope">{{ scope.row.score.toFixed(4) }}</template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" />
        <p class="note">分数表示模型对所选类别的支持程度，不代表真实攻击概率。</p>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { http, errorText, type DetectionTask } from '../api/client'
import { statusName } from '../api/status'
import Chart from '../components/Chart.vue'
const route = useRoute(), router = useRouter()
const task = ref<DetectionTask>(), error = ref(''), label = ref(''), page = ref(1), total = ref(0)
const loading = ref(false), retrying = ref(false)
const items = ref<Array<{ source_row_id: number; predicted_name: string; score: number }>>([])
const stats = ref<{total: number; normal: number; attack: number; attack_ratio: number}>()
const distribution = computed(() => ({
  tooltip: { trigger: 'item' }, legend: { bottom: 0 }, color: ['#34d399', '#fb7185'],
  series: [{ type: 'pie', radius: ['40%', '68%'], label: { formatter: '{b}：{c}条' },
    data: [{name: '正常', value: stats.value?.normal ?? 0}, {name: '攻击', value: stats.value?.attack ?? 0}] }]
}))
const progress = computed(() => task.value?.total_rows ? Math.min(100, Math.round(task.value.processed_rows / task.value.total_rows * 100)) : 0)
const downloadUrl = computed(() => `/api/detections/${route.params.id}/report${label.value !== '' ? '?label=' + label.value : ''}`)
let timer: ReturnType<typeof setTimeout> | undefined, stopped = false, resultVersion = 0
async function loadResults() {
  const version = ++resultVersion
  loading.value = true
  const params = { page: page.value, page_size: 20, label: label.value === '' ? undefined : Number(label.value) }
  try {
    const [rows, counts] = await Promise.all([
      http.get(`/detections/${route.params.id}/results`, { params }),
      http.get(`/detections/${route.params.id}/statistics`, { params: { label: params.label } })
    ])
    if (version !== resultVersion || stopped) return
    items.value = rows.data.items; total.value = rows.data.total; stats.value = counts.data; error.value = ''
  } catch (e) { if (version === resultVersion) error.value = errorText(e) }
  finally { if (version === resultVersion) loading.value = false }
}
async function poll() {
  const id = route.params.id
  try {
    const response = await http.get<DetectionTask>(`/detections/${id}`)
    if (stopped || id !== route.params.id) return
    task.value = response.data; error.value = ''
    if (task.value.status === 'succeeded') await loadResults()
    else if (['queued', 'running'].includes(task.value.status)) timer = setTimeout(poll, 1000)
  } catch (e) { error.value = errorText(e); if (!stopped) timer = setTimeout(poll, 3000) }
}
async function retry() {
  retrying.value = true
  try { const response = await http.post<DetectionTask>(`/detections/${route.params.id}/retry`); router.push(`/detections/${response.data.id}`) }
  catch (e) { error.value = errorText(e) }
  finally { retrying.value = false }
}
watch(() => route.params.id, () => { clearTimeout(timer); task.value = undefined; items.value = []; stats.value = undefined; error.value = ''; label.value = ''; page.value = 1; resultVersion++; poll() }, { immediate: true })
watch(label, () => { if (page.value !== 1) page.value = 1; else if (task.value?.status === 'succeeded') loadResults() })
watch(page, () => { if (task.value?.status === 'succeeded') loadResults() })
onBeforeUnmount(() => { stopped = true; resultVersion++; clearTimeout(timer) })
</script>

<style scoped>
p { line-height: 1.7; }
.filters { display: flex; flex-wrap: wrap; gap: 24px; align-items: center; margin: 20px 0; }
select {
  margin-left: 10px; padding: 8px 18px;
  border: 1px solid var(--id-border-strong);
  border-radius: 8px;
  background: var(--id-surface-strong);
  color: var(--id-text);
  font-family: var(--id-font);
}
.el-pagination { margin-top: 20px; }
.note { color: var(--id-text-dim); }
.el-alert { margin: 16px 0; }
</style>
