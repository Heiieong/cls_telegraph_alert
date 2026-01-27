#!/usr/bin/env python3
"""
CLS Telegraph Alert - Auto-send latest news from 财联社电报 to Telegram
"""

import os
import json
import time
import re
import hashlib
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ============ CONFIGURATION ============
# Reads from environment variables (for GitHub Actions) or uses defaults (for local)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8248558481:AAEGZAnoi8x1suFMifKbSaREqZjuYhloTlU")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "984635456")
CHECK_INTERVAL = 60  # seconds between checks
CLS_URL = "https://www.cls.cn/telegraph"
KEYWORDS = ["上市申请", "联席保荐人", "发行H股", "独家保荐人"]  # Only send messages containing these keywords
# =======================================

STATE_FILE = os.path.join(os.path.dirname(__file__), ".seen_ids.json")


def load_seen_ids():
    """Load previously seen message IDs."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def save_seen_ids(seen):
    """Save seen message IDs."""
    with open(STATE_FILE, 'w') as f:
        json.dump(list(seen), f)


def send_telegram(message):
    """Send message to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        resp = requests.post(url, data=data, timeout=30)
        resp.raise_for_status()
        log("✓ Message sent")
        return True
    except Exception as e:
        log(f"✗ Send failed: {e}")
        return False


def log(msg):
    """Print timestamped log message."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_telegraph():
    """Fetch telegraph items from CLS."""
    items = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            log("Fetching CLS Telegraph...")
            page.goto(CLS_URL, timeout=60000)
            page.wait_for_timeout(6000)
            
            # Try multiple selectors to find telegraph items
            # Look for elements that contain the telegraph news
            selectors = [
                '.telegraph-list .telegraph-item',
                '[class*="telegraph"] [class*="item"]',
                '.content-wrapper .item',
                'div[class*="telegraph"]',
            ]
            
            found_elements = []
            for selector in selectors:
                try:
                    elements = page.locator(selector).all()
                    if elements:
                        log(f"Found {len(elements)} elements with selector: {selector}")
                        found_elements = elements
                        break
                except:
                    continue
            
            if found_elements:
                for elem in found_elements[:30]:
                    try:
                        text = elem.text_content().strip()
                        # Look for time pattern and title in brackets
                        match = re.search(r'(\d{2}:\d{2}(?::\d{2})?)\s*【([^】]+)】(.*)', text, re.DOTALL)
                        if match:
                            time_str, title, content = match.groups()
                            content = content.strip()[:800]
                            item_id = hashlib.md5(f"{time_str}_{title}".encode()).hexdigest()[:12]
                            items.append({
                                'id': item_id,
                                'time': time_str,
                                'title': title.strip(),
                                'content': content
                            })
                    except Exception as e:
                        continue
            
            # Fallback: extract from full page text
            if not items:
                log("Trying fallback extraction from page text...")
                text = page.locator('body').text_content()
                
                # Pattern: time【title】content
                pattern = r'(\d{2}:\d{2}:\d{2})\s*【([^】]+)】'
                matches = list(re.finditer(pattern, text))
                
                for i, match in enumerate(matches[:30]):
                    time_str = match.group(1)
                    title = match.group(2).strip()
                    
                    # Get content until next time marker or end
                    start = match.end()
                    if i + 1 < len(matches):
                        end = matches[i + 1].start()
                    else:
                        end = min(start + 1000, len(text))
                    
                    content = text[start:end].strip()
                    # Clean up content - remove noise
                    content = re.sub(r'\s+', ' ', content)
                    content = content[:500]
                    
                    item_id = hashlib.md5(f"{time_str}_{title}".encode()).hexdigest()[:12]
                    items.append({
                        'id': item_id,
                        'time': time_str,
                        'title': title,
                        'content': content
                    })
            
            log(f"Found {len(items)} items")
            
        except Exception as e:
            log(f"Fetch error: {e}")
        finally:
            browser.close()
    
    return items


def matches_keywords(item):
    """Check if item contains any of the keywords."""
    if not KEYWORDS:
        return True
    text = f"{item['title']} {item['content']}"
    return any(kw in text for kw in KEYWORDS)


def format_message(item):
    """Format telegraph item for Telegram."""
    date = datetime.now().strftime("%Y-%m-%d")
    msg = f"🔔 <b>财联社电报</b>\n"
    msg += f"⏰ {date} {item['time']}\n\n"
    msg += f"<b>【{item['title']}】</b>\n\n"
    if item['content']:
        # Clean content for Telegram
        content = item['content']
        content = re.sub(r'<[^>]+>', '', content)  # Remove any HTML
        content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        msg += content
    return msg


def run():
    """Main monitoring loop."""
    print("=" * 50, flush=True)
    print("  CLS Telegraph Alert", flush=True)
    print(f"  Checking every {CHECK_INTERVAL}s", flush=True)
    print(f"  Keywords: {KEYWORDS}", flush=True)
    print("=" * 50, flush=True)
    
    seen = load_seen_ids()
    first_run = True
    
    while True:
        try:
            items = fetch_telegraph()
            
            if items:
                new_items = [i for i in items if i['id'] not in seen]
                
                if new_items:
                    # Filter by keywords
                    matched_items = [i for i in new_items if matches_keywords(i)]
                    
                    if first_run:
                        # First run: mark all as seen, send only matched
                        log(f"First run: {len(new_items)} items, {len(matched_items)} matched keywords")
                        if matched_items:
                            send_telegram(format_message(matched_items[0]))
                        for item in new_items:
                            seen.add(item['id'])
                    else:
                        # Send all matched items
                        log(f"{len(new_items)} new items, {len(matched_items)} matched keywords")
                        for item in reversed(matched_items):
                            send_telegram(format_message(item))
                            time.sleep(1)
                        for item in new_items:
                            seen.add(item['id'])
                    
                    save_seen_ids(seen)
                else:
                    log("No new items")
            
            first_run = False
            
        except Exception as e:
            log(f"Error: {e}")
        
        time.sleep(CHECK_INTERVAL)


def run_once():
    """Fetch and send latest item once (for testing)."""
    items = fetch_telegraph()
    if items:
        log(f"Found {len(items)} items")
        for i, item in enumerate(items[:3]):
            log(f"  {i+1}. [{item['time']}] {item['title'][:50]}...")
        send_telegram(format_message(items[0]))
    else:
        log("No items found")


def run_once_check():
    """Single check for new items (for GitHub Actions / cron)."""
    log(f"Single check mode - Keywords: {KEYWORDS}")
    
    seen = load_seen_ids()
    items = fetch_telegraph()
    
    if not items:
        log("No items found")
        return
    
    new_items = [i for i in items if i['id'] not in seen]
    
    if not new_items:
        log("No new items")
        return
    
    # Filter by keywords
    matched_items = [i for i in new_items if matches_keywords(i)]
    log(f"{len(new_items)} new items, {len(matched_items)} matched keywords")
    
    # Send matched items
    for item in reversed(matched_items):
        send_telegram(format_message(item))
        time.sleep(1)
    
    # Mark all new items as seen
    for item in new_items:
        seen.add(item['id'])
    
    save_seen_ids(seen)
    log("Done")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test mode: just fetch and send latest
        log("Test mode - fetching once...")
        run_once()
    elif len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Single check mode (for GitHub Actions / cron)
        run_once_check()
    else:
        # Normal mode: test connection then monitor
        log("Testing Telegram connection...")
        keywords_str = ', '.join(KEYWORDS) if KEYWORDS else 'All'
        if send_telegram(f"✅ CLS Telegraph Alert started!\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🔍 Keywords: {keywords_str}"):
            run()
        else:
            print("\n⚠️  Failed to send test message. Check your bot token and chat ID.", flush=True)
