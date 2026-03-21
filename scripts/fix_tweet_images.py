#!/usr/bin/env python3
"""
fix_tweet_images.py — Regenerate all tweet card images with Twitter bird logo,
and add line breaks after every tweet image in posts.
"""

import os
import re
import textwrap
from PIL import Image, ImageDraw, ImageFont

POSTS_EN = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
POSTS_ES = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"
IMAGES_DIR = "/Users/floresll/Desktop/iloveepoetry/assets/images/tweets/"
TWITTER_ICON = "/Users/floresll/Desktop/iloveepoetry/assets/images/twitter_icon.png"

FONT_BOLD = "/System/Library/Fonts/Helvetica.ttc"
FONT_REGULAR = "/System/Library/Fonts/Helvetica.ttc"
IMG_WIDTH = 550
PADDING = 24
TEXT_WIDTH = IMG_WIDTH - (PADDING * 2)


def create_tweet_image(text, display_name, handle, date, output_path, icon):
    """Create a tweet card image with Twitter bird logo."""
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
    if not wrapped_lines:
        wrapped_lines = [""]

    line_height_text = 22
    header_height = 55
    text_height = len(wrapped_lines) * line_height_text
    date_height = 35
    total_height = PADDING + header_height + text_height + date_height + PADDING

    img = Image.new("RGB", (IMG_WIDTH, total_height), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    # Border and accent bar
    draw.rectangle([0, 0, IMG_WIDTH - 1, total_height - 1], outline="#E1E8ED", width=1)
    draw.rectangle([0, 0, 3, total_height - 1], fill="#1DA1F2")

    y = PADDING

    # Paste Twitter bird icon (scaled to 22px)
    icon_size = 22
    icon_resized = icon.resize((icon_size, icon_size), Image.LANCZOS)
    # Paste with alpha mask
    img.paste(icon_resized, (PADDING, y), icon_resized)

    # Display name
    draw.text((PADDING + icon_size + 8, y + 1), display_name, fill="#14171A", font=font_name)
    y += 24

    # Handle
    draw.text((PADDING + icon_size + 8, y), f"@{handle}", fill="#657786", font=font_handle)
    y += 31

    # Tweet text
    for line in wrapped_lines:
        draw.text((PADDING, y), line, fill="#14171A", font=font_text)
        y += line_height_text

    # Separator and date
    y += 8
    draw.line([(PADDING, y), (IMG_WIDTH - PADDING, y)], fill="#E1E8ED", width=1)
    y += 8
    draw.text((PADDING, y), date, fill="#657786", font=font_date)

    img.save(output_path, "PNG", optimize=True)


def extract_info_from_image(fpath):
    """Try to determine if an image has real text or is a fallback by file size."""
    return os.path.getsize(fpath)


def main():
    # Load Twitter icon
    icon = Image.open(TWITTER_ICON).convert("RGBA")

    # Step 1: Read all post files to find tweet image references and their alt text
    # This lets us extract the tweet text from alt attributes
    tweet_data = {}  # filename -> {text, display_name, handle, date}

    for lang_dir in [POSTS_EN, POSTS_ES]:
        for fname in os.listdir(lang_dir):
            fpath = os.path.join(lang_dir, fname)
            if not os.path.isfile(fpath) or not fname.endswith(".html"):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()

            # Find all tweet image references
            for m in re.finditer(
                r'<img[^>]*src="[^"]*(/assets/images/tweets/(tweet_[^"]+\.png))"[^>]*alt="([^"]*)"',
                content
            ):
                img_filename = m.group(2)
                alt_text = m.group(3)

                if img_filename in tweet_data:
                    continue

                # Parse alt text: "Tweet by @handle (Display Name) on Date: Text"
                alt_match = re.match(
                    r'Tweet by @(\w+)\s*\(([^)]*)\)(?:\s*on\s+([^:]+))?\s*:\s*(.*)',
                    alt_text, re.DOTALL
                )
                if alt_match:
                    handle = alt_match.group(1)
                    display_name = alt_match.group(2)
                    date = (alt_match.group(3) or "").strip()
                    text = alt_match.group(4).replace("&quot;", '"').strip()
                    tweet_data[img_filename] = {
                        "text": text,
                        "display_name": display_name,
                        "handle": handle,
                        "date": date,
                    }
                else:
                    # Fallback parsing: "Tweet by @handle (reason)"
                    alt_match2 = re.match(r'Tweet by @(\w+)\s*\(([^)]*)\)', alt_text)
                    if alt_match2:
                        handle = alt_match2.group(1)
                        reason = alt_match2.group(2)
                        tweet_data[img_filename] = {
                            "text": f"[{reason}]" if "no longer" in reason or "could not" in reason else reason,
                            "display_name": handle,
                            "handle": handle,
                            "date": "",
                        }

    print(f"Found tweet data for {len(tweet_data)} images from post alt text")

    # Step 2: Also handle images not referenced in posts (unlikely but just in case)
    for fname in sorted(os.listdir(IMAGES_DIR)):
        if not fname.startswith("tweet_") or not fname.endswith(".png"):
            continue
        if fname in tweet_data:
            continue
        # Parse handle from filename
        m = re.match(r"tweet_(.+)_(\d+)\.png", fname)
        if m:
            handle = m.group(1)
            tweet_data[fname] = {
                "text": "[Tweet no longer available]",
                "display_name": handle,
                "handle": handle,
                "date": "",
            }

    # Step 3: Regenerate all images with Twitter bird logo
    print(f"\nRegenerating {len(tweet_data)} tweet images with Twitter bird logo...")
    for fname, data in sorted(tweet_data.items()):
        fpath = os.path.join(IMAGES_DIR, fname)
        create_tweet_image(
            data["text"],
            data["display_name"],
            data["handle"],
            data["date"],
            fpath,
            icon
        )
    print(f"  Done: {len(tweet_data)} images regenerated")

    # Step 4: Add line break after every tweet image in posts
    print("\nAdding line breaks after tweet images in posts...")
    files_updated = 0
    for lang_dir in [POSTS_EN, POSTS_ES]:
        for fname in sorted(os.listdir(lang_dir)):
            fpath = os.path.join(lang_dir, fname)
            if not os.path.isfile(fpath) or not fname.endswith(".html"):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()

            if "/assets/images/tweets/" not in content:
                continue

            # Add <br> after tweet images if not already present
            # Pattern: <img ...tweets/...> not followed by <br>
            new_content = re.sub(
                r'(<img[^>]*/assets/images/tweets/[^>]*>)\s*(?!<br)',
                r'\1\n<br>\n',
                content
            )

            if new_content != content:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                files_updated += 1

    print(f"  Done: {files_updated} files updated with line breaks")


if __name__ == "__main__":
    main()
