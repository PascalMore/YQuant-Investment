---
name: reports
description: "YQuant 复盘报告模块：用于日周月季报告生成、可视化 Dashboard、多格式输出与推送服务。"
---

# Reports Module

复盘报告模块。

## 职责
- 日/周/月/季度报告生成
- 可视化 Dashboard
- 多格式输出 (Markdown/PDF/HTML)
- 推送服务

## 目录结构
```
reports/
├── templates/     # 报告模板
├── dashboard/     # Dashboard 组件
├── formatters/    # 格式化器
└── delivery/      # 推送服务
```

## 状态
🚧 建设中；上述目录为能力规划，不代表已部署 Dashboard 或推送服务。

## 与 Trading 的协作（规划）

依据 [RFC-26-072](../../docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md)：Reports 消费 Research/Strategy 的研究与回测结果、Portfolio 的组合事实与归因，以及 [Trading](../trading/SKILL.md) 的运行、订单/成交、费用、滑点、对账与异常事实，形成交易绩效、执行质量和风险复盘报告。报告计算不反向控制下单。

报告须区分回测、本地模拟、交易所测试环境与实盘，标注来源、时间和缺失/未对账状态；不将策略估算收益冒充账户净值。复盘产生再研究和再验证候选，不自动替换生产策略。统一 Web/移动工作台归 01_app，Reports 提供报告及展示内容，不接管整个应用壳。本次不新增推送、网关或长期调度。
