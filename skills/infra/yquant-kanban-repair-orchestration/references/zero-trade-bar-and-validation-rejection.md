# 零成交 bar 合法化：取证、契约修订与多层拒绝点排查

适用于“交易所 K 线含零成交 bar 导致整窗回测失败”的类任务。核心立场：**零成交是合法市场状态，
不是数据错误**；校验器拒绝它就是把单根合法 bar 放大为整窗失败。

## 1. 定性：直查交易所原始 API，不信中间层报错

后端日志最内层异常往往比外层错误码有用得多。按 jobId 精确定位日志窗口，读**最内层**异常，
再映射到具体校验函数与行号。

对同一窗口直接查交易所原始 candlesticks API，统计零成交 bar：

```python
import json, urllib.request, datetime as dt
F = dt.timezone.utc
def bars(contract, itv, frm, to, host="api.gateio.ws"):
    url = (f"https://{host}/api/v4/futures/usdt/candlesticks"
           f"?contract={contract}&interval={itv}"
           f"&from={int(frm.timestamp())}&to={int(to.timestamp())}")
    with urllib.request.urlopen(url, timeout=25) as r:
        return json.load(r)
```

零成交率统计（按标的分别算，不要只看一个）：

```python
b = bars("JUP_USDT", "15m", dt.datetime(2026,8,1,tzinfo=F), dt.datetime(2026,11,1,tzinfo=F))
z = sum(1 for x in b if float(x.get("v", 0)) == 0)
print(f"{len(z)}/{len(b)} = {len(z)/len(b):.2%}")
```

## 2. 判别真实零成交 vs API 自相矛盾

三条**同时**成立 → 真实零成交；任一不成立 → 才是 API/抓取侧问题：

1. 该 bar 的 OHLC 四价**完全相等**（o=h=l=c）；
2. 该 bar 的 open **精确等于**前一根 bar 的 close；
3. `sum`（计价币成交额）与 `v`（合约张数）**同时为 0**，且与 base volume 自洽。

对照组：非零成交 bar 的 OHLC 通常**不全等**（可用来确认这套判据不是恒真）。

## 3. 周期变长 → 零成交变少，但不会归零

零成交分钟是**成片聚集**的：清淡时段（亚洲盘尾、美盘前）整段无人交易，而非每分钟随机漏几笔。
所以：

- 1m 零成交率高（可达 20%+），5m/15m 大幅下降；
- 但只要聚集段长度 ≥ 目标周期，聚合后仍是 `v=0` bar；
- 因此不能用“15m 肯定比 1m 干净”来假设窗口内无零成交。

可用 1m 聚合出 5m/15m 与原生 15m 互验；但注意**历史小周期 API 窗口有限制**：
某些交易所的 5m/1m 历史请求返回 HTTP 400，近期窗口可查而更早窗口不可按同样方式取回。
遇到这种情况时用近期原生 1m 聚合做对比，不要反复重试更早窗口。

找出聚集段（连续零成交分钟）：

```python
runs, cur = [], [z[0]]
for t in z[1:]:
    if t - cur[-1] == 900: cur.append(t)   # 900 = 15min
    else: runs.append(cur); cur = [t]
runs.append(cur)
runs.sort(key=len, reverse=True)
```

最长段 ≥ 目标周期 ⇒ 该周期必然会出现零成交 bar。

## 4. 多层拒绝点：同一个谓词在多层各有一份

“某取值被拒”的通用形态：同一个业务谓词在解析层、转换层、消费/聚合层、撮合层各有一份拒绝实现。
只修抛错那一处，消费链会在下一层再拒一次，生产症状原样复现。

排查纪律：

1. 把谓词（`volume > 0` / `<= 0` / `is None`）**全仓 grep**，列出所有拒绝点与行号；
2. 逐点判定该取值是合法市场状态还是无效输入；
3. 合法状态必须表达为“不成交/不动作”，不能表达为“整窗失败”；
4. 只对合法状态走契约修订；无效输入的拒绝点保持不动。

典型形态（两层）：

```python
# 解析层：raw_v_contracts 校验
if not isinstance(raw_v, (int, float)) or not math.isfinite(raw_v) or raw_v < 0:
    raise ...  # 负值/非有限/非数值才拒；0 放行

# 消费层：同一谓词的第二份
if not math.isfinite(candle[5]) or candle[5] < 0:   # 原为 <= 0
    raise ...
```

### 分页账本重置：证据缺失类失败的第四层

逐项证据/审计账本（每根 bar 一份 trace）叠加分页拉取时，检查状态在**每一页进入时**是累积还是重置：
`state.bars = page_evidence` 这类整本重写会让**除最后一页外的所有条目**证据丢失，消费端逐项核验报
“证据缺失”（EvidenceMissing）而非数据错误——极易误诊为又一道谓词拒绝。鉴别方法：**两页 mock 最小实验**
（页 1 解析后查页 1 条目 → 存在；页 2 解析后再查 → 消失即实锤），两页足够定案，不需真实交易所数据。
修复语义三件套：同 identity 逐页 merge（新页同 key 覆盖）+ 容量上界淘汰最旧 + identity 变化/线程更替仍整体重置；
验收矩阵单列跨页条目（三批全可查/换身份重置/容量淘汰/同 key 覆盖），移交物必须含修复后同款 mock 自证。

## 5. 契约修订的语义边界（写进 RFC/SPEC/Design）

合法化的**精确边界**必须逐条冻结：

- 放行：某取值 = 合法零成交 → base volume 精确 0.0、quote volume 0.0、六列结构不变、
  证据对象字段集合与正量 bar **完全一致**；
- 仍拒：null / 缺字段 / 非数值 / 负值 / 非有限值 / 乘数缺失 / 乘数非正；
- **不引入 epsilon**、**不设最小流动性下限**；
- **负零按数值相等语义归入零成交**，禁止符号位特判（`copysign`/`signbit` 一律不用）；
- 乘数校验先于零成交判定（乘数缺失 + v=0 → MetadataMissing，不是零成交）；
- 下溢/上溢守卫保留（raw_v>0 但乘积恰为 0 仍拒绝）；
- 重采样/聚合路径上，**聚合 bar 不得伪造逐根证据**（无 volume_evidence、无 raw_v_contracts）。

### 已知的语义残留差异（必须披露，不得写成已修复）

若撮合器（如 `runtime._liquidity_cap`）对 `volume <= 0` 返回 None（不设流动性上限），
而研究语义声明“零成交 bar 不成交”，这是**语义声明 ≠ 平台行为**的差异。
处置：写进 RFC 的披露小节（原文逐字、标注“**仍未修复**”），作为移交物强制交付项，
**不扩大授权去改撮合器**——那需要另一次契约修订。

## 6. 验收矩阵写法（Verify 逐条取证）

用**编号矩阵**而不是散文描述，每条给期望/实际/证据位置：

| 编号 | 条目 | 期望 |
|---|---|---|
| V-01 | 零值合法 | base_volume 精确 0.0、证据字段集合与正量 bar 一致、适用性 verified/unknown 按 fixture 区分 |
| V-02 | 仍拒八类 | null/""/"bad"/"-1"/"NaN"/"Inf"/"-Inf"/True 及**键完全缺失** → 同一错误标识，消息不变 |
| V-03 | 负零 | 与零行为一致；源码 grep `copysign`/`signbit` 零命中 |
| V-04 | 乘数优先 | 乘数缺失 → MetadataMissing；非正乘数 → MetadataInvalid |
| V-05 | 上下溢 | 1e308×10、1e-300×1e-300、raw_v>0 而乘积恰为 0 均仍拒 |
| V-06 | 消费链两路径 | 单 bar + 重采样均不抛错、不走 fallback、不伪造证据 |
| V-07 | 传播回归 | 五类错误仍立即 re-raise，fallback 调用 0 次；非该交易所路径行为不变 |
| V-08 | 披露交付 | 披露全文逐字存在于移交物，且明确标注“未修复” |
| V-09 | xfail 解除 | 原 xfail 装饰器整块删除、函数体逐字未改；结果无 xfailed/xpassed |

## 7. 反向回退实验：证明新用例不是恒真

Verify 必须把候选实现回退（只读副本，不污染共享树），重跑新增用例，新增用例必须失败：

- 回退解析层 → 零成交/负零相关用例失败（其余通过）；
- 回退消费层 → 零成交消费链用例失败。

失败数对得上 → 新用例确实锁定了本次变更。全部通过反而说明用例写错了。

## 8. 不做的事

- 不在研究脚本里过滤掉零成交 bar（会让报告与平台行为不一致，掩盖真实流动性事实 → 证据污染）；
- 不改错误标识与消息文本（下游可能有依赖）；
- 不动撮合器（超出契约范围，需另一次修订）；
- 不用“测试通过”替代逐条验收矩阵。
