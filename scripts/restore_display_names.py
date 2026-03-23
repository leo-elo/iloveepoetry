#!/usr/bin/env python3
"""
restore_display_names.py

Restores original display-name formatting for categories and tags in Jekyll
posts by reading them from the original WordPress XML export.

During WordPress-to-Jekyll migration, categories and tags were slugified:
  "Electronic Literature Collection, Vol. 1" -> "electronic-literature-collection-vol-1"
  "Jim Andrews" (tag) -> "jim-andrews"

This script parses the XML to get original display names and writes them back
into the Jekyll post front matter.
"""

import os
import re
import html
import xml.etree.ElementTree as ET

# -- Configuration ----------------------------------------------------------

XML_PATH = "/Users/floresll/Downloads/ie-poetry.WordPress.2026-03-19.xml"
POST_DIRS = [
    "/Users/floresll/Desktop/iloveepoetry/_posts/en/",
    "/Users/floresll/Desktop/iloveepoetry/_posts/es/",
]

WP_NS = {"wp": "http://wordpress.org/export/1.2/"}

# YAML special characters that require quoting
YAML_SPECIAL_RE = re.compile(r'[,:&#*?|<>=!%@`{}\[\]"\'\\]')


# -- Helpers ----------------------------------------------------------------

def needs_yaml_quoting(value):
    """Return True if the YAML value must be wrapped in double quotes."""
    if YAML_SPECIAL_RE.search(value):
        return True
    # Values starting with special YAML indicators
    if value and value[0] in ("-", "[", "]", "{", "}", ">", "|", "!", "&", "*", "?", "%", "@", "#"):
        return True
    # Strings that look like YAML booleans or null
    if value.lower() in ("true", "false", "yes", "no", "null", "~"):
        return True
    return False


def yaml_format_value(value):
    """Format a value for YAML list output, quoting if necessary."""
    if needs_yaml_quoting(value):
        # Escape any existing double quotes inside the value
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return '"{}"'.format(escaped)
    return value


def extract_yaml_list(fm_text, key):
    """
    Extract a YAML list from front matter text for a given key.
    Returns (list_of_values, start_line_index, end_line_index).
    The line indices are inclusive of the key line and all list item lines.
    """
    lines = fm_text.split("\n")
    start_idx = None
    values = []

    for i, line in enumerate(lines):
        if line.strip() == "{}:".format(key):
            start_idx = i
            continue
        if start_idx is not None and i > start_idx:
            stripped = line.strip()
            if stripped.startswith("- "):
                val = stripped[2:].strip()
                # Remove surrounding quotes if present
                if (val.startswith("'") and val.endswith("'") and len(val) >= 2):
                    val = val[1:-1]
                elif (val.startswith('"') and val.endswith('"') and len(val) >= 2):
                    val = val[1:-1]
                values.append(val)
            else:
                # End of the list
                return values, start_idx, i - 1
    if start_idx is not None:
        return values, start_idx, len(lines) - 1

    return [], -1, -1


def rebuild_yaml_list(key, values):
    """Build YAML list lines for a key."""
    lines = ["{}:".format(key)]
    for v in values:
        lines.append("- {}".format(yaml_format_value(v)))
    return "\n".join(lines)


def get_wp_post_id(fm_text):
    """Extract wp_post_id from front matter text."""
    match = re.search(r'^wp_post_id:\s*(.+)$', fm_text, re.MULTILINE)
    if match:
        val = match.group(1).strip().strip("'\"")
        return val
    return None


# -- Main -------------------------------------------------------------------

def main():
    print("Parsing WordPress XML...")
    tree = ET.parse(XML_PATH)
    root = tree.getroot()

    # Build per-post slug->display mappings keyed by wp_post_id
    # Also build global slug -> display name mappings
    post_cat_maps = {}   # wp_id -> {slug: display_name}
    post_tag_maps = {}   # wp_id -> {slug: display_name}
    global_cat_slug_to_name = {}
    global_tag_slug_to_name = {}

    for item in root.iter("item"):
        status_el = item.find("wp:status", WP_NS)
        post_type_el = item.find("wp:post_type", WP_NS)
        post_id_el = item.find("wp:post_id", WP_NS)

        if status_el is None or post_type_el is None or post_id_el is None:
            continue
        if status_el.text != "publish" or post_type_el.text != "post":
            continue

        wp_id = post_id_el.text
        cat_map = {}
        tag_map = {}

        for cat_el in item.findall("category"):
            domain = cat_el.get("domain")
            nicename = cat_el.get("nicename")
            display_name = cat_el.text
            if not display_name or not nicename:
                continue
            # Decode HTML entities (WordPress double-encodes & as &amp; in CDATA)
            display_name = html.unescape(display_name)

            if domain == "category":
                cat_map[nicename] = display_name
                global_cat_slug_to_name[nicename] = display_name
            elif domain == "post_tag":
                tag_map[nicename] = display_name
                global_tag_slug_to_name[nicename] = display_name

        post_cat_maps[wp_id] = cat_map
        post_tag_maps[wp_id] = tag_map

    print("  Found {} published posts in XML".format(len(post_cat_maps)))
    print("  Global category slug mappings: {}".format(len(global_cat_slug_to_name)))
    print("  Global tag slug mappings: {}".format(len(global_tag_slug_to_name)))

    # -- Process Jekyll posts -----------------------------------------------

    total_processed = 0
    total_cats_restored = 0
    total_tags_restored = 0
    unmapped_slugs = set()
    posts_modified = 0

    for post_dir in POST_DIRS:
        if not os.path.isdir(post_dir):
            print("  WARNING: Directory not found: {}".format(post_dir))
            continue

        for filename in sorted(os.listdir(post_dir)):
            if not filename.endswith(".html") and not filename.endswith(".md"):
                continue

            filepath = os.path.join(post_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.startswith("---"):
                continue

            # Find the front matter boundaries
            # Structure: ---\n{fm_text}\n---\n{body}
            try:
                second_dash = content.index("\n---", 3)
            except ValueError:
                continue

            fm_text = content[4:second_dash]  # skip "---\n", stop before "\n---"
            # body includes everything from "\n---\n" onward (the closing fence and rest)
            # We reconstruct as: "---\n" + new_fm + content[second_dash:]
            after_fm = content[second_dash:]  # starts with "\n---\n..."

            total_processed += 1

            wp_id = get_wp_post_id(fm_text)

            # Get current categories and tags from the front matter
            current_cats, cat_start, cat_end = extract_yaml_list(fm_text, "categories")
            current_tags, tag_start, tag_end = extract_yaml_list(fm_text, "tags")

            if not current_cats and not current_tags:
                continue

            # Get post-specific slug->name maps
            xml_cat_slug_map = post_cat_maps.get(wp_id, {}) if wp_id else {}
            xml_tag_slug_map = post_tag_maps.get(wp_id, {}) if wp_id else {}

            # Resolve each current slug to its display name
            new_cats = []
            cats_changed = False
            for slug in current_cats:
                # Try post-specific mapping first, then global
                if slug in xml_cat_slug_map:
                    display = xml_cat_slug_map[slug]
                elif slug in global_cat_slug_to_name:
                    display = global_cat_slug_to_name[slug]
                else:
                    display = slug  # keep as-is
                    unmapped_slugs.add(("category", slug))
                new_cats.append(display)
                if display != slug:
                    cats_changed = True

            new_tags = []
            tags_changed = False
            for slug in current_tags:
                if slug in xml_tag_slug_map:
                    display = xml_tag_slug_map[slug]
                elif slug in global_tag_slug_to_name:
                    display = global_tag_slug_to_name[slug]
                else:
                    display = slug
                    unmapped_slugs.add(("tag", slug))
                new_tags.append(display)
                if display != slug:
                    tags_changed = True

            if not cats_changed and not tags_changed:
                continue

            # Rebuild the front matter with new categories/tags
            fm_lines = fm_text.split("\n")

            # Collect replacements
            replacements = []
            if tags_changed and tag_start >= 0:
                new_tag_block = rebuild_yaml_list("tags", new_tags)
                replacements.append((tag_start, tag_end, new_tag_block))
                total_tags_restored += sum(1 for o, n in zip(current_tags, new_tags) if o != n)

            if cats_changed and cat_start >= 0:
                new_cat_block = rebuild_yaml_list("categories", new_cats)
                replacements.append((cat_start, cat_end, new_cat_block))
                total_cats_restored += sum(1 for o, n in zip(current_cats, new_cats) if o != n)

            # Sort by start index descending so we replace from bottom up
            replacements.sort(key=lambda r: r[0], reverse=True)

            for start, end, new_block in replacements:
                new_lines = new_block.split("\n")
                fm_lines[start:end + 1] = new_lines

            new_fm = "\n".join(fm_lines)
            # Reconstruct: "---\n" + new front matter + original closing "\n---\n" + body
            new_content = "---\n" + new_fm + after_fm

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)

            posts_modified += 1

    # -- Summary ------------------------------------------------------------

    print("")
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Total posts processed:      {}".format(total_processed))
    print("Posts modified:              {}".format(posts_modified))
    print("Total categories restored:  {}".format(total_cats_restored))
    print("Total tags restored:        {}".format(total_tags_restored))

    if unmapped_slugs:
        print("")
        print("Unmapped slugs ({}):".format(len(unmapped_slugs)))
        for domain, slug in sorted(unmapped_slugs):
            print("  [{}] {}".format(domain, slug))
    else:
        print("")
        print("All slugs were successfully mapped!")


if __name__ == "__main__":
    main()
