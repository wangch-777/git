<template>
  <div>
    <h2>评估分析</h2>
    <p>混淆矩阵、每类 Recall/F1、PR 曲线与误判样本。仅当数据含真实标签且划分合规时展示。</p>
    <el-empty description="无真实标签时评估入口不可用" />
  </div>
</template>

<script setup lang="ts"></script>