# RFC-10-014：Windows Redis 启动期假活最小自愈

版本：V2.0
创建日期：2026-10-26；最后更新：2026-10-27
状态：已冻结（最小方案）
作者：YQuant-Principal

关联文档：
- [SPEC V2.0](../../spec/10_infra/SPEC-10-014-windows-redis-startup-readiness-recovery.md)
- [DESIGN V2.0](../../design/10_infra/DESIGN-10-014-windows-redis-startup-readiness-recovery.md)

## 1. 原因与证据边界

根据 2026-10-26 主控只读取证，6380 的 Redis 日志直接记录 bind 失败并退出：
`Could not create server TCP listening socket 172.25.240.1:6380: bind: Cannot assign requested address`。
该失败早于 WSL 启动约 22 秒，支持 Redis 自启早于 WSL 网络就绪的启动时序解释。
服务包装容器仍显示 Running、端口却无监听，形成启动期假活。
6379 自身日志未直接取证；同类根因仅为推断，不能称两实例根因均已证实。
以上沿用已有取证结论，本卡未重新读取服务日志或执行 Windows 命令。

## 2. 最小目标

只修改既有 `C:\Users\pascal\AppData\Local\YQuant\wsl-keepalive-runner.ps1`。
保留保活职责，在后台启动原保活命令后，对 Redis=6379、RedisJobs=6380 做最多 3 轮监听检查。
首次检查前及轮间均等待 15 秒；仅未监听时重启对应服务，有监听不重启。
恢复失败只记既有事件日志，不中断已启动的保活；最后等待保活退出并传回其退出码。
保活启动异常则记录并退出 1，不操作 Redis。五步行为与验收以 SPEC 为准。

## 3. 范围与限制

仅以 Windows 端口监听作为本次恢复判据，不保证 Redis 协议可用或监听者身份正确。
不增加地址发现、协议探针、记录平台、额外日志文件、脚本、服务、任务或退出码表。
不更改配置、权限、计划任务 XML、防火墙、WSL 或 QuantDinger，不为输出合并增加包装器。
本卡只交付三份文档；离线检查不等于真实恢复成功，Windows 重启及服务操作须另行授权。

## 版本记录

V2.0（2026-10-27）：按 Pascal 指示收敛为最小方案，删除过度设计。
