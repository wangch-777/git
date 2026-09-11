# Digest功能验证记录

- 22项测试通过，覆盖完整digest读取、远程/短digest拒绝、旧锁拒绝、运行前不匹配阻断、运行后变化标记及原有评测流程。
- 新代码完成2160次mock调用，报告明确标记`mock_not_applicable`，不是权重验证或真实模型结果。
- 尝试冻结真实`qwen3:8b`时，本地`/api/tags`返回`{"models": []}`，因此freeze失败且没有产生真实实验lock，也未发起模型推理。这验证了模型缺失时的阻断路径。
- 当前版本尚未完成真实模型的digest匹配后推理。需要恢复本地模型，再重新freeze与run。此前36次真实调用属于旧版历史证据，不能当作本次新功能的真实验证。

模拟报告见`examples/digest-mock-report.md`。模型身份机制与复现命令见[model-identity.md](model-identity.md)。
