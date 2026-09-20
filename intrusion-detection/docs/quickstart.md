# 新手运行指南

## 现在已经能做什么

1. 启动页面和后台，在首页查看基础模型和预测示例。
2. 下载并核验 UNSW-NB15 公开镜像的两个 CSV。
3. 训练固定参数随机森林，保存模型与验证/测试指标。
4. 读取兼容 CSV，输出带“正常／攻击”中文标签的 CSV。

已经支持页面上传、批量检测、模型评估和独立Worker调度。模型实验页可以训练逻辑回归、决策树、随机森林，查看日志、对比验证指标并选用训练产物检测。

## 不用命令的网页训练

1. 打开“模型实验”，点击“准备训练示例”，导入原训练文件中带真实标签的2000条数据。
2. 选择算法、填写参数，点击“启动训练”。可以离开页面，后台仍会继续。
3. 在实验记录中查看进度和“日志详情”。对三种算法分别启动一次训练。
4. 在“验证结果对比”查看同一划分下的准确率、召回率、F1与误报率。
5. 点击成功实验的“选它去检测”，选择检测CSV，再点击“开始检测”。

训练失败或重启中断时可点“重试”；重试会创建新实验，保留原记录。参数修改需要新建实验。详细规则及真实验收结果见[模型实验说明](experiments.md)。

## 不用命令的页面检测

1. 打开左侧“数据管理”。
2. 点击“使用100条示例”，或选择CSV后点击“上传并校验”。
3. 校验通过后点击“下一步：开始检测”。
4. 确认数据和随机森林模型，点击“开始检测”。
5. 页面自动显示排队、检测进度和完成结果，无需手动刷新。
6. 选择“全部／正常／攻击”筛选结果，点击“下载当前筛选结果 CSV”。筛选后的统计、表格及下载文件使用相同条件。

支持UTF-8 CSV，每个文件最多50MB和300,000行，上传时检查必需字段、重复列名、数值类型和空文件。模型推理不使用label、attack_cat或id。页面显示预测统计，不把它当作准确率或真实攻击数量。

每个检测任务绑定导入的数据与已冻结的模型版本。重新训练基础模型不会改变历史任务所用的模型。任务失败或中断时可以点击“重试此任务”，生成新的任务并保留旧记录。

任务如果一直排队，请检查`.runtime/worker.log`并确认使用`start-windows.cmd`启动了全部服务。开发模式只启动一个Worker，不要另开多个Worker进程。

## 在当前 Windows 电脑上直接使用

在文件资源管理器中打开 `D:\git\intrusion-detection`：

- 双击 `start-windows.cmd`，浏览器自动打开 http://127.0.0.1:5173。
- 保留启动窗口，使用完毕按 Ctrl+C 停止前端、后台和Worker。
- 如果提示 8000 或 5173 端口已占用，先直接打开上面的网址，可能已有本项目在运行。不要重复启动。
- 后台接口文档：http://127.0.0.1:8000/docs。
- 双击 `predict-demo.cmd`，重新预测 100 条示例数据。
- 用 Excel 打开 `data/processed/demo_predictions.csv` 查看结果。Excel 占用输出文件时，先关闭再运行预测。

CSV 的 predicted_name 列就是“正常／攻击”；score 是模型对所选类别的分数，不是现实攻击概率。source_row_id 是输入文件的数据行序号，从0开始，不包含标题行。

## 文件位置

|文件|作用|
|---|---|
|data/raw/UNSW_NB15_training-set.csv|原训练文件175,341条|
|data/raw/UNSW_NB15_testing-set.csv|原测试文件82,332条|
|data/processed/demo_input.csv|100条无标签示例输入|
|data/processed/demo_truth.csv|对应真值，仅供核对|
|data/processed/demo_predictions.csv|100条中文预测结果|
|data/processed/test_predictions.csv|完整测试文件的预测结果|
|artifacts/baseline/random_forest.pack_joblib|训练好的模型二进制|
|artifacts/baseline/random_forest.pack_meta.json|模型字段协议与版本信息|
|artifacts/baseline/summary.json|训练及评价指标|
|artifacts/baseline/data_quality.json|质量及重复记录审计|
|.runtime/backend.log、frontend.log、worker.log|启动及任务日志|
|data/processed/detections/task-N.csv|网页检测任务N的完整结果|
|artifacts/registered/|冻结后的模型版本|

数据、模型、运行环境已加入 Git 忽略规则，复制项目源代码到别的电脑后需要安装依赖并重新下载/训练，或另行复制可信模型与数据。不要加载来历不明的 joblib 文件。

## 第一次安装（Windows）

安装 Python 3.12 和 Node.js 24 LTS，并确保在终端中能运行 python 和 node。当前机器的 .venv 已经由可用的 Python 3.12 环境创建，无需重复安装。

在项目根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
cd frontend
npm.cmd ci --cache ../.npm-cache
cd ..
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ml.cli baseline
.\.venv\Scripts\python.exe scripts/dev.py
```

无需激活虚拟环境，也无需改变 PowerShell 执行策略。requirements-lock.txt 与 package-lock.json 记录当前验证过的版本。

## 预测自己的兼容 CSV

在项目根目录执行，替换 input.csv 和 output.csv 路径：

```powershell
.\.venv\Scripts\python.exe -m ml.cli predict --input "input.csv" --output "output.csv"
```

输入字段需要符合 configs/feature_schema.json 的42个特征，列顺序可不同；label、attack_cat 和 id 不进入模型。缺少必需列、重复列名、非法数值和空文件会报错。可以直接把 demo_input.csv 当作格式参考。普通表格、PCAP 或另一种特征提取器的数据不能直接交给该模型。

## 重新训练

```powershell
.\.venv\Scripts\python.exe -m ml.cli baseline
```

命令会复用已经下载且摘要正确的文件，按固定种子划分训练/验证数据，训练80棵树，并覆盖 artifacts/baseline 下当前基础模型及示例结果。模型阈值固定0.5，不根据测试结果调参。需要保留旧实验时先将整个 baseline 目录另存一份。

## Mac 开发方式

Mac 也需要 Python 3.12 和 Node.js。进入项目目录后：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
cd frontend
npm ci --cache ../.npm-cache
cd ..
.venv/bin/python -m ml.cli baseline
.venv/bin/python scripts/dev.py
```

也可运行 `bash start-macos.command`。此路线复用代码，但当前只在 Windows 实际测试，Mac 仍需本机验收。当前交付为开发版本，尚未制作 Windows 或 Mac 桌面安装包。

## 数据来源

官方介绍：https://research.unsw.edu.au/projects/unsw-nb15-dataset

当前下载使用 configs/dataset_source.json 中固定提交的公开 GitHub 镜像。每个文件验证SHA256及行列数量，但尚未与官方原文件逐字节比对。论文引用要求和学术使用条件以官方页面为准。本次基础实验的限制详见 baseline-results.md。
