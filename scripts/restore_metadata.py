#!/usr/bin/env python3
"""
restore_metadata.py

Extracts Dublin Core metadata from WordPress XML export and adds it
to Jekyll post front matter as a `metadata` dictionary.

For Spanish posts that share a translation link with an English post,
Dublin Core metadata is copied from the English counterpart if the
Spanish post itself has none in the XML.
"""

import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

# -- Configuration --

XML_PATH = "/Users/floresll/Downloads/ie-poetry.WordPress.2026-03-19.xml"
EN_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
ES_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"

DC_FIELDS = [
    "dublin_core_author",
    "dublin_core_contributor",
    "dublin_core_coverage",
    "dublin_core_description",
    "dublin_core_format",
    "dublin_core_language",
    "dublin_core_publisher",
    "dublin_core_relation",
    "dublin_core_rights",
    "dublin_core_source",
    "dublin_core_subject",
    "dublin_core_title",
    "dublin_core_type",
]

# Placeholder values that should be treated as empty
PLACEHOLDER_VALUES = {
    "Enter author here",
    "Enter comma separated keywords here",
    "Enter title here",
    "Enter description here",
    "Enter type here",
    "Enter source here",
    "Enter coverage here",
    "Enter relation here",
    "Enter publisher here",
    "Enter contributor here",
    "Enter rights here",
    "Enter format here",
    "Language will appear here",
}

NS = {"wp": "http://wordpress.org/export/1.2/"}


# -- Step 1: Parse the WordPress XML --

def parse_xml_dublin_core(xml_path):
    """
    Parse the WordPress XML and return a dict mapping
    wp_post_id (str) -> dict of {dc_fieldname: value}.
    Only fields with meaningful content are included.
    """
    print(f"Parsing XML file: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    channel = root.find("channel")
    items = channel.findall("item")
    print(f"  Total <item> elements in XML: {len(items)}")

    dc_by_post_id = {}
    total_with_dc = 0

    for item in items:
        post_id_el = item.find("wp:post_id", NS)
        if post_id_el is None or not post_id_el.text:
            continue
        post_id = post_id_el.text.strip()

        metas = item.findall("wp:postmeta", NS)
        dc_data = {}

        for meta in metas:
            key_el = meta.find("wp:meta_key", NS)
            val_el = meta.find("wp:meta_value", NS)
            if key_el is None or not key_el.text:
                continue
            key = key_el.text.strip()
            if key not in DC_FIELDS:
                continue

            raw_val = val_el.text if val_el is not None and val_el.text else ""
            val = raw_val.strip()

            # Skip empty, whitespace-only, or placeholder values
            if not val or val in PLACEHOLDER_VALUES:
                continue

            # Convert dublin_core_xyz -> dc_xyz
            short_key = "dc_" + key[len("dublin_core_"):]
            dc_data[short_key] = val

        if dc_data:
            dc_by_post_id[post_id] = dc_data
            total_with_dc += 1

    print(f"  Posts with meaningful Dublin Core metadata: {total_with_dc}")
    return dc_by_post_id


# -- Step 2 & 3: Read Jekyll posts, match, and update --

def read_post(filepath):
    """Read a Jekyll post and return (front_matter_str, body_str).
    Returns (None, None) if the front matter cannot be parsed."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # Match the YAML front matter between --- delimiters
    m = re.match(r"^(---\n)(.*?\n)(---\n?)", content, re.DOTALL)
    if not m:
        return None, None
    fm_body = m.group(2)
    rest = content[m.end():]
    return fm_body, rest


def extract_yaml_field(fm_text, field_name):
    """Extract a simple scalar value from YAML front matter text."""
    pattern = rf"^{re.escape(field_name)}:\s*(.+)$"
    m = re.search(pattern, fm_text, re.MULTILINE)
    if m:
        val = m.group(1).strip().strip("'").strip('"')
        return val
    return None


def yaml_escape(value):
    """
    Escape a value for safe YAML output.
    If the value contains characters that could break YAML parsing,
    wrap it in double quotes with internal double-quotes escaped.
    """
    needs_quoting = False
    if any(ch in value for ch in [':', '#', '{', '}', '[', ']', ',', '&', '*',
                                   '?', '|', '-', '<', '>', '=', '!', '%',
                                   '@', '`', '"', "'"]):
        needs_quoting = True
    if value.startswith((' ', '\t')) or value.endswith((' ', '\t')):
        needs_quoting = True
    if value.lower() in ('true', 'false', 'yes', 'no', 'null', 'on', 'off'):
        needs_quoting = True
    # If it looks like a number, quote it
    try:
        float(value)
        needs_quoting = True
    except ValueError:
        pass

    if needs_quoting:
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return value


def build_metadata_yaml(dc_data):
    """
    Build the YAML block for metadata, like:
      metadata:
        dc_author: "Author Name"
        dc_title: "Work Title"
    """
    lines = ["metadata:"]
    for key in sorted(dc_data.keys()):
        val = dc_data[key]
        lines.append(f"  {key}: {yaml_escape(val)}")
    return "\n".join(lines) + "\n"


def add_metadata_to_frontmatter(fm_text, dc_data):
    """
    Add metadata block to the end of the front matter text.
    Returns the new front matter text.
    """
    metadata_block = build_metadata_yaml(dc_data)
    if not fm_text.endswith("\n"):
        fm_text += "\n"
    return fm_text + metadata_block


def process_posts(posts_dir, dc_by_post_id, label=""):
    """
    Process all Jekyll posts in a directory.
    Returns:
      - updated_posts: list of (filename, wp_post_id)
      - post_info: dict of wp_post_id -> {permalink, filepath, translation, filename}
      - no_dc_posts: list of (filename, wp_post_id)
    """
    updated_posts = []
    no_dc_posts = []
    post_info = {}

    for fn in sorted(os.listdir(posts_dir)):
        filepath = os.path.join(posts_dir, fn)
        if not os.path.isfile(filepath):
            continue

        fm_text, body = read_post(filepath)
        if fm_text is None:
            continue

        wp_post_id = extract_yaml_field(fm_text, "wp_post_id")
        permalink = extract_yaml_field(fm_text, "permalink")
        translation = extract_yaml_field(fm_text, "translation")

        if wp_post_id:
            post_info[wp_post_id] = {
                "filepath": filepath,
                "filename": fn,
                "permalink": permalink,
                "translation": translation,
            }

        if not wp_post_id or wp_post_id not in dc_by_post_id:
            if wp_post_id:
                no_dc_posts.append((fn, wp_post_id))
            continue

        dc_data = dc_by_post_id[wp_post_id]
        new_fm = add_metadata_to_frontmatter(fm_text, dc_data)

        # Write the updated file
        new_content = "---\n" + new_fm + "---\n" + body
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        updated_posts.append((fn, wp_post_id))

    return updated_posts, post_info, no_dc_posts


def process_spanish_translations(es_post_info, en_post_info, dc_by_post_id):
    """
    For Spanish posts without Dublin Core metadata that have a `translation`
    field pointing to an English post, copy DC metadata from the English counterpart.
    Returns list of (filename, es_wp_post_id, en_wp_post_id).
    """
    # Build a map: English permalink -> English wp_post_id
    en_permalink_to_id = {}
    for wp_id, info in en_post_info.items():
        if info["permalink"]:
            perm = info["permalink"]
            en_permalink_to_id[perm] = wp_id
            stripped = perm.rstrip("/")
            en_permalink_to_id[stripped] = wp_id
            en_permalink_to_id[stripped + "/"] = wp_id

    inherited_posts = []

    for es_wp_id, es_info in es_post_info.items():
        # Skip if this Spanish post already has DC metadata in the XML
        if es_wp_id in dc_by_post_id:
            continue

        translation = es_info.get("translation")
        if not translation:
            continue

        # Find the corresponding English post's wp_post_id
        en_wp_id = en_permalink_to_id.get(translation)
        if not en_wp_id:
            en_wp_id = en_permalink_to_id.get(translation.rstrip("/"))
        if not en_wp_id:
            en_wp_id = en_permalink_to_id.get(translation.rstrip("/") + "/")

        if not en_wp_id or en_wp_id not in dc_by_post_id:
            continue

        dc_data = dc_by_post_id[en_wp_id]
        filepath = es_info["filepath"]

        fm_text, body = read_post(filepath)
        if fm_text is None:
            continue

        # Safety check: skip if metadata was already added
        if "metadata:" in fm_text:
            continue

        new_fm = add_metadata_to_frontmatter(fm_text, dc_data)
        new_content = "---\n" + new_fm + "---\n" + body
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        inherited_posts.append((es_info["filename"], es_wp_id, en_wp_id))

    return inherited_posts


# -- Step 5: Print summary --

def print_summary(dc_by_post_id, en_updated, es_updated, es_inherited,
                  en_no_dc, es_no_dc, en_post_info, es_post_info):
    """Print a comprehensive summary of what was done."""

    print("\n" + "=" * 70)
    print("DUBLIN CORE METADATA RESTORATION - SUMMARY")
    print("=" * 70)

    print(f"\n[XML Data]")
    print(f"  Posts with meaningful Dublin Core metadata in XML: {len(dc_by_post_id)}")

    # Field frequency
    field_counts = defaultdict(int)
    for dc_data in dc_by_post_id.values():
        for key in dc_data:
            field_counts[key] += 1

    print(f"\n[Dublin Core Field Frequency]")
    for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
        print(f"  {field}: {count}")

    # Posts updated
    total_updated = len(en_updated) + len(es_updated) + len(es_inherited)
    print(f"\n[Posts Updated]")
    print(f"  English posts updated (direct match):  {len(en_updated)}")
    print(f"  Spanish posts updated (direct match):  {len(es_updated)}")
    print(f"  Spanish posts updated (from EN translation): {len(es_inherited)}")
    print(f"  Total posts updated: {total_updated}")

    if en_updated:
        print(f"\n  English posts updated:")
        for fn, wp_id in en_updated:
            print(f"    - {fn} (wp_post_id={wp_id})")

    if es_updated:
        print(f"\n  Spanish posts updated (direct):")
        for fn, wp_id in es_updated:
            print(f"    - {fn} (wp_post_id={wp_id})")

    if es_inherited:
        print(f"\n  Spanish posts updated (inherited from English):")
        for fn, es_id, en_id in es_inherited:
            print(f"    - {fn} (es_wp_id={es_id}, from en_wp_id={en_id})")

    # Posts with no DC metadata
    total_en = len(en_post_info)
    total_es = len(es_post_info)
    en_without = total_en - len(en_updated)
    es_without = total_es - len(es_updated) - len(es_inherited)

    print(f"\n[Posts Without Dublin Core Metadata]")
    print(f"  English posts: {total_en} total, {en_without} without metadata")
    print(f"  Spanish posts: {total_es} total, {es_without} without metadata")
    print(f"  Combined: {en_without + es_without} posts have no Dublin Core metadata")

    print("\n" + "=" * 70)
    print("Done.")


# -- Main --

def main():
    # Step 1: Parse XML
    dc_by_post_id = parse_xml_dublin_core(XML_PATH)

    # Step 2: Process English posts
    print(f"\nProcessing English posts in: {EN_DIR}")
    en_updated, en_post_info, en_no_dc = process_posts(EN_DIR, dc_by_post_id, "EN")
    print(f"  Updated: {len(en_updated)}, No DC data: {len(en_no_dc)}")

    # Step 2: Process Spanish posts (direct match)
    print(f"\nProcessing Spanish posts in: {ES_DIR}")
    es_updated, es_post_info, es_no_dc = process_posts(ES_DIR, dc_by_post_id, "ES")
    print(f"  Updated: {len(es_updated)}, No DC data: {len(es_no_dc)}")

    # Step 3: Inherit DC metadata from English translations for Spanish posts
    print(f"\nChecking Spanish posts for inherited DC metadata from English translations...")
    es_inherited = process_spanish_translations(es_post_info, en_post_info, dc_by_post_id)
    print(f"  Inherited: {len(es_inherited)}")

    # Step 5: Summary
    print_summary(dc_by_post_id, en_updated, es_updated, es_inherited,
                  en_no_dc, es_no_dc, en_post_info, es_post_info)


if __name__ == "__main__":
    main()
