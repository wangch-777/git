<template>
  <section v-loading="loading">
    <h2 class="page-title">模型实验</h2>
    <p class="page-sub">训练模型、查看阶段日志，对比相同数据划分下的验证结果，并选用模型进行检测。</p>
    <el-alert v-if="error || loadError" :title="error || loadError" type="error" :closable="false" show-icon />
    <el-alert v-if="notice" :title="notice" type="success" :closable="false" />
    <article class="glass-card experiment-form">
      <h3>新建训练实验</h3>
      <p class="hint">训练必须有真实标签。可以使用原训练文件中的2000条示例，不会使用原测试文件。</p>
      <el-button :loading="preparing" :disabled="submitting" @click="prepareSample">准备训练示例</el-button>
      <el-button @click="router.push('/data')">上传带标签的数据</el-button>
      <el-form label-position="top" class="fields" @submit.prevent="submit">
        <el-form-item label="实验名称"><el-input v-model="name" maxlength="100" placeholder="给这次实验起个名字" /></el-form-item>
        <el-form-item label="训练数据集">
          <el-select v-model="datasetId" placeholder="请选择带真实标签的数据" style="width:100%">
            <el-option v-for="d in datasets.filter(d => d.label_available)" :key="d.id" :value="d.id" :label="`${d.name}（${d.row_count}条）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="训练算法">
          <el-radio-group v-model="algorithm"><el-radio-button v-for="(title,key) in algorithms" :key="key" :value="key">{{ title }}</el-radio-button></el-radio-group>
        </el-form-item>
        <el-form-item label="类别权重"><el-select v-model="weight" style="width:100%"><el-option label="平衡类别" value="balanced" /><el-option label="不加权" value="none" /></el-select></el-form-item>
        <template v-if="algorithm === 'logistic_regression'">
          <el-form-item label="正则化强度倒数"><el-input-number v-model="c" :min="0.001" :max="100" :step="0.1" /></el-form-item>
          <el-form-item label="最大迭代次数"><el-input-number v-model="iterations" :min="100" :max="5000" :step="100" /></el-form-item>
        </template>
        <template v-else>
          <el-form-item label="树的最大深度"><el-input-number v-model="depth" :min="1" :max="40" :step="1" :precision="0" /></el-form-item>
          <el-form-item label="叶节点最少样本数"><el-input-number v-model="leaf" :min="1" :max="50" :precision="0" /></el-form-item>
          <el-form-item v-if="algorithm === 'random_forest'" label="森林中的树数"><el-input-number v-model="trees" :min="10" :max="300" :step="10" :precision="0" /></el-form-item>
        </template>
        <el-form-item label="验证分组占比（%）"><el-input-number v-model="validation" :min="10" :max="40" :step="5" :precision="0" /></el-form-item>
        <el-form-item label="随机种子"><el-input-number v-model="seed" :min="0" :max="2147483647" :precision="0" /></el-form-item>
      </el-form>
      <p class="hint">相同特征记录保留在同一组；预处理只在训练部分拟合。检测阈值固定为0.5。</p>
      <el-button type="primary" :loading="submitting" :disabled="!datasetId || preparing" @click="submit">启动训练</el-button>
      <el-button :loading="refreshing" @click="refresh">刷新实验</el-button>
    </article>

    <h3>实验记录</h3>
    <p class="hint">进度表示处理阶段，不是已完成的树数。后台训练期间可以切换页面。</p>
    <div v-if="!loading && !records.length && !error && !loadError" class="empty glass-card">
      <div class="empty-mark mono">≋</div>
      <h3>还没有训练实验</h3>
      <p class="hint">点击“准备训练示例”，选择算法后启动训练。</p>
    </div>
    <el-table v-if="records.length" :data="records" row-key="id" stripe>
      <el-table-column prop="id" label="编号" width="70" />
      <el-table-column prop="name" label="实验名称" min-width="160" />
      <el-table-column prop="algorithm_name" label="算法" width="100" />
      <el-table-column prop="dataset_name" label="数据集" min-width="190" show-overflow-tooltip />
      <el-table-column label="状态与阶段" min-width="170"><template #default="{row}">
        <span>{{ statusName(row.status) }}</span>
        <el-progress :percentage="row.progress" :status="row.status === 'succeeded' ? 'success' : undefined" />
      </template></el-table-column>
      <el-table-column label="创建时间" min-width="175"><template #default="{row}">{{ date(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" width="255"><template #default="{row}">
        <el-button link type="primary" @click="selectedId = row.id; detailsOpen = true">日志详情</el-button>
        <el-button v-if="row.model_id" link type="success" @click="useModel(row)">选它去检测</el-button>
        <el-button v-if="['failed','interrupted'].includes(row.status)" link type="warning" :disabled="actionId === row.id" @click="retry(row)">重试</el-button>
        <el-button link @click="editId = row.id; editName = row.name; editOpen = true">重命名</el-button>
        <el-popconfirm title="从实验列表移除并停用此模型？历史记录保留。" confirm-button-text="移除" cancel-button-text="取消" @confirm="remove(row)">
          <template #reference><el-button link type="danger" :disabled="row.status === 'running' || actionId === row.id">删除</el-button></template>
        </el-popconfirm>
      </template></el-table-column>
    </el-table>

    <article class="glass-card comparison">
      <h3>验证结果对比</h3>
      <p class="hint">只对比数据摘要、特征协议、随机种子和验证比例一致的实验。准确率、召回率和F1越高越好，误报率越低越好。验证结果不等于最终测试结果。</p>
      <el-select v-if="groups.length" v-model="comparisonKey" placeholder="选择可比较的实验组" style="width:100%">
        <el-option v-for="group in groups" :key="group.key" :value="group.key" :label="group.label" />
      </el-select>
      <el-empty v-if="!compared.length" description="成功训练后，这里会出现同一划分下的对比结果" />
      <el-table v-else :data="compared" stripe>
        <el-table-column label="实验" min-width="160"><template #default="{row}">#{{ row.id }} {{ row.algorithm_name }}<el-tag v-if="row.id === compared[0]?.id" size="small">本组F1最高</el-tag></template></el-table-column>
        <el-table-column label="超参数" min-width="230"><template #default="{row}">{{ paramText(row.params) }}</template></el-table-column>
        <el-table-column label="训练／验证条数" width="145"><template #default="{row}">{{ row.train_rows }} / {{ row.validation_rows }}</template></el-table-column>
        <el-table-column v-for="(title,key) in metrics" :key="key" :label="title" width="110"><template #default="{row}">{{ (row.metrics[key] * 100).toFixed(2) }}%</template></el-table-column>
        <el-table-column label="训练秒数" width="100"><template #default="{row}">{{ row.train_seconds?.toFixed(2) }}</template></el-table-column>
        <el-table-column label="选用" width="120"><template #default="{row}"><el-button link type="primary" @click="useModel(row)">选它去检测</el-button></template></el-table-column>
      </el-table>
    </article>

    <el-drawer v-model="detailsOpen" title="实验日志与追溯信息" size="min(650px, 95vw)">
      <template v-if="selected">
        <h3>#{{ selected.id }} {{ selected.name }}</h3>
        <p>{{ selected.algorithm_name }} · {{ statusName(selected.status) }}</p>
        <el-alert v-if="selected.error" :title="selected.error" type="error" :closable="false" />
        <p>数据集：{{ selected.dataset_name }}</p>
        <p class="digest">数据摘要：{{ selected.dataset_hash }}</p>
        <p>超参数：{{ paramText(selected.params) }}</p>
        <p>随机种子：{{ selected.seed }}；验证分组占比：{{ selected.validation_fraction * 100 }}%</p>
        <p>训练 {{ selected.train_rows ?? '待计算' }} 条；验证 {{ selected.validation_rows ?? '待计算' }} 条</p>
        <p>训练用时：{{ selected.train_seconds?.toFixed(2) ?? '待完成' }} 秒</p>
        <p>创建时间：{{ date(selected.created_at) }}</p>
        <el-timeline><el-timeline-item v-for="(log,index) in selected.logs" :key="index" :timestamp="date(log.time)">{{ log.message }}</el-timeline-item></el-timeline>
      </template>
    </el-drawer>
    <el-dialog v-model="editOpen" title="重命名实验" width="min(460px, 95vw)">
      <el-input v-model="editName" maxlength="100" aria-label="新的实验名称" />
      <p class="hint">训练参数保持不变，调整参数请新建实验。</p>
      <template #footer><el-button @click="editOpen = false">取消</el-button><el-button type="primary" :loading="actionId === editId" @click="rename">保存名称</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { http, errorText, type Dataset } from '../api/client'
interface Experiment {
  id: number; name: string; algorithm: string; algorithm_name: string; dataset_id: number; dataset_name: string;
  dataset_hash: string; params: Record<string, unknown>; seed: number; validation_fraction: number;
  train_rows: number | null; validation_rows: number | null; train_seconds: number | null;
  metrics: Record<string, number> | null; progress: number; status: string; error: string | null;
  logs: Array<{time: string; message: string}>; created_at: string; model_id: number | null; comparison_key: string;
}
const router = useRouter()
const algorithms = {logistic_regression:'逻辑回归',decision_tree:'决策树',random_forest:'随机森林'}
const metrics = {accuracy:'准确率',recall:'攻击召回率',f1:'攻击F1',fpr:'正常误报率'}
const algorithm = ref<keyof typeof algorithms>('logistic_regression')
const name = ref(''), datasetId = ref<number>(), weight = ref('balanced')
const c = ref(1), iterations = ref(1000), depth = ref(18), leaf = ref(2), trees = ref(80), seed = ref(42), validation = ref(20)
const datasets = ref<Dataset[]>([]), records = ref<Experiment[]>([])
const loading = ref(true), refreshing = ref(false), preparing = ref(false), submitting = ref(false)
const error = ref(''), loadError = ref(''), notice = ref(''), actionId = ref<number>()
const selectedId = ref<number>(), detailsOpen = ref(false), editId = ref<number>(), editName = ref(''), editOpen = ref(false)
const comparisonKey = ref('')
let stopped = false, timer: ReturnType<typeof setTimeout> | undefined
const selected = computed(() => records.value.find(r => r.id === selectedId.value))
const groups = computed(() => {
  const unique = new Map<string, string>()
  for (const r of records.value.filter(r => r.status === 'succeeded' && r.metrics))
    unique.set(r.comparison_key, `${r.dataset_name} · 种子${r.seed} · 验证${Math.round(r.validation_fraction * 100)}% · ${r.comparison_key.slice(0,6)}`)
  return [...unique].map(([key,label]) => ({key,label}))
})
const compared = computed(() => records.value.filter(r => r.status === 'succeeded' && r.metrics && r.comparison_key === comparisonKey.value).sort((a,b) => b.metrics!.f1 - a.metrics!.f1 || a.metrics!.fpr - b.metrics!.fpr))
const statusName = (status: string) => ({queued:'排队中',running:'训练中',succeeded:'成功',failed:'失败',interrupted:'已中断'}[status] ?? status)
const date = (value: string) => new Date(value.endsWith('Z') ? value : value + 'Z').toLocaleString('zh-CN')
function paramText(params: Record<string,unknown>) {
  const names: Record<string,string> = {C:'正则化倒数',max_iter:'迭代上限',max_depth:'最大深度',min_samples_leaf:'叶节点样本',n_estimators:'树数',class_weight:'类别权重',random_state:'随机种子',n_jobs:'并行数'}
  return Object.entries(params).map(([key,value]) => `${names[key] ?? key}：${value === 'balanced' ? '平衡' : value === null ? '不限制／不加权' : value}`).join('；')
}
async function refresh() {
  if (refreshing.value || stopped) return
  clearTimeout(timer); refreshing.value = true
  try {
    const [experiments, data] = await Promise.all([http.get<Experiment[]>('/experiments'), http.get<Dataset[]>('/datasets')])
    if (stopped) return
    records.value = experiments.data; datasets.value = data.data; loadError.value = ''
    if (!datasetId.value) datasetId.value = data.data.find(d=>d.label_available)?.id
    if (!groups.value.some(g=>g.key === comparisonKey.value)) comparisonKey.value = groups.value[0]?.key ?? ''
  } catch(e) { loadError.value = errorText(e) }
  finally {
    loading.value=false;refreshing.value=false
    if (!stopped) timer=setTimeout(refresh,2000)
  }
}
async function prepareSample() {
  preparing.value=true;error.value='';notice.value=''
  try {
    const result=await http.post<Dataset>('/experiments/sample', {}, {timeout:120000})
    datasetId.value=result.data.id
    datasets.value=[result.data,...datasets.value.filter(d=>d.id !== result.data.id)]
    notice.value=`训练示例已准备，共${result.data.row_count}条，请选择算法后启动训练`
  } catch(e) { error.value=errorText(e) }
  finally { preparing.value=false }
}
async function submit() {
  submitting.value=true;error.value='';notice.value=''
  const params: Record<string,unknown> = {class_weight:weight.value === 'balanced' ? 'balanced' : null}
  if (algorithm.value === 'logistic_regression') Object.assign(params,{C:c.value,max_iter:iterations.value})
  else Object.assign(params,{max_depth:depth.value,min_samples_leaf:leaf.value})
  if (algorithm.value === 'random_forest') params.n_estimators=trees.value
  try {
    const {data}=await http.post<Experiment>('/experiments',{dataset_id:datasetId.value,name:name.value.trim() || `${algorithms[algorithm.value]}实验`,algorithm:algorithm.value,params,seed:seed.value,validation_fraction:validation.value/100})
    records.value=[data,...records.value];selectedId.value=data.id
    notice.value=`实验#${data.id}已进入后台队列，可在下方查看进度与日志`
  } catch(e) { error.value=errorText(e) }
  finally { submitting.value=false }
}
async function retry(row: Experiment) {
  actionId.value=row.id
  try { const {data}=await http.post<Experiment>(`/experiments/${row.id}/retry`); records.value=[data,...records.value];notice.value=`已创建重试实验#${data.id}` }
  catch(e) {error.value=errorText(e)} finally {actionId.value=undefined}
}
async function remove(row: Experiment) {
  actionId.value=row.id
  try {await http.delete(`/experiments/${row.id}`);records.value=records.value.filter(r=>r.id!==row.id);notice.value='实验已移除，历史检测记录保留'}
  catch(e) {error.value=errorText(e)} finally {actionId.value=undefined}
}
async function rename() {
  actionId.value=editId.value
  try {const {data}=await http.patch<Experiment>(`/experiments/${editId.value}`,{name:editName.value});records.value=records.value.map(r=>r.id===data.id?data:r);editOpen.value=false}
  catch(e) {error.value=errorText(e)} finally {actionId.value=undefined}
}
function useModel(row: Experiment) { router.push({path:'/detections',query:{model:row.model_id}}) }
onMounted(refresh)
onBeforeUnmount(()=>{stopped=true;clearTimeout(timer)})
</script>

<style scoped>
.experiment-form, .comparison { padding: 24px; margin: 20px 0; }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 24px; margin-top: 20px; }
.el-alert { margin: 12px 0; }
.digest { overflow-wrap: anywhere; }
.el-timeline { margin-top: 24px; }
@media (max-width: 900px) { .fields { grid-template-columns: 1fr; } }
.empty { padding: 48px; text-align: center; }
.empty-mark {
  font-size: 24px; color: var(--id-accent);
  width: 58px; height: 58px; margin: 0 auto 16px;
  display: grid; place-items: center;
  border: 1px solid var(--id-border); border-radius: 14px;
  background: var(--id-gradient-soft);
}
.empty h3 { margin: 0 0 8px; font-size: 17px; }
.hint { color: var(--id-text-dim); margin: 0 0 16px; }
.cmd {
  display: inline-block;
  padding: 10px 18px;
  border-radius: 10px; border: 1px solid var(--id-border);
  background: var(--id-surface-strong);
  color: var(--id-accent);
}
</style>
