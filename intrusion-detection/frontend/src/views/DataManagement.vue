<template>
  <section>
    <h2>数据管理</h2>
    <p>上传流量特征 CSV，校验通过后即可检测。支持 UTF-8 编码，最多 50MB、300,000 行。</p>
    <p>第一次使用？可以直接使用已准备的100条示例，或<a href="/api/datasets/sample">下载示例文件</a>查看格式。</p>
    <div class="actions">
      <label>选择 CSV 文件 <input type="file" accept=".csv" @change="choose" :disabled="busy" /></label>
      <el-button type="primary" :disabled="!file" :loading="busy" @click="upload">上传并校验</el-button>
      <el-button :disabled="busy" @click="demo">使用100条示例</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="uploaded" :title="`${uploaded.name} 校验通过，共 ${uploaded.row_count} 行`" type="success" :closable="false" />
    <p v-if="uploaded"><el-button type="success" @click="detect(uploaded.id)">下一步：开始检测</el-button></p>
    <h3>已导入的数据</h3>
    <div v-if="loadError" class="state-error">
      <el-alert :title="loadError" type="error" :closable="false" show-icon />
      <el-button size="small" @click="load">重试</el-button>
    </div>
    <el-table v-else :data="datasets" stripe v-loading="listLoading" empty-text="还没有数据，请上传或使用示例">
      <el-table-column prop="name" label="文件名" min-width="190" />
      <el-table-column prop="row_count" label="行数" width="100" />
      <el-table-column label="操作" width="200">
        <template #default="scope">
          <el-button link type="primary" @click="showPreview(scope.row.id)">预览</el-button>
          <el-button link type="primary" @click="detect(scope.row.id)">去检测</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="previewOpen" title="前5行数据预览" width="90%">
      <el-table :data="preview.rows" max-height="360">
        <el-table-column v-for="col in preview.columns" :key="col" :prop="col" :label="col" min-width="125" />
      </el-table>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { http, errorText, type Dataset } from '../api/client'
const router = useRouter()
const file = ref<File | null>(null)
const busy = ref(false)
const error = ref('')
const listLoading = ref(true)
const loadError = ref('')
const datasets = ref<Dataset[]>([])
const uploaded = ref<Dataset | null>(null)
const previewOpen = ref(false)
const preview = ref<{ columns: string[]; rows: Record<string, unknown>[] }>({columns: [], rows: []})
function choose(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] ?? null; error.value = ''; uploaded.value = null }
async function refresh() { datasets.value = (await http.get<Dataset[]>('/datasets')).data }
async function load() {
  listLoading.value = true; loadError.value = ''
  try { datasets.value = (await http.get<Dataset[]>('/datasets')).data }
  catch (e) { loadError.value = errorText(e) }
  finally { listLoading.value = false }
}
async function upload() {
  if (!file.value) return
  if (file.value.size > 50 * 1024 * 1024) { error.value = '文件超过50MB，请拆分后上传'; return }
  const form = new FormData(); form.append('file', file.value)
  await importData(() => http.post<Dataset>('/datasets', form, { timeout: 120000 }))
}
async function demo() { await importData(() => http.post<Dataset>('/datasets/demo')) }
async function importData(request: () => Promise<{ data: Dataset }>) {
  busy.value = true; error.value = ''; uploaded.value = null
  try { uploaded.value = (await request()).data; await refresh() }
  catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}
function detect(id: number) { router.push({ path: '/detections', query: { dataset: id } }) }
async function showPreview(id: number) {
  try { preview.value = (await http.get(`/datasets/${id}/preview`)).data; previewOpen.value = true }
  catch (e) { error.value = errorText(e) }
}
onMounted(load)
</script>

<style scoped>
p { line-height: 1.7; }
.state-error { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.state-error .el-alert { flex: 1; }
.actions { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin: 24px 0; }
.el-alert { margin-top: 12px; }
h3 { margin-top: 28px; }
</style>
