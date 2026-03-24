#!/usr/bin/env python3
"""Scan all posts/pages for internal links and check against known permalinks."""

import os
import re
import glob
from urllib.parse import unquote, urlparse
import html

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"
POSTS_DIR = os.path.join(BASE_DIR, "_posts")
PAGES_DIR = os.path.join(BASE_DIR, "_pages")

def get_all_files():
    """Get all HTML files from _posts and _pages."""
    files = []
    for d in [POSTS_DIR, PAGES_DIR]:
        for root, dirs, fnames in os.walk(d):
            for f in fnames:
                if f.endswith('.html'):
                    files.append(os.path.join(root, f))
    return files

def extract_permalink(filepath):
    """Extract permalink from YAML front matter."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    m = re.search(r'^permalink:\s*["\']?(/[^\s"\']+)["\']?\s*$', content, re.MULTILINE)
    if m:
        return unquote(m.group(1))
    return None

def extract_links(filepath):
    """Extract all href links from a file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split off front matter
    parts = content.split('---', 2)
    if len(parts) >= 3:
        body = parts[2]
        front = parts[1]
    else:
        body = content
        front = ""
    
    links = []
    # Find href="..." links in body
    for m in re.finditer(r'href=["\']([^"\']+)["\']', body):
        links.append(m.group(1))
    
    # Also check translation field in front matter
    tm = re.search(r'^translation:\s*["\']?(/[^\s"\']+)["\']?\s*$', front, re.MULTILINE)
    if tm:
        links.append(("translation", tm.group(1)))
    
    return links

def is_internal_link(href):
    """Check if a link is internal to the site."""
    if isinstance(href, tuple):
        return True  # translation links are always internal
    
    # Skip Liquid template links - they'll be resolved at build time
    if '{{' in href or '{%' in href:
        return False
    
    # Skip anchors and mailto
    if href.startswith('#') or href.startswith('mailto:') or href.startswith('javascript:'):
        return False
    
    # Internal absolute links
    if 'iloveepoetry.org' in href or 'iloveepoetry.com' in href:
        return True
    
    # Links with /iloveepoetry/ prefix
    if href.startswith('/iloveepoetry/'):
        return True
    
    # Relative links starting with /
    if href.startswith('/') and not href.startswith('//'):
        return True
    
    # Old localhost links
    if 'localhost' in href:
        return True
    
    return False

def normalize_link(href):
    """Normalize an internal link to a permalink path."""
    if isinstance(href, tuple):
        return unquote(href[1])
    
    # Parse URL
    parsed = urlparse(href)
    path = parsed.path
    
    # Remove /iloveepoetry prefix
    if path.startswith('/iloveepoetry/'):
        path = path[len('/iloveepoetry'):]
    elif path.startswith('/iloveepoetry'):
        path = path[len('/iloveepoetry'):]
    
    # Handle iloveepoetry.org links
    if 'iloveepoetry.org' in href or 'iloveepoetry.com' in href:
        path = parsed.path
    
    # Handle ?p=ID links
    if parsed.query and 'p=' in parsed.query:
        return f"?p={parsed.query.split('p=')[1].split('&')[0]}"
    
    # URL decode
    path = unquote(path)
    
    # Ensure trailing slash
    if path and not path.endswith('/') and '.' not in path.split('/')[-1]:
        path += '/'
    
    return path

def main():
    files = get_all_files()
    print(f"Scanning {len(files)} files...")
    
    # Build permalink index
    permalink_set = set()
    permalink_to_file = {}
    wp_id_map = {}
    
    for f in files:
        pl = extract_permalink(f)
        if pl:
            permalink_set.add(pl)
            permalink_to_file[pl] = f
            
            # Also extract wp_post_id
            with open(f, 'r', encoding='utf-8') as fh:
                content = fh.read()
            m = re.search(r'^wp_post_id:\s*(\d+)', content, re.MULTILINE)
            if m:
                wp_id_map[m.group(1)] = pl
    
    print(f"Found {len(permalink_set)} permalinks")
    
    # Also add known static paths (assets, etc)
    # We won't check links to assets/images
    
    broken = []
    old_wp_links = []
    
    for f in files:
        links = extract_links(f)
        for href in links:
            if not is_internal_link(href):
                continue
            
            raw = href if not isinstance(href, tuple) else href[1]
            
            # Skip asset/image links
            if '/assets/' in str(raw) or '/wp-content/' in str(raw):
                continue
            
            # Skip links that use Liquid
            if '{{' in str(raw) or '{%' in str(raw):
                continue
                
            norm = normalize_link(href)
            
            # Handle ?p=ID
            if norm.startswith('?p='):
                pid = norm[3:]
                if pid in wp_id_map:
                    broken.append({
                        'file': f,
                        'href': raw,
                        'type': 'wp_id',
                        'target': wp_id_map[pid]
                    })
                else:
                    broken.append({
                        'file': f,
                        'href': raw,
                        'type': 'wp_id_unknown',
                        'target': None
                    })
                continue
            
            # Check if old iloveepoetry.org link
            if 'iloveepoetry.org' in str(raw) or 'iloveepoetry.com' in str(raw):
                old_wp_links.append({
                    'file': f,
                    'href': raw,
                    'normalized': norm
                })
                continue
            
            # Check if localhost link
            if 'localhost' in str(raw):
                broken.append({
                    'file': f,
                    'href': raw,
                    'type': 'localhost',
                    'target': None
                })
                continue
            
            # Check against permalink set
            if norm and norm not in permalink_set:
                # Try without trailing slash
                alt = norm.rstrip('/')
                if alt and alt + '/' not in permalink_set and alt not in permalink_set:
                    # Try to find a close match
                    slug = norm.rstrip('/').split('/')[-1] if '/' in norm else norm
                    matches = [p for p in permalink_set if slug and slug in p]
                    broken.append({
                        'file': f,
                        'href': raw,
                        'type': 'broken_permalink',
                        'normalized': norm,
                        'possible_matches': matches[:3]
                    })
    
    print(f"\n=== BROKEN INTERNAL LINKS ({len(broken)}) ===")
    for b in broken:
        rel_file = os.path.relpath(b['file'], BASE_DIR)
        print(f"\nFile: {rel_file}")
        print(f"  Link: {b['href']}")
        print(f"  Type: {b['type']}")
        if b.get('target'):
            print(f"  Should be: {b['target']}")
        if b.get('normalized'):
            print(f"  Normalized: {b['normalized']}")
        if b.get('possible_matches'):
            print(f"  Possible matches: {b['possible_matches']}")
    
    print(f"\n=== OLD ILOVEEPOETRY.ORG LINKS ({len(old_wp_links)}) ===")
    for link in old_wp_links[:50]:  # Show first 50
        rel_file = os.path.relpath(link['file'], BASE_DIR)
        print(f"\nFile: {rel_file}")
        print(f"  Link: {link['href']}")
        print(f"  Normalized: {link['normalized']}")
        # Check if normalized path matches a permalink
        if link['normalized'] in permalink_set:
            print(f"  -> MATCH FOUND: {link['normalized']}")
        else:
            slug = link['normalized'].rstrip('/').split('/')[-1]
            matches = [p for p in permalink_set if slug and slug in p]
            if matches:
                print(f"  -> Possible matches: {matches[:3]}")
            else:
                print(f"  -> NO MATCH")
    
    if len(old_wp_links) > 50:
        print(f"\n... and {len(old_wp_links) - 50} more old iloveepoetry.org links")

if __name__ == '__main__':
    main()
