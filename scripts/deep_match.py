#!/usr/bin/env python3
"""
deep_match.py — Thorough matching of unlinked English and Spanish posts.

Scans all English posts without a `translation` field and all Spanish posts
without a `translation` field, then attempts to match them using multiple
heuristics: title normalization, slug comparison, tag overlap, content
similarity (featured_image, work_url, elmcip_url), and editorial pattern
matching.

Output is grouped into HIGH CONFIDENCE, MEDIUM CONFIDENCE, and TRULY UNMATCHED.
"""

import os
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

# -- Paths -----------------------------------------------------------------
EN_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
ES_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"

# -- YAML front-matter parser (lightweight, no PyYAML dependency) ----------

def parse_front_matter(filepath):
    """Return a dict of front-matter fields from a Jekyll post."""
    meta = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return meta

    if not text.startswith("---"):
        return meta

    end = text.find("\n---", 3)
    if end == -1:
        return meta

    fm_block = text[3:end].strip()
    meta["_body"] = text[end + 4:]

    current_key = None
    list_values = []
    in_list = False

    for line in fm_block.split("\n"):
        if in_list and line.startswith("- "):
            val = line[2:].strip().strip('"').strip("'")
            list_values.append(val)
            continue
        elif in_list:
            meta[current_key] = list_values
            in_list = False
            list_values = []
            current_key = None

        m = re.match(r'^(\w[\w_]*):\s*(.*)', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val == "":
                current_key = key
                in_list = True
                list_values = []
            else:
                val = val.strip('"').strip("'")
                meta[key] = val

    if in_list and current_key:
        meta[current_key] = list_values

    for k in ("categories", "tags"):
        if k in meta and isinstance(meta[k], str):
            meta[k] = [meta[k]]

    meta["_filename"] = os.path.basename(filepath)
    return meta


# -- Normalization helpers -------------------------------------------------

def strip_accents(s):
    """Remove diacritical marks."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_title(title):
    """Aggressively normalize a title for comparison."""
    if not title:
        return ""
    t = title.lower()
    t = strip_accents(t)
    t = re.sub(r'["\u201c\u201d\u2018\u2019\'`]', '', t)
    t = re.sub(r'\bpor\b', 'by', t)
    t = re.sub(r'\b y \b', ' and ', t)
    t = re.sub(r'\b(el|la|los|las|the|a|an|un|una|unos|unas|del)\b', '', t)
    t = re.sub(r'\b(en espanol|in spanish|in english|en ingles)\b', '', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t).strip()
    return t


def extract_core_slug(permalink):
    """Extract a normalized core slug from a permalink."""
    if not permalink:
        return ""
    s = permalink.strip("/")
    s = re.sub(r'^(en|es)/', '', s)
    cats_to_remove = [
        r'\d{4}(-es)?/',
        r'(adult|teen|children|ninos|adulto|adolescente)(-es)?/',
        r'(entries|entradas|news|noticias)/',
        r'(aural|auditivo|kinetic|cinetico|static|estatico|mutable|mudable)(-es)?/',
        r'(responsive|sensible)(-es)?/',
        r'[a-z]+-es/',
    ]
    for pat in cats_to_remove:
        s = re.sub(pat, '', s, flags=re.IGNORECASE)

    slug = s.strip("/")
    slug = strip_accents(slug)
    slug = slug.lower()
    slug = re.sub(r'-por-', '-by-', slug)
    slug = re.sub(r'-\d+$', '', slug)
    slug = re.sub(r'-(es|en)$', '', slug)
    return slug


def extract_work_name_from_title(title):
    """Extract the work name from a title like 'WorkName by Author'."""
    if not title:
        return ""
    m = re.match(r'^["\u201c\u201d\u2018\u2019\']*(.+?)["\u201c\u201d\u2018\u2019\']*\s+(by|por)\s+', title, re.IGNORECASE)
    if m:
        return normalize_title(m.group(1))
    return normalize_title(title)


def extract_author_from_title(title):
    """Extract author name from title like 'Work by Author Name'."""
    if not title:
        return ""
    m = re.search(r'\s+(by|por)\s+(.+)$', title, re.IGNORECASE)
    if m:
        return normalize_title(m.group(2))
    return ""


# -- Editorial pattern matching --------------------------------------------

EDITORIAL_PATTERNS = [
    (r'new contributor[:\s]+(.+)', r'nuev[oa] colaborador[a]?[:\s]+(.+)', 'contributor intro'),
    (r'year in review', r'retrospectiva del a[nñ]o', 'year in review'),
    (r'call for (papers|proposals|submissions)|cfp', r'convocatoria|llamada a (trabajos|propuestas)', 'CFP'),
    (r'advisory board', r'junta asesora|consejo asesor', 'advisory board'),
    (r"editor'?s? (note|message|letter)", r'mensaje del editor|nota del editor', 'editor message'),
    (r'welcome to', r'bienvenidos? a', 'welcome message'),
    (r'hello world', r'hello world', 'hello world'),
    (r'examples of electronic literature', r'ejemplos de literatura electr[oó]nica', 'examples of e-lit'),
    (r'best of', r'lo mejor de|mejores de', 'best of'),
    (r'(first|second|third|\d+)\s*anniversary', r'(primer|segundo|tercer|\d+)\s*aniversario', 'anniversary'),
    (r'about (this|the) (blog|project|site)', r'acerca de (este|el) (blog|proyecto|sitio)', 'about'),
    (r'international book fair', r'feria internacional del libro', 'book fair'),
]


def editorial_match_score(en_title, es_title):
    """Check if two titles match editorial patterns."""
    en_norm = strip_accents(en_title.lower()) if en_title else ""
    es_norm = strip_accents(es_title.lower()) if es_title else ""

    for en_pat, es_pat, desc in EDITORIAL_PATTERNS:
        en_m = re.search(en_pat, en_norm)
        es_m = re.search(es_pat, es_norm)
        if en_m and es_m:
            return (0.8, f"editorial pattern: {desc}")
    return None


# -- Scoring functions -----------------------------------------------------

def title_similarity(en_meta, es_meta):
    """Compare normalized titles."""
    en_title = normalize_title(en_meta.get("title", ""))
    es_title = normalize_title(es_meta.get("title", ""))
    if not en_title or not es_title:
        return (0.0, "")

    if en_title == es_title:
        return (1.0, "exact normalized title match")

    en_work = extract_work_name_from_title(en_meta.get("title", ""))
    es_work = extract_work_name_from_title(es_meta.get("title", ""))
    en_author = extract_author_from_title(en_meta.get("title", ""))
    es_author = extract_author_from_title(es_meta.get("title", ""))

    if en_work and es_work and en_work == es_work:
        if en_author and es_author and en_author == es_author:
            return (0.98, "work name + author match")
        elif en_author and es_author:
            author_sim = SequenceMatcher(None, en_author, es_author).ratio()
            if author_sim > 0.7:
                return (0.95, f"work name match, author similar ({author_sim:.2f})")
        else:
            return (0.90, "work name match (no author comparison)")

    ratio = SequenceMatcher(None, en_title, es_title).ratio()
    if ratio >= 0.85:
        return (ratio, f"fuzzy title match ({ratio:.2f})")
    if ratio >= 0.7:
        return (ratio * 0.9, f"partial title match ({ratio:.2f})")

    return (0.0, "")


def slug_similarity(en_meta, es_meta):
    """Compare core slugs."""
    en_slug = extract_core_slug(en_meta.get("permalink", ""))
    es_slug = extract_core_slug(es_meta.get("permalink", ""))
    if not en_slug or not es_slug:
        return (0.0, "")

    if en_slug == es_slug:
        return (1.0, "exact slug match")

    ratio = SequenceMatcher(None, en_slug, es_slug).ratio()
    if ratio >= 0.85:
        return (ratio, f"fuzzy slug match ({ratio:.2f})")
    if ratio >= 0.7:
        return (ratio * 0.85, f"partial slug match ({ratio:.2f})")

    return (0.0, "")


def tag_similarity(en_meta, es_meta):
    """Compare tags (author names)."""
    en_tags = set(normalize_title(t) for t in en_meta.get("tags", []) if t)
    es_tags = set(normalize_title(t) for t in es_meta.get("tags", []) if t)
    if not en_tags or not es_tags:
        return (0.0, "")

    overlap = en_tags & es_tags
    if overlap:
        union = en_tags | es_tags
        jaccard = len(overlap) / len(union)
        if jaccard >= 0.5:
            return (0.7 * jaccard + 0.3, f"tag overlap: {', '.join(overlap)} (jaccard={jaccard:.2f})")
        else:
            return (0.5 * jaccard + 0.1, f"partial tag overlap: {', '.join(overlap)}")
    return (0.0, "")


def content_similarity(en_meta, es_meta):
    """Compare featured_image, work_url, elmcip_url."""
    score = 0.0
    reasons = []

    en_img = en_meta.get("featured_image", "").strip().lower()
    es_img = es_meta.get("featured_image", "").strip().lower()
    if en_img and es_img and en_img == es_img:
        score += 0.4
        reasons.append("same featured_image")

    en_url = en_meta.get("work_url", "").strip().rstrip("/").lower()
    es_url = es_meta.get("work_url", "").strip().rstrip("/").lower()
    if en_url and es_url and en_url == es_url:
        score += 0.4
        reasons.append("same work_url")

    en_elm = en_meta.get("elmcip_url", "").strip().rstrip("/").lower()
    es_elm = es_meta.get("elmcip_url", "").strip().rstrip("/").lower()
    if en_elm and es_elm and en_elm == es_elm:
        score += 0.3
        reasons.append("same elmcip_url")

    if score > 0:
        return (min(score, 1.0), "; ".join(reasons))
    return (0.0, "")


# -- Main matching logic ---------------------------------------------------

def load_posts(directory):
    """Load all posts from a directory."""
    posts = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".html"):
            continue
        fpath = os.path.join(directory, fname)
        meta = parse_front_matter(fpath)
        if meta:
            meta["_filepath"] = fpath
            posts.append(meta)
    return posts


def get_unlinked(posts):
    """Return posts that do NOT have a translation field."""
    return [p for p in posts if "translation" not in p]


def compute_match_score(en, es):
    """Compute overall match score between an EN and ES post."""
    all_reasons = []
    total_score = 0.0

    # 1. Title matching (highest priority)
    t_score, t_reason = title_similarity(en, es)
    if t_reason:
        all_reasons.append(f"title: {t_reason}")
    total_score = max(total_score, t_score)

    # 2. Slug matching
    s_score, s_reason = slug_similarity(en, es)
    if s_reason:
        all_reasons.append(f"slug: {s_reason}")
    total_score = max(total_score, s_score)

    # 3. Tag matching
    tag_score, tag_reason = tag_similarity(en, es)
    if tag_reason:
        all_reasons.append(f"tags: {tag_reason}")

    # 4. Content similarity
    c_score, c_reason = content_similarity(en, es)
    if c_reason:
        all_reasons.append(f"content: {c_reason}")

    # 5. Editorial patterns
    ed = editorial_match_score(en.get("title", ""), es.get("title", ""))
    if ed:
        ed_score, ed_reason = ed
        all_reasons.append(ed_reason)
        total_score = max(total_score, ed_score)

    # Combine signals
    if total_score < 0.7:
        combined_secondary = tag_score * 0.5 + c_score * 0.5
        if combined_secondary > total_score:
            total_score = combined_secondary

    # Boost strong primary matches with secondary evidence
    if total_score >= 0.7 and c_score > 0:
        total_score = min(1.0, total_score + c_score * 0.1)
    if total_score >= 0.7 and tag_score > 0:
        total_score = min(1.0, total_score + tag_score * 0.1)

    # Cap if only secondary evidence
    if t_score < 0.3 and s_score < 0.3:
        if tag_score > 0 and c_score > 0:
            total_score = min(total_score, 0.65)
        elif tag_score > 0 or c_score > 0:
            total_score = min(total_score, 0.50)

    return (total_score, all_reasons)


def find_matches(en_posts, es_posts):
    """Find best matches between unlinked EN and ES posts."""
    # Build indexes for faster matching
    en_title_idx = defaultdict(list)
    es_title_idx = defaultdict(list)
    en_slug_idx = defaultdict(list)
    es_slug_idx = defaultdict(list)
    en_tag_idx = defaultdict(list)
    es_tag_idx = defaultdict(list)

    for i, p in enumerate(en_posts):
        nt = normalize_title(p.get("title", ""))
        if nt:
            en_title_idx[nt].append(i)
            work = extract_work_name_from_title(p.get("title", ""))
            if work and work != nt:
                en_title_idx[work].append(i)
        slug = extract_core_slug(p.get("permalink", ""))
        if slug:
            en_slug_idx[slug].append(i)
        for tag in p.get("tags", []):
            tag_norm = normalize_title(tag)
            if tag_norm:
                en_tag_idx[tag_norm].append(i)

    for j, p in enumerate(es_posts):
        nt = normalize_title(p.get("title", ""))
        if nt:
            es_title_idx[nt].append(j)
            work = extract_work_name_from_title(p.get("title", ""))
            if work and work != nt:
                es_title_idx[work].append(j)
        slug = extract_core_slug(p.get("permalink", ""))
        if slug:
            es_slug_idx[slug].append(j)
        for tag in p.get("tags", []):
            tag_norm = normalize_title(tag)
            if tag_norm:
                es_tag_idx[tag_norm].append(j)

    # Build candidate pairs
    candidates = set()

    # Candidate generation: title index
    for key in en_title_idx:
        if key in es_title_idx:
            for i in en_title_idx[key]:
                for j in es_title_idx[key]:
                    candidates.add((i, j))
        for es_key in es_title_idx:
            if abs(len(key) - len(es_key)) <= 10:
                ratio = SequenceMatcher(None, key, es_key).ratio()
                if ratio >= 0.65:
                    for i in en_title_idx[key]:
                        for j in es_title_idx[es_key]:
                            candidates.add((i, j))

    # Candidate generation: slug index
    for key in en_slug_idx:
        if key in es_slug_idx:
            for i in en_slug_idx[key]:
                for j in es_slug_idx[key]:
                    candidates.add((i, j))
        for es_key in es_slug_idx:
            if abs(len(key) - len(es_key)) <= 8:
                ratio = SequenceMatcher(None, key, es_key).ratio()
                if ratio >= 0.65:
                    for i in en_slug_idx[key]:
                        for j in es_slug_idx[es_key]:
                            candidates.add((i, j))

    # Candidate generation: tag index
    for tag_key in en_tag_idx:
        if tag_key in es_tag_idx:
            for i in en_tag_idx[tag_key]:
                for j in es_tag_idx[tag_key]:
                    candidates.add((i, j))

    # Candidate generation: content-based (featured_image, work_url)
    en_img_idx = {}
    es_img_idx = {}
    en_wurl_idx = {}
    es_wurl_idx = {}
    for i, p in enumerate(en_posts):
        img = p.get("featured_image", "").strip().lower()
        if img:
            en_img_idx.setdefault(img, []).append(i)
        wurl = p.get("work_url", "").strip().rstrip("/").lower()
        if wurl:
            en_wurl_idx.setdefault(wurl, []).append(i)
    for j, p in enumerate(es_posts):
        img = p.get("featured_image", "").strip().lower()
        if img:
            es_img_idx.setdefault(img, []).append(j)
        wurl = p.get("work_url", "").strip().rstrip("/").lower()
        if wurl:
            es_wurl_idx.setdefault(wurl, []).append(j)

    for img_key in en_img_idx:
        if img_key in es_img_idx:
            for i in en_img_idx[img_key]:
                for j in es_img_idx[img_key]:
                    candidates.add((i, j))

    for url_key in en_wurl_idx:
        if url_key in es_wurl_idx:
            for i in en_wurl_idx[url_key]:
                for j in es_wurl_idx[url_key]:
                    candidates.add((i, j))

    # Editorial candidate pairs
    en_editorial = [i for i, p in enumerate(en_posts)
                    if any(cat.lower() in ("news", "noticias", "uncategorized", "sin categorizar")
                           for cat in p.get("categories", []))]
    es_editorial = [j for j, p in enumerate(es_posts)
                    if any(cat.lower() in ("news", "noticias", "uncategorized", "sin categorizar")
                           for cat in p.get("categories", []))]

    for i in en_editorial:
        for j in es_editorial:
            en_title = en_posts[i].get("title", "").lower()
            es_title = es_posts[j].get("title", "").lower()
            en_kw = any(kw in en_title for kw in
                        ["contributor", "review", "cfp", "board", "editor", "welcome",
                         "hello", "example", "best of", "anniversary", "about", "fair",
                         "award", "grant", "conference", "symposium", "festival"])
            es_kw = any(kw in strip_accents(es_title) for kw in
                        ["colaborador", "retrospectiva", "convocatoria", "asesora", "editor",
                         "bienvenido", "hello", "ejemplo", "mejor", "aniversario", "acerca",
                         "feria", "premio", "beca", "conferencia", "simposio", "festival"])
            if en_kw or es_kw:
                candidates.add((i, j))

    print(f"  Generated {len(candidates)} candidate pairs to evaluate...")

    # Score all candidates
    scored = []
    for (i, j) in candidates:
        score, reasons = compute_match_score(en_posts[i], es_posts[j])
        if score >= 0.20:
            scored.append((score, reasons, i, j))

    scored.sort(key=lambda x: -x[0])

    # Greedy 1-to-1 matching
    matched_en = set()
    matched_es = set()
    high_confidence = []
    medium_confidence = []

    for score, reasons, i, j in scored:
        if i in matched_en or j in matched_es:
            continue
        if score >= 0.70:
            high_confidence.append((score, reasons, en_posts[i], es_posts[j]))
            matched_en.add(i)
            matched_es.add(j)
        elif score >= 0.35:
            medium_confidence.append((score, reasons, en_posts[i], es_posts[j]))
            matched_en.add(i)
            matched_es.add(j)

    unmatched_en = [en_posts[i] for i in range(len(en_posts)) if i not in matched_en]
    unmatched_es = [es_posts[j] for j in range(len(es_posts)) if j not in matched_es]

    return high_confidence, medium_confidence, unmatched_en, unmatched_es


# -- Pretty printing -------------------------------------------------------

def fmt_post(meta, prefix="  "):
    """Format a post for display."""
    return (
        f"{prefix}File:      {meta.get('_filename', '?')}\n"
        f"{prefix}Title:     {meta.get('title', '?')}\n"
        f"{prefix}Permalink: {meta.get('permalink', '?')}"
    )


def main():
    print("=" * 80)
    print("DEEP MATCH: Unlinked English <-> Spanish Post Matching")
    print("=" * 80)
    print()

    print("Loading posts...")
    all_en = load_posts(EN_DIR)
    all_es = load_posts(ES_DIR)
    print(f"  Total English posts: {len(all_en)}")
    print(f"  Total Spanish posts: {len(all_es)}")

    en_unlinked = get_unlinked(all_en)
    es_unlinked = get_unlinked(all_es)
    print(f"  Unlinked English posts: {len(en_unlinked)}")
    print(f"  Unlinked Spanish posts: {len(es_unlinked)}")
    print()

    print("Matching...")
    high, medium, unmatched_en, unmatched_es = find_matches(en_unlinked, es_unlinked)

    # Section 1: HIGH CONFIDENCE
    print()
    print("=" * 80)
    print(f"1. HIGH CONFIDENCE MATCHES ({len(high)} pairs)")
    print("   (score >= 0.70 -- title or slug matches clearly)")
    print("=" * 80)
    for idx, (score, reasons, en, es) in enumerate(high, 1):
        print(f"\n  Match #{idx}  [score: {score:.2f}]")
        print(f"  Reasons: {'; '.join(reasons)}")
        print(f"  EN:")
        print(fmt_post(en, "    "))
        print(f"  ES:")
        print(fmt_post(es, "    "))

    # Section 2: MEDIUM CONFIDENCE
    print()
    print("=" * 80)
    print(f"2. MEDIUM CONFIDENCE MATCHES ({len(medium)} pairs)")
    print("   (score 0.35-0.69 -- tag/content/editorial pattern matches)")
    print("=" * 80)
    for idx, (score, reasons, en, es) in enumerate(medium, 1):
        print(f"\n  Match #{idx}  [score: {score:.2f}]")
        print(f"  Reasons: {'; '.join(reasons)}")
        print(f"  EN:")
        print(fmt_post(en, "    "))
        print(f"  ES:")
        print(fmt_post(es, "    "))

    # Section 3: TRULY UNMATCHED
    print()
    print("=" * 80)
    print(f"3. TRULY UNMATCHED POSTS")
    print("=" * 80)

    print(f"\n  --- English posts needing Spanish translation ({len(unmatched_en)}) ---")
    for idx, p in enumerate(unmatched_en, 1):
        print(f"\n  {idx}. {p.get('title', '?')}")
        print(f"     File:      {p.get('_filename', '?')}")
        print(f"     Permalink: {p.get('permalink', '?')}")
        tags = p.get("tags", [])
        if tags:
            print(f"     Tags:      {', '.join(tags)}")

    print(f"\n  --- Spanish posts needing English translation ({len(unmatched_es)}) ---")
    for idx, p in enumerate(unmatched_es, 1):
        print(f"\n  {idx}. {p.get('title', '?')}")
        print(f"     File:      {p.get('_filename', '?')}")
        print(f"     Permalink: {p.get('permalink', '?')}")
        tags = p.get("tags", [])
        if tags:
            print(f"     Tags:      {', '.join(tags)}")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total unlinked English posts:  {len(en_unlinked)}")
    print(f"  Total unlinked Spanish posts:  {len(es_unlinked)}")
    print(f"  High confidence matches:       {len(high)}")
    print(f"  Medium confidence matches:     {len(medium)}")
    print(f"  Total matched pairs:           {len(high) + len(medium)}")
    print(f"  Truly unmatched English:       {len(unmatched_en)}")
    print(f"  Truly unmatched Spanish:       {len(unmatched_es)}")
    print()


if __name__ == "__main__":
    main()
