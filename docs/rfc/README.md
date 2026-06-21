# RFC 文档层

`docs/rfc` 是 YQuant-Investment 的项目需求与架构约束层。当前目录下已有文档继续作为项目需求文档/RFC 使用，不需要迁移到 `docs/spec`。

## 与 SPEC/DESIGN 的关系

- RFC：说明为什么做、做什么、业务边界、模块职责、数据/接口方向、验收标准。
- SPEC：从 RFC 派生，说明可执行、可测试的工程行为。
- DESIGN：从 SPEC 派生，说明怎么实现、改哪些文件、如何验证和回滚。

## 使用规则

- 新功能、数据模型、接口、交易/风控语义变更，必须先更新相关 RFC。
- 进入代码实现前，应创建或更新对应 `docs/spec` 和 `docs/design`。
- 小修可以不新增 RFC，但必须在最终交付中说明影响范围和验证结果。
- RFC 不应写成实现日志；实现细节放入 SPEC/DESIGN 或任务目录。

## 推荐流转

```text
docs/rfc/RFC-XX-XXX-*.md
  -> docs/spec/SPEC-XX-XXX-*.md
  -> docs/design/DESIGN-XX-XXX-*.md
  -> code/tests
  -> test report
  -> review
  -> closeout
```

