#!/usr/bin/env python3
"""
Script to add featured_image to 39 posts that are missing it.

Strategy:
1. Check if the post body has leading <img> tags. If so, use the first image's src
   as featured_image and remove the leading image from the body.
2. If no images in body, check if there's a translation counterpart (en<->es) that
   has a featured_image. If so, use the same image.
3. If still no image, use the fallback logo: /assets/images/uprm/iloveepoetry500.png
"""

import os
import re
import sys

SITE_ROOT = "/Users/floresll/Desktop/iloveepoetry"
POSTS_DIR = os.path.join(SITE_ROOT, "_posts")
FALLBACK_IMAGE = "/assets/images/uprm/iloveepoetry500.png"

# The 39 posts that need featured images, with corrected paths based on actual filesystem
# Some posts the user listed as "en" are actually in "es" based on filesystem inspection
POSTS_TO_FIX = [
    # English posts
    "en/2012-03-22-assessing-i-e-poetry.html",
    "en/2013-02-05-i-e-poetry-nominated-for-2012-dh-awards.html",
    "en/2013-03-07-i-e-poetry-advisory-board.html",
    "en/2013-05-07-open-call-for-contributions.html",
    "en/2013-05-08-new-tools-for-exploring-i-\u2665-e-poetry.html",
    "en/2013-05-09-i-\u2665-e-poetry-reviewed-in-proxecto-le-es-literatura-electronica-en-espana.html",
    "en/2013-05-16-cfp-the-e-lit-i-love.html",
    "en/2013-06-17-teaching-with-i-\u2665-e-poetry-poster.html",
    "en/2013-06-19-i-\u2665-e-poetry-500-entries-later.html",
    "en/2013-08-26-the-i-\u2665-e-poetry-summer-of-pedagogy-report.html",
    "en/2013-08-27-call-for-regular-contributors.html",
    "en/2013-09-01-cfp-the-poetics-of-electronic-literature.html",
    "en/2013-09-02-i-\u2665-e-poetry-phase-2-the-next-500-entries.html",
    "en/2013-11-02-e-poetry-as-code-and-data-remix-by-leonardo-flores.html",
    "en/2013-11-03-teaching-with-i-\u2665-e-poetry-by-leonardo-flores.html",
    "en/2013-11-03-visualizing-i-\u2665-e-poetry-by-leonardo-flores.html",
    "en/2014-11-02-site-redesign-underway.html",
    # Spanish posts
    "es/2011-12-20-hello-world-2.html",
    "es/2017-01-01-i-\u2665\ufe0e-e-poetry-phase-3-begins-2.html",
    "es/2017-03-07-presentation-i-\u2665\ufe0e-e-poetry-discovering-digital-media-poetry-2.html",
    "es/2017-08-26-hello-world-en-espanol.html",
    "es/2018-02-26-assessing-i-\u2665-e-poetry.html",
    "es/2018-04-10-i-\u2665-e-poetry-nominado-para-los-dh-awards-de-2012.html",
    "es/2018-04-17-i-\u2665-e-poetry-junta-asesora.html",
    "es/2018-04-25-ensenando-con-i-\u2665-e-poetry-poster.html",
    "es/2018-04-25-i-\u2665-e-poetry-500-entradas-mas-tarde.html",
    "es/2018-04-30-cfp-the-e-lit-i-love-2.html",
    "es/2018-04-30-i-\u2665-e-poetry-revisado-en-proxecto-le-es-literatura-electronica-en-espana.html",
    "es/2018-04-30-nuevas-herramientas-para-explorar-i-\u2665-e-poetry.html",
    "es/2018-05-02-convocatoria-abierta-para-contribuciones.html",
    "es/2018-05-07-cfp-la-poetica-de-la-literatura-electronica.html",
    "es/2018-05-07-el-informe-de-verano-de-pedagogia-i-\u2665-e-poesia.html",
    "es/2018-05-07-i-\u2665-e-poetry-phase-2-las-siguientes-500-entradas.html",
    "es/2018-05-07-llame-para-contribuyentes-regulares.html",
    "es/2018-05-08-e-poetry-as-code-and-data-remix-por-leonardo-flores.html",
    "es/2018-05-08-teaching-with-i-\u2665-e-poetry-por-leonardo-flores.html",
    "es/2018-05-08-visualizing-i-\u2665-e-poetry-por-leonardo-flores.html",
    "es/2018-05-19-nuevo-contribuidor-kyle-brett.html",
    "es/2018-05-19-rediseno-del-sitio-en-marcha.html",
]


def parse_front_matter(content):
    """Parse a Jekyll file into front matter string, body string, and full content."""
    if not content.startswith("---"):
        return None, content
    end = content.find("---", 3)
    if end == -1:
        return None, content
    fm_str = content[3:end].strip()
    body = content[end + 3:]
    return fm_str, body


def get_featured_image_from_front_matter(fm_str):
    """Extract featured_image value from front matter string."""
    if fm_str is None:
        return None
    for line in fm_str.split("\n"):
        stripped = line.strip()
        if stripped.startswith("featured_image:"):
            value = stripped[len("featured_image:"):].strip()
            # Remove quotes
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            return value
    return None


def get_translation_from_front_matter(fm_str):
    """Extract translation permalink from front matter string."""
    if fm_str is None:
        return None
    for line in fm_str.split("\n"):
        stripped = line.strip()
        if stripped.startswith("translation:"):
            value = stripped[len("translation:"):].strip()
            # Remove quotes
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            return value
    return None


def get_permalink_from_front_matter(fm_str):
    """Extract permalink from front matter string."""
    if fm_str is None:
        return None
    for line in fm_str.split("\n"):
        stripped = line.strip()
        if stripped.startswith("permalink:"):
            value = stripped[len("permalink:"):].strip()
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            return value
    return None


def build_permalink_index():
    """Build a dict mapping permalink -> filepath for all posts."""
    index = {}
    for lang_dir in ["en", "es"]:
        full_dir = os.path.join(POSTS_DIR, lang_dir)
        if not os.path.isdir(full_dir):
            continue
        for fname in os.listdir(full_dir):
            if not fname.endswith(".html"):
                continue
            fpath = os.path.join(full_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            fm_str, _ = parse_front_matter(content)
            permalink = get_permalink_from_front_matter(fm_str)
            if permalink:
                index[permalink] = fpath
    return index


def extract_first_img_from_body(body):
    """
    Check if the body starts with a leading image (possibly wrapped in <a>, <figure>, <p>).
    Returns (image_src, cleaned_body) or (None, body) if no leading image found.
    """
    stripped = body.lstrip()

    # Pattern: leading <img> possibly wrapped in <a>, <figure>, or <p>
    # We look for an image at the very start of the body content

    # Try to match patterns like:
    # <a ...><img src="..." ...></a>
    # <figure ...><img src="..." ...></figure>
    # <p><a ...><img src="..." ...></a></p>
    # <p><img src="..." ...></p>
    # <img src="..." ...>

    patterns = [
        # <p><a ...><img ...></a></p> or <p><a ...><img .../></a></p>
        r'^(<p[^>]*>\s*<a[^>]*>\s*<img\s[^>]*?src=["\']([^"\']+)["\'][^>]*/?>\s*</a>\s*</p>)',
        # <a ...><img ...></a>
        r'^(<a[^>]*>\s*<img\s[^>]*?src=["\']([^"\']+)["\'][^>]*/?>\s*</a>)',
        # <figure ...><img ...></figure>
        r'^(<figure[^>]*>\s*<img\s[^>]*?src=["\']([^"\']+)["\'][^>]*/?>\s*</figure>)',
        # <p><img ...></p>
        r'^(<p[^>]*>\s*<img\s[^>]*?src=["\']([^"\']+)["\'][^>]*/?>\s*</p>)',
        # bare <img ...>
        r'^(<img\s[^>]*?src=["\']([^"\']+)["\'][^>]*?/?>)',
    ]

    for pattern in patterns:
        m = re.match(pattern, stripped, re.IGNORECASE | re.DOTALL)
        if m:
            full_match = m.group(1)
            img_src = m.group(2)
            # Remove the matched element from body
            cleaned = stripped[len(full_match):]
            # Preserve the leading whitespace structure
            cleaned_body = "\n" + cleaned
            return img_src, cleaned_body

    return None, body


def normalize_image_path(src):
    """Normalize image path to start with /assets/images/..."""
    if not src:
        return None

    # If it's already a proper local path
    if src.startswith("/assets/images/"):
        return src

    # If it has /iloveepoetry/ prefix, remove it
    if src.startswith("/iloveepoetry/assets/images/"):
        return src[len("/iloveepoetry"):]

    # If it's a wp-content path
    if "/wp-content/uploads/" in src:
        idx = src.find("/wp-content/uploads/")
        return "/assets/images" + src[idx:]

    # If it's a relative path to assets
    if "assets/images/" in src:
        idx = src.find("assets/images/")
        return "/" + src[idx:]

    # External URLs - skip these
    if src.startswith("http://") or src.startswith("https://"):
        return None

    return src


def add_featured_image_to_front_matter(content, image_path):
    """Add featured_image field to front matter."""
    # Find the closing --- of front matter
    first = content.find("---")
    if first == -1:
        return content
    second = content.find("---", first + 3)
    if second == -1:
        return content

    fm_section = content[first + 3:second]
    body = content[second:]

    # Add featured_image before the closing ---
    new_fm = fm_section.rstrip() + '\nfeatured_image: "' + image_path + '"\n'

    return "---" + new_fm + body


def find_counterpart_featured_image(fm_str, permalink_index):
    """
    Look for a translation counterpart and return its featured_image if it has one.
    """
    translation_permalink = get_translation_from_front_matter(fm_str)
    if translation_permalink:
        counterpart_path = permalink_index.get(translation_permalink)
        if counterpart_path:
            try:
                with open(counterpart_path, "r", encoding="utf-8") as f:
                    counterpart_content = f.read()
                counterpart_fm, _ = parse_front_matter(counterpart_content)
                fi = get_featured_image_from_front_matter(counterpart_fm)
                if fi:
                    return fi
            except Exception:
                pass

    # Also try to find by looking at all posts that have a translation pointing to this post
    my_permalink = get_permalink_from_front_matter(fm_str)
    if my_permalink:
        for plink, fpath in permalink_index.items():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    c = f.read()
                c_fm, _ = parse_front_matter(c)
                c_translation = get_translation_from_front_matter(c_fm)
                if c_translation and c_translation == my_permalink:
                    fi = get_featured_image_from_front_matter(c_fm)
                    if fi:
                        return fi
            except Exception:
                continue

    return None


def main():
    print("Building permalink index...")
    permalink_index = build_permalink_index()
    print(f"Indexed {len(permalink_index)} posts by permalink.\n")

    stats = {
        "img_from_body": 0,
        "img_from_counterpart": 0,
        "img_fallback": 0,
        "errors": 0,
        "already_has": 0,
    }

    results = []

    for rel_path in POSTS_TO_FIX:
        full_path = os.path.join(POSTS_DIR, rel_path)
        short_name = rel_path

        if not os.path.exists(full_path):
            print(f"ERROR: File not found: {full_path}")
            stats["errors"] += 1
            continue

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        fm_str, body = parse_front_matter(content)

        # Safety check: skip if already has featured_image
        existing = get_featured_image_from_front_matter(fm_str)
        if existing:
            print(f"SKIP (already has featured_image): {short_name}")
            stats["already_has"] += 1
            continue

        # Strategy 1: Check for leading <img> in body
        img_src, cleaned_body = extract_first_img_from_body(body)
        if img_src:
            normalized = normalize_image_path(img_src)
            if normalized:
                # Reconstruct content with cleaned body
                first = content.find("---")
                second = content.find("---", first + 3)
                new_content = content[:second + 3] + cleaned_body
                new_content = add_featured_image_to_front_matter(
                    new_content, normalized
                )
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"BODY IMG: {short_name} -> {normalized}")
                stats["img_from_body"] += 1
                results.append((short_name, "body_img", normalized))
                continue

        # Strategy 2: Check counterpart translation
        counterpart_img = find_counterpart_featured_image(fm_str, permalink_index)
        if counterpart_img:
            new_content = add_featured_image_to_front_matter(content, counterpart_img)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"COUNTERPART: {short_name} -> {counterpart_img}")
            stats["img_from_counterpart"] += 1
            results.append((short_name, "counterpart", counterpart_img))
            continue

        # Strategy 3: Fallback to logo
        new_content = add_featured_image_to_front_matter(content, FALLBACK_IMAGE)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"FALLBACK: {short_name} -> {FALLBACK_IMAGE}")
        stats["img_fallback"] += 1
        results.append((short_name, "fallback", FALLBACK_IMAGE))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Images extracted from body:    {stats['img_from_body']}")
    print(f"Images from counterpart post:  {stats['img_from_counterpart']}")
    print(f"Fallback logo used:            {stats['img_fallback']}")
    print(f"Already had featured_image:    {stats['already_has']}")
    print(f"Errors (file not found):       {stats['errors']}")
    total = stats['img_from_body'] + stats['img_from_counterpart'] + stats['img_fallback']
    print(f"Total posts updated:           {total}")
    print()

    # Print detailed results
    print("DETAILED RESULTS:")
    print("-" * 70)
    for short_name, method, image in results:
        print(f"  [{method:12s}] {short_name}")
        print(f"                -> {image}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
