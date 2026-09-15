# 前后端协作契约

核对日期：2026-09-14。按当前后端实现整理，供 TraeWorkCN 前端对接。

## 分工

- TraeWorkCN：前端页面、交互、样式、前端接口调用。
- Codex：后端API、数据库、机器学习、Worker、后端测试及启动问题。
- 双方保留当前未提交修改，避免同时改同一文件。需要变更接口时先更新契约；本文不表示已收到另一方确认。

## 请求方式

开发页面 `http://127.0.0.1:5173`，Vite将 `/api` 转发到本地8000端口。现有http客户端若baseURL已是 `/api`，调用路径不要再次加 `/api`。

## 实验接口（已实现，不需要另造接口）

|方法|完整路径|响应|
|---|---|---|
|GET|/api/datasets|数据集数组；训练选项过滤label_available=true|
|POST|/api/experiments/sample|201，带标签示例数据集对象，无请求体|
|POST|/api/experiments|201，实验对象；保存配置后异步排队|
|GET|/api/experiments|实验对象数组，编号倒序，不含软删除项|
|GET|/api/experiments/{id}|单个实验对象|
|PATCH|/api/experiments/{id}|请求仅含name；返回实验对象|
|DELETE|/api/experiments/{id}|返回message；运行中409，其他状态软删除并停用模型|
|POST|/api/experiments/{id}/retry|无请求体，201新实验；仅失败/中断可重试|
|GET|/api/models|可用模型数组，包含实验模型|
|POST|/api/detections|请求dataset_id、model_id，创建检测任务|

创建实验示例（dataset_id使用实际列表中的编号）：

```json
{"dataset_id":3,"name":"随机森林实验","algorithm":"random_forest","params":{"max_depth":18,"min_samples_leaf":2,"n_estimators":80,"class_weight":"balanced"},"seed":42,"validation_fraction":0.2}
```

算法枚举及params：

|algorithm|中文|允许的专用参数及默认值|
|---|---|---|
|logistic_regression|逻辑回归|C=1，范围0.001至100；max_iter=1000，整数100至5000|
|decision_tree|决策树|max_depth=18，可为null或整数1至40；min_samples_leaf=2，整数1至50|
|random_forest|随机森林|同决策树，另有n_estimators=80，整数10至300|

通用params只有class_weight，允许balanced或null，默认balanced。random_state由顶层seed生成，n_jobs由后台设置，不能作为输入params传回。seed为0至2147483647整数；validation_fraction范围0.1至0.4。name最多100字符，不可全空白。不支持的参数会返回422。

实验对象字段：

```ts
interface Experiment {
  id: number; name: string; algorithm: string; algorithm_name: string;
  params: Record<string, unknown>; dataset_id: number; dataset_name: string;
  dataset_hash: string; seed: number; validation_fraction: number;
  train_rows: number | null; validation_rows: number | null;
  train_seconds: number | null;
  metrics: {accuracy: number; recall: number; f1: number; fpr: number;
            [key: string]: number} | null;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'interrupted';
  progress: number; logs: {time: string; message: string}[];
  error: string | null; created_at: string;
  started_at: string | null; finished_at: string | null;
  model_id: number | null; comparison_key: string;
}
```

时间为UTC，当前响应可能不带Z，展示时按UTC解析再转本地。指标为0至1，前端乘100显示百分比。比较仅取成功且metrics非空、comparison_key相同的记录。F1高更好，fpr低更好。

每两秒轮询即可；页面卸载应清理轮询。progress是阶段百分比，小样本可能一次刷新就到100%，logs仍记录各阶段。中断重试为新实验从头训练，不是迭代断点续训。

数据集字段：id、name、schema_version（可空）、row_count（可空）、label_available、created_at。示例准备依赖本地原训练CSV存在且校验通过。

模型字段：id、name、experiment_id（基础模型为null）、threshold、created_at、feature_count。成功实验model_id可用作检测请求model_id；现有跳转约定 `/detections?model=编号`。不要将实验id当作模型id。

## 错误与页面状态

业务错误及请求校验错误通常为 `{"detail":"中文说明"}`，404表示记录或数据不存在，409表示状态/文件冲突，422表示参数不合法。网络断开或未处理的服务器异常不保证该JSON格式，前端须给中文兜底提示。

分别处理初次加载、成功空列表和加载失败；轮询成功不能抹掉用户操作失败提示。训练中禁止删除；失败/中断显示重试按钮，成功且model_id非空才显示选用按钮。

## 已有验证与后续协作

三种算法真实网页训练和实验产物检测已完成，详细指标与验收见 `docs/experiments.md`。后端已有 `tests/test_experiments.py`。API文档位于 `http://127.0.0.1:8000/docs`；返回对象细节以服务序列化函数和本文为准，目前实验响应未全部声明Pydantic响应模型。

TraeWorkCN 如需新增字段或改变语义，请把需求写入独立的 `docs/frontend-api-requests.md`，注明页面、字段、用途、示例；Codex随后核对实现与测试。不要在两边分别实现同名接口。
