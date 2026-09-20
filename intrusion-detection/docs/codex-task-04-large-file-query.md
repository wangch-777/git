# 任务04：优化大文件查询（统计摘要 + 分页读取）

## 目标

当前结果文件的三个查询接口都会调用 `result_frame()`，用 `pd.read_csv(path)` 完整读入整个 CSV：
- 分页 `GET /detections/{task_id}/results`
- 统计 `GET /detections/{task_id}/statistics`
- 导出 `GET /{task_id}/report`

小文件没问题，大文件（最多 30 万行）会在每次请求时重复读全文件，浪费时间和内存。本任务要：
1. 检测完成时保存统计摘要，统计接口不再读全文件。
2. 分页接口只读需要的行，不再整表读入内存。
3. 导出接口用流式方式生成 CSV，避免把整个 DataFrame 拼成一个大字符串。

## 现状（已核实）

- 结果文件由 `worker/worker.py` 的 `_execute()` 分块写出（`chunksize=10000`），已经累计了 `processed` 行数，但**没有**累计攻击/正常条数。
- `backend/app/db_models.py` 的 `DetectionTask` 目前字段：`id, dataset_id, model_id, status, processed_rows, total_rows, result_path, error, started_at, finished_at, created_at`，没有统计字段。
- `backend/app/database.py` 的 `initialize_database()` 已有一套"给旧 SQLite 表补列 + 迁移前备份"的模式（目前只针对 `experiments` 表）。需要给 `detection_tasks` 表加同样的补列逻辑。
- 统计接口 `get_statistics` 现在读全文件后计算：`total`、`attack`（predicted_label==1）、`normal`、`attack_ratio`。`label` 过滤参数是筛选 `predicted_label==label` 后再统计。
- `predicted_label` 只有 0/1 两种取值，所以"分 label 统计"等价于：只要存全局的 `attack` 与 `normal` 两个计数即可还原所有 label 组合。

## 要求

### 1. 保存统计摘要（完成时写入 DB）

- 给 `DetectionTask` 新增两个整型字段，例如 `normal_count` 和 `attack_count`（默认 0 / 可空）。
- 在 `worker/worker.py` 的 `_execute()` 里，逐块处理时累计 `attack_count` 与 `normal_count`（依据 `result.predicted_label`），任务成功落盘时把这些值连同 `result_path`、`status="succeeded"` 一起写回该任务行。
- 累计逻辑要复用与现有 `processed_rows` 相同的 Update 写入方式（不要在循环里频繁改，选在完成时一次性写，或沿用现有每块更新 `processed_rows` 的习惯，但保证最终值一致）。
- 新旧任务兼容：旧任务没有这两个计数时，统计接口应能回退（见下）。

### 2. 统计接口不再读全文件

`GET /detections/{task_id}/statistics`（`backend/app/api/detections.py`）：

- 若任务行已有 `normal_count`/`attack_count`（非 NULL），直接用它们还原结果，**不读文件**：
  - `label=None`：`total = attack + normal`，`attack`、`normal` 原样，`attack_ratio = attack / total`。
  - `label=1`：`total = attack`，`attack`，`normal = 0`。
  - `label=0`：`total = normal`，`attack = 0`，`normal`。
- 若任务行**没有**计数（旧任务），回退到一次性读文件计算（分块求和，避免整表读入内存），保持行为一致。

### 3. 分页接口只读需要的行

`GET /detections/{task_id}/results`（`backend/app/api/detections.py`）：

- `label=None`（最常见）：直接用 `pd.read_csv(path, skiprows=..., nrows=...)` 只读当前页（注意保留表头），总共约 `total_rows` 行，实现 O(page) 的时间和内存。
- `label` 有值：用 `chunksize` 分块流式扫描，边扫边统计"匹配总数"并只收集当前页命中的行（内存只保留 page_size 行），不要 `df.loc[df.predicted_label==label]` 全表过滤。
- 返回结构不变：`{"total": int, "items": [ ...page 内每行 dict... ]}`。`total` 表示该 label 下的总命中数。
- `result_frame()` 函数仍然被 `reports.py` 的导出接口引用，请评估是否保留；如果分页/统计都不再需要它，导出可自行流式读取，避免留下"全表读入"的函数被误用。

### 4. 导出接口流式生成

`GET /{task_id}/report`（`backend/app/api/reports.py`）：

- 用 `StreamingResponse`（或等价方式）边读边写。逐块 `pd.read_csv(..., chunksize=...)`，按 `label` 过滤后 `to_csv` 追加到流，避免把一个超大 DataFrame 序列化成整段字符串再返回。
- 注意保持现有响应头：`Content-Disposition` 附件文件名 `detection-{task_id}-{suffix}.csv`、`media_type="text/csv"`、UTF-8 BOM（现有用 `utf-8-sig`）。逐块追加时注意：首块写表头、后续块不写表头、BOM 只写一次。
- `label=None` 时可以直接流式拷贝文件内容，不用逐行重解析（可选优化）。

### 5. 数据库迁移

- 在 `backend/app/database.py` 的 `initialize_database()` 中，仿照 `experiments` 表的写法，给 `detection_tasks` 表补 `normal_count`、`attack_count` 两列（迁移前同样备份 sqlite 文件）。注意现有函数里已经有一个针对 `experiments` 的 `additions` 字典逻辑，请实现成通用/能同时处理两张表，而不是复制一大段重复代码。

## 约束

- 不改动对外 API 的路径、参数名、返回 JSON 结构（前端已按现有契约对接）。
- 保持现有结果文件格式不变（列名、顺序、编码）。
- 不改变 Worker 的任务状态机（queued→running→succeeded/failed/interrupted）。
- 数据集上限仍是 300,000 行；优化应在该量级下明显降低内存和时间，但不要为"更大规模"过度设计。

## 验收标准

1. 跑通现有测试（当前 46 项）；如有必要，为新行为补充测试：统计接口在"有摘要"与"旧任务无摘要"两种路径下结果一致；分页接口页边界、`total`、label 过滤正确；导出流式生成的 CSV 与 `pd.read_csv` 回读结果等价。
2. 统计接口在读取台账（不读 CSV）时可返回与读全文件完全相同的 `total/attack/normal/attack_ratio`。
3. 分页接口读一个大文件时，内存约等于 page_size 行的开销，而非整表。
4. 完成一份简短的交付说明（建议写入 `docs/large-file-query.md`），说明：
   - 新增字段与迁移方式；
   - 各接口改动前后的读取方式差异；
   - 用真实/合成大文件测的内存与耗时对比（例如 5 万、30 万行两档），以及如何复现该对比。