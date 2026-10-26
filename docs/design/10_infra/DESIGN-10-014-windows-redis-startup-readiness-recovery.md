# DESIGN-10-014：Windows Redis 启动期假活最小自愈

版本：V2.0
创建日期：2026-10-27；最后更新：2026-10-27
状态：已冻结（最小方案）
作者：YQuant-Principal

关联文档：
- [RFC V2.0](../../rfc/10_infra/RFC-10-014-windows-redis-startup-readiness-recovery.md)
- [SPEC V2.0](../../spec/10_infra/SPEC-10-014-windows-redis-startup-readiness-recovery.md)

## 1. 执行顺序

唯一运行文件：`C:\Users\pascal\AppData\Local\YQuant\wsl-keepalive-runner.ps1`。
保留原参数、WslExe 解析、ErrorActionPreference=Stop 及 RUNNER_STARTED 事件。
Start-Process 后台启动原 WSL 保活命令，以 -PassThru 保存进程对象。
传参须保留 Distro 的参数边界，并使 `/bin/sh -lc` 收到完整的 `exec sleep infinity` 命令字符串。
不使用 stdout/stderr 重定向，不增加 cmd/PowerShell 包装器或日志文件。

进程启动成功 → 等待 15 秒 → 检查监听并按需重启 → 必要时等待 15 秒进入下一轮。
最多 3 轮，固定 Redis=6379、RedisJobs=6380；Get-NetTCPConnection 的 Listen 结果不限制本地地址。
每轮对各端口独立判断：有监听则跳过，无监听才 Restart-Service 对应服务（-Force）。
仅当本轮同一次查询中两端口同时监听才结束循环；历史监听字段仅作结果信息，不参与控制；恢复检查结束后记录结果，再 WaitForExit 等待保活。
最后记录 WSL_EXITED 并返回保活退出码，绝不以 Redis 结果替代。
结果行使用最后实际观察值，区分“尝试重启”与“已观察恢复”，不虚报未复查的状态。

## 2. 异常边界

Start-Process 抛异常或无进程对象：记录 RUNNER_ERROR，退出 1，不进入 Redis 检查。
监听查询异常：记录错误且该次不重启，不把查询失败解释成无监听。
重启异常：记录错误，不影响另一实例、剩余轮次及已启动的保活。
达到轮数上限仍未恢复：记录结果后仍等待保活，不退出、不杀保活、不新增重试机制。
日志沿用原 LogPath、时间戳及 UTF-8 追加方式，恢复异常捕获范围不包住最终保活等待。

## 3. 相对 23 行原脚本的最小差异

保留必填 Distro/LogPath 的名称、顺序和无默认值语义，以及原 WslExe 与 ErrorActionPreference 设置。
将同步 `& $WslExe ... *>> $LogPath` 改为后台启动并保留进程对象，取消子进程输出捕获。
在启动与退出等待之间插入有限监听检查及恢复结果事件；原 WSL_EXITED 改为读取进程对象退出码。
除此之外不增加地址发现、协议探针、记录平台、额外脚本/任务、超时表、提权或配置修改。
本卡仅产出设计；离线检查与真实 Windows 重启验收按 SPEC 分开，不在本卡执行运行命令。

## 版本记录

V2.0（2026-10-27）：按 Pascal 指示收敛为最小方案，删除过度设计。

V2.0 验收澄清（2026-10-27，主控据 M3 F-1～F-3）：提前结束只依据当前轮同时监听；历史监听字段仅作结果信息，不新增机制或改变 3 轮/15 秒边界。
