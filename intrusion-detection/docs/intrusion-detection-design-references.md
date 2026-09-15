# 网络入侵检测毕业设计：官方依据核查

核查日期：2026-09-12。本文用于设计依据，不代表已经运行实验。

## 数据集

- **UNSW-NB15**：完整数据包含 2,540,044 条记录，分布在 4 个 CSV 文件；官方另提供训练集 175,341 条、测试集 82,332 条。包含 Fuzzers、Analysis、Backdoors、DoS、Exploits、Generic、Reconnaissance、Shellcode、Worms 九种攻击，加正常类别可设计十分类。官方表述为包含类别标签的 49 个特征/字段，不能直接写成“49 个可训练输入”；实际输入数量应按下载文件表头和排除标签、标识字段后的结果记录。[UNSW 官方页面](https://research.unsw.edu.au/projects/unsw-nb15-dataset)
- **CICIDS2017**：采集日期为 2017 年 7 月 3—7 日，周一为正常流量，后续日期按计划包含暴力破解、DoS、Heartbleed、Web 攻击、渗透、Botnet、端口扫描与 DDoS。官方提供 PCAP、带标签流文件及机器学习 CSV；CICFlowMeter 提取超过 80 个流量特征。具体模型输入列数应以所选文件版本为准。使用时需引用其 ICISSP 2018 数据集论文。[UNB/CIC 官方页面](https://www.unb.ca/cic/datasets/ids-2017.html)

## 实验设计规则

- **避免泄漏**：先划分训练/验证/测试数据，再学习填补、缩放、编码与特征选择参数；测试数据只能 transform，不能参与 fit、调参或选模型。使用 Pipeline 将转换和模型绑定，交叉验证内每折独立拟合。[scikit-learn：常见陷阱](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)
- **不平衡评价**：Macro-F1 对每类等权，适合突出少数类表现；应同时报告各类 Precision、Recall、F1 和样本量，避免只展示总体 Accuracy 或 Weighted-F1。二分类误报率 FPR = FP/(FP+TN)，与 1-Precision 不同。[scikit-learn：评价指标](https://scikit-learn.org/stable/modules/model_evaluation.html)
- **阈值评价**：PR 曲线适合严重类别不平衡情形，展示不同阈值下 Precision/Recall 的变化；建议报告 Average Precision，并明确与梯形积分的 PR-AUC 计算口径差异。[scikit-learn：Precision-Recall 示例](https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html)

## 基于上述事实的设计建议（属于设计推论）

1. 本科最小版本建议以 UNSW-NB15 官方固定划分完成 CSV 离线检测，训练集内部划验证集；保留官方测试集用于最后评估。不要合并后重新随机划分并仍宣称使用官方协议。
2. `label` 与 `attack_cat` 均属于监督目标信息。二分类、多分类训练均应从输入中删除所有目标列与 `id`；类别名称和映射须由实际数据核验。
3. CICIDS2017 按日期安排攻击，时间和端点可能成为环境捷径。地址、流 ID 与时间宜作为展示元数据；评估跨日/会话划分时必须说明类别覆盖变化，不能把训练未见类别的失败混同于普通闭集分类表现。
4. 不同数据集的流特征定义、单位和标签不一致，不能直接把 UNSW 模型用于 CIC CSV；如做扩展，应分别训练、分别评价，或先定义经核验的公共特征方案。
5. PCAP/实时采集属于扩展：提取器必须与训练特征语义一致。定时推送已有 CSV 记录应称“流量回放/模拟实时”，不能称为真实在线抓包检测。
6. 数据导入应执行缺失、无穷值、重复记录、类型、列名和类别分布审计；这些是应执行的检查，本文未下载数据，不能断言具体脏数据数量。

## 核心引用

1. UNSW Research. The UNSW-NB15 Dataset. https://research.unsw.edu.au/projects/unsw-nb15-dataset
2. Canadian Institute for Cybersecurity, UNB. Intrusion detection evaluation dataset (CIC-IDS2017). https://www.unb.ca/cic/datasets/ids-2017.html
3. scikit-learn. Common pitfalls and recommended practices. https://scikit-learn.org/stable/common_pitfalls.html
4. scikit-learn. Metrics and scoring: quantifying the quality of predictions. https://scikit-learn.org/stable/modules/model_evaluation.html
5. scikit-learn. Precision-Recall. https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html
