<template>
  <section v-loading="loading">
    <h2>基础模型评估</h2>
    <p>使用带真实标签的 UNSW-NB15 原划分测试文件，独立于用户上传的检测任务。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="data">
      <el-alert :title="data.limitations" type="warning" :closable="false" />
      <p>测试样本 {{ data.rows.toLocaleString() }} 条；攻击判定阈值 {{ data.threshold }}。</p>
      <el-table :data="metricRows" stripe><el-table-column prop="name" label="指标" /><el-table-column prop="value" label="实测值" /></el-table>
      <div class="charts">
        <article><h3>混淆矩阵</h3><p>纵轴为真实类别，横轴为预测类别，单位：条。</p><Chart :option="matrix" label="真实类别与预测类别的混淆矩阵" /></article>
        <article><h3>Precision–Recall 曲线</h3><p>攻击为正类；曲线最多展示250个点，AP使用完整分数计算。</p><Chart :option="pr" label="攻击类别的精确率召回率曲线" /></article>
      </div>
      <h3>每类检测表现</h3>
      <Chart :option="classChart" label="正常与攻击两类的精确率、召回率和F1比较" />
      <el-table :data="data.classes" stripe>
        <el-table-column prop="name" label="类别" /><el-table-column prop="support" label="真实样本数" />
        <el-table-column v-for="key in ['precision','recall','f1']" :key="key" :label="key"><template #default="scope">{{ scope.row[key].toFixed(4) }}</template></el-table-column>
      </el-table>
      <p>误报：{{ data.confusion[0][1] }} 条正常样本被预测为攻击；漏报：{{ data.confusion[1][0] }} 条攻击样本被预测为正常。</p>
    </template>
    <el-button @click="load" :loading="loading">刷新评价</el-button>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Chart from '../components/Chart.vue'
import { http, errorText } from '../api/client'
interface Evaluation {
  rows: number; threshold: number; limitations: string; confusion: number[][]; pr_curve: number[][];
  metrics: Record<string, number>;
  classes: Array<{name: string; precision: number; recall: number; f1: number; support: number}>;
}
const data = ref<Evaluation>(), loading = ref(false), error = ref('')
const metricRows = computed(() => Object.entries({precision:'攻击精确率',recall:'攻击召回率',f1:'攻击F1',fpr:'正常流量误报率',accuracy:'准确率',ap:'Average Precision（AP）'}).map(([key,name]) => ({name,value:data.value?.metrics[key].toFixed(4)})))
const matrix = computed(() => ({
  tooltip: {}, grid: {left: 65, right: 25, top: 25, bottom: 75},
  xAxis: {type:'category',data:['正常','攻击']}, yAxis:{type:'category',data:['正常','攻击'],inverse:true},
  visualMap:{min:0,max:Math.max(1,...(data.value?.confusion.flat() ?? [])),orient:'horizontal',left:'center',bottom:0,inRange:{color:['#13212b','#2dd4bf']}},
  series:[{type:'heatmap',label:{show:true},data:data.value?.confusion.flatMap((row,y)=>row.map((value,x)=>[x,y,value])) ?? []}]
}))
const pr = computed(() => ({
  tooltip:{trigger:'axis'},grid:{left:65,right:25,top:25,bottom:65},
  xAxis:{type:'value',name:'Recall',min:0,max:1,nameLocation:'middle',nameGap:30},
  yAxis:{type:'value',name:'Precision',min:0,max:1},
  series:[{type:'line',showSymbol:false,data:[...(data.value?.pr_curve ?? [])].reverse(),lineStyle:{color:'#2dd4bf',width:2}}]
}))
const classChart = computed(() => ({
  tooltip:{trigger:'axis'},legend:{bottom:0},grid:{left:50,right:25,top:25,bottom:65},
  xAxis:{type:'category',data:data.value?.classes.map(c=>c.name) ?? []},yAxis:{type:'value',min:0,max:1},
  series:(['precision','recall','f1'] as const).map((key,i)=>({name:key,type:'bar',data:data.value?.classes.map(c=>c[key]) ?? [],itemStyle:{color:['#2dd4bf','#8b7cff','#fbbf24'][i]}}))
}))
async function load() {
  loading.value=true;error.value=''
  try { data.value=(await http.get<Evaluation>('/evaluation')).data }
  catch(e) { data.value=undefined;error.value=errorText(e) }
  finally { loading.value=false }
}
onMounted(load)
</script>
<style scoped>
section { max-width: 1200px; } p { line-height: 1.7; }
.charts { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px; }
@media(max-width:1000px){.charts{grid-template-columns:1fr}}
</style>
