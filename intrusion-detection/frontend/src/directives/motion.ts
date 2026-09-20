import type { Directive } from 'vue'

/**
 * 交互动效指令集：
 *  v-magnet —— 磁吸：元素随指针位移（rAF 缓动跟随），移出后弹性回位（适合按钮 / 导航）
 *  v-tilt   —— 3D 视差：元素随指针倾斜，并通过 --mx/--my 驱动扫光高光（适合卡片）
 * 均尊重系统「减少动态效果」偏好，降级为静止。
 */

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const store = new WeakMap<HTMLElement, () => void>()

export const magnet: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    if (prefersReducedMotion()) return
    const strength = binding.value ?? 0.34
    let tx = 0, ty = 0      // 目标偏移
    let cx = 0, cy = 0      // 当前偏移
    let hovering = false
    let raf = 0
    el.style.willChange = 'transform'
    const tick = () => {
      const ease = hovering ? 0.16 : 0.14
      cx += (tx - cx) * ease
      cy += (ty - cy) * ease
      if (!hovering && Math.abs(tx - cx) < 0.05 && Math.abs(ty - cy) < 0.05) {
        cx = 0; cy = 0
        el.style.transform = 'translate3d(0, 0, 0)'
        raf = 0
        return
      }
      el.style.transform = `translate3d(${cx.toFixed(2)}px, ${cy.toFixed(2)}px, 0)`
      raf = requestAnimationFrame(tick)
    }
    const enter = () => { hovering = true }
    const move = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      tx = (e.clientX - (r.left + r.width / 2)) * strength
      ty = (e.clientY - (r.top + r.height / 2)) * strength
      if (!raf) raf = requestAnimationFrame(tick)
    }
    const leave = () => {
      hovering = false
      tx = 0; ty = 0
      if (!raf) raf = requestAnimationFrame(tick)
    }
    el.addEventListener('mouseenter', enter)
    el.addEventListener('mousemove', move)
    el.addEventListener('mouseleave', leave)
    store.set(el, () => {
      el.removeEventListener('mouseenter', enter)
      el.removeEventListener('mousemove', move)
      el.removeEventListener('mouseleave', leave)
      cancelAnimationFrame(raf)
      el.style.transform = ''
    })
  },
  unmounted(el) { store.get(el)?.() },
}

export const tilt: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    if (prefersReducedMotion()) return
    const max = binding.value ?? 7
    el.dataset.tilt = ''
    el.style.transformStyle = 'preserve-3d'
    el.style.willChange = 'transform'
    const move = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      const px = (e.clientX - r.left) / r.width
      const py = (e.clientY - r.top) / r.height
      // 快速跟随：几乎无延迟
      el.style.transition = 'transform .06s linear'
      el.style.transform = `perspective(900px) rotateX(${((0.5 - py) * max).toFixed(2)}deg) rotateY(${((px - 0.5) * max).toFixed(2)}deg)`
      el.style.setProperty('--mx', `${(px * 100).toFixed(2)}%`)
      el.style.setProperty('--my', `${(py * 100).toFixed(2)}%`)
    }
    const leave = () => {
      el.style.transition = 'transform .5s cubic-bezier(.22, 1, .36, 1)'
      el.style.transform = 'perspective(900px) rotateX(0deg) rotateY(0deg)'
    }
    el.addEventListener('mousemove', move)
    el.addEventListener('mouseleave', leave)
    store.set(el, () => {
      el.removeEventListener('mousemove', move)
      el.removeEventListener('mouseleave', leave)
      el.style.transform = ''
      el.style.transition = ''
      delete el.dataset.tilt
    })
  },
  unmounted(el) { store.get(el)?.() },
}