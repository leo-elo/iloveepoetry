#!/usr/bin/env python3
"""Fix remaining unresolved internal links."""
import os
import re

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"

# page_id links to strip (no equivalent pages exist)
PAGE_IDS_TO_STRIP = ['6814', '7893', '7896', '7900', '7904', '8049']

def strip_page_id_links(filepath):
    """Strip ?page_id=X links where pages don't exist."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    for pid in PAGE_IDS_TO_STRIP:
        pattern = r'<a\s+[^>]*href=["\'][^"\']*iloveepoetry\.org/?\?page_id=' + pid + r'["\'][^>]*>(.*?)</a>'
        content = re.sub(pattern, r'\1', content, flags=re.DOTALL)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

# Files with unresolved page_id links
files_with_page_ids = [
    "_posts/es/2018-05-15-pasantes-de-i-♥-e-poetry-en-otono-del-2013.html",
    "_posts/es/2018-04-10-tramway-por-alexandra-saemmer.html",
    "_posts/es/2018-04-24-no-choice-about-the-terminology-por-jason-edward-lewis-christian-gratton-elie-zananiri-y-bruno-nadeau.html",
    "_posts/en/2013-04-11-no-choice-about-the-terminology-by-jason-edward.html",
    "_posts/en/2013-02-07-tramway-by-alexandra-saemmer.html",
    "_posts/en/2014-01-07-i-♥-e-poetry-fall-2013-interns.html",
]

count = 0
for relpath in files_with_page_ids:
    fp = os.path.join(BASE_DIR, relpath)
    if os.path.exists(fp) and strip_page_id_links(fp):
        print(f"  Stripped page_id links: {relpath}")
        count += 1

print(f"\nStripped page_id links in {count} files")

# Fix ?p=7112 links (typerider) in index pages
for relpath in ["_pages/es/indice-a-a-z-por-titulo.html", "_pages/en/index-a-to-z-by-title.html"]:
    fp = os.path.join(BASE_DIR, relpath)
    if not os.path.exists(fp):
        continue
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    # Replace with link to the actual typerider post
    if '/es/' in relpath:
        content = re.sub(
            r'href=["\']http://iloveepoetry\.org/\?p=7112["\']',
            'href="{{ "/es/2013/typerider-por-cosmografik/" | relative_url }}"',
            content
        )
    else:
        content = re.sub(
            r'href=["\']http://iloveepoetry\.org/\?p=7112["\']',
            'href="{{ "/en/2013/typerider-cosmografik/" | relative_url }}"',
            content
        )
    if content != original:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Fixed ?p=7112 link: {relpath}")

# Fix ?p=52\ (trailing backslash) - metaphor-a-minute
fp = os.path.join(BASE_DIR, "_posts/es/2018-05-19-snowclone-a-minute-snowcloneminute-por-bradley-momberger-y-pizza-clones-pizzaclones-por-allison-parrish.html")
if os.path.exists(fp):
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace(
        'http://iloveepoetry.org/?p=52\\',
        '{{ "/es/2013/metaphor-a-minute-por-darius-kazemi/" | relative_url }}'
    )
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  Fixed ?p=52\\ link in snowclone post")

# Fix /en/uncategorized/ link
fp = os.path.join(BASE_DIR, "_posts/es/2018-03-16-literatura-electronica-americana.html")
if os.path.exists(fp):
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace(
        '/en/uncategorized/recurso-literatura-electronica-para-los-ninos-de-ahora/',
        '{{ "/es/uncategorized/recurso-literatura-electronica-para-los-ninos-de-ahora/" | relative_url }}'
    )
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  Fixed /en/uncategorized/ link -> /es/uncategorized/")

print("\nDone!")
