import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: () => import('./views/Dashboard.vue') },
  { path: '/data', component: () => import('./views/DataManagement.vue') },
  { path: '/experiments', component: () => import('./views/Experiments.vue') },
  { path: '/detections', component: () => import('./views/Detections.vue') },
  { path: '/detections/:id', component: () => import('./views/DetectionDetail.vue') },
  { path: '/evaluation', component: () => import('./views/Evaluation.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})