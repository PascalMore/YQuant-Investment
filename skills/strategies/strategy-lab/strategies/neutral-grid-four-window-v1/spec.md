# neutral-grid-four-window-v1：契约引用

权威需求：docs/spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md V1.4。
权威设计：docs/design/06_strategy/DESIGN-06-002-neutral-grid-multi-window-research.md V1.3。
本文件仅索引，不复制第二份正文、不调整原五点或验收标准。

- 矩阵、UTC 半开窗口、wire 日期、精确 coverage：SPEC §3.1；Design §5。
- 同产品前置最多365根已收盘训练、短历史、L/U/g/N 和成本评分：SPEC §3.2。
- 唯一1000/true/10传递与数量复用：SPEC §3.3；Design §4。
- 保证金收益、峰值 MDD、完整15m Sharpe、有效均值：SPEC §3.4；Design §7。
- gross/E≤2.5、开仓余单预留、被动越限动作与风险粒度：SPEC §3.5；Design §6。
- 同池多空强平情景与未知状态：SPEC §3.6；Design §7。
- PUMP 历史单位/官方同 bar 原始证据：SPEC §3.7；Design §3、§10 G-03。
- 预算、停止、受限 Agent 通道：SPEC §3.8；Design §5。
- 输出载体与来源、未知不是零：SPEC §3.9、§4；Design §7。
- 离线八类测试集合与原79回归保护：Design §8。

本实例仅离线源码/计算/载体工具，不执行十六业务，不补全未知证据。
G-01/G-02/G-03 未闭合，PUMP 可合法输出 N/A；三件套离线自检不解除门禁。
strategy.py 为锁定的 synthetic 静态示例，非正式研究产物、非可提交策略。
