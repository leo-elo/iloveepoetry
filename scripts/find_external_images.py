#!/usr/bin/env python3
"""Find all posts with external (http/https) featured_image URLs."""
import os
import re

external = {}
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
        m = re.search(r'featured_image:\s*["\']([^"\']+)["\']', parts[1])
        if not m:
            continue
        img = m.group(1).strip()
        if img.startswith('http'):
            if img not in external:
                external[img] = []
            external[img].append(f'{lang_dir}/{fn}')

print(f'Total unique external featured image URLs: {len(external)}')
total_posts = sum(len(v) for v in external.values())
print(f'Total posts affected: {total_posts}')
print()
for url, files in sorted(external.items()):
    print(f'{url} ({len(files)} posts)')
    for f in files[:3]:
        print(f'  - {f}')
    if len(files) > 3:
        print(f'  ... +{len(files)-3} more')
