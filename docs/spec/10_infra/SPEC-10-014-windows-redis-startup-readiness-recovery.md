# SPEC-10-014：Windows Redis 启动期假活最小自愈

版本：V2.0
创建日期：2026-10-26；最后更新：2026-10-27
状态：已冻结（最小方案）
作者：YQuant-Principal

关联文档：
- [RFC V2.0](../../rfc/10_infra/RFC-10-014-windows-redis-startup-readiness-recovery.md)
- [DESIGN V2.0](../../design/10_infra/DESIGN-10-014-windows-redis-startup-readiness-recovery.md)

## 1. 唯一运行文件与常量

运行文件：`C:\Users\pascal\AppData\Local\YQuant\wsl-keepalive-runner.ps1`。
基线为 23 行；SHA256：`08bdde7bce921f4e5754310e8d9907d84812febeaac2466eb387b9bbde8666e8`。
服务与端口固定映射：Redis=6379、RedisJobs=6380。
最多 3 轮；首次检查前等待 15 秒，后续轮间等待 15 秒，不增加其他超时常量。

## 2. 五步行为

1. 保留必填且无默认值的 Distro、LogPath，名称及顺序不变；保留 `$WslExe = Join-Path $env:WINDIR "System32\wsl.exe"`、`$ErrorActionPreference = "Stop"`，以及带 `[$(Get-Date -Format s)]` 前缀、UTF-8 追加到 LogPath 的既有事件日志。
2. 用 Start-Process 后台启动原命令 `wsl.exe -d <Distro> --exec /bin/sh -lc 'exec sleep infinity'`，正确传递参数引号，用 -PassThru 保留进程对象。启动抛异常或未取得对象，记录错误并 exit 1，不操作 Redis；不重定向或合并子进程 stdout/stderr，不增加包装器或输出文件。
3. 首次等待后，在每轮通过 Get-NetTCPConnection 检查 Windows 6379/6380 的 Listen 条目，任意本地地址有监听即跳过对应服务；确定未监听才执行 `Restart-Service -Name <对应服务名> -Force`，每服务每轮最多一次。查询异常不等于确定无监听：记录错误、跳过该次操作；重启异常记录错误，继续另一实例及后续轮次。仅当本轮同一次查询中两端口同时监听才提前结束；历史曾监听不参与结束判定，否则最多 3 轮；轮间等待 15 秒。
4. 检查结束后向既有 LogPath 追加结果行，带时间戳、两实例最后监听观察结果、是否尝试重启及错误摘要。查询失败标为未知；未复查的重启不冒充恢复成功，不写凭据。不因恢复失败退出或终止已启动的保活。
5. 等待保活进程 WaitForExit，记录既有 WSL_EXITED 事件并 exit 该进程退出码。Redis 恢复结果不覆盖保活退出码，不主动停止保活。

## 3. 验收边界

### 3.1 文档离线检查（本卡）

三份独立文档均存在、为 V2.0、最后更新 2026-10-27、各不超过 120 行。
相对链接指向正确文件；无重复章节、乱码或残留占位内容；五步、映射、轮数及间隔一致。
核对本卡三路径改动，不要求共享工作树全局干净，不清理并行任务改动。
对每个 untracked 文档执行 `git diff --no-index --check /dev/null <实际文件路径>`，记录退出码及输出；同时记录行数与 SHA256。
禁止的是实现额外机制，不是禁止在“不做”范围说明中提到它们；不以全文禁词搜索代替语义核对。

### 3.2 实现离线检查（既有 M2/M3/M4）

对照原始基线 diff，逐项验证五步分支、参数引号、有限轮次、健康态零重启、异常隔离及等待退出。
PowerShell 解析器实际可用时仅解析，不执行 runner；不可用则明确未验证，不安装依赖、不用字符串检查冒充解析。
Windows 原生仅解析命令（本卡不执行）：
`$tokens=$null; $parseErrors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('C:\Users\pascal\AppData\Local\YQuant\wsl-keepalive-runner.ps1',[ref]$tokens,[ref]$parseErrors); $parseErrors; if ($parseErrors.Count -gt 0) { exit 1 }`

### 3.3 真实 Windows 验收（Pascal 另行授权）

真实重启宿主并登录后，核对两端口监听、既有日志中的恢复动作和结果；有监听的实例不得被重启。
健康态重跑须零 Redis 重启；runner 会持续等待保活，不以它立即返回作为成功条件。
恢复失败应有错误日志且保活继续；启动异常应退出 1 且无 Redis 操作；保活退出码须原样传回。
Windows 实际执行、Redis 恢复、任务控制权限及整机重启分别记录结果；离线阶段均为 not_verified。

## 4. 不做与授权

不增加地址发现、协议探针、监控或记录框架、额外日志、退出码表、脚本、服务、任务或依赖。
不提权，不修改 Redis 配置/数据、任务 XML、权限、防火墙、WSL、QuantDinger 或 API 服务。
本卡只写三文档，不执行 Windows 命令、不连接 Redis、不重启服务、不提交或推送。

## 版本记录

V2.0（2026-10-27）：按 Pascal 指示收敛为最小方案，删除过度设计。

V2.0 验收澄清（2026-10-27，主控据 M3 F-1～F-3）：提前结束只依据当前轮同时监听；历史监听字段仅作结果信息，不新增机制或改变 3 轮/15 秒边界。
