import { createApp } from 'vue'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/theme.css'
import App from './App.vue'
import { router } from './router'
import { magnet, tilt } from './directives/motion'

document.documentElement.classList.add('dark')

const app = createApp(App)
app.directive('magnet', magnet)
app.directive('tilt', tilt)
app.use(router).mount('#app')