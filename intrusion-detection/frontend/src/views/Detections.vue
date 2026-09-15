<template>
  <section>
    <h2>批量检测</h2>
    <p>选择已校验的数据和检测模型。检测在本机后台运行，完成后可筛选与下载结果。</p>

    <!-- 请求失败：给出重试 -->
    <div v-if="loadError" class="state-error">
      <el-alert :title="loadError" type="error" :closable="false" show-icon />
      <el-button size="small" @click="load">重试</el-button>
    </div>

    <!-- 请求成功但缺少前置数据：给出引导 -->
    <el-alert v-else-if="guide" :title="guide" type="info" :closable="false" show-icon style="margin-bottom:16px">
      <template #default>
        <span v-if="!datasets.length">可先在「数据管理」导入文件或使用示例。</span>
        <span v-else-if="!models.length">可先在「模型实验」训练模型。</span>
      </template>
    </el-alert>

    <el-form v-loading="loading" label-position="top" class="form">
      <el-form-item label="数据文件">
        <el-select v-model="datasetId" placeholder="请选择已导入数据" style="width:100%">
          <el-option v-for="d in datasets" :key="d.id" :value="d.id" :label="`${d.name}（${d.row_count}行，#${d.id}）`" />
        </el-select>
      </el-form-item>
      <el-form-item label="检测模型">
        <el-select v-model="modelId" placeholder="请先训练基础模型" style="width:100%">
          <el-option v-for="m in models" :key="m.id" :value="m.id" :label="m.name" />
        </el-select>
      </el-form-item>
      <div class="actions">
        <el-button type="primary" :disabled="!datasetId || !modelId" :loading="busy" @click="start">开始检测</el-button>
        <el-button @click="router.push('/data')">导入其他文件</el-button>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    </el-form>

    <div class="task-head">
      <h3>最近100个检测任务</h3>
      <el-button link type="primary" :loading="tasksLoading && !tasks.length" @click="refreshTasks">手动刷新</el-button>
    </div>
    <el-table :data="tasks" stripe v-loading="tasksLoading && !tasks.length" empty-text="还没有检测任务，创建一次检测后会出现在这里">
      <el-table-column prop="id" label="任务编号" width="100" />
      <el-table-column label="数据文件" min-width="160"><template #default="scope">{{ datasets.find(d => d.id === scope.row.dataset_id)?.name || `数据 #${scope.row.dataset_id}` }}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="scope">{{ statusName(scope.row.status) }}</template></el-table-column>
      <el-table-column label="处理进度" min-width="150"><template #default="scope">{{ scope.row.processed_rows }} / {{ scope.row.total_rows }}</template></el-table-column>
      <el-table-column label="操作" width="120"><template #default="scope"><el-button link type="primary" @click="router.push(`/detections/${scope.row.id}`)">查看任务</el-button></template></el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { http, errorText, type Dataset, type Model, type DetectionTask } from '../api/client'
import { statusName } from '../api/status'
const router = useRouter(), route = useRoute()
const datasets = ref<Dataset[]>([]), models = ref<Model[]>([]), tasks = ref<DetectionTask[]>([])
const datasetId = ref<number>(), modelId = ref<number>()
const error = ref(''), loadError = ref(''), guide = ref(''), busy = ref(false)
const loading = ref(true), tasksLoading = ref(false)
let stopped = false, timer: ReturnType<typeof setTimeout> | undefined

async function load() {
  loading.value = true; loadError.value = ''; guide.value = ''
  try {
    const [d, m] = await Promise.all([http.get<Dataset[]>('/datasets'), http.get<Model[]>('/models')])
    datasets.value = d.data; models.value = m.data
    const requested = Number(route.query.dataset)
    datasetId.value = d.data.find(x => x.id === requested)?.id ?? d.data[0]?.id
    const requestedModel = Number(route.query.model)
    modelId.value = m.data.find(x => x.id === requestedModel)?.id ?? m.data[0]?.id
    if (!d.data.length) guide.value = '还没有可用的数据，请先导入文件或使用示例。'
    else if (!m.data.length) guide.value = '还没有可用模型，请先在「模型实验」训练。'
  } catch (e) { loadError.value = errorText(e) }
  finally { loading.value = false }
  if (!stopped) refreshTasks()
}

async function refreshTasks() {
  if (stopped) return
  tasksLoading.value = true
  try { tasks.value = (await http.get<DetectionTask[]>('/detections')).data }
  catch { /* 轮询失败不打断页面，下次重试 */ }
  finally {
    tasksLoading.value = false
    if (!stopped) timer = setTimeout(refreshTasks, 2000)
  }
}

async function start() {
  busy.value = true; error.value = ''
  try {
    const { data } = await http.post<DetectionTask>('/detections', { dataset_id: datasetId.value, model_id: modelId.value })
    router.push(`/detections/${data.id}`)
  } catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}

onMounted(load)
onBeforeUnmount(() => { stopped = true; clearTimeout(timer) })
</script>

<style scoped>
.form { max-width: 640px; margin: 24px 0 12px; }
.actions { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 4px; }
p { line-height: 1.7; }
.state-error { display: flex; align-items: center; gap: 12px; }
.state-error .el-alert { flex: 1; }
.task-head { display: flex; align-items: baseline; justify-content: space-between; margin-top: 28px; }
.task-head h3 { margin: 0; }
</style>