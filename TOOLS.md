# TOOLS.md - Local Notes

## 邮件配置

### SMTP 设置（QQ 邮箱）
- **服务器:** smtp.qq.com
- **端口:** 465 (SSL)
- **发件人:** 532484187@qq.com
- **授权码:** <请在 QQ 邮箱设置中获取>

### 收件人
- **主邮箱:** 532484187@qq.com

## 投资系统配置

### 数据源
- AKShare: A 股/港股数据（免费）
- YFinance: 美股数据（免费）
- Binance API: 币安行情（免费）

### 推送配置
- 邮件推送
- 时间：每个交易日 08:30

### 自选股列表
- A 股：600519, 000858, 300750
- 港股：00700, 09988
- 美股：AAPL, NVDA, TSLA
- Crypto: BTC, ETH, SOL

## 常用命令

```bash
# 测试邮件发送
python3 ~/.openclaw/workspace/skills/common/utils/email/send_email.py \
  "532484187@qq.com" \
  "测试邮件" \
  "这是一封测试邮件"
```

## Hermes Agent 升级

从源码升级 Hermes Agent 使用项目专属脚本（fork-aware，RFC-10-005/006 + SPEC-10-005/006 + DESIGN-10-006）：

```bash
cd /home/pascal/workspace/yquant-investment

# 干跑（不修改任何状态）
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --branch <当前分支> --no-restart --no-push

# 真实升级（保留 feishu 修复 + merge 上游，不重启 gateway、不推送 fork）
python3 scripts/upgrade/upgrade_hermes_agent.py --branch <当前分支> --no-restart --no-push --verbose

# 升级后：config migrate + 重启 gateway
hermes config migrate
# 重启需在 gateway 进程外执行（否则会杀当前会话）：
systemctl --user restart hermes-gateway-<profile>.service
```

**注意**：
- **不要**用 `hermes --version` 的 "Up to date" 判断是否最新——它对 fork 只对比 `origin/main`，不看官方 `upstream`（P-5 陷阱，见 `hermes-source-upgrade` skill）。真实差距用 `git fetch upstream && git rev-list --count HEAD..upstream/main` 或 GitHub 的 main-vs-upstream 对比。
- 脚本 S6 merge 冲突时 fail-stop（abort）；若已知 adapter 冲突，先手工 `git merge --no-edit upstream/main` 解决，再跑脚本（此时 classify 识别 already-up-to-date，脚本专注 backup/install/verify）。
- 参考：`docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md`、`docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md`

## Telegram 配置

### Bot
- **Token**: <YOUR_TELEGRAM_BOT_TOKEN>
- **Chat ID**: 6805320916（Pascal 个人）

### 发送文件函数
```python
def telegram_send_file(token: str, chat_id: str, file_path: str, caption: str = ""):
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": f}
        data = {"chat_id": chat_id, "caption": caption}
        r = requests.post(url, data=data, files=files)
    return r.json()
```