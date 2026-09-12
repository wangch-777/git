# 模型 digest 冻结与校验

对于本地 Ollama，freeze 自动查询 `/api/tags`，将每个精确模型标签对应的完整64位 SHA256 写入 lock 的 `model_digests`，并纳入配置哈希。不接受缺失、重复、短digest或已知远程/cloud模型条目；云模型的本地条目不能证明远程权重被固定。

这里固定的是 Ollama 模型清单的 digest（用于识别模型版本及其引用的内容），不是自行逐字节重算权重文件。前提是信任本地 Ollama 服务及其返回的数据。

```powershell
python -m bench freeze --provider ollama --models qwen3:8b --dataset data/dev-v02.json --repeats 1 --out runs/pinned-lock.json
python -m bench run --lock runs/pinned-lock.json --out runs/pinned-run
```

也可以追加 `--digest qwen3:8b=完整64位digest` 对已知版本做显式断言；多模型可重复该参数。省略参数仍自动冻结实际digest，不是跳过校验。

run 在创建输出目录、调用模型之前核对；不一致立即停止。结束后再次核对，失败则保留原始日志、将 `model-verification.json` 标为 `failed_postcheck` 并以非零状态退出。JSON汇总及Markdown报告都携带模型校验状态。运行被中断时状态保持running，不能当作完成验证。

这两次检查不能检测运行期间切换后又恢复的模型，也不阻止外部进程替换模型。实验期间不要更新模型；这不是操作系统级锁定或绝对确定性保证。

旧真实模型lock缺少digest时明确拒绝运行，需要重新freeze并使用新输出目录；不自动补写旧锁或覆盖旧结果。历史报告重新汇总时标为 `legacy_unverified`。Mock不声称拥有权重，标为 `mock_not_applicable`。

本次验证先运行小规模真实开发样本，不运行4题历史测试集。完整30题单模型一次重复仍为1080次调用。
