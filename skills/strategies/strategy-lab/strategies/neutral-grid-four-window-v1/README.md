# neutral-grid-four-window-v1

离线研究工具实例，契约来源为 SPEC-06-002 V1.4、Design V1.3 §5–8。
默认矩阵引用 SPEC §3.1；不复制十六套策略，不执行撮合或真实业务请求。

状态：runtime_loaded=NOT_VERIFIED，historical_evidence=UNKNOWN，
full_research_status=DEFERRED。G-01（加载/缓存）、G-02（前置训练读取）、
G-03（历史乘数及官方同窗证据）均未闭合。当前不具备提交十六研究的授权或能力。
PUMP 缺历史证据时保持 N/A，未知不是零。离线自检不等于独立 Verify/Review。

五文件职责：

- spec.md 只引用权威契约，不维护第二份研究结论。
- config.json 只含冻结资金、成本与风险数值，不承载市场身份或训练来源。
- research.py 为本地协调/静态生成入口；只读取原模板和调用 grid_research 纯函数。
  不导入 quantdinger 的凭据/服务模块，不发任何 CLI 业务调用；真实业务阶段未启用。
- strategy.py 是原生中性模板的静态审计扩展示例，由上述生成器产生；只能作为源码文本读取。
  默认 geometry 是明确 synthetic 的 L=90/U=100/N=8，不是 PUMP 的正式参数或历史训练结果。
  INSTRUMENT=None、训练未知、volume 单位 unknown、EVIDENCE_READY=False；初始化明确拒绝执行。
  不得本地 import/exec，不得直接提交、部署或修改开关冒充证据闭合。

项目根离线命令（项目 .venv；不读取凭据）：

    PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python skills/strategies/strategy-lab/strategies/neutral-grid-four-window-v1/research.py --describe

参数化历法入口支持 --contracts 与 --anchor；函数 describe_plan 支持 windows_spec。
真实入口验证锚点已经到达；默认描述只输出内存计划到 stdout，不写研究清单/结果。
--execute 必须退出 3，说明缺证与业务执行禁用，零请求，不生成完成报告。
--write-example <路径> 仅写静态源码示例；除本实例自己的 strategy.py 可确定性刷新外，
目标必须不存在。不覆盖其它文件、不写结果或回执。

生成器校验原模板路径 neutral-grid-pumpusdt/strategy.py 与 SHA256，
使用 AST 定位常数与必要接缝，保留原生角色/格生命周期。geometry 可显式参数化；
不允许改变 SPEC 格距阈值、成本或风险上限。SHA 可由最终交接核对。

风险实现使用两腿绝对值 gross、同 bar cash+持仓按 close 重估 E，累计跟踪开仓目标/
filled/remaining，开仓前预留全部余单并计入候选与预计费用。容量模型仅为冻结格区间+
可见 bar 区间的有限价格情景，不承诺任意跳空风险可控。可见越限保留事实，撤开仓、
停止增仓并排队原生下 bar 减仓。after_trading_end 记录受控 GRID_*_V1 JSON；
仅真正到达末 bar 才发 END，破产跳回调不补日志。bar-close 证据不能升级 event/tick，
event_audit=unknown，intrabar_tick_audit=not_observable。

资金/订单数量链路、沙箱加载、季度日志全量返回、历史单位、原生指标与同窗业务证据
均需未来授权后的真实验证；当前未运行真实 compile/backtest/job，也不伪造结果。
