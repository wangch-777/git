# 基于机器学习的网络入侵检测与可视化分析系统

面向离线网络流量特征（CSV）的入侵检测与结果分析系统，提供数据导入、模型训练、批量检测、结果检索、模型评估与报告导出。算法实验与 Web 系统共用同一套预处理管道与模型包。

> 本仓库为**项目骨架与实现框架**，尚非已完成的系统，也不包含未经实验验证的性能数字。

## 技术栈

| 层次 | 选型 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + ECharts |
| 后端 | Python + FastAPI + Pydantic |
| 机器学习 | pandas / NumPy / scikit-learn |
| 持久化 | SQLAlchemy + SQLite |
| 任务执行 | 独立 Python Worker |
| 模型存储 | joblib + JSON 元数据 |
| 报告 | Jinja2 生成 HTML |

## 目录结构

```text
intrusion-detection/
  backend/app/        # API、服务、数据库与 schema
  frontend/src/       # 页面、组件、请求与图表
  ml/                 # prepare、train、evaluate、predict
  worker/             # 任务领取、运行与状态恢复
  configs/            # 训练参数、特征协议与标签映射
  data/raw/           # 本地原始文件（不提交大文件）
  data/processed/
  artifacts/          # 模型包和实验输出
  tests/              # 协议、评估、接口和任务流程
  docs/               # 设计、数据字典、实验与论文
```

## 快速开始（开发）

```bash
# 后端
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn backend.app.main:app --reload

# Worker（独立进程）
python -m worker.worker

# 前端
cd frontend && npm install && npm run dev
```

## 边界说明

- 仅支持**离线 CSV 流量特征**做闭集检测，不宣称实时在线抓包、自动阻断或未知攻击检测。
- 批次回放属于"离线回放"，不得描述为实时网络监测。
- 预测分数不等于实际攻击概率或威胁严重度。
- 没有真实标签时，界面不显示准确率、误报率、漏报率。

## 相关文档

- 完整设计方案：`docs/基于机器学习的网络入侵检测与可视化分析系统-完整设计方案.md`
- 官方依据核查：`docs/intrusion-detection-design-references.md`
- 数据字典：`docs/data_dictionary.md`