#!/usr/bin/env python3
"""Find all missing body images (inside post HTML) across all posts."""
import os
import re

missing = []
for lang_dir in ['en', 'es']:
    dir_path = f'_posts/{lang_dir}'
    for fn in sorted(os.listdir(dir_path)):
        if not fn.endswith('.html'):
            continue
        fp = os.path.join(dir_path, fn)
        with open(fp, 'r') as f:
            content = f.read()
        parts = content.split('---', 2)
        if len(parts) < 3:
            continue
        body = parts[2]

        # Find all img src attributes in body
        for m in re.finditer(r'<img[^>]*\bsrc=["\']([^"\']+)["\']', body):
            src = m.group(1)
            # Skip external URLs
            if src.startswith('http://') or src.startswith('https://') or src.startswith('//'):
                continue
            # Skip Liquid template tags
            if '{{' in src:
                continue
            # Normalize path
            local_path = src.lstrip('/')
            if not os.path.exists(local_path):
                missing.append((lang_dir, fn, src))

        # Also find a href to images in body
        for m in re.finditer(r'<a[^>]*\bhref=["\']([^"\']+\.(?:png|jpg|jpeg|gif|webp|svg))["\']', body, re.I):
            href = m.group(1)
            if href.startswith('http://') or href.startswith('https://') or href.startswith('//'):
                continue
            if '{{' in href:
                continue
            local_path = href.lstrip('/')
            if not os.path.exists(local_path):
                missing.append((lang_dir, fn, href))

# Deduplicate
unique_images = {}
for lang, fn, img in missing:
    if img not in unique_images:
        unique_images[img] = []
    unique_images[img].append((lang, fn))

print(f'Total missing body image references: {len(missing)}')
print(f'Unique missing image paths: {len(unique_images)}')
for img, files in sorted(unique_images.items()):
    print(f'  {img} ({len(files)} refs)')
    for lang, fn in files[:3]:
        print(f'    - {lang}/{fn}')
    if len(files) > 3:
        print(f'    ... and {len(files)-3} more')
