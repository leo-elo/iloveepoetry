#!/usr/bin/env python3
"""Comprehensive fix for ALL remaining iloveepoetry.org links."""
import os
import re
from urllib.parse import unquote, urlparse, parse_qs
from collections import defaultdict

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"

# Build wp_post_id -> permalink map
wp_id_to_permalink = {}
slug_to_permalinks = defaultdict(list)

for d in [os.path.join(BASE_DIR, "_posts"), os.path.join(BASE_DIR, "_pages")]:
    for root, dirs, fnames in os.walk(d):
        for f in fnames:
            if not f.endswith('.html'): continue
            fp = os.path.join(root, f)
            with open(fp, 'r', encoding='utf-8') as fh:
                content = fh.read()
            pm = re.search(r'^permalink:\s*["\']?(/[^\s"\']+)', content, re.MULTILINE)
            wm = re.search(r'^wp_post_id:\s*(\d+)', content, re.MULTILINE)
            lm = re.search(r'^lang:\s*["\']?(\w+)', content, re.MULTILINE)
            if pm:
                pl = unquote(pm.group(1))
                lang = lm.group(1) if lm else 'en'
                if wm:
                    wp_id_to_permalink[wm.group(1)] = (pl, lang)
                slug = pl.rstrip('/').split('/')[-1]
                if slug:
                    slug_to_permalinks[slug].append((pl, lang))

print(f"Index: {len(wp_id_to_permalink)} WP IDs, {len(slug_to_permalinks)} slugs")

def resolve_href(href, file_lang):
    """Try to resolve an old WP link. Returns new href or None to strip."""
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    path = unquote(parsed.path).rstrip('/')
    
    # ?p=ID or ?page_id=ID
    for key in ['p', 'page_id']:
        if key in query:
            pid = query[key][0].rstrip('\\')
            if pid in wp_id_to_permalink:
                pl, _ = wp_id_to_permalink[pid]
                return pl
            return None  # Strip - unknown ID
    
    # ?cat=, ?tag=, ?s=, ?author=, ?m= - no equivalent
    for key in ['cat', 'tag', 's', 'author', 'm']:
        if key in query:
            return None
    
    # /wp-admin/ - strip
    if '/wp-admin' in path:
        return None
    
    # Bare iloveepoetry.org -> homepage
    if path in ['', '/']:
        if file_lang == 'es':
            return '/es/'
        return '/en/'
    
    # /viz/ paths - visualizations, no equivalent
    if '/viz/' in path:
        return None
    
    # /uncategorized/slug/ -> try to find by slug
    if '/uncategorized/' in path:
        slug = path.rstrip('/').split('/')[-1]
        if slug in slug_to_permalinks:
            for pl, lang in slug_to_permalinks[slug]:
                if lang == file_lang:
                    return pl
            return slug_to_permalinks[slug][0][0]
    
    # /wp-content/ -> skip (image link)
    if '/wp-content/' in path:
        return "SKIP"
    
    # Generic path -> try slug match
    slug = path.rstrip('/').split('/')[-1]
    if slug and slug in slug_to_permalinks:
        for pl, lang in slug_to_permalinks[slug]:
            if lang == file_lang:
                return pl
        return slug_to_permalinks[slug][0][0]
    
    return None

files_modified = 0
total_resolved = 0
total_stripped = 0

for d in [os.path.join(BASE_DIR, "_posts"), os.path.join(BASE_DIR, "_pages")]:
    for root, dirs, fnames in os.walk(d):
        for f in fnames:
            if not f.endswith('.html'): continue
            fp = os.path.join(root, f)
            with open(fp, 'r', encoding='utf-8') as fh:
                content = fh.read()
            
            if 'iloveepoetry.org' not in content and 'iloveepoetry.com' not in content:
                continue
            
            # Get file language
            lm = re.search(r'^lang:\s*["\']?(\w+)', content, re.MULTILINE)
            file_lang = lm.group(1) if lm else 'en'
            
            # Split front matter and body
            parts = content.split('---', 2)
            if len(parts) < 3:
                continue
            body = parts[2]
            original_body = body
            
            # Collect all links to process
            links_to_resolve = []
            links_to_strip = []
            
            for m in re.finditer(r'href=["\']([^"\']*(?:iloveepoetry\.org|iloveepoetry\.com)[^"\']*)["\']', body):
                href = m.group(1)
                result = resolve_href(href, file_lang)
                if result == "SKIP":
                    continue
                elif result is None:
                    links_to_strip.append(href)
                else:
                    links_to_resolve.append((href, result))
            
            modified = False
            
            # Resolve links
            for old_href, new_pl in links_to_resolve:
                escaped = re.escape(old_href)
                new_href = '{{ "' + new_pl + '" | relative_url }}'
                body = re.sub(r'href=["\']' + escaped + r'["\']', f'href="{new_href}"', body)
                total_resolved += 1
                modified = True
            
            # Strip links (replace <a>...</a> with just inner text)
            for href in links_to_strip:
                escaped = re.escape(href)
                pattern = r'<a\s+[^>]*href=["\']' + escaped + r'["\'][^>]*>(.*?)</a>'
                new_body = re.sub(pattern, r'\1', body, flags=re.DOTALL)
                if new_body != body:
                    body = new_body
                    total_stripped += 1
                    modified = True
            
            if modified:
                new_content = parts[0] + '---' + parts[1] + '---' + body
                with open(fp, 'w', encoding='utf-8') as fh:
                    fh.write(new_content)
                files_modified += 1

print(f"\nFiles modified: {files_modified}")
print(f"Links resolved: {total_resolved}")
print(f"Links stripped: {total_stripped}")

# Verify: count remaining
remaining = 0
for d in [os.path.join(BASE_DIR, "_posts"), os.path.join(BASE_DIR, "_pages")]:
    for root, dirs, fnames in os.walk(d):
        for f in fnames:
            if not f.endswith('.html'): continue
            fp = os.path.join(root, f)
            with open(fp, 'r', encoding='utf-8') as fh:
                content = fh.read()
            parts = content.split('---', 2)
            body = parts[2] if len(parts) >= 3 else content
            hrefs = re.findall(r'href=["\'][^"\']*iloveepoetry\.org[^"\']*["\']', body)
            remaining += len(hrefs)

print(f"Remaining iloveepoetry.org href links: {remaining}")
