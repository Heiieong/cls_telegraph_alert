# CLS Telegraph Alert 📢

Auto-send latest news from [财联社电报](https://www.cls.cn/telegraph) to Telegram.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run
python cls_alert.py
```

That's it! The script will:
1. Send a test message to verify connection
2. Start monitoring for new telegraph items
3. Auto-send new items to your Telegram

## Configuration

Edit `cls_alert.py` to change:

```python
CHECK_INTERVAL = 60  # Check every 60 seconds
```

## Run in Background

```bash
nohup python cls_alert.py > alert.log 2>&1 &
```

View logs: `tail -f alert.log`

Stop: `pkill -f cls_alert.py`
