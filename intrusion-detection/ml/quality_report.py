"""从已冻结的一次性结果生成报告与验证曲线；不会读取数据集或重新预测。"""
import argparse
import json
import os
from pathlib import Path

from .cli import ROOT


def render(output):
    os.environ.setdefault('MPLCONFIGDIR', str(output / '.matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import pandas as pd

    def read(name):
        return json.loads((output / name).read_text(encoding='utf-8'))

    results, frozen, plan, split = (read(name) for name in ('results.json', 'frozen.json', 'plan.json', 'split.json'))
    scores = results['metrics']
    candidates = frozen['candidates']
    selected = next(c for c in candidates if c['id'] == frozen['selected_id'])
    columns = ['precision', 'recall', 'f1', 'fpr', 'accuracy', 'ap']
    header = '|实验 / 评价集|训练条数|训练源去重条数|评价条数|Precision|Recall|F1|FPR|Accuracy|AP|\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|'
    rows = []

    def row(name, train_n, removed, n, m):
        rows.append('|' + '|'.join([name, str(train_n), str(removed), str(n)] + [f'{m[key] * 100:.4f}%' for key in columns]) + '|')

    for name in ('A', 'B'):
        for part in ('validation', 'test'):
            row(name + ' / ' + ('验证' if part == 'validation' else '原测试'),
                scores['A']['train_rows'] if name == 'A' else split['train_rows'],
                0 if name == 'A' else split['removed_rows'],
                (scores['A']['validation']['rows'] if name == 'A' else split['validation_rows']) if part == 'validation' else results['test_rows'],
                scores[name][part])
    row('C(A) / 非重叠测试诊断', scores['A']['train_rows'], 0, results['diagnostic_rows'], scores['C_A'])
    row('C(B) / 非重叠测试诊断', split['train_rows'], split['removed_rows'], results['diagnostic_rows'], scores['C_B'])
    sensitivity = header + '\n' + '\n'.join(rows)
    rows.clear()
    for item in candidates:
        row(item['id'] + ' / 验证(阈值0.5)', item['train_rows'], split['removed_rows'], split['validation_rows'], item['validation'])
    search = header + '\n' + '\n'.join(rows)
    rows.clear()
    under = next(c for c in candidates if c['undersample'])
    row('欠采样 / 原测试(阈值0.5)', under['train_rows'], split['removed_rows'], results['test_rows'], scores['欠采样']['test'])
    for part in ('validation', 'test'):
        row('最终选择 / ' + ('验证' if part == 'validation' else '原测试'), selected['train_rows'], split['removed_rows'],
            split['validation_rows'] if part == 'validation' else results['test_rows'], scores['selected'][part])
    final = header + '\n' + '\n'.join(rows)
    delta_val = (scores['B']['validation']['fpr'] - scores['A']['validation']['fpr']) * 100
    delta_test = (scores['B']['test']['fpr'] - scores['A']['test']['fpr']) * 100
    delta_final = (scores['selected']['test']['fpr'] - scores['A']['test']['fpr']) * 100
    curve = pd.read_csv(output / selected['id'] / 'recall-fpr.csv')
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(curve.fpr, curve.recall, label='Validation thresholds')
    point = selected['validation_tuned']
    ax.scatter([point['fpr']], [point['recall']], label=f"Selected threshold = {frozen['threshold']:.6f}", zorder=3)
    ax.axhline(.9, linestyle='--', color='gray', label='Recall target = 0.90')
    ax.set(xlabel='False positive rate', ylabel='Attack recall', xlim=(0, 1), ylim=(0, 1.02))
    ax.grid(alpha=.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / 'validation-recall-fpr.svg')
    fig.savefig(output / 'validation-recall-fpr.png', dpi=160)
    plt.close(fig)
    text = f'''# 实验质量报告：去重与仅验证集选参

任务02实测日期：2026-09-14。完整46项回归测试通过，包含无测试文件也能完成选参、预处理只拟合训练行、阈值并列分数、模型篡改拒绝和重复评估拒绝。

## 协议与结论边界

原训练文件175,341条；按原CSV顺序的42个特征行哈希去重，保留首次出现，移除{split['removed_rows']:,}条，保留101,040条。特征不含id、label、attack_cat。去重发现{split['conflicting_label_groups']}组相同特征对应不同标签；keep=first会保留其中首次标签，因而本实验也受标签冲突影响。

GroupShuffleSplit(seed=42, test_size=0.2)，去重后训练{split['train_rows']:,}条、验证{split['validation_rows']:,}条，特征组不跨训练/验证。预处理（中位数填补、标准化、类别独热编码）只在实际拟合部分训练。训练源和测试源按文件隔离；原文件仍有{results['overlap_removed']:,}条测试特征出现在训练源，因此不能宣称三者在特征层面严格无重叠。最终测试保持全部{results['test_rows']:,}条；C才移除此重叠，剩{results['diagnostic_rows']:,}条，只用于诊断。

C是A、B的同一批预测在非重叠子集上的统计，不重新训练，没有单独验证集。它不是最终成绩，也不是可保证的泛化上界；子集难度和分布变化可能使指标上升或下降。测试重复信息不参与选参。第六项指标使用AP（Average Precision），不将其称作梯形积分PR-AUC。

## A/B/C敏感性结果

A复用已有基线summary.json的验证/测试结果；为C(A)加载既有模型并统一预测一次，同时核对测试结果与摘要一致。B使用相同模型参数，在训练源去重后重训；所有阈值为0.5。C(A)、C(B)提供成对诊断。

{sensitivity}

B相对A：验证FPR变化{delta_val:+.4f}个百分点，原测试FPR变化{delta_test:+.4f}个百分点。验证集合的重复权重和条数也发生改变，所以验证差异不能全部归因于模型改善；原测试保持不变，测试对比更直接。去重可减少训练量并限制重复样本权重，但是否降低误报须依本表判断，不能预先保证；标签冲突仍需进一步审计。

本次结论：不建议把keep=first去重直接替换为默认训练方式。B虽然提高攻击召回率，却明显增加正常误报且降低F1；本次验证选参和阈值调整仍未把测试误报降到基线以下。保留A作为现有基线，记录本次负结果。后续应先研究标签冲突、类别比例及数据分布差异，使用新的独立留出数据验证，不能继续用本次测试集反馈筛选方案。

## 冻结搜索与阈值选择

搜索空间在plan.json中预先固定，基于去重训练源，4组顺序固定：

1. B：80棵树，深度18，叶节点至少2条，class_weight=balanced。
2. 浅树：80棵树，深度12，叶节点至少4条，class_weight=balanced。
3. 深树：120棵树，深度24，叶节点至少2条，class_weight=balanced。
4. 欠采样：B结构；只对拟合部分各类别按seed=42抽到少数类数量，不放回，class_weight=None。实际拟合{under['train_rows']:,}条；验证、测试分布不动。

统一random_state=42、n_jobs=2；按验证集阈值0.5的F1最大选择，AP决胜，完全同分按候选顺序。未将测试指标传入选择函数。

{search}

选中 **{selected['id']}**。在其全部验证概率阈值中要求Recall≥0.90，最小化FPR；FPR同分优先更高Recall，再取更高阈值。最终阈值 **{frozen['threshold']:.12f}**，分类规则probability≥threshold即攻击。完整阈值曲线CSV在对应模型目录；曲线如下（只含验证数据）。

![验证集召回率与误报率曲线](validation-recall-fpr.svg)

参数及阈值写入frozen.json后才读取测试文件；不在训练+验证合并数据上重新拟合，以保持选阈值时的分数口径。一次最终阶段统一评价B、欠采样和选中模型，未对未选中的其他候选输出测试成绩；相同模型只预测一次并复用分数。

{final}

最终测试FPR为{scores['selected']['test']['fpr'] * 100:.4f}%，相对基线16.0676%变化{delta_final:+.4f}个百分点；测试Recall为{scores['selected']['test']['recall'] * 100:.4f}%。验证Recall约束不保证在新分布仍满足；即使最终结果不如基线，也不回头用测试结果改选模型或阈值。

相对同一深树模型阈值0.5，验证选出的阈值将测试FPR从{scores[selected['id']]['test']['fpr'] * 100:.4f}%降到{scores['selected']['test']['fpr'] * 100:.4f}%，但依然高于原基线。欠采样与B的原测试FPR分别为{scores['欠采样']['test']['fpr'] * 100:.4f}%和{scores['B']['test']['fpr'] * 100:.4f}%，没有明显解决该问题。以上均在冻结之后一次性计算，不用于二次选型。

## 复现与审计

在项目根目录运行（已有基线可跳过baseline，保留其原始产物）：

```powershell
.\\.venv\\Scripts\\python.exe -m pip install -r requirements-lock.txt -r requirements-quality.txt
.\\.venv\\Scripts\\python.exe -m ml.cli baseline
.\\.venv\\Scripts\\python.exe -m ml.quality prepare --output artifacts/quality-reproduction
.\\.venv\\Scripts\\python.exe -m ml.quality finalize --output artifacts/quality-reproduction
.\\.venv\\Scripts\\python.exe -m ml.quality_report --output artifacts/quality-reproduction
```

baseline仅为重建固定对照模型，不参与搜索；实际本次复用了已有基线。prepare不读取测试文件，目录必须不存在。finalize绑定计划、代码、划分和模型摘要，并使用排他创建test-started.json拒绝同一目录重复测试；失败的最终评估也不会自动重试。此为流程防误用，不是阻止人为删除标记或换目录刷分的权限系统。复现必须保持搜索方案不变，不能把看到的测试成绩反馈进新方案后仍声称测试未使用。

本次运行目录：artifacts/quality-02；结果results.json；原始行索引split.json；各模型验证概率validation.csv、测试概率test-predictions.csv、模型包及元数据均保存在artifacts内，不入Git。报告可反复生成，报告生成器不读数据集、不重新训练或预测。

冻结摘要：{results['frozen_hash']}。

运行环境：{json.dumps(plan['environment'], ensure_ascii=False)}。随机性来自分组划分、森林自助采样及特征选择、欠采样，均固定seed=42。不同依赖版本、浮点计算和并行实现可能产生细微差异；耗时不要求逐位复现。原训练SHA256：{plan['source']['files']['UNSW_NB15_training-set.csv']['sha256']}；原测试SHA256：{plan['source']['files']['UNSW_NB15_testing-set.csv']['sha256']}。

本次不修改前端，不替换线上基础模型或实验模型。新模型只作为实验产物保存；报告结论不等同于上线选型决定。
'''
    (output / 'report.md').write_text(text, encoding='utf-8')
    print(output / 'report.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从已完成的质量实验生成报告和验证曲线')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/quality-02')
    render(parser.parse_args().output.resolve())
