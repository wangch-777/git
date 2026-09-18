"""只读取冻结实验结果生成任务05报告和前沿图，不重新选参或预测。"""
import argparse
import json
import os
from pathlib import Path

from .cli import ROOT

NAMES={'drop_conflicts':'丢弃冲突组','majority':'多数侧保留','keep_first':'首次保留对照',
       'balanced':'平衡权重','target_55':'目标先验55%','default':'默认权重'}
POINTS={'raw_0.5':'原分数0.5','calibrated_0.5':'校准0.5','cost_1':'成本1:1','cost_5':'成本5:1',
        'cost_10':'成本10:1','fnr_constraint':'验证漏报≤3.23%'}


def report(output):
    os.environ.setdefault('MPLCONFIGDIR',str(output/'.matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import pandas as pd
    read=lambda name:json.loads((output/name).read_text(encoding='utf-8'))
    result,frozen,plan,splits=(read(name) for name in ('results.json','frozen.json','plan.json','splits.json'))
    selected=next(c for c in frozen['candidates'] if c['id']==result['selected'])
    tested={c['id']:c for c in result['candidates']}
    keys=['fpr','fnr','recall','f1','ap','accuracy']
    def name(item):
        return NAMES[item['strategy']]+' / '+NAMES[item['prior']]
    def table(rows):
        text='|方案|工作点|阈值|FPR|漏报率|Recall|F1|AP|Accuracy|\n|---|---|---:|---:|---:|---:|---:|---:|---:|'
        for label,point,t,metrics in rows:
            text+='\n|'+'|'.join([label,point,f'{t:.9f}']+[f'{metrics[k]*100:.4f}%' for k in keys])+'|'
        return text
    validation=[]
    full=[]
    diagnostic=[]
    for item in frozen['candidates']:
        for key,label in POINTS.items():
            threshold=.5 if key=='raw_0.5' else item['thresholds'][key]
            validation.append((name(item),label,threshold,item['validation'][key]))
            full.append((name(item),label,threshold,tested[item['id']]['test'][key]))
        diagnostic.append((name(item),'仅诊断·冻结约束点',item['thresholds']['fnr_constraint'],tested[item['id']]['diagnostic']['fnr_constraint']))
    baseline=result['baseline']
    chosen=tested[result['selected']]
    final=chosen['test']['fnr_constraint']
    success=final['fpr']<baseline['fpr'] and final['fnr']<=baseline['fnr']
    conclusion=('冻结推荐工作点同时降低了误报且漏报不高于历史基线。' if success else
                '冻结推荐工作点未同时达到误报下降且漏报不高于基线；保留历史基线，不依据测试结果重新选工作点。')
    passing=[]
    for label,point,t,m in full:
        if m['fpr']<baseline['fpr'] and m['fnr']<=baseline['fnr']:
            passing.append((label,point,t,m))
    audit='|策略|移除条数|冲突组|平票组|拟合条数|原验证条数|校准条数|\n|---|---:|---:|---:|---:|---:|---:|'
    for strategy,a in splits['audit'].items():
        audit+='\n|'+'|'.join([NAMES[strategy]]+[str(a[k]) for k in ['removed','conflict_groups','tie_groups','train_rows','validation_rows','calibration_rows']])+'|'
    calibration='|方案|校准前Brier|校准后Brier|拟合秒数|\n|---|---:|---:|---:|'
    for item in frozen['candidates']:
        calibration+=f"\n|{name(item)}|{item['brier_raw']:.6f}|{item['brier_calibrated']:.6f}|{item['train_seconds']:.2f}|"
    oracle=chosen['retrospective_oracle_not_recommended']
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    for ax,filename,title in zip(axes,['validation-frontier.csv','test-frontier-diagnostic.csv'],['Validation selection','Test retrospective diagnostic']):
        data=pd.read_csv(output/selected['id']/filename)
        ax.plot(data.fpr,data.fnr,label='Full empirical frontier')
        ax.axhline(.0323,color='gray',linestyle='--',label='FNR limit 3.23%')
        metrics=selected['validation'] if filename.startswith('validation') else chosen['test']
        for point,marker in [('cost_1','o'),('cost_5','s'),('cost_10','^'),('fnr_constraint','*')]:
            m=metrics[point]
            ax.scatter(m['fpr'],m['fnr'],marker=marker,s=60,label=point)
        ax.set(title=title,xlabel='False positive rate',ylabel='False negative rate',xlim=(0,1),ylim=(0,1))
        ax.grid(alpha=.2)
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output/'frontiers.svg')
    fig.savefig(output/'frontiers.png',dpi=150)
    plt.close(fig)
    body=f'''# 任务05：冲突清理、校准与成本敏感工作点

## 结论与推荐

{conclusion}

仅按共同验证集冻结的方案为 **{name(selected)}**，阈值 **{selected['thresholds']['fnr_constraint']:.12f}**。完整原测试集FPR **{final['fpr']:.4%}**、漏报率 **{final['fnr']:.4%}**；历史基线FPR **{baseline['fpr']:.4%}**、漏报率 **{baseline['fnr']:.4%}**。推荐身份在读取本次测试文件前已经冻结，不能因下面测试表而变更。

所有预先固定候选工作点中，事后满足“双指标条件”的点有{len(passing)}个。这是报告结果的计数，不是第二轮选型。{'满足条件的记录见下表；除非恰为冻结方案，均不能据此作为新推荐。' if passing else '这9组有限候选未提供双指标同时改善的可复现证据；不能据此证明其他模型也无法改善。'}

{table(passing) if passing else ''}

## S1 冲突清理及公平划分

按42个特征行哈希分组，排除id/label/attack_cat。丢弃冲突组策略删除组中所有记录；多数策略不重写标签，仅保留多数标签侧的原始样本，平票整组丢弃；keep=first仅作为对照。前两种策略保留一致重复样本的频数，避免把冲突清理与全面去重混为一谈。

{audit}

每个清理结果独立GroupShuffleSplit(seed=42,test_size=0.2)。因为删掉的组不同，各自验证集不同，不能直接用不同集合的F1选择模型。因此取三者验证特征组的交集，以原训练源中的样本频数构建共同选型集，共 **{splits['selection_rows']}条**，标签数为{splits['selection_label_counts']}。每种策略自己的其余验证组只用于Platt拟合。三者的拟合组、校准组、共同选型组互斥；索引全部保存。

交集来自原始频数，但只是局部样本，样本量有限；共同组还排除了冲突区域，不代表全部验证流量分布。阈值约束是该集合的经验值，不是总体误差上界。

## S2 校准与成本阈值

对训练未见过的校准样本计算随机森林攻击分数，将分数裁剪到[1e-8,1-1e-8]后转logit，再拟合LogisticRegression(C=1e6,max_iter=1000,random_state=42)。共同选型样本不参与校准拟合。要求映射单调递增。

校准并不保证更好，更不能单凭校准同时改善ROC两端：严格单调映射保持排序，只改变分数刻度和工作点。Brier越小越好，下表在共同选型集计算，未用校准拟合集自评。

{calibration}

1:1、5:1、10:1表示漏报单样本代价:误报单样本代价，在共同选型集上最小化`成本比×FN+FP`。不是直接把理论1/(1+成本比)当作最终阈值。完全同成本时先选漏报更低，再选误报更低。保留未校准0.5及校准0.5对照。

独立的推荐规则：在共同选型集所有概率工作点中，约束FNR≤0.0323，最小化FPR；同分先较低FNR、较高AP、最后候选编号。若测试分布变化，验证约束不保证在测试仍满足。历史基线精确漏报率为{baseline['fnr']:.8%}，0.0323略严格于四舍五入后的历史值。

## S3 预设先验

固定三类：balanced；默认不加权；目标攻击先验55%。目标权重仅由实际拟合标签频率p计算：攻击权重0.55/p，正常权重0.45/(1-p)。不读取本次测试标签估计权重，校准不再套用测试先验。

55/45来自任务书指定且接近已知历史测试比例，只能视为部署情景敏感性分析，不能宣称完全未受测试历史影响。现有数据不能证明标签冲突、先验变化或校准任一因素是唯一根因。

森林结构统一：80棵树、最大深度18、叶节点最少2条、random_state=42、n_jobs=2。预处理仅在每组拟合样本上训练。一次搜索空间为3种清理×3种权重，共9组，不根据测试扩展搜索。

## 共同验证集：所有预定工作点

{table(validation)}

## 完整原测试集：一次性报告

基线复用历史summary，历史复现路径未改。新候选全部冻结后一次性读取完整{result['rows']}条，测试不清洗、不重采样。每个分类器推理一次，复用概率计算所有预定阈值。以下包含所有候选，不能挑选其中最好的测试数字宣称它是验证推荐。

{table([('历史基线','原分数0.5',.5,baseline)]+full)}

## S4 非重叠诊断及完整前沿

按原训练源全部特征组排除{result['overlap_removed']}条测试重叠记录，剩{result['diagnostic_rows']}条；即使某策略清除了这些训练组，也使用相同排除口径。下表仅诊断，不是最终成绩、上界或新的选型集。

{table(diagnostic)}

![完整误报与漏报前沿](frontiers.svg)

所有9组的完整验证前沿、完整测试事后前沿以CSV保存，包含每个不同概率对应的阈值、FPR、FNR、Recall。图展示冻结方案；测试图只作事后诊断，不更改冻结阈值。

冻结方案的验证约束点完整测试FPR={final['fpr']:.4%}、FNR={final['fnr']:.4%}。如果**事后查看测试全部阈值**，该方案在测试FNR≤3.23%条件下的经验最低FPR为{oracle['fpr']:.4%}（阈值{oracle['threshold']:.12f}、FNR={oracle['fnr']:.4%}）。这个值使用了测试标签，**不能作为推荐阈值或最终选型成绩**。任务书同时要求“最低测试FPR”和“不看测试选阈值”，两者必须这样区分。

## 复现、模型包与边界

```powershell
.\\.venv\\Scripts\\python.exe -m ml.miss_reduction prepare --output artifacts/miss-reproduction
.\\.venv\\Scripts\\python.exe -m ml.miss_reduction finalize --output artifacts/miss-reproduction
.\\.venv\\Scripts\\python.exe -m ml.miss_report --output artifacts/miss-reproduction
.\\.venv\\Scripts\\python.exe -m pytest -q --disable-warnings
```

安装依赖沿用requirements-lock.txt，绘图使用requirements-quality.txt。prepare仅读训练源，生成清理审计、行索引、校准映射、候选工作点和冻结文件；目录必须不存在。finalize校验源数据、代码、划分和模型摘要，排他创建test-started.json，禁止同目录再评估；报告生成只读已有结果。

模型包外层仍为preprocessor/classifier/meta，classifier为可序列化PlattClassifier，包含原森林及映射器，predict_proba返回校准概率。旧Worker及predict_dataframe自动应用冻结阈值；输出列、标签语义不变。meta增加calibration、working_points和protocol，兼容旧包。score依然是所预测类别的支持分数，不保证是真实概率。

实际目录：`{output.relative_to(ROOT).as_posix()}`。首次开发尝试目录miss-reduction-05在修复包装器兼容性时中断，只训练过部分候选，没有进入finalize；正式全部重跑后才最终测试一次。此次不覆盖基础模型、不自动注册或启用新模型，不改前端。

冻结摘要：{result['frozen_hash']}。环境：{json.dumps(plan['environment'],ensure_ascii=False)}。源文件摘要：{json.dumps(plan['source']['files'],ensure_ascii=False)}。分组划分、森林采样、逻辑回归均固定seed42；同版本通常复现指标，耗时及跨平台浮点细节不保证逐位相同。

“测试一次”是本次协议的执行限制；该测试源在历史任务中已经使用过，并非全新的独立外部测试。最终要证明泛化，需要另行收集未参与设计决策的独立数据。负结果只限制本次9组方法与有限特征，不证明模型性能的理论上限。
'''
    (output/'report.md').write_text(body,encoding='utf-8')
    print(output/'report.md')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='生成任务05报告，不重新训练或预测')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/miss-reduction-05-v1')
    report(parser.parse_args().output.resolve())
