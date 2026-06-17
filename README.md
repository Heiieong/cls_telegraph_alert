# CLS Telegraph Alert 📢

Auto-send latest news from [财联社电报](https://www.cls.cn/telegraph) to Telegram.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Safe test run: fetch once, print matching Telegram messages, do not send
python cls_alert.py --dry-run

# Run one production check, send matched new items, update seen state
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python cls_alert.py --once

# Continuous local monitor
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python cls_alert.py
```

The script sends 财联社电报 items only when the title or content contains one of:

```text
上市申请, 联席保荐人, 发行H股, 独家保荐人
```

## Configuration

Use environment variables:

```bash
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export CHECK_INTERVAL=60
export KEYWORDS="上市申请,联席保荐人,发行H股,独家保荐人"
```

Use `python cls_alert.py --send-test-message` to verify Telegram credentials.

## Run in Background

```bash
nohup python cls_alert.py > alert.log 2>&1 &
```

View logs: `tail -f alert.log`

Stop: `pkill -f cls_alert.py`
