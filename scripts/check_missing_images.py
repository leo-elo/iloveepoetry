#!/usr/bin/env python3
"""Check for missing featured images and body images."""
import os, re

missing_featured = []
missing_body = []
total_featured = 0

for lang in ['en', 'es']:
    dir_path = f'_posts/{lang}'
    for fn in sorted(os.listdir(dir_path)):
        if not fn.endswith('.html'):
            continue
        fp = os.path.join(dir_path, fn)
        with open(fp) as f:
            content = f.read()

        # Split front matter and body
        parts = content.split('---', 2)
        if len(parts) < 3:
            continue
        fm = parts[1]
        body = parts[2]

        # Check featured_image
        m = re.search(r'^featured_image:\s*"?(.*?)"?\s*$', fm, re.MULTILINE)
        if m:
            total_featured += 1
            img_path = m.group(1).strip().strip('"').strip("'")
            if img_path.startswith('http'):
                continue  # external URL, skip
            if img_path.startswith('/'):
                disk_path = '.' + img_path
            else:
                disk_path = img_path
            if not os.path.exists(disk_path):
                missing_featured.append((fp, img_path))

        # Check body images
        for img_match in re.finditer(r'src="([^"]*)"', body):
            src = img_match.group(1)
            # Skip external URLs and liquid template tags
            if src.startswith('http') or '{{' in src:
                continue
            if src.startswith('/'):
                disk_path = '.' + src
            else:
                disk_path = src
            if not os.path.exists(disk_path):
                missing_body.append((fp, src))

print(f"Total featured images: {total_featured}")
print(f"Missing featured images: {len(missing_featured)}")
for fp, img in missing_featured:
    print(f"  {img}")
    print(f"    in: {fp}")

print(f"\nMissing body images: {len(missing_body)}")
for fp, img in missing_body[:30]:
    print(f"  {img}")
    print(f"    in: {fp}")
