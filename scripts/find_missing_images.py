#!/usr/bin/env python3
"""Find all missing featured images across all posts."""
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
        fm = parts[1]
        m = re.search(r'featured_image:\s*["\']([^"\']+)["\']', fm)
        if not m:
            m = re.search(r'featured_image:\s*(\S+)', fm)
        if not m:
            continue
        img_path = m.group(1).strip()
        if not img_path or img_path.startswith('http'):
            continue
        local_path = img_path.lstrip('/')
        if not os.path.exists(local_path):
            missing.append((lang_dir, fn, img_path))

print(f'Total missing featured images: {len(missing)}')
unique_images = {}
for lang, fn, img in missing:
    if img not in unique_images:
        unique_images[img] = []
    unique_images[img].append((lang, fn))

print(f'Unique missing image paths: {len(unique_images)}')
for img, files in sorted(unique_images.items()):
    print(f'  {img} ({len(files)} posts)')
    for lang, fn in files:
        print(f'    - {lang}/{fn}')
