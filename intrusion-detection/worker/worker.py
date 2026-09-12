"""独立任务 Worker：领取任务、执行、状态恢复。"""
from __future__ import annotations

import time

from backend.app.config import settings
from backend.app.database import SessionLocal

# 任务状态常量
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"


def run_worker(poll_interval: float | None = None) -> None:
    """单 Worker 主循环。基础版只启用一个 Worker，简化任务抢占与 SQLite 写并发。"""
    interval = poll_interval or settings.worker_poll_interval
    _mark_interrupted_on_startup()

    while True:
        task = _claim_next_task()
        if task is None:
            time.sleep(interval)
            continue
        _execute(task)
        time.sleep(0.1)


def _mark_interrupted_on_startup() -> None:
    """重启后把遗留 running 任务标记为 interrupted，允许人工重试。"""
    # TODO: UPDATE detection_tasks/experiments SET status='interrupted' WHERE status='running'
    pass


def _claim_next_task():
    """从队列领取一个 queued 任务并置为 running。"""
    # TODO: 事务内 claim 任务，避免多 Worker 抢占
    return None


def _execute(task) -> None:
    """按任务类型分发到 ml 训练或批量推理。"""
    # TODO: 根据 task 类型调用 ml.train / ml.predict，更新状态与结果路径
    raise NotImplementedError


if __name__ == "__main__":
    run_worker()