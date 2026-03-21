#!/usr/bin/env python3
"""
add_authors.py — Extract author information from WordPress XML exports
and add it to Jekyll post front matter.

Reads dc:creator from two WordPress XML exports (2018 and 2026),
maps login names to display names, and inserts `author:` fields
into Jekyll post YAML front matter.
"""

import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

# ── Paths ──────────────────────────────────────────────────────────────
XML_2018 = "/Users/floresll/Desktop/Desktop Cleanup/ilovee-poetry.wordpress.2018-08-28.xml"
XML_2026 = "/Users/floresll/Downloads/ie-poetry.WordPress.2026-03-19.xml"
POSTS_EN = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
POSTS_ES = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"

# ── XML namespaces ─────────────────────────────────────────────────────
NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

# ── Author login → display name mapping ───────────────────────────────
AUTHOR_MAP = {
    "hayhielo": "Leonardo Flores",
    "reina.santiago1": "Reina Santiago",
    "alan.valle": "Alan Valle",
    "keysalis.fermin": "Keysalis Fermín",
    "julianna.canabal": "Julianna Canabal",
    "claudio.fajardo": "Luís Claudio Fajardo",
    "barbara.bordalejo": "Bárbara Bordalejo",
    "alvaroseica": "Álvaro Seiça",
    "samira.nadkarni": "Samira Nadkarni",
    "claire.taylor": "Claire Taylor",
    "HectorLopez": "Héctor López",
    "noheliameza": "Nohelia Meza",
    "leonardo.flores": "Leonardo Flores",
    "LaurenPerez": "Lauren Pérez",
    "EmanuelDeLeon": "Emanuel De León",
    "JuanKuang": "J.C. Kuang",
    "edcelcintron": "Edcel Cintron",
    "sophiacaraballo": "Sophia Caraballo",
    "calumrodger": "Calum Rodger",
    "cynthia": "Cynthia Román",
    "ianrolon": "Ian Rolón",
    "JonathanBaillehache": "Jonathan Baillehache",
    "PedroDoreste": "Pedro Noel Doreste",
    "YaishaCordero": "Yaisha Cordero",
    "JuanColon": "Juan A. Colón",
    "matt.la.schneider": "Matt Schneider",
    "kylebrett": "Kyle Brett",
    "jonathannegron": "Jonathan Negron",
    "vashtitacoronte": "Vashti Tacoronte",
    "dalinaperdomo": "Dalina Perdomo",
    "mayazalbildea": "Maya Zalbildea",
    "tomkonyves": "Tom Konyves",
    "desireesoltero": "Desiree Soltero",
    "andersonroman": "Anderson Roman",
    "carlosaguayo": "Carlos Aguayo",
    "williamrodriguez": "William Rodríguez",
    "marilyn.sanabria": "Marilyn Sanabria",
    "lourdes.caraballo": "Lourdes Caraballo",
    "jose.escabi": "José Escabí",
    "jose.cruz": "José Cruz",
    "demifuentes": "Demi Fuentes",
    "arantxaserantes": "Arantxa Serantes",
    "kyle.dase": "Kyle Dase",
    "christianquintero": "Christian Quintero",
    "leonardoflores": "Leonardo Flores",
}


def parse_xml_posts(xml_path):
    """
    Parse a WordPress XML export and return a dict mapping
    post_id (str) → creator login (str) for all post-type items.
    """
    print(f"  Parsing: {os.path.basename(xml_path)}")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    post_id_to_creator = {}
    items = root.findall(".//item")
    post_count = 0

    for item in items:
        post_type_el = item.find("wp:post_type", NS)
        if post_type_el is None or post_type_el.text != "post":
            continue

        post_id_el = item.find("wp:post_id", NS)
        creator_el = item.find("dc:creator", NS)

        if post_id_el is not None and creator_el is not None:
            post_id = post_id_el.text.strip()
            creator = creator_el.text.strip()
            post_id_to_creator[post_id] = creator
            post_count += 1

    print(f"    Found {post_count} posts")
    return post_id_to_creator


def read_front_matter(filepath):
    """
    Read a Jekyll post and return (front_matter_text, body_text).
    front_matter_text includes the opening and closing '---' delimiters.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return None, content

    second_dash = content.index("---", 3)
    front_matter = content[: second_dash + 3]
    body = content[second_dash + 3 :]
    return front_matter, body


def extract_field(front_matter, field_name):
    """Extract a field value from YAML front matter text."""
    pattern = rf"^{re.escape(field_name)}:\s*(.+)$"
    match = re.search(pattern, front_matter, re.MULTILINE)
    if match:
        value = match.group(1).strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        return value
    return None


def add_author_to_front_matter(front_matter, author_name):
    """
    Insert `author: "Name"` into the YAML front matter,
    right after the layout field.
    """
    author_line = f'author: "{author_name}"'
    lines = front_matter.rstrip("\n").split("\n")

    # Insert after layout line
    insert_idx = None
    for i, line in enumerate(lines):
        if line.startswith("layout:"):
            insert_idx = i + 1
            break

    if insert_idx is not None:
        lines.insert(insert_idx, author_line)
    elif lines[-1].strip() == "---":
        lines.insert(-1, author_line)
    else:
        lines.append(author_line)

    return "\n".join(lines) + "\n"


def main():
    print("=" * 60)
    print("Adding author information to Jekyll posts")
    print("=" * 60)

    # ── Step 1: Parse both XML files ──────────────────────────────────
    print("\n[1] Parsing XML exports...")
    creators_2018 = parse_xml_posts(XML_2018)
    creators_2026 = parse_xml_posts(XML_2026)

    # Merge: 2018 takes priority (has real author data), 2026 as fallback
    all_creators = {}
    all_creators.update(creators_2026)
    all_creators.update(creators_2018)
    print(f"  Combined: {len(all_creators)} unique post IDs")

    # ── Step 2: Process English posts ─────────────────────────────────
    print("\n[2] Processing English posts...")
    en_posts_data = {}  # filepath → {wp_post_id, permalink, author}
    updated_en = 0
    unmatched = []
    author_counts = defaultdict(int)

    en_files = sorted(
        f for f in os.listdir(POSTS_EN)
        if os.path.isfile(os.path.join(POSTS_EN, f)) and f.endswith(".html")
    )

    for filename in en_files:
        filepath = os.path.join(POSTS_EN, filename)
        front_matter, body = read_front_matter(filepath)
        if front_matter is None:
            unmatched.append(f"en/{filename} (no front matter)")
            continue

        wp_post_id = extract_field(front_matter, "wp_post_id")
        permalink = extract_field(front_matter, "permalink")

        post_data = {
            "filepath": filepath,
            "filename": filename,
            "wp_post_id": wp_post_id,
            "permalink": permalink,
            "author": None,
        }

        if wp_post_id and wp_post_id in all_creators:
            login = all_creators[wp_post_id]
            display_name = AUTHOR_MAP.get(login)
            if display_name is None:
                unmatched.append(
                    f"en/{filename} (unknown login: '{login}', post_id: {wp_post_id})"
                )
                en_posts_data[filepath] = post_data
                continue

            post_data["author"] = display_name
            new_front_matter = add_author_to_front_matter(front_matter, display_name)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_front_matter + body)

            author_counts[display_name] += 1
            updated_en += 1
        else:
            unmatched.append(
                f"en/{filename} (wp_post_id: {wp_post_id} not found in XML)"
            )

        en_posts_data[filepath] = post_data

    print(f"  Updated: {updated_en} English posts")

    # ── Step 3: Process Spanish posts ─────────────────────────────────
    print("\n[3] Processing Spanish posts...")
    updated_es = 0
    es_translation_pending = []

    es_files = sorted(
        f for f in os.listdir(POSTS_ES)
        if os.path.isfile(os.path.join(POSTS_ES, f)) and f.endswith(".html")
    )

    for filename in es_files:
        filepath = os.path.join(POSTS_ES, filename)
        front_matter, body = read_front_matter(filepath)
        if front_matter is None:
            unmatched.append(f"es/{filename} (no front matter)")
            continue

        wp_post_id = extract_field(front_matter, "wp_post_id")
        translation = extract_field(front_matter, "translation")

        if wp_post_id and wp_post_id in all_creators:
            login = all_creators[wp_post_id]
            display_name = AUTHOR_MAP.get(login)
            if display_name is None:
                unmatched.append(
                    f"es/{filename} (unknown login: '{login}', post_id: {wp_post_id})"
                )
                continue

            new_front_matter = add_author_to_front_matter(front_matter, display_name)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_front_matter + body)

            author_counts[display_name] += 1
            updated_es += 1
        else:
            es_translation_pending.append({
                "filepath": filepath,
                "filename": filename,
                "wp_post_id": wp_post_id,
                "translation": translation,
                "front_matter": front_matter,
                "body": body,
            })

    print(f"  Updated via XML: {updated_es} Spanish posts")

    # ── Step 4: Resolve Spanish posts via translation field ───────────
    print("\n[4] Resolving Spanish posts via translation field...")
    resolved_via_translation = 0

    # Build lookup of English posts by permalink
    en_by_permalink = {}
    for data in en_posts_data.values():
        p = data.get("permalink")
        if p:
            en_by_permalink[p.rstrip("/")] = data

    for pending in es_translation_pending:
        translation = pending["translation"]
        resolved = False

        if translation:
            norm = translation.rstrip("/")
            en_data = en_by_permalink.get(norm)
            if en_data and en_data.get("author"):
                display_name = en_data["author"]
                new_front_matter = add_author_to_front_matter(
                    pending["front_matter"], display_name
                )
                with open(pending["filepath"], "w", encoding="utf-8") as f:
                    f.write(new_front_matter + pending["body"])

                author_counts[display_name] += 1
                updated_es += 1
                resolved_via_translation += 1
                resolved = True

        if not resolved:
            unmatched.append(
                f"es/{pending['filename']} (wp_post_id: {pending['wp_post_id']}, "
                f"translation: {pending['translation']})"
            )

    print(f"  Resolved via translation: {resolved_via_translation}")
    print(f"  Total Spanish posts updated: {updated_es}")

    # ── Step 5: Print summary ─────────────────────────────────────────
    total_updated = updated_en + updated_es

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nTotal posts updated with author: {total_updated}")
    print(f"  English: {updated_en}")
    print(f"  Spanish: {updated_es} ({resolved_via_translation} via translation)")

    print(f"\n--- Author distribution ({len(author_counts)} unique authors) ---")
    for author, count in sorted(author_counts.items(), key=lambda x: -x[1]):
        print(f"  {author:30s} {count:4d} posts")

    if unmatched:
        print(f"\n--- Posts that could not be matched ({len(unmatched)}) ---")
        for msg in sorted(unmatched):
            print(f"  {msg}")
    else:
        print("\nAll posts were matched successfully!")


if __name__ == "__main__":
    main()
