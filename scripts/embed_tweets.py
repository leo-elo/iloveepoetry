#!/usr/bin/env python3
"""
embed_tweets.py — Replace bare Twitter/X status URLs with embedded tweet images.

For each bare tweet URL found on its own line in a post:
1. Fetch the tweet text, author, and date from the Wayback Machine
2. Generate a screenshot-like image of the tweet
3. Save the image and replace the URL with an <img> tag
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
from collections import defaultdict

# ── Paths ──────────────────────────────────────────────────────────────
POSTS_EN = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
POSTS_ES = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"
IMAGES_DIR = "/Users/floresll/Desktop/iloveepoetry/assets/images/tweets/"

# ── Fonts ──────────────────────────────────────────────────────────────
FONT_BOLD = "/System/Library/Fonts/Helvetica.ttc"
FONT_REGULAR = "/System/Library/Fonts/Helvetica.ttc"

# ── Tweet image dimensions ─────────────────────────────────────────────
IMG_WIDTH = 550
PADDING = 24
TEXT_WIDTH = IMG_WIDTH - (PADDING * 2)

# ── Regex for bare tweet URLs on their own line ────────────────────────
TWEET_URL_RE = re.compile(
    r'^(https?://(?:twitter\.com|x\.com)/(\w+)/status(?:es)?/(\d+))\s*$',
    re.MULTILINE
)

# ── Cache for Wayback CDX lookups ──────────────────────────────────────
wayback_cache = {}


def fetch_wayback_snapshot(tweet_url):
    """Find the best Wayback Machine snapshot for a tweet URL."""
    if tweet_url in wayback_cache:
        return wayback_cache[tweet_url]

    # Normalize URL
    clean_url = tweet_url.replace("https://", "").replace("http://", "")
    cdx_url = (
        f"http://web.archive.org/cdx/search/cdx?"
        f"url={clean_url}&output=json&limit=5"
        f"&fl=timestamp,original,statuscode"
        f"&filter=statuscode:200"
    )

    try:
        req = urllib.request.Request(cdx_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if len(data) > 1:
                # First row is headers, rest are results
                timestamp = data[1][0]
                original = data[1][1]
                result = f"https://web.archive.org/web/{timestamp}/{original}"
                wayback_cache[tweet_url] = result
                return result
    except Exception as e:
        print(f"    CDX error for {tweet_url}: {e}")

    wayback_cache[tweet_url] = None
    return None


def extract_tweet_data(wayback_url):
    """Fetch an archived tweet page and extract text, author display name, handle, and date."""
    try:
        req = urllib.request.Request(wayback_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            page = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    Fetch error: {e}")
        return None

    # Extract tweet text
    tweet_text = None

    # Pattern 1: Modern Twitter (TweetTextSize class)
    m = re.search(
        r'TweetTextSize[^>]*>(.*?)</p>',
        page, re.DOTALL
    )
    if m:
        tweet_text = m.group(1)

    # Pattern 2: Older Twitter (tweet-text class)
    if not tweet_text:
        m = re.search(
            r'class="[^"]*tweet-text[^"]*"[^>]*>(.*?)</p>',
            page, re.DOTALL
        )
        if m:
            tweet_text = m.group(1)

    # Pattern 3: js-tweet-text
    if not tweet_text:
        m = re.search(
            r'class="[^"]*js-tweet-text[^"]*"[^>]*>(.*?)</p>',
            page, re.DOTALL
        )
        if m:
            tweet_text = m.group(1)

    if not tweet_text:
        return None

    # Clean HTML tags from tweet text but preserve link text
    tweet_text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', tweet_text)
    tweet_text = re.sub(r'<[^>]+>', '', tweet_text)
    tweet_text = html.unescape(tweet_text).strip()

    # Extract display name
    display_name = None
    m = re.search(r'class="[^"]*fullname[^"]*"[^>]*>(.*?)<', page, re.DOTALL)
    if m:
        display_name = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()

    # Extract handle
    handle = None
    m = re.search(r'class="[^"]*username[^"]*"[^>]*>.*?@(\w+)', page, re.DOTALL)
    if m:
        handle = m.group(1)

    # Extract timestamp
    tweet_date = None
    m = re.search(r'data-time="(\d+)"', page)
    if m:
        ts = int(m.group(1))
        tweet_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y")

    # Fallback for date
    if not tweet_date:
        m = re.search(r'class="[^"]*_timestamp[^"]*"[^>]*title="([^"]*)"', page)
        if m:
            tweet_date = m.group(1)

    return {
        "text": tweet_text,
        "display_name": display_name,
        "handle": handle,
        "date": tweet_date,
    }


def create_tweet_image(tweet_data, handle_fallback, output_path):
    """Create a screenshot-like image of a tweet."""
    text = tweet_data["text"]
    display_name = tweet_data.get("display_name") or handle_fallback
    handle = tweet_data.get("handle") or handle_fallback
    date = tweet_data.get("date") or ""

    # Load fonts
    try:
        font_name = ImageFont.truetype(FONT_BOLD, 17, index=1)  # Bold
        font_handle = ImageFont.truetype(FONT_REGULAR, 14, index=0)  # Regular
        font_text = ImageFont.truetype(FONT_REGULAR, 16, index=0)
        font_date = ImageFont.truetype(FONT_REGULAR, 13, index=0)
    except Exception:
        font_name = ImageFont.load_default()
        font_handle = font_name
        font_text = font_name
        font_date = font_name

    # Wrap text
    char_width = TEXT_WIDTH // 9  # approx chars per line at 16px
    wrapped_lines = []
    for line in text.split("\n"):
        if line.strip():
            wrapped_lines.extend(textwrap.wrap(line, width=char_width))
        else:
            wrapped_lines.append("")

    # Calculate image height
    line_height_text = 22
    header_height = 55  # name + handle
    text_height = len(wrapped_lines) * line_height_text
    date_height = 35
    total_height = PADDING + header_height + text_height + date_height + PADDING

    # Create image
    img = Image.new("RGB", (IMG_WIDTH, total_height), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    # Draw border
    draw.rectangle(
        [0, 0, IMG_WIDTH - 1, total_height - 1],
        outline="#E1E8ED", width=1
    )

    # Draw left accent bar
    draw.rectangle([0, 0, 3, total_height - 1], fill="#1DA1F2")

    y = PADDING

    # Draw Twitter/X icon (simple text "𝕏")
    try:
        icon_font = ImageFont.truetype(FONT_BOLD, 20, index=1)
    except Exception:
        icon_font = font_name
    draw.text((PADDING, y), "𝕏", fill="#000000", font=icon_font)

    # Draw display name
    draw.text((PADDING + 28, y), display_name, fill="#14171A", font=font_name)

    # Draw handle
    y += 24
    draw.text((PADDING + 28, y), f"@{handle}", fill="#657786", font=font_handle)

    y += 31

    # Draw tweet text
    for line in wrapped_lines:
        draw.text((PADDING, y), line, fill="#14171A", font=font_text)
        y += line_height_text

    # Draw date
    y += 8
    draw.line([(PADDING, y), (IMG_WIDTH - PADDING, y)], fill="#E1E8ED", width=1)
    y += 8
    draw.text((PADDING, y), date, fill="#657786", font=font_date)

    # Save
    img.save(output_path, "PNG", optimize=True)
    return total_height


def process_posts():
    """Process all post files and replace bare tweet URLs with embedded images."""
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Collect all files with bare tweet URLs
    all_files = []
    for lang_dir in [POSTS_EN, POSTS_ES]:
        for fname in sorted(os.listdir(lang_dir)):
            fpath = os.path.join(lang_dir, fname)
            if os.path.isfile(fpath) and fname.endswith(".html"):
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                matches = TWEET_URL_RE.findall(content)
                if matches:
                    lang = "en" if lang_dir == POSTS_EN else "es"
                    all_files.append((fpath, fname, lang, matches))

    total_tweets = sum(len(m) for _, _, _, m in all_files)
    print(f"Found {total_tweets} bare tweet URLs across {len(all_files)} files")
    print("=" * 60)

    stats = {
        "fetched": 0,
        "no_archive": 0,
        "no_text": 0,
        "images_created": 0,
        "files_updated": 0,
    }

    processed_tweets = {}  # url → (image_path, alt_text) to avoid re-fetching duplicates

    for fpath, fname, lang, matches in all_files:
        print(f"\n--- {lang}/{fname} ({len(matches)} tweets) ---")

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        modified = False

        for tweet_url, handle, status_id in matches:
            # Check if we already processed this tweet (EN/ES duplicate)
            if tweet_url in processed_tweets:
                img_rel_path, alt_text = processed_tweets[tweet_url]
                replacement = f'<br><br>\n<img src="{{{{ "{img_rel_path}" | relative_url }}}}" alt="{alt_text}" style="max-width:550px; width:100%;" loading="lazy">\n'
                content = content.replace(tweet_url, replacement.strip(), 1)
                modified = True
                print(f"  ✓ Reused: @{handle}/status/{status_id}")
                continue

            print(f"  Fetching: @{handle}/status/{status_id}...", end=" ", flush=True)

            # Step 1: Find Wayback snapshot
            wayback_url = fetch_wayback_snapshot(tweet_url)
            if not wayback_url:
                # Try x.com variant
                alt_url = tweet_url.replace("twitter.com", "x.com")
                wayback_url = fetch_wayback_snapshot(alt_url)

            if not wayback_url:
                print("NO ARCHIVE")
                stats["no_archive"] += 1
                # Create a simple text-based fallback
                img_filename = f"tweet_{handle}_{status_id}.png"
                img_path = os.path.join(IMAGES_DIR, img_filename)
                img_rel_path = f"/assets/images/tweets/{img_filename}"

                fallback_data = {
                    "text": "[Tweet no longer available]",
                    "display_name": handle,
                    "handle": handle,
                    "date": "",
                }
                create_tweet_image(fallback_data, handle, img_path)
                alt_text = f"Tweet by @{handle} (no longer available)"
                processed_tweets[tweet_url] = (img_rel_path, alt_text)

                replacement = f'<br><br>\n<img src="{{{{ "{img_rel_path}" | relative_url }}}}" alt="{alt_text}" style="max-width:550px; width:100%;" loading="lazy">\n'
                content = content.replace(tweet_url, replacement.strip(), 1)
                modified = True
                stats["images_created"] += 1
                continue

            # Step 2: Extract tweet data
            tweet_data = extract_tweet_data(wayback_url)
            time.sleep(0.5)  # Rate limiting

            if not tweet_data or not tweet_data.get("text"):
                print("NO TEXT FOUND")
                stats["no_text"] += 1
                # Fallback
                img_filename = f"tweet_{handle}_{status_id}.png"
                img_path = os.path.join(IMAGES_DIR, img_filename)
                img_rel_path = f"/assets/images/tweets/{img_filename}"

                fallback_data = {
                    "text": "[Tweet content could not be retrieved]",
                    "display_name": handle,
                    "handle": handle,
                    "date": "",
                }
                create_tweet_image(fallback_data, handle, img_path)
                alt_text = f"Tweet by @{handle} (content could not be retrieved)"
                processed_tweets[tweet_url] = (img_rel_path, alt_text)

                replacement = f'<br><br>\n<img src="{{{{ "{img_rel_path}" | relative_url }}}}" alt="{alt_text}" style="max-width:550px; width:100%;" loading="lazy">\n'
                content = content.replace(tweet_url, replacement.strip(), 1)
                modified = True
                stats["images_created"] += 1
                continue

            # Step 3: Create image
            img_filename = f"tweet_{handle}_{status_id}.png"
            img_path = os.path.join(IMAGES_DIR, img_filename)
            img_rel_path = f"/assets/images/tweets/{img_filename}"

            create_tweet_image(tweet_data, handle, img_path)
            stats["fetched"] += 1
            stats["images_created"] += 1

            # Alt text = tweet text as citation
            safe_text = tweet_data["text"].replace('"', '&quot;')
            display = tweet_data.get("display_name") or handle
            date_str = f" on {tweet_data['date']}" if tweet_data.get("date") else ""
            alt_text = f"Tweet by @{handle} ({display}){date_str}: {safe_text}"
            # Truncate alt text if too long
            if len(alt_text) > 500:
                alt_text = alt_text[:497] + "..."

            processed_tweets[tweet_url] = (img_rel_path, alt_text)

            replacement = f'<br><br>\n<img src="{{{{ "{img_rel_path}" | relative_url }}}}" alt="{alt_text}" style="max-width:550px; width:100%;" loading="lazy">\n'
            content = content.replace(tweet_url, replacement.strip(), 1)
            modified = True

            print(f"OK ({len(tweet_data['text'])} chars)")

        if modified:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            stats["files_updated"] += 1
            print(f"  → File updated")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total tweets processed: {total_tweets}")
    print(f"  Successfully fetched: {stats['fetched']}")
    print(f"  No archive found:     {stats['no_archive']}")
    print(f"  No text extracted:    {stats['no_text']}")
    print(f"  Images created:       {stats['images_created']}")
    print(f"  Files updated:        {stats['files_updated']}")
    print(f"  Unique tweets cached: {len(processed_tweets)}")


if __name__ == "__main__":
    process_posts()
