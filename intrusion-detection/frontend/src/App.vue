<template>
  <el-container class="layout">
    <el-aside width="220px">
      <div class="logo">入侵检测系统</div>
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/dashboard">分析总览</el-menu-item>
        <el-menu-item index="/data">数据管理</el-menu-item>
        <el-menu-item index="/experiments">模型实验</el-menu-item>
        <el-menu-item index="/detections">批量检测</el-menu-item>
        <el-menu-item index="/evaluation">评估分析</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>基于机器学习的网络入侵检测与可视化分析系统</el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts"></script>

<style scoped>
.layout {
  height: 100vh;
}
.logo {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-weight: 600;
  color: #fff;
  background: #1f2d3d;
}
.el-aside {
  background: #1f2d3d;
}
.el-aside :deep(.el-menu) {
  border-right: none;
  background: #1f2d3d;
}
.el-aside :deep(.el-menu-item) {
  color: #bfcbd9;
}
.el-aside :deep(.el-menu-item.is-active) {
  color: #409eff;
}
.el-header {
  line-height: 56px;
  font-size: 18px;
  font-weight: 600;
  border-bottom: 1px solid #eee;
}
</style>