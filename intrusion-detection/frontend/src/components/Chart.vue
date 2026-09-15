<template><div ref="element" class="chart" role="img" :aria-label="label" /></template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart, BarChart, LineChart, HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([PieChart, BarChart, LineChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, CanvasRenderer])
const props = defineProps<{ option: echarts.EChartsCoreOption; label: string }>()
const emit = defineEmits<{ select: [name: string] }>()
const element = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined, observer: ResizeObserver | undefined
const themed = (option: echarts.EChartsCoreOption): echarts.EChartsCoreOption => ({
  textStyle: { color: '#9aa7bd' },
  ...option,
})
onMounted(() => {
  chart = echarts.init(element.value!)
  chart.setOption(themed(props.option))
  chart.on('click', event => emit('select', event.name))
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value!)
})
watch(() => props.option, option => chart?.setOption(themed(option), true), { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>
<style scoped>.chart { width: 100%; height: 330px; min-width: 0; }</style>
