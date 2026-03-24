#!/usr/bin/env python3
"""Final comprehensive fix for ALL remaining iloveepoetry.org links."""
import os
import re
from urllib.parse import unquote
from collections import defaultdict

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"

# Build complete mapping
id_to_pages = defaultdict(list)
slug_to_pages = defaultdict(list)

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
                    id_to_pages[wm.group(1)].append((pl, lang))
                slug = pl.rstrip('/').split('/')[-1]
                if slug:
                    slug_to_pages[slug].append((pl, lang))

print(f"Total WP IDs mapped: {len(id_to_pages)}")

def get_permalink(pid, file_lang):
    if pid not in id_to_pages:
        return None
    entries = id_to_pages[pid]
    for pl, lang in entries:
        if lang == file_lang:
            return pl
    return entries[0][0]

def find_by_slug(slug, file_lang):
    decoded = unquote(slug)
    if decoded in slug_to_pages:
        for pl, lang in slug_to_pages[decoded]:
            if lang == file_lang:
                return pl
        return slug_to_pages[decoded][0][0]
    return None

counters = {'resolved': 0, 'stripped': 0}
files_modified = 0

for d in [os.path.join(BASE_DIR, "_posts"), os.path.join(BASE_DIR, "_pages")]:
    for root, dirs, fnames in os.walk(d):
        for f in fnames:
            if not f.endswith('.html'): continue
            fp = os.path.join(root, f)
            with open(fp, 'r', encoding='utf-8') as fh:
                content = fh.read()
            
            if 'iloveepoetry.org' not in content:
                continue
            
            lm = re.search(r'^lang:\s*["\']?(\w+)', content, re.MULTILINE)
            file_lang = lm.group(1) if lm else 'en'
            
            parts = content.split('---', 2)
            if len(parts) < 3:
                continue
            body = parts[2]
            original = body
            
            # Step 1: Resolve ?page_id= and ?p= links
            def resolve_id_link(m):
                href = m.group(1)
                pid_match = re.search(r'[?&](?:page_id|p)=(\d+)', href)
                if not pid_match:
                    return m.group(0)
                pid = pid_match.group(1)
                pl = get_permalink(pid, file_lang)
                if pl:
                    counters['resolved'] += 1
                    return 'href="{{ "' + pl + '" | relative_url }}"'
                return m.group(0)
            
            body = re.sub(r'href="([^"]*iloveepoetry\.org[^"]*(?:page_id|[?&]p)=\d+[^"]*)"', resolve_id_link, body)
            
            # Step 2: Resolve bare homepage links
            body = re.sub(
                r'href="https?://iloveepoetry\.org/?"',
                lambda m: 'href="{{ "/' + file_lang + '/" | relative_url }}"',
                body
            )
            if 'href="{{ "/' in body and 'href="{{ "/' not in original:
                counters['resolved'] += body.count('relative_url') - original.count('relative_url')
            
            # Step 3: Resolve wp-content links (PDFs)
            def resolve_wp_content(m):
                href = m.group(1)
                path_match = re.search(r'/wp-content/uploads/(.+)', href)
                if path_match:
                    counters['resolved'] += 1
                    return 'href="{{ "/assets/images/wp-content/uploads/' + path_match.group(1) + '" | relative_url }}"'
                return m.group(0)
            body = re.sub(r'href="([^"]*iloveepoetry\.org[^"]*/wp-content/[^"]*)"', resolve_wp_content, body)
            
            # Step 4: Resolve path-based slug links
            def resolve_slug_link(m):
                href = m.group(1)
                if '?' in href or '/wp-content/' in href or '/wp-admin' in href or '/viz/' in href:
                    return m.group(0)
                parsed_path = re.search(r'iloveepoetry\.org(/[^"\'?#]+)', href)
                if parsed_path:
                    path = unquote(parsed_path.group(1)).rstrip('/')
                    slug = path.split('/')[-1]
                    if slug:
                        pl = find_by_slug(slug, file_lang)
                        if pl:
                            counters['resolved'] += 1
                            return 'href="{{ "' + pl + '" | relative_url }}"'
                return m.group(0)
            body = re.sub(r'href="([^"]*iloveepoetry\.org/[^"?]+)"', resolve_slug_link, body)
            
            # Step 5: Strip unresolvable links (replace <a> with inner text)
            strip_patterns = [
                r'iloveepoetry\.org[^"\']*[?&]cat=',
                r'iloveepoetry\.org[^"\']*[?&]tag=',
                r'iloveepoetry\.org[^"\']*[?&]s=',
                r'iloveepoetry\.org[^"\']*[?&]author=',
                r'iloveepoetry\.org[^"\']*[?&]m=',
                r'iloveepoetry\.org[^"\']*wp-admin',
                r'iloveepoetry\.org[^"\']*viz/',
                r'iloveepoetry\.org[^"\']*page_id=',  # remaining unresolved page_ids
            ]
            for pat in strip_patterns:
                regex = r'<a\s+[^>]*href=["\'][^"\']*' + pat + r'[^"\']*["\'][^>]*>(.*?)</a>'
                new_body = re.sub(regex, r'\1', body, flags=re.DOTALL)
                if new_body != body:
                    counters['stripped'] += len(re.findall(regex, body, re.DOTALL))
                    body = new_body
            
            if body != original:
                new_content = parts[0] + '---' + parts[1] + '---' + body
                with open(fp, 'w', encoding='utf-8') as fh:
                    fh.write(new_content)
                files_modified += 1

print(f"\nFiles modified: {files_modified}")
print(f"Links resolved: {counters['resolved']}")
print(f"Links stripped: {counters['stripped']}")

# Verify
remaining = 0
samples = []
for d in [os.path.join(BASE_DIR, "_posts"), os.path.join(BASE_DIR, "_pages")]:
    for root, dirs, fnames in os.walk(d):
        for f in fnames:
            if not f.endswith('.html'): continue
            fp = os.path.join(root, f)
            with open(fp, 'r', encoding='utf-8') as fh:
                body = fh.read().split('---', 2)
            body = body[2] if len(body) >= 3 else body[0]
            for m in re.finditer(r'href=["\']([^"\']*iloveepoetry\.org[^"\']*)["\']', body):
                remaining += 1
                if remaining <= 10:
                    samples.append((os.path.relpath(fp, BASE_DIR), m.group(1)))

print(f"Remaining: {remaining}")
for f, h in samples:
    print(f"  {f}: {h}")
