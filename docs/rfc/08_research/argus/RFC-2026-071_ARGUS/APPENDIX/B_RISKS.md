---
file_id: ARGUS-APP-B
title: "风险登记簿 (Standalone Edition)"
title_en: "Risk Register (Standalone Edition)"
rfc_id: RFC-2026-071
doc_status: DRAFT
approval_status: NOT_SUBMITTED
impl_status: NOT_STARTED
version: "2.0.0-draft"
created: "2026-04-12"
last_updated: "2026-04-12"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on:
  - "ARGUS-07 (影响分析与替代方案 v2.0)"
  - "ARGUS-08 (MVP实施计划与验收标准 v2.0)"
  - "ARGUS-APP-A (参数注册表 v2.0)"
  - "EXPERT_PANEL_WG3_WG4_WG5.md (芒格终审 + WG3工程评估)"
  - "ADVANCED_FEATURES_DISCUSSION.md (达尔文时刻 + 共识方向)"
supersedes: "ARGUS-APP-B v0.1.0 (archived as B_RISK_REGISTER.md, 10 risks for Empire submodule)"
amendment_level: L2
---

# 附录B: 风险登记簿 (Standalone Edition) {#ARGUS-APP-B:root}

# Appendix B: Risk Register (Standalone Edition)

> **V2.0 核心变更**: 风险格局因独立化而根本性改变。V1.0的10项风险中: RISK-001 (DuckDB锁竞争) **消除** (MVP不用DuckDB); RISK-003 (隐形重仓滞后)、RISK-004 (NHC干预)、RISK-008 (AH共线性)、RISK-009 (Kalman/Lasso模型风险) **降级/Deferred** (对应功能不在MVP); Empire集成风险 **大幅降低** (JSON文件不是共享DB)。同时新增3项独立系统特有风险。
>
> **V2.0 Key Change**: Risk profile fundamentally reshaped. RISK-001 DuckDB locking ELIMINATED. Multiple V1 risks deferred with their features. 3 new standalone-specific risks added.

**影响等级定义 / Impact Level Definitions**:

- **HIGH**: 可能导致核心功能失效或产生错误信号, 需在对应Phase内解决 / May cause core function failure or erroneous signals
- **MEDIUM**: 可能降低精度或限制功能, 可在后续Phase处理 / May reduce accuracy or limit features
- **LOW**: 影响有限, 常规运维可处理 / Limited impact, handled by routine operations

---

## S1 风险登记矩阵 (Risk Matrix) {#ARGUS-APP-B:matrix}

| 风险ID | 描述 / Description | 影响 | 可能性 | V1.0状态 |
|:--:|:--|:--:|:--:|:--|
| RISK-S01 | 单用户数据导入可靠性 (data import reliability) | HIGH | 中 | **NEW** |
| RISK-S02 | 贝叶斯信誉在牛市中虚高 (credibility inflation) | HIGH | 高 | 继承V1.0 RISK-002, 方案不变 |
| RISK-S03 | 达尔文时刻误报率 (Darwin false positives) | MEDIUM | 中 | **NEW** |
| RISK-S04 | 共识方向引擎在快速市场中滞后 (consensus lag) | MEDIUM | 高 | **NEW** |
| RISK-S05 | 多产品共识同质化陷阱 (homogeneous consensus) | MEDIUM | 中 | 继承V1.0 RISK-006, 简化方案 |
| RISK-S06 | Excel数据格式变更导致导入失败 (format drift) | MEDIUM | 中 | V1.0无 (V1.0走API) |
| RISK-S07 | 芒格警告: T+1延迟导致alpha衰减 (signal decay) | MEDIUM | 高 | 继承芒格终审第一刀 |
| RISK-S08 | 样本量不足导致统计不显著 (small sample) | MEDIUM | 高 | V1.0 RISK-009相关, 但scope不同 |
| RISK-S09 | 用户注意力过载 (attention overload) | LOW | 中 | 继承芒格终审第五刀 |
| RISK-S10 | 实施周期延期 (schedule overrun) | LOW | 低 | 继承V1.0 RISK-010, 风险降低 |

---

## S2 风险详细登记 (Detailed Risk Register) {#ARGUS-APP-B:detail}

### RISK-S01: 单用户数据导入可靠性 (Data Import Reliability) -- NEW {#ARGUS-APP-B:s01}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S01 |
| **描述** | ARGUS作为独立系统, 数据导入完全依赖单一用户手动操作。V1.0中数据通过Wind API管道自动摄取, 有多源交叉验证; V2.0中用户每天从数据供应商获取Excel文件, 手动上传或CLI导入。如果用户忘记导入、导入错误文件、或Excel格式不一致, 系统的信号链将基于不完整或错误数据运行, 可能产出误导性信号 |
| **描述(EN)** | As standalone, data import relies entirely on single user's manual action. Missing imports, wrong files, or format inconsistencies can produce misleading signals from incomplete/incorrect data |
| **触发条件** | 用户连续2+天未导入数据; 用户导入错误日期文件; 数据供应商更改Excel列顺序或编码 |
| **影响等级** | **HIGH** |
| **影响范围** | 信号基于陈旧数据计算 -> 过期信号未被新数据覆盖 -> 池状态frozen -> 用户看到的dashboard是"昨天的新闻" |
| **缓解措施** | (1) 导入缺失检测: 系统在dashboard上显著提示"距上次导入已N天, 数据可能过时"; (2) Idempotent import: 重复导入同一天数据不产生错误; (3) 格式校验: 导入时检查列名、数据类型、日期格式, 不匹配时拒绝并给出明确错误信息; (4) 导入确认: Web upload界面显示文件名+行数+日期范围, 用户确认后才入库; (5) CLI+Web双路径: 降低单一入口的故障风险 |
| **关联AC** | AC-01, AC-02, AC-03, AC-04 |
| **责任方** | 用户 (导入操作) + 系统 (校验+提示) |
| **验证时点** | Phase 1 Gate; Phase 6纸上交易 (10日零失败) |

---

### RISK-S02: 贝叶斯信誉在牛市中虚高 (Credibility Inflation in Bull Markets) {#ARGUS-APP-B:s02}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S02 |
| **描述** | 继承V1.0 RISK-002。顺风环境中大量产品信号"恰好正确"但并非真正有预测力, 导致信誉系统性膨胀。市场连续上行时, 看多信号天然高正确率, 信誉系统无法区分"alpha正确"和"beta幸存偏差" |
| **描述(EN)** | Inherited from V1.0 RISK-002. Bull markets inflate credibility scores as bullish signals are "correct" due to market beta, not alpha. System cannot distinguish skill from luck in one-directional markets |
| **触发条件** | 连续2个季度以上单边上行; 多数产品credibility > 0.7; CONVICTION区容纳数异常增加 |
| **影响等级** | **HIGH** |
| **影响范围** | CONVICTION区被低质量股票填充; 市场转折时系统反应迟缓; 产出方向错误信号 |
| **缓解措施** | (1) 自适应衰减: 高波动期decay加速至~0.90 (ARG-009/010); (2) 后验饱和: posterior > 0.92时新信号LR递减 (ARG-012); (3) 每季执行"纯alpha信号正确率检验": 剔除市场beta后的正确率, 低于随机基准触发全局衰减; (4) Fama null hypothesis: Phase 5回测必须包含"alpha为零"假设下的表现 |
| **关联参数** | ARG-009, ARG-010, ARG-012 |
| **关联AC** | AC-07 |
| **责任方** | 信誉引擎模块 |
| **验证时点** | Phase 2 Gate (引擎逻辑); Phase 5 (回测验证) |

---

### RISK-S03: 达尔文时刻误报率 (Darwin Moment False Positive Rate) -- NEW {#ARGUS-APP-B:s03}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S03 |
| **描述** | 达尔文时刻检测器依赖行业跌幅+信誉分歧两个条件。但条件过宽可能导致频繁误报 (板块短暂回调但非真正的自然选择时刻), 条件过窄可能导致漏报。Fama指出: A股每年板块跌>10%的事件有限, 样本量可能不够做统计推断。Kahneman警告幸存者偏差: 只看到反弹的案例 |
| **描述(EN)** | Darwin detector may trigger on routine sector dips (false positives) or miss real moments (false negatives). Limited sample size (2-3 events/year with >10% sector drops) makes statistical validation challenging. Survivorship bias risk |
| **触发条件** | 行业短暂回调(-10%)后快速反弹, 非真正达尔文事件; 系统性下跌被误判为行业特有下跌 |
| **影响等级** | **MEDIUM** |
| **影响范围** | 误报导致用户对达尔文信号失去信任; Checklist中darwin_flag失去信息价值 |
| **缓解措施** | (1) 系统性风险过滤: 沪深300同期跌>8%时降权 (ARG-049, 芒格建议); (2) 强度条件: 至少2个高信誉产品显示hold/add, 不只是"没卖"; (3) 回测所有历史达尔文事件(含失败案例), 展示胜率+亏损分布 (Kahneman要求); (4) Phase 4 Gate: 误报率>50%时禁用检测器 |
| **关联参数** | ARG-046, ARG-047, ARG-048, ARG-049 |
| **关联AC** | AC-14, AC-15 |
| **责任方** | darwin_detector模块 |
| **验证时点** | Phase 4 Gate |

---

### RISK-S04: 共识方向引擎在快速市场中滞后 (Consensus Direction Lag) -- NEW {#ARGUS-APP-B:s04}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S04 |
| **描述** | 景气度方向仪使用30日滚动delta, 信念偏移使用6个月基准。在快速市场转折中(如2020年3月疫情冲击, 2024年1月流动性危机), 这些窗口可能反应过慢。当方向仪终于显示DEFENSIVE时, 市场可能已经跌了2周; 当它切回BULLISH时, 最佳入场点可能已过 |
| **描述(EN)** | Prosperity direction indicator uses 30-day rolling delta; conviction shift uses 6-month baseline. Both lag significantly during rapid market reversals. By the time the indicator flips, the move may be largely complete |
| **触发条件** | 市场在2-3周内发生剧烈方向转换 (如V型反转); 产品行为在1周内从进攻转为防御 |
| **影响等级** | **MEDIUM** |
| **影响范围** | 景气度方向信号滞后导致Checklist给出过时判断; 用户可能基于过时的方向信号做决策 |
| **缓解措施** | (1) 短期窗口叠加: 在30日delta基础上, 同时展示10日delta作为"快速方向"指标; (2) Web界面明确标注"本指标有30日滞后, 不适用于短期择时"; (3) 信念偏移的加速度指标(正向加速/减速)可提前捕捉转折; (4) 用户教育: Dashboard上注明"共识方向是中期趋势指标, 不是短期交易信号" |
| **关联参数** | ARG-050, ARG-051, ARG-052, ARG-053 |
| **关联AC** | AC-16 |
| **责任方** | consensus_engine模块 |
| **验证时点** | Phase 4 Gate |

---

### RISK-S05: 多产品共识同质化陷阱 (Homogeneous Consensus Trap) {#ARGUS-APP-B:s05}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S05 |
| **描述** | 继承V1.0 RISK-006。多位同风格产品经理同时买入同一股票被识别为"高确信共识", 但实质可能是风格因子暴露(如3位GROWTH经理同时增持高成长股)而非独立alpha判断。V2.0中top-5产品的universe更小, 同质化风险更高 |
| **描述(EN)** | Inherited from V1.0 RISK-006. Multiple same-style products buying the same stock may reflect shared factor exposure, not independent alpha. V2.0's smaller universe (top-5) amplifies this risk |
| **触发条件** | CONVICTION区入池的>=3位经理均为同一style_label; 同行业同风格产品持仓相关性>0.7 |
| **影响等级** | **MEDIUM** |
| **影响范围** | CONVICTION区被虚假共识填充; 后验概率因独立性假设违反而高估 |
| **缓解措施** | (1) CONVICTION入池要求>=2种不同style_label (ARG-038, REV-015); (2) Dashboard展示共识时标注参与产品的风格分布; (3) 当同质化占比>80%时, 系统标注"WARNING: 同质化共识, 非独立验证" |
| **关联参数** | ARG-038, ARG-040 |
| **关联AC** | AC-10 |
| **责任方** | 池引擎模块 |
| **验证时点** | Phase 3 Gate |

---

### RISK-S06: Excel数据格式变更导致导入失败 (Data Format Drift) {#ARGUS-APP-B:s06}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S06 |
| **描述** | 数据供应商可能不定期调整Excel文件的列顺序、列名、日期格式、编码(GBK/UTF-8)。V1.0通过Wind API有结构化schema保障, V2.0直接解析Excel文件, 对格式变更更脆弱 |
| **描述(EN)** | Data vendor may change Excel column order, names, date format, or encoding. V2.0 parses Excel directly (no API schema protection), making it more fragile to format drift |
| **触发条件** | 数据供应商季度更新文件模板; 新增/删除列; 日期格式从YYYY-MM-DD变为YYYYMMDD |
| **影响等级** | **MEDIUM** |
| **影响范围** | 导入失败 -> 数据断流 -> 触发RISK-S01级联 |
| **缓解措施** | (1) 导入脚本使用列名匹配(而非列序号), 对列名做模糊匹配+别名表; (2) 格式校验在导入前完成: 不匹配时拒绝并报错, 不写入脏数据; (3) 维护一个format_spec.yaml配置文件, 记录期望的列名/类型/格式, 供应商格式变更时只改配置不改代码; (4) 导入失败时日志记录详细错误(哪一列、哪一行、什么问题) |
| **关联AC** | AC-01, AC-04 |
| **责任方** | importer模块 + 用户 (维护format_spec.yaml) |
| **验证时点** | Phase 1 Gate; 运行期间持续监控 |

---

### RISK-S07: T+1延迟导致Alpha衰减 (Signal Decay from T+1 Lag) {#ARGUS-APP-B:s07}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S07 |
| **描述** | 芒格终审第一刀。经理在T日买入后, 用户在T+1日才获知。如果T日买入后股价已涨3%, 跟进空间减少3%。这是ARGUS作为"事后系统"的根本性限制。不是bug, 是feature boundary |
| **描述(EN)** | Munger's first cut. Manager buys on Day T, user learns on Day T+1. If price already moved +3%, the alpha opportunity is reduced by 3%. This is a fundamental limitation of T+1 data, not a fixable bug |
| **触发条件** | 高流动性股票在经理买入当日即大涨; 市场对机构交易的反应速度加快 |
| **影响等级** | **MEDIUM** |
| **影响范围** | FAST层信号的可操作窗口收窄; 用户跟进时已"迟到" |
| **缓解措施** | (1) 系统定位: "ARGUS是望远镜, 不是自动驾驶" -- ENG-01在座谈会上的表述; (2) MEDIUM/SLOW层信号天然不受T+1影响(它们关注的是周级/月级趋势); (3) 四区池模型本身是多日积累, 不依赖单日信号; (4) Dashboard不显示"立即行动"按钮 -- Kahneman: "Friction is a feature"; (5) JSON输出到Empire需经roundtable讨论, 增加了决策延迟但也增加了判断质量 |
| **关联参数** | ARG-033 (FAST expiry = 10日) |
| **责任方** | 系统设计层面, 无法通过代码消除 |
| **验证时点** | Phase 5回测: 计算T+1已知后的residual alpha |

---

### RISK-S08: 样本量不足导致统计不显著 (Small Sample Size) {#ARGUS-APP-B:s08}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S08 |
| **描述** | ARGUS跟踪top-5产品。5个产品的universe极小: (1) 贝叶斯信誉需要足够的正确/错误信号才能收敛, 5个产品可能需要6+个月数据; (2) 共识检测需要>=3个产品同向, 5个中3个同向在随机情况下概率约31% (C(5,3)*0.5^5 = 10/32); (3) 达尔文时刻需要高/低信誉分歧, 5个产品中这种分歧可能极少发生 |
| **描述(EN)** | Top-5 product universe is extremely small. Bayesian convergence needs 6+ months; consensus of 3/5 has 31% random probability; Darwin moment divergence is rare with only 5 products |
| **触发条件** | 运行<3个月时, 信誉分尚未从prior(0.5)有意义地偏离; 达尔文事件全年可能<3次 |
| **影响等级** | **MEDIUM** |
| **影响范围** | 信号在早期可能不比随机好; 用户对系统失去信心 |
| **缓解措施** | (1) 明确设定"冷启动期": 前3个月系统输出标注"冷启动阶段, 信号仅供参考"; (2) Phase 5回测使用历史数据 (非实时) 验证信号质量; (3) Fama null hypothesis纳入Phase 5: 如果alpha为零, ARGUS的表现与随机的差异是否显著; (4) 考虑在Phase 5+扩展跟踪产品数至10-15个 |
| **关联参数** | ARG-007, ARG-008 (先验: Beta(2,2)) |
| **关联AC** | AC-07, AC-17 |
| **责任方** | 系统设计层面 + 用户 (管理预期) |
| **验证时点** | Phase 5 (回测统计显著性) |

---

### RISK-S09: 用户注意力过载 (Attention Overload) {#ARGUS-APP-B:s09}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S09 |
| **描述** | 芒格终审第五刀。ARGUS每天生成信号, 用户每天看dashboard, 每天roundtable讨论。如果ARGUS导致用户从"深度研究3只股票"变成"浅度关注30只", 净效果可能为负。信息过载降低决策质量 |
| **描述(EN)** | Munger's fifth cut. Daily signal generation may shift user from "deep research on 3 stocks" to "shallow monitoring of 30". Information overload degrades decision quality |
| **触发条件** | SCAN区持续>50只股票; 用户每天花>30分钟看ARGUS dashboard; 用户开始"追信号"而非"做研究" |
| **影响等级** | **LOW** |
| **影响范围** | 投资决策质量下降; ARGUS从"望远镜"退化为"噪声放大器" |
| **缓解措施** | (1) Dashboard默认只显示CONVICTION区(3-8只)和CANDIDATE区(8-15只), SCAN区折叠隐藏; (2) 信号页面默认按bayesian_score降序, 只显示top-10; (3) 周报比日报更重要 -- Claude的weekly roundtable应是主要决策输入, 不是每日信号; (4) Kahneman: 不显示精确数字, 显示等级(Low/Medium/High/Very High) |
| **关联AC** | AC-05, AC-09 |
| **责任方** | Web UI设计 + 用户 (自律) |
| **验证时点** | Phase 6纸上交易 (观察用户行为模式) |

---

### RISK-S10: 实施周期延期 (Schedule Overrun) {#ARGUS-APP-B:s10}

| 字段 / Field | 内容 / Content |
|:--|:--|
| **风险ID** | RISK-S10 |
| **描述** | V2.0计划14周 (12周开发+2周纸上交易)。Phase 2 (贝叶斯引擎) 或Phase 4 (达尔文/共识) 可能遇到技术障碍。但与V1.0 RISK-010相比, 风险大幅降低: 不涉及DuckDB集成、不涉及Empire耦合、不涉及SENTINEL注册, 每个Phase的scope更小 |
| **描述(EN)** | V2.0 plans 14 weeks. Phase 2 (Bayesian engine) or Phase 4 (Darwin/Consensus) may encounter obstacles. Risk significantly lower than V1.0: no DuckDB, no Empire coupling, smaller scope per phase |
| **触发条件** | 贝叶斯引擎100信号模拟发现模型缺陷; 达尔文检测器误报率过高需重新设计 |
| **影响等级** | **LOW** |
| **影响范围** | 延期最多2-4周; 不影响Empire运行 |
| **缓解措施** | (1) 每Phase Gate检查, 早期发现问题; (2) Phase 4 (达尔文/共识) 可选跳过: 如果阻塞, Phase 5可不依赖Phase 4直接做回测; (3) 模块化设计: Phase 1-3构成最小可用系统, Phase 4-5为增值; (4) 最坏情况: Phase 1-3 (6周) 独立交付, Phase 4-6延后 |
| **关联AC** | 全部Gate检查点 |
| **责任方** | 用户 |
| **验证时点** | 每Phase Gate |

---

## S3 风险热力图 (Risk Heatmap) {#ARGUS-APP-B:heatmap}

```
影响等级
         |
  HIGH   |  RISK-S01(导入可靠性)         RISK-S02(信誉虚高)
         |      [中可能性]                    [高可能性]
         |
  MEDIUM |  RISK-S03(达尔文误报)  RISK-S05(同质化)   RISK-S04(共识滞后)
         |  RISK-S06(格式变更)                        RISK-S07(T+1衰减)
         |      [中可能性]                             RISK-S08(小样本)
         |                                            [高可能性]
         |
  LOW    |  RISK-S10(延期)       RISK-S09(注意力)
         |      [低可能性]            [中可能性]
         |
         +------------------------------------------------------> 触发可能性
                低                  中                  高
```

---

## S4 V1.0 -> V2.0 风险映射 (Risk Migration Map) {#ARGUS-APP-B:migration}

| V1.0风险 | V2.0状态 | 说明 |
|:--|:--|:--|
| RISK-001: DuckDB锁竞争 | **ELIMINATED** | MVP不使用DuckDB, 风险完全消除 |
| RISK-002: 信誉虚高 | -> RISK-S02 | 风险不变, 缓解方案不变 |
| RISK-003: 隐形重仓滞后 | **DEFERRED** | HF估算功能deferred, 风险随之deferred |
| RISK-004: NHC干预失效 | **DEFERRED** | 北向资金模块deferred |
| RISK-005: 拥挤度误杀 | **SIMPLIFIED** | V2.0拥挤度仅3级, KILL区deferred, 误杀风险大幅降低 |
| RISK-006: 同质化陷阱 | -> RISK-S05 | 风险继承, 在小universe中放大 |
| RISK-007: 季报数据质量 | **ELIMINATED** | V2.0不摄取季报(日度T+1数据为唯一源) |
| RISK-008: AH共线性 | **DEFERRED** | AH模块deferred |
| RISK-009: Kalman/Lasso风险 | **DEFERRED** | HF估算deferred |
| RISK-010: 实施延期 | -> RISK-S10 | 风险大幅降低(scope缩小, 无DuckDB/Empire耦合) |
| -- | **NEW** RISK-S01 | 单用户数据导入可靠性 (独立系统特有) |
| -- | **NEW** RISK-S03 | 达尔文时刻误报率 (新功能特有) |
| -- | **NEW** RISK-S04 | 共识方向滞后 (新功能特有) |
| -- | **NEW** RISK-S06 | Excel格式变更 (独立导入特有) |
| -- | **NEW** RISK-S07 | T+1 alpha衰减 (芒格警告) |
| -- | **NEW** RISK-S08 | 小样本量 (top-5 universe特有) |
| -- | **NEW** RISK-S09 | 注意力过载 (芒格警告) |

---

## S5 风险监控与升级路径 (Risk Monitoring & Escalation) {#ARGUS-APP-B:escalation}

| 状况 / Situation | 响应 / Response | 决策权 / Authority |
|:--|:--|:--|
| 风险缓解措施按计划落实, 风险在预期范围内 | 继续实施, Phase Gate确认 | 用户 |
| 风险实际触发但影响可控 | 执行缓解措施, 更新风险评估 | 用户 |
| 风险触发且影响超预期 | 暂停当前Phase, 评估是否需要redesign | 用户 + Claude roundtable |
| 多个HIGH风险同时触发 | 暂停开发, 评估系统可行性 | Internal Review Board |
| 发现新风险 | 记录至本登记簿, Phase Gate评估纳入 | 用户 |

> **V2.0简化说明**: V1.0的升级路径涉及三叉戟专家组、IC表决等复杂流程。V2.0作为单人独立工具, 升级路径简化为用户自行判断+Claude辅助分析。

---

## Attestation {#ARGUS-APP-B:attestation}

本附录由Internal Review Board基于以下材料编制:

This appendix was compiled by the Empire Decision Committee based on:

- B_RISK_REGISTER.md (V1.0, 10项风险, 已归档): 风险基线和缓解方案
- EXPERT_PANEL_WG3_WG4_WG5.md: WG5芒格终审五刀 (alpha衰减/注意力/简化)
- ADVANCED_FEATURES_DISCUSSION.md: 达尔文时刻+共识方向的风险分析 (Fama样本量质疑, Kahneman幸存者偏差警告)
- EXPERT_PANEL_WG1_WG2.md: 贝叶斯信誉风险 + 同质化陷阱分析

V2.0风险格局: 消除2项V1.0高风险 (DuckDB锁+季报数据), 降级4项 (HF/NHC/AH/Kalman), 继承2项 (信誉虚高+同质化), 新增7项独立系统特有风险。净效果: 总风险profile从HIGH-dominated变为MEDIUM-dominated。

---

## Changelog {#ARGUS-APP-B:changelog}

| 版本 / Version | 日期 / Date | 作者 / Author | 变更说明 / Changes |
|:--|:--|:--|:--|
| 0.1.0-draft | 2026-04-12 | Claude (SESSION-008) | V1.0初稿: 10项风险 (Empire子模块, 已归档为B_RISK_REGISTER.md) |
| 2.0.0-draft | 2026-04-12 | Internal Review Board | V2.0重写: 10项风险(独立系统); 2项消除+4项deferred+2项继承+7项新增; 风险映射表; 简化升级路径 |

---

**[ATTESTATION]**
ARGUS-APP-B V2.0.0-draft | RFC-2026-071 | 2026-04-12
Based on: V1.0 10-risk register + Munger 5 cuts + Darwin/Consensus risk analysis + Standalone architecture
SOP: init-context-draft-review-finalize
