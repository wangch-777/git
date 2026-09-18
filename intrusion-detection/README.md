# 基于机器学习的网络入侵检测与可视化分析系统

针对离线网络流量特征（CSV）的入侵检测与结果分析系统，覆盖数据导入、模型训练、批量检测、结果检索、模型评估与报告导出。算法实验与 Web 界面共用同一套预处理管道和模型包。

## 主要特性

- 网页上训练逻辑回归、决策树、随机森林，比较验证集指标并选用产物进行检测
- 独立 Worker 异步执行训练与检测，页面轮询进度，失败或中断可重试
- 检测结果分页、筛选与 CSV 导出；带标签数据可查看误报/漏报样本与阈值实验
- 基础模型评估：混淆矩阵、Precision–Recall 曲线、各类别指标

## 技术栈

| 层次 | 选型 |
|---|---|
| 前端 | Vue 3 · TypeScript · Vite · Element Plus · ECharts |
| 后端 | Python · FastAPI · Pydantic |
| 机器学习 | pandas · NumPy · scikit-learn |
| 存储 | SQLAlchemy · SQLite · joblib + JSON 元数据 |
| 任务 | 独立 Python Worker |
| 报告 | Jinja2 生成 HTML |

## 快速开始

Windows PowerShell，项目根目录：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m ml.cli baseline    # 训练基础模型并生成示例预测
cd frontend
npm.cmd ci --cache ../.npm-cache
cd ..
.\.venv\Scripts\python.exe scripts/dev.py       # 启动前端、API 与 Worker
```

Windows 可改为双击 `start-windows.cmd`。完整安装、页面训练/检测与 Mac 说明见 [docs/quickstart.md](docs/quickstart.md)。

## 基线指标

UNSW-NB15 原测试集 82,332 条，固定阈值 0.5：

| 指标 | 值 |
|---|---|
| 准确率 | 91.00% |
| 攻击 Precision | 88.06% |
| 攻击 Recall | 96.77% |
| 攻击 F1 | 92.21% |
| 正常流量误报率 | 16.07% |
| Average Precision | 98.84% |

指标口径、训练/验证划分与限制见 [docs/baseline-results.md](docs/baseline-results.md)。

## 目录结构

```text
intrusion-detection/
  backend/app/        # API、服务、数据库与 schema
  frontend/src/       # 页面、组件、请求与图表
  ml/                 # prepare、train、evaluate、predict、error_analysis
  worker/             # 任务领取、运行与状态恢复
  configs/            # 训练参数、特征协议与标签映射
  tests/              # 协议、评估、接口与任务流程测试
  docs/               # 设计、数据字典、实验与验收记录
  data/               # 本地原始与处理后文件（不提交）
  artifacts/          # 模型包与实验输出（不提交）
```

## 边界说明

- 仅支持离线 CSV 流量特征做闭集检测，不提供实时抓包、自动阻断或未知攻击检测。
- 批次回放属于离线回放，不作实时网络监测。
- 预测分数不等于真实攻击概率或威胁严重度。
- 数据无真实标签时，界面不显示准确率、误报率、漏报率。

## 数据来源与参考

- 数据集 UNSW-NB15：https://research.unsw.edu.au/projects/unsw-nb15-dataset
- 模型与评估：scikit-learn、pandas、NumPy；界面：Element Plus、ECharts
- 数据字典：[docs/data_dictionary.md](docs/data_dictionary.md)
- 完整设计方案：[docs/基于机器学习的网络入侵检测与可视化分析系统-完整设计方案.md](docs/基于机器学习的网络入侵检测与可视化分析系统-完整设计方案.md)