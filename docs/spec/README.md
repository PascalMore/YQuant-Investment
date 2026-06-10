# SPEC 文档层

`docs/spec` 用于沉淀从 `docs/rfc` 派生出的工程规格。RFC 说明业务目标和架构约束，SPEC 说明可执行、可测试的行为。

## 使用规则

- 当 `docs/rfc` 中的需求进入实装阶段时，先创建对应 SPEC。
- SPEC 必须引用来源 RFC。
- Developer 和 Test Engineer 以 SPEC 为直接依据。
- RFC 发生业务语义变化时，同步更新对应 SPEC。

## 推荐命名

```text
SPEC-{模块编号}-{序号}-{short-name}.md
```

示例：

```text
SPEC-05-001-stock-pool-crud.md
```

