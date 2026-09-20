<template>
  <article class="glass-card diagnostics">
    <h3>误报／漏报与阈值实验</h3>
    <p>误报：正常流量被判为攻击；漏报：攻击流量被判为正常。分数是模型对攻击类别的支持度，不是真实攻击概率。</p>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" />
    <el-button v-if="loadError" @click="loadAnalysis">重试误差分析</el-button>
    <div v-loading="loading">
      <template v-if="analysis">
        <el-radio-group v-model="scope" aria-label="分析数据范围">
          <el-radio-button value="validation">验证集：阈值试验</el-radio-button>
          <el-radio-button value="test">测试集：固定结果</el-radio-button>
        </el-radio-group>
        <p v-if="scope === 'validation'">以下指标和样本随阈值实时更新，仅用于验证集探索，不会修改检测模型或最终测试结果。</p>
        <p v-else>测试集阈值固定为 {{ analysis.fixed_threshold }}。要调整阈值，请切换到验证集。</p>
        <div v-if="scope === 'validation'" class="threshold">
          <label>攻击判定阈值：{{ threshold.toFixed(2) }}</label>
          <el-slider v-model="thresholdIndex" :min="0" :max="100" :step="1" :format-tooltip="formatThreshold" aria-label="验证集攻击阈值" />
          <p>拖动滑块调整阈值，步长0.01；聚焦滑块后也可用方向键微调。</p>
          <el-button @click="thresholdIndex = 50">重置为0.50</el-button>
        </div>
        <p>当前：{{ scope === 'validation' ? '验证集' : '原测试集' }} · {{ current?.rows.toLocaleString() }}条 · 阈值{{ threshold.toFixed(2) }} · 攻击分数≥阈值判为攻击</p>
        <div class="metric-grid" v-if="current">
          <div v-for="(label,key) in metricNames" :key="key"><span>{{ label }}</span><strong>{{ percent(current[key]) }}</strong></div>
        </div>
        <div class="error-actions" v-if="current">
          <el-button :type="kind === 'fp' ? 'danger' : 'default'" @click="kind = 'fp'">误报正常样本：{{ current.fp }}条</el-button>
          <el-button :type="kind === 'fn' ? 'warning' : 'default'" @click="kind = 'fn'">漏报攻击样本：{{ current.fn }}条</el-button>
        </div>
        <Chart v-if="scope === 'validation'" :option="thresholdChart" label="验证集阈值与召回率、误报率、F1变化曲线" />
        <h4>{{ kind === 'fp' ? '被误报的正常样本' : '被漏报的攻击样本' }}</h4>
        <p>来源：{{ scope === 'validation' ? 'UNSW_NB15_training-set.csv 的留出验证部分' : 'UNSW_NB15_testing-set.csv' }}。数据行从0开始，CSV行号含表头，从1开始。点击“完整特征”查看原始记录。</p>
        <el-alert v-if="samplesError" :title="samplesError" type="error" :closable="false" />
        <el-button v-if="samplesError" @click="loadSamples">重试样本</el-button>
        <div v-loading="samplesLoading">
          <el-empty v-if="!samplesLoading && !samplesError && !samples.length" description="当前范围和阈值下没有此类错误样本" />
          <el-table v-if="samples.length" :data="samples" stripe>
            <el-table-column prop="source_row_id" label="原数据行" width="105" />
            <el-table-column label="CSV行号" width="105"><template #default="{row}">{{ row.source_row_id + 2 }}</template></el-table-column>
            <el-table-column prop="true_name" label="真实类别" width="100" />
            <el-table-column prop="predicted_name" label="预测类别" width="100" />
            <el-table-column label="攻击分数" width="115"><template #default="{row}">{{ row.attack_score.toFixed(4) }}</template></el-table-column>
            <el-table-column prop="proto" label="协议" width="90" />
            <el-table-column prop="service" label="服务" width="95" />
            <el-table-column prop="attack_cat" label="原始攻击类型" min-width="130" />
            <el-table-column label="查看" width="110"><template #default="{row}"><el-button link type="primary" @click="selected = row; drawerOpen = true">完整特征</el-button></template></el-table-column>
          </el-table>
        </div>
        <el-pagination v-if="total > 0" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="scheduleSamples" />
      </template>
      <p v-else-if="loading">正在读取误差分析数据…</p>
    </div>
    <el-drawer v-model="drawerOpen" title="错误样本原始特征" size="min(650px, 95vw)">
      <p>label、attack_cat、id仅供追溯，不作为训练输入；attack_score是诊断分数。</p>
      <el-table :data="Object.entries(selected ?? {}).map(([field,value]) => ({field,value}))">
        <el-table-column prop="field" label="字段" /><el-table-column prop="value" label="值" />
      </el-table>
    </el-drawer>
  </article>
  <article class="glass-card diagnostics" v-loading="duplicateLoading">
    <h3>重复数据影响：去重前后对比</h3>
    <el-alert v-if="duplicateError" :title="duplicateError" type="error" :closable="false" />
    <el-button v-if="duplicateError" @click="loadDuplicates">重试去重分析</el-button>
    <template v-if="duplicate">
      <p>{{ duplicate.source }}。移除训练源重复记录{{ duplicate.removed.toLocaleString() }}条；标签冲突{{ duplicate.conflicts }}组；原测试与训练源重叠{{ duplicate.overlap.toLocaleString() }}条。</p>
      <el-alert :title="duplicate.conclusion" type="warning" :closable="false" />
      <p>{{ duplicate.limitations }}</p>
      <Chart :option="duplicateChart" label="相同原测试集上去重前后的误报率、召回率和F1对比" />
      <el-table :data="duplicate.rows" stripe>
        <el-table-column prop="name" label="实验方案" min-width="190" /><el-table-column prop="scope" label="评价范围" width="115" />
        <el-table-column v-for="(title,key) in metricNames" :key="key" :label="title" width="125"><template #default="{row}">{{ percent(row[key]) }}</template></el-table-column>
      </el-table>
      <p>历史验证选参后的模型：阈值{{ duplicate.selected.threshold.toFixed(6) }}，最终测试误报率{{ percent(duplicate.selected.test.fpr) }}、召回率{{ percent(duplicate.selected.test.recall) }}。这些是冻结的历史结果，不随上方滑块改变。</p>
    </template>
  </article>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from './Chart.vue'
import { http, errorText } from '../api/client'
interface Metrics { threshold:number; rows:number; tn:number; fp:number; fn:number; tp:number; accuracy:number; precision:number; recall:number; f1:number; fpr:number }
interface Analysis { model_hash:string; fixed_threshold:number; thresholds:Metrics[]; test:Metrics }
interface Sample { source_row_id:number; attack_score:number; [key:string]:string|number|null }
interface Duplicate { rows:Array<Metrics & {name:string; scope:string}>; removed:number; conflicts:number; overlap:number; source:string; conclusion:string; limitations:string; selected:{threshold:number; test:Metrics} }
const metricNames = {accuracy:'准确率', precision:'攻击精确率', recall:'攻击召回率', f1:'攻击F1', fpr:'正常误报率'}
const percent = (value:number) => (value * 100).toFixed(2) + '%'
const formatThreshold = (value:number) => (value / 100).toFixed(2)
const analysis = ref<Analysis>(), duplicate = ref<Duplicate>()
const loading = ref(false), loadError = ref(''), duplicateLoading = ref(false), duplicateError = ref('')
const scope = ref<'validation'|'test'>('validation'), thresholdIndex = ref(50), kind = ref<'fp'|'fn'>('fp'), page = ref(1)
const threshold = computed(() => scope.value === 'test' ? analysis.value?.fixed_threshold ?? .5 : thresholdIndex.value / 100)
const current = computed(() => scope.value === 'test' ? analysis.value?.test : analysis.value?.thresholds[thresholdIndex.value])
const samples = ref<Sample[]>([]), samplesError = ref(''), samplesLoading = ref(false), total = ref(0)
const selected = ref<Sample>(), drawerOpen = ref(false)
let timer:ReturnType<typeof setTimeout>|undefined, sequence = 0, stopped = false
const thresholdChart = computed(() => ({tooltip:{trigger:'axis'},legend:{bottom:0},grid:{left:55,right:20,top:30,bottom:70},
  xAxis:{type:'value',name:'阈值',min:0,max:1},yAxis:{type:'value',min:0,max:1},
  series:([['recall','攻击召回率'],['fpr','正常误报率'],['f1','攻击F1']] as const).map(([key,name]) => ({type:'line',name,showSymbol:false,data:analysis.value?.thresholds.map(m=>[m.threshold,m[key]]) ?? []}))}))
const duplicateChart = computed(() => {const rows=duplicate.value?.rows.filter(r=>r.scope === '原测试集') ?? []; return {
  tooltip:{trigger:'axis'},legend:{bottom:0},grid:{left:55,right:20,top:30,bottom:70},xAxis:{type:'category',data:rows.map(r=>r.name)},yAxis:{type:'value',min:0,max:1},
  series:([['fpr','正常误报率'],['recall','攻击召回率'],['f1','攻击F1']] as const).map(([key,name])=>({type:'bar',name,data:rows.map(r=>r[key])}))}})
async function loadAnalysis(){
  loading.value=true;loadError.value=''
  try {const response=await http.get<Analysis>('/evaluation/diagnostics'); if(stopped)return;analysis.value=response.data;scheduleSamples()}
  catch(e){if(!stopped){analysis.value=undefined;loadError.value=errorText(e)}}
  finally{loading.value=false}
}
async function loadDuplicates(){
  duplicateLoading.value=true;duplicateError.value=''
  try{const response=await http.get<Duplicate>('/evaluation/duplicates');if(!stopped)duplicate.value=response.data}
  catch(e){if(!stopped){duplicate.value=undefined;duplicateError.value=errorText(e)}}
  finally{duplicateLoading.value=false}
}
function scheduleSamples(){
  clearTimeout(timer);sequence++;samples.value=[];samplesError.value='';samplesLoading.value=true;total.value=current.value?.[kind.value] ?? 0
  timer=setTimeout(loadSamples,250)
}
async function loadSamples(){
  clearTimeout(timer);const id=++sequence;samplesLoading.value=true;samplesError.value=''
  try{const response=await http.get<{total:number;items:Sample[]}>('/evaluation/errors',{params:{split:scope.value,threshold:threshold.value,kind:kind.value,page:page.value}})
    if(stopped||id!==sequence)return;samples.value=response.data.items;total.value=response.data.total}
  catch(e){if(!stopped&&id===sequence)samplesError.value=errorText(e)}
  finally{if(!stopped&&id===sequence)samplesLoading.value=false}
}
watch([scope,thresholdIndex,kind],()=>{page.value=1;drawerOpen.value=false;scheduleSamples()})
onMounted(()=>{loadAnalysis();loadDuplicates()})
onBeforeUnmount(()=>{stopped=true;sequence++;clearTimeout(timer)})
</script>

<style scoped>
.diagnostics{padding:24px;margin:24px 0;min-width:0}.diagnostics p{line-height:1.8;color:var(--text-muted,#9aa7bd)}
.threshold{margin:24px 0}.threshold .el-slider{max-width:650px}.threshold span{margin:0 12px}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:16px;margin:20px 0}.metric-grid span{display:block;color:#9aa7bd}.metric-grid strong{display:block;font-size:24px;margin-top:6px}.error-actions{display:flex;gap:12px;flex-wrap:wrap}.error-actions .el-button{margin:0}.el-pagination{margin-top:16px;overflow:auto}
</style>
