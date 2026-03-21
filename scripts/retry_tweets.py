#!/usr/bin/env python3
"""
retry_tweets.py — Retry fetching tweet text for fallback images.
Uses longer delays to avoid Wayback Machine rate limiting.
"""

import os
import re
import json
import time
import html
import textwrap
import urllib.request
import urllib.error
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

POSTS_EN = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
POSTS_ES = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"
IMAGES_DIR = "/Users/floresll/Desktop/iloveepoetry/assets/images/tweets/"

FONT_BOLD = "/System/Library/Fonts/Helvetica.ttc"
FONT_REGULAR = "/System/Library/Fonts/Helvetica.ttc"
IMG_WIDTH = 550
PADDING = 24
TEXT_WIDTH = IMG_WIDTH - (PADDING * 2)


def fetch_url(url, timeout=20):
    """Fetch a URL with retries."""
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt < 3:
                wait = 3 * (2 ** attempt)  # 3, 6, 12 seconds
                time.sleep(wait)
            else:
                return None
    return None


def find_wayback_snapshot(handle, status_id):
    """Find a Wayback snapshot for a tweet."""
    variants = [
        f"twitter.com/{handle}/status/{status_id}",
        f"twitter.com/{handle}/statuses/{status_id}",
    ]

    for clean_url in variants:
        cdx_url = (
            f"http://web.archive.org/cdx/search/cdx?"
            f"url={clean_url}&output=json&limit=5"
            f"&fl=timestamp,original,statuscode"
            f"&filter=statuscode:200"
        )
        data_str = fetch_url(cdx_url)
        if data_str:
            try:
                data = json.loads(data_str)
                if len(data) > 1:
                    ts = data[1][0]
                    orig = data[1][1]
                    return f"https://web.archive.org/web/{ts}/{orig}"
            except Exception:
                pass
        time.sleep(2)

    return None


def extract_tweet_data(wayback_url):
    """Extract tweet text, author, handle, date from archived page."""
    page = fetch_url(wayback_url)
    if not page:
        return None

    tweet_text = None
    for pat in [
        r'TweetTextSize[^>]*>(.*?)</p>',
        r'class="[^"]*tweet-text[^"]*"[^>]*>(.*?)</p>',
        r'class="[^"]*js-tweet-text[^"]*"[^>]*>(.*?)</p>',
    ]:
        m = re.search(pat, page, re.DOTALL)
        if m:
            tweet_text = m.group(1)
            break

    if not tweet_text:
        return None

    # Clean HTML
    tweet_text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', tweet_text)
    tweet_text = re.sub(r'<[^>]+>', '', tweet_text)
    tweet_text = html.unescape(tweet_text).strip()

    display_name = None
    m = re.search(r'class="[^"]*fullname[^"]*"[^>]*>(.*?)<', page, re.DOTALL)
    if m:
        display_name = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()

    handle_found = None
    m = re.search(r'class="[^"]*username[^"]*"[^>]*>.*?@(\w+)', page, re.DOTALL)
    if m:
        handle_found = m.group(1)

    tweet_date = None
    m = re.search(r'data-time="(\d+)"', page)
    if m:
        ts = int(m.group(1))
        tweet_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y")

    return {
        "text": tweet_text,
        "display_name": display_name,
        "handle": handle_found,
        "date": tweet_date,
    }


def create_tweet_image(tweet_data, handle_fallback, output_path):
    """Create a tweet card image."""
    text = tweet_data["text"]
    display_name = tweet_data.get("display_name") or handle_fallback
    handle = tweet_data.get("handle") or handle_fallback
    date = tweet_data.get("date") or ""

    try:
        font_name = ImageFont.truetype(FONT_BOLD, 17, index=1)
        font_handle = ImageFont.truetype(FONT_REGULAR, 14, index=0)
        font_text = ImageFont.truetype(FONT_REGULAR, 16, index=0)
        font_date = ImageFont.truetype(FONT_REGULAR, 13, index=0)
    except Exception:
        font_name = ImageFont.load_default()
        font_handle = font_name
        font_text = font_name
        font_date = font_name

    char_width = TEXT_WIDTH // 9
    wrapped_lines = []
    for line in text.split("\n"):
        if line.strip():
            wrapped_lines.extend(textwrap.wrap(line, width=char_width))
        else:
            wrapped_lines.append("")

    line_height_text = 22
    header_height = 55
    text_height = max(len(wrapped_lines), 1) * line_height_text
    date_height = 35
    total_height = PADDING + header_height + text_height + date_height + PADDING

    img = Image.new("RGB", (IMG_WIDTH, total_height), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, IMG_WIDTH - 1, total_height - 1], outline="#E1E8ED", width=1)
    draw.rectangle([0, 0, 3, total_height - 1], fill="#1DA1F2")

    y = PADDING
    try:
        icon_font = ImageFont.truetype(FONT_BOLD, 20, index=1)
    except Exception:
        icon_font = font_name
    draw.text((PADDING, y), "\U0001d54f", fill="#000000", font=icon_font)
    draw.text((PADDING + 28, y), display_name, fill="#14171A", font=font_name)
    y += 24
    draw.text((PADDING + 28, y), f"@{handle}", fill="#657786", font=font_handle)
    y += 31

    for line in wrapped_lines:
        draw.text((PADDING, y), line, fill="#14171A", font=font_text)
        y += line_height_text

    y += 8
    draw.line([(PADDING, y), (IMG_WIDTH - PADDING, y)], fill="#E1E8ED", width=1)
    y += 8
    draw.text((PADDING, y), date, fill="#657786", font=font_date)

    img.save(output_path, "PNG", optimize=True)


def update_alt_in_posts(img_filename, handle, new_alt):
    """Update alt text for a tweet image in all post files."""
    img_ref = f"/assets/images/tweets/{img_filename}"
    for lang_dir in [POSTS_EN, POSTS_ES]:
        for post_fname in os.listdir(lang_dir):
            post_path = os.path.join(lang_dir, post_fname)
            if not os.path.isfile(post_path):
                continue
            with open(post_path, "r", encoding="utf-8") as f:
                content = f.read()
            if img_ref not in content:
                continue
            old_pattern = re.compile(
                r'alt="Tweet by @' + re.escape(handle) + r'[^"]*"'
            )
            new_content = old_pattern.sub(f'alt="{new_alt}"', content)
            if new_content != content:
                with open(post_path, "w", encoding="utf-8") as f:
                    f.write(new_content)


def main():
    # Find fallback images (small size = no real text)
    needs_retry = []
    for fname in sorted(os.listdir(IMAGES_DIR)):
        if not fname.startswith("tweet_") or not fname.endswith(".png"):
            continue
        m = re.match(r"tweet_(.+)_(\d+)\.png", fname)
        if not m:
            continue
        handle = m.group(1)
        status_id = m.group(2)
        fpath = os.path.join(IMAGES_DIR, fname)
        if os.path.getsize(fpath) < 7000:
            needs_retry.append((handle, status_id, fname, fpath))

    print(f"Retrying {len(needs_retry)} tweets")
    print("=" * 60)

    success = 0
    failed = 0

    for i, (handle, status_id, fname, fpath) in enumerate(needs_retry):
        print(f"\n[{i+1}/{len(needs_retry)}] @{handle}/{status_id}...", end=" ", flush=True)

        snapshot = find_wayback_snapshot(handle, status_id)
        if not snapshot:
            print("NO ARCHIVE")
            failed += 1
            time.sleep(3)
            continue

        tweet_data = extract_tweet_data(snapshot)
        time.sleep(3)

        if not tweet_data or not tweet_data.get("text"):
            print("NO TEXT")
            failed += 1
            continue

        # Regenerate image
        create_tweet_image(tweet_data, handle, fpath)

        # Build alt text
        safe_text = tweet_data["text"].replace('"', '&quot;')
        display = tweet_data.get("display_name") or handle
        date_str = f" on {tweet_data['date']}" if tweet_data.get("date") else ""
        new_alt = f"Tweet by @{handle} ({display}){date_str}: {safe_text}"
        if len(new_alt) > 500:
            new_alt = new_alt[:497] + "..."

        update_alt_in_posts(fname, handle, new_alt)

        print(f"OK: {tweet_data['text'][:70]}...")
        success += 1

    print("\n" + "=" * 60)
    print(f"Retried: {len(needs_retry)}")
    print(f"  Success: {success}")
    print(f"  Failed:  {failed}")


if __name__ == "__main__":
    main()
