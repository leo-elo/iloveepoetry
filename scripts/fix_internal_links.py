#!/usr/bin/env python3
"""Fix all internal links across the site."""

import os
import re
import json
from urllib.parse import unquote, urlparse, parse_qs
from collections import defaultdict

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"
POSTS_DIR = os.path.join(BASE_DIR, "_posts")
PAGES_DIR = os.path.join(BASE_DIR, "_pages")

def get_all_files():
    files = []
    for d in [POSTS_DIR, PAGES_DIR]:
        for root, dirs, fnames in os.walk(d):
            for f in fnames:
                if f.endswith('.html'):
                    files.append(os.path.join(root, f))
    return files

def parse_front_matter(content):
    """Parse YAML front matter, return (front_matter_dict, body)."""
    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content
    front = parts[1]
    body = parts[2]
    
    fm = {}
    for line in front.split('\n'):
        m = re.match(r'^(\w[\w_]*):\s*(.+)$', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip('"').strip("'")
            fm[key] = val
    return fm, body

def build_indexes(files):
    """Build lookup indexes."""
    permalink_set = set()
    wp_id_to_permalink = {}
    slug_to_permalinks = defaultdict(list)
    
    for f in files:
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
        fm, _ = parse_front_matter(content)
        
        pl = fm.get('permalink', '')
        if pl:
            pl_decoded = unquote(pl)
            permalink_set.add(pl_decoded)
            
            # wp_post_id mapping
            wp_id = fm.get('wp_post_id', '')
            if wp_id:
                wp_id_to_permalink[wp_id] = pl_decoded
            
            # slug mapping (last part of permalink)
            slug = pl_decoded.rstrip('/').split('/')[-1]
            if slug:
                slug_to_permalinks[slug].append(pl_decoded)
    
    return permalink_set, wp_id_to_permalink, slug_to_permalinks

def resolve_wp_link(href, wp_id_to_permalink, slug_to_permalinks, file_lang):
    """Resolve an old iloveepoetry.org link to a new permalink."""
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    path = unquote(parsed.path).rstrip('/')
    
    # ?p=ID or ?page_id=ID
    for key in ['p', 'page_id']:
        if key in query:
            pid = query[key][0]
            if pid in wp_id_to_permalink:
                return wp_id_to_permalink[pid]
    
    # ?cat=ID, ?tag=X, ?s=X, ?author=X, ?m=X - no direct equivalent
    # These should be removed (keep text, strip link)
    for key in ['cat', 'tag', 's', 'author', 'm']:
        if key in query:
            return None  # Signal to strip the link
    
    # /wp-admin/ links
    if '/wp-admin' in path:
        return None  # Strip
    
    # Path-based: try to find matching slug
    if path and path != '/':
        # Remove leading slash
        path_parts = path.strip('/').split('/')
        slug = path_parts[-1]
        
        if slug in slug_to_permalinks:
            matches = slug_to_permalinks[slug]
            # Prefer same language
            lang_prefix = f'/{file_lang}/' if file_lang else '/en/'
            for m in matches:
                if m.startswith(lang_prefix):
                    return m
            return matches[0]
    
    return "UNRESOLVED"

def fix_file(filepath, wp_id_to_permalink, slug_to_permalinks, permalink_set):
    """Fix all internal links in a file. Returns (modified_content, changes_list)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    fm, _ = parse_front_matter(content)
    file_lang = fm.get('lang', 'en')
    
    changes = []
    
    # Split into front matter and body
    parts = content.split('---', 2)
    if len(parts) < 3:
        return content, []
    
    body = parts[2]
    original_body = body
    
    # Find all href links to iloveepoetry.org/com or localhost
    def replace_link(match):
        full_match = match.group(0)
        href = match.group(1)
        
        if not ('iloveepoetry.org' in href or 'iloveepoetry.com' in href or 'localhost' in href):
            return full_match
        
        # Skip asset links
        if '/wp-content/uploads/' in href and '/assets/' not in href:
            # These image links might need fixing too but handle separately
            return full_match
        
        resolved = resolve_wp_link(href, wp_id_to_permalink, slug_to_permalinks, file_lang)
        
        if resolved is None:
            # Strip link: we need to handle this differently
            changes.append(('strip', href))
            return full_match  # Will handle in second pass
        elif resolved == "UNRESOLVED":
            changes.append(('unresolved', href))
            return full_match
        else:
            changes.append(('fix', href, resolved))
            new_href = '{{ "' + resolved + '" | relative_url }}'
            return f'href="{new_href}"'
    
    # First pass: replace resolvable links
    body = re.sub(r'href="([^"]*(?:iloveepoetry\.org|iloveepoetry\.com|localhost)[^"]*)"', replace_link, body)
    body = re.sub(r"href='([^']*(?:iloveepoetry\.org|iloveepoetry\.com|localhost)[^']*)'", replace_link, body)
    
    # Second pass: strip unreachable links (keep text, remove <a> tag)
    def strip_links(body_text):
        stripped = []
        for change in changes:
            if change[0] == 'strip':
                href = re.escape(change[1])
                # Replace <a href="...">text</a> with just text
                pattern = r'<a\s+[^>]*href=["\']' + href + r'["\'][^>]*>(.*?)</a>'
                body_text = re.sub(pattern, r'\1', body_text, flags=re.DOTALL)
                stripped.append(change[1])
        return body_text, stripped
    
    body, stripped = strip_links(body)
    
    if body != original_body:
        new_content = parts[0] + '---' + parts[1] + '---' + body
        return new_content, changes
    
    return content, []

def main():
    files = get_all_files()
    print(f"Scanning {len(files)} files...")
    
    permalink_set, wp_id_to_permalink, slug_to_permalinks = build_indexes(files)
    print(f"Index: {len(permalink_set)} permalinks, {len(wp_id_to_permalink)} WP IDs, {len(slug_to_permalinks)} slugs")
    
    total_fixed = 0
    total_stripped = 0
    total_unresolved = 0
    unresolved_links = []
    files_modified = 0
    
    for f in files:
        new_content, changes = fix_file(f, wp_id_to_permalink, slug_to_permalinks, permalink_set)
        
        if changes:
            fixed = sum(1 for c in changes if c[0] == 'fix')
            stripped = sum(1 for c in changes if c[0] == 'strip')
            unresolved = sum(1 for c in changes if c[0] == 'unresolved')
            
            total_fixed += fixed
            total_stripped += stripped
            total_unresolved += unresolved
            
            for c in changes:
                if c[0] == 'unresolved':
                    unresolved_links.append((f, c[1]))
            
            if fixed > 0 or stripped > 0:
                with open(f, 'w', encoding='utf-8') as fh:
                    fh.write(new_content)
                files_modified += 1
                rel = os.path.relpath(f, BASE_DIR)
                print(f"  Fixed {rel}: {fixed} resolved, {stripped} stripped")
    
    print(f"\n=== SUMMARY ===")
    print(f"Files modified: {files_modified}")
    print(f"Links resolved to permalinks: {total_fixed}")
    print(f"Links stripped (no equivalent): {total_stripped}")
    print(f"Unresolved links: {total_unresolved}")
    
    if unresolved_links:
        print(f"\n=== UNRESOLVED ({len(unresolved_links)}) ===")
        for f, href in unresolved_links[:30]:
            print(f"  {os.path.relpath(f, BASE_DIR)}: {href}")
        if len(unresolved_links) > 30:
            print(f"  ... and {len(unresolved_links) - 30} more")

if __name__ == '__main__':
    main()
