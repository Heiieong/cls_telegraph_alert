#!/usr/bin/env python3
"""
CLS Telegraph Alert - Auto-send latest news from 财联社电报 to Telegram
"""

import os
import json
import time
import re
import hashlib
import argparse
import html
import unicodedata
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ============ CONFIGURATION ============
# Reads from environment variables (for GitHub Actions or local shell).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))  # seconds between checks
CLS_URL = "https://www.cls.cn/telegraph"
DEFAULT_KEYWORDS = ["上市申请", "联席保荐人", "发行H股", "独家保荐人"]
KEYWORDS = [kw.strip() for kw in os.environ.get("KEYWORDS", ",".join(DEFAULT_KEYWORDS)).split(",") if kw.strip()]
MAX_SEEN_IDS = int(os.environ.get("MAX_SEEN_IDS", "1000"))
# =======================================

STATE_FILE = os.environ.get("STATE_FILE", os.path.join(os.path.dirname(__file__), ".seen_ids.json"))


def load_seen_ids():
    """Load previously seen message IDs."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data = data.get("ids", [])
                return set(data)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            log(f"Could not load state file {STATE_FILE}: {exc}")
            return set()
    return set()


def save_seen_ids(seen):
    """Save seen message IDs."""
    trimmed = list(seen)[-MAX_SEEN_IDS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def send_telegram(message, dry_run=False):
    """Send message to Telegram."""
    if dry_run:
        log("Dry run: would send Telegram message:")
        print(message, flush=True)
        return True

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram credentials missing. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
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
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            log("Fetching CLS Telegraph...")
            page.goto(CLS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            
            # Scroll down to load more items
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 1000)")
                page.wait_for_timeout(1000)
            
            # Scroll back to top
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1000)
            
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
                for elem in found_elements[:50]:
                    try:
                        text = clean_text(elem.text_content())
                        # Look for time pattern and title in brackets
                        match = re.search(r'(\d{2}:\d{2}(?::\d{2})?)\s*【([^】]+)】(.*)', text, re.DOTALL)
                        if match:
                            time_str, title, content = match.groups()
                            content = clean_text(content)[:800]
                            item_id = make_item_id(time_str, title, content)
                            items.append({
                                'id': item_id,
                                'time': time_str,
                                'title': title.strip(),
                                'content': content
                            })
                    except Exception:
                        continue
            
            # Fallback: extract from full page text
            if not items:
                log("Trying fallback extraction from page text...")
                text = clean_text(page.locator('body').text_content())
                
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
                    
                    content = clean_text(text[start:end])[:800]
                    
                    item_id = make_item_id(time_str, title, content)
                    items.append({
                        'id': item_id,
                        'time': time_str,
                        'title': title,
                        'content': content
                    })
            
            log(f"Found {len(items)} items")
            
            browser.close()
    except Exception as e:
        log(f"Fetch error: {str(e).splitlines()[0]}")
    
    return items


def clean_text(text):
    """Normalize whitespace from browser text extraction."""
    return re.sub(r'\s+', ' ', text or '').strip()


def normalize_for_match(text):
    """Normalize Chinese/English mixed text for keyword matching."""
    normalized = unicodedata.normalize("NFKC", text or "")
    return re.sub(r'\s+', '', normalized).lower()


def make_item_id(time_str, title, content):
    """Create a stable ID that does not collide across trading days."""
    today = datetime.now().strftime("%Y-%m-%d")
    raw = f"{today}_{time_str}_{title}_{content[:80]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def matches_keywords(item):
    """Check if item contains any of the keywords."""
    if not KEYWORDS:
        return True
    text = normalize_for_match(f"{item['title']} {item['content']}")
    return any(normalize_for_match(kw) in text for kw in KEYWORDS)


def format_message(item):
    """Format telegraph item for Telegram."""
    date = datetime.now().strftime("%Y-%m-%d")
    msg = f"🔔 <b>财联社电报</b>\n"
    msg += f"⏰ {date} {html.escape(item['time'])}\n\n"
    msg += f"<b>【{html.escape(item['title'])}】</b>\n\n"
    if item['content']:
        # Clean content for Telegram
        content = clean_text(item['content'])
        content = re.sub(r'<[^>]+>', '', content)  # Remove any HTML
        msg += html.escape(content)
    return msg


def send_matched_items(matched_items, dry_run=False):
    """Send matching items oldest-first."""
    sent = 0
    for item in reversed(matched_items):
        if send_telegram(format_message(item), dry_run=dry_run):
            sent += 1
        time.sleep(1)
    return sent


def process_items(items, seen, dry_run=False, update_state=True):
    """Filter new items by keyword, send matches, and update seen state."""
    if not items:
        log("No items found")
        return 0, 0

    new_items = [i for i in items if i['id'] not in seen]

    if not new_items:
        log("No new items")
        return 0, 0

    matched_items = [i for i in new_items if matches_keywords(i)]
    log(f"{len(new_items)} new items, {len(matched_items)} matched keywords")

    sent = send_matched_items(matched_items, dry_run=dry_run)

    if update_state:
        for item in new_items:
            seen.add(item['id'])
        save_seen_ids(seen)

    return len(matched_items), sent


def run(dry_run=False):
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
                        send_matched_items(matched_items, dry_run=dry_run)
                        for item in new_items:
                            seen.add(item['id'])
                    else:
                        # Send all matched items
                        log(f"{len(new_items)} new items, {len(matched_items)} matched keywords")
                        send_matched_items(matched_items, dry_run=dry_run)
                        for item in new_items:
                            seen.add(item['id'])
                    
                    save_seen_ids(seen)
                else:
                    log("No new items")
            
            first_run = False
            
        except Exception as e:
            log(f"Error: {e}")
        
        time.sleep(CHECK_INTERVAL)


def run_once(dry_run=True, update_state=False):
    """Fetch once and print/send only keyword-matched items."""
    log(f"Single fetch - Keywords: {KEYWORDS}")
    items = fetch_telegraph()
    if items:
        matched_items = [item for item in items if matches_keywords(item)]
        log(f"Found {len(items)} items, {len(matched_items)} matched keywords")
        for i, item in enumerate(items[:3]):
            log(f"  {i+1}. [{item['time']}] {item['title'][:50]}...")
        seen = load_seen_ids()
        process_items(items, seen, dry_run=dry_run, update_state=update_state)
    else:
        log("No items found")


def run_once_check(dry_run=False):
    """Single check for new items (for GitHub Actions / cron)."""
    log(f"Single check mode - Keywords: {KEYWORDS}")
    
    seen = load_seen_ids()
    items = fetch_telegraph()
    process_items(items, seen, dry_run=dry_run, update_state=not dry_run)
    log("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CLS Telegraph keyword alert for Telegram")
    parser.add_argument("command", nargs="?", choices=["test"], help="Alias for --dry-run")
    parser.add_argument("--once", action="store_true", help="Run one check and update state")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and show matching messages without sending or saving state")
    parser.add_argument("--send-test-message", action="store_true", help="Send a Telegram startup test message only")
    args = parser.parse_args()

    if args.command == "test" or args.dry_run:
        log("Dry-run mode - fetching once without sending...")
        run_once(dry_run=True, update_state=False)
    elif args.send_test_message:
        keywords_str = ', '.join(KEYWORDS) if KEYWORDS else 'All'
        send_telegram(f"✅ CLS Telegraph Alert test\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🔍 Keywords: {keywords_str}")
    elif args.once:
        run_once_check()
    else:
        # Normal mode: test connection then monitor
        log("Testing Telegram connection...")
        keywords_str = ', '.join(KEYWORDS) if KEYWORDS else 'All'
        if send_telegram(f"✅ CLS Telegraph Alert started!\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🔍 Keywords: {keywords_str}"):
            run()
        else:
            print("\n⚠️  Failed to send test message. Check your bot token and chat ID.", flush=True)
