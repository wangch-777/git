export const statusName = (status: string) => ({
  queued: '排队中', running: '检测中', succeeded: '已完成', failed: '失败', interrupted: '已中断'
}[status] ?? status)
