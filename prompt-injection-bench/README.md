# Multilingual Indirect Prompt-Injection Bench

**本科安全研究项目 v0.2 / Undergraduate security research pilot**

新增：30个合成开发问题、3种攻击表达、2种正常困难条件、别名评分、误删诊断及非破坏性重评分。详见 [v0.2开发说明](docs/v02-development.md) 和 [原始12条输出的AI辅助复核](reviews/v01-ai-review.md)。原4个测试问题保留不变，未用于本次模型运行。

已验证：[v0.2真实运行结果与失败分析](examples/v02-validation.md)。17项测试、2160次mock调用、36次真实本地调用通过；真实调用发现了正常证据误删及受攻击后拒答的问题。

研究问题：当文档问答助手读取夹带指令的资料时，中文、英文及中英混合的注入内容是否影响攻击成功率？防御会产生多少正常任务损失？

This repository provides a reproducible paired evaluation pipeline, not a claim of a new defense. Both the legacy ten-question seed and the expanded dataset (30 development + 4 unchanged test questions) are **synthetic**, not collected from universities. Mock outputs must never be cited as model performance.

## Quick start / 一分钟离线演示

Python 3.10+，仅使用标准库，无需安装依赖或提供密钥。在本目录执行：

```powershell
python -m unittest discover -s tests -v
python -m bench freeze --out runs/demo-lock.json --repeats 1
python -m bench run --lock runs/demo-lock.json --out runs/demo
```

打开 `runs/demo/report.md` 查看结果。默认模式是 **mock**，两个模型名只是测试桩；正常回答也是占位符，因此准确率没有研究意义。重复运行请换一个输出目录和 lock 文件名，已有实验不会被覆盖。

## Implemented / 已实现

- 30 个合成开发问题、4个原有测试问题；按来源及问题族校验隔离。
- 固定中文问题与证据；每个开发问题含3个干净条件和9个攻击变体。
- D0 普通问答；D1 明确信任边界；D2 在 D1 基础上以正则规则移除疑似指令片段。
- 多模型、重复试验、可复现的随机执行顺序；同次重复在配对条件中使用同一 seed。
- 冻结数据、提示词、参数和代码哈希；运行时检查配置完整性。
- Ollama 本地模型适配器、显式 mock 适配器；不让模型执行工具。
- 保存完整提示词、回答、删除片段、运行时间、token 数与调用错误。
- Markdown 报告、JSON 汇总、按问题族 bootstrap 区间、人工复核 CSV。

## Real local model / 真实本地模型

先运行 `ollama list` 选择已安装的**生成模型**，不要选择 embedding 模型。适配器使用 [Ollama chat API](https://docs.ollama.com/api/chat)，关闭流式输出和思考模式，输出上限 256 token。模型必须支持这些设置。

```powershell
python -m bench freeze --provider ollama --models qwen3:8b --repeats 1 --split dev --out runs/local-dev-lock.json
python -m bench run --lock runs/local-dev-lock.json --out runs/local-dev
```

两模型三次重复：将 `--models` 后面填写两个已安装的模型名，并改为 `--repeats 3`。扩充开发集总调用数为 `30 × 12 × 3 × 2 × 3 = 6480`，旧测试集仍为288次；测试集规模不足以支撑正式结论。默认mock演示一次重复为2160次调用。可以先导出少量开发题作为独立数据文件联调。

模型权重哈希及 Ollama 版本应随实验归档：

```powershell
ollama --version
ollama list
```

当前锁文件固定模型名称而非权重内容；正式研究时必须另存 `/api/tags` 的模型 digest，固定机器环境，避免同名模型更新。服务地址可通过 `--endpoint` 修改，默认仅连接本机。默认每次调用超时为 120 秒；失败保留记录并最终返回非零状态，不自动重试或伪造回答。

## Outputs / 输出说明

| 文件 | 内容 |
|---|---|
| `lock.json` | 配置、完整数据、代码与数据哈希 |
| `environment.json` | 运行时间、Python 版本、平台、mock 标志 |
| `results.jsonl` | 每次实验的输入、输出、筛查记录及自动评分 |
| `summary.json` | 各分组指标、失败数、95% 区间和平均延迟 |
| `comparisons.json` | 以同题同次重复配对的防御及语言差异，按问题族等权重计算区间 |
| `report.md` | 可阅读的结果表 |
| `review.csv` | 待人工标注记录；重新生成报告不会覆盖已有标注 |

`python -m bench report --run runs/local-dev` 可重新生成自动报告。人工标注暂不自动合并；报告始终标记为未经人工审核。成本字段为 null，本地硬件与电力费用没有测量。

## Research workflow / 研究流程

```mermaid
flowchart TD
 A[定义威胁模型和攻击目标] --> B[整理资料与标准答案]
 B --> C[按来源与问题族划分开发集和测试集]
 C --> D[创建干净对照及三语言攻击变体]
 D --> E[开发集调试并检查评分]
 E --> F[冻结代码、数据、参数]
 F --> G[运行模型与防御矩阵]
 G --> H[自动评分及人工复核]
 H --> I[分析语言差异、防御代价和失败案例]
 I --> J[英文研究报告与可复现实验]
```

## Limitations / 第一版边界

1. 三种开发攻击表达共用“输出指定无害标记”目标，没有覆盖所有提示注入形式。
2. D2保留旧规则；新增模板用于开发诊断，不是封存的未见攻击测试。仍需另建独立测试集。
3. 自动评分支持预登记别名，但仍可能漏掉正确长句改写；拒答使用完整短语代理，需要人工复核。AI辅助复核不等于独立人类评审。
4. 所有正常问题和证据为中文。实验测的是注入语言差异，不能推导普遍的多语种问答性能。
5. 已加入教材引用及与证据同段的困难负例，并统计误删；合成负例的结果不能外推为真实误删率。
6. 测试集以明文保存；哈希防止无意变更，不构成访问隔离。查看测试结果后改进方案，需要另建未见测试集。
7. 该仓库只完成固定证据评测，不包括真实检索、正式公开语料、双盲标注或论文投稿。

详见 [研究方案](docs/protocol.md) 和 [英文报告模板](docs/report-template.md)。
