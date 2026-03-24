#!/usr/bin/env python3
"""Check /iloveepoetry/ prefixed links against known permalinks."""
import os
import re
from urllib.parse import unquote

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"

# Build permalink set
permalink_set = set()
for root, dirs, fnames in os.walk(os.path.join(BASE_DIR, "_posts")):
    for f in fnames:
        if not f.endswith('.html'): continue
        with open(os.path.join(root, f), 'r', encoding='utf-8') as fh:
            content = fh.read()
        m = re.search(r'^permalink:\s*["\']?(/[^\s"\']+)', content, re.MULTILINE)
        if m:
            permalink_set.add(unquote(m.group(1)))

for root, dirs, fnames in os.walk(os.path.join(BASE_DIR, "_pages")):
    for f in fnames:
        if not f.endswith('.html'): continue
        with open(os.path.join(root, f), 'r', encoding='utf-8') as fh:
            content = fh.read()
        m = re.search(r'^permalink:\s*["\']?(/[^\s"\']+)', content, re.MULTILINE)
        if m:
            permalink_set.add(unquote(m.group(1)))

print(f"Permalink set: {len(permalink_set)} entries")

# Find all /iloveepoetry/ links
broken = []
total_links = 0
for root, dirs, fnames in os.walk(BASE_DIR):
    if '/_site/' in root or '/.git/' in root or '/scripts/' in root:
        continue
    for f in fnames:
        if not f.endswith('.html'): continue
        fp = os.path.join(root, f)
        with open(fp, 'r', encoding='utf-8') as fh:
            content = fh.read()
        
        # Split off front matter
        parts = content.split('---', 2)
        body = parts[2] if len(parts) >= 3 else content
        
        for m in re.finditer(r'href=["\'](/iloveepoetry/(?:en|es)/[^"\'#]+)["\']', body):
            href = unquote(m.group(1))
            total_links += 1
            # Remove /iloveepoetry prefix to get permalink
            pl = href.replace('/iloveepoetry', '')
            # Ensure trailing slash
            if not pl.endswith('/') and '.' not in pl.split('/')[-1]:
                pl += '/'
            
            if pl not in permalink_set:
                # Check without trailing slash
                if pl.rstrip('/') not in permalink_set:
                    slug = pl.rstrip('/').split('/')[-1]
                    matches = [p for p in permalink_set if slug in p][:3]
                    broken.append({
                        'file': os.path.relpath(fp, BASE_DIR),
                        'href': href,
                        'permalink': pl,
                        'matches': matches
                    })

print(f"Total /iloveepoetry/ links checked: {total_links}")
print(f"Broken: {len(broken)}")
for b in broken:
    print(f"\n  File: {b['file']}")
    print(f"  Link: {b['href']}")
    print(f"  Permalink: {b['permalink']}")
    if b['matches']:
        print(f"  Possible: {b['matches']}")
