#!/usr/bin/env python3
"""
Validate the generated Jekyll site:
1. Post count verification
2. Front matter validation
3. Image reference checking
4. Duplicate permalink detection
5. Encoding checks
6. Empty content detection
7. Date validity
"""

import json
import os
import re
import sys
import logging
from pathlib import Path
from datetime import datetime

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
POSTS_DIR = PROJECT_DIR / "_posts"
PAGES_DIR = PROJECT_DIR / "_pages"
ASSETS_DIR = PROJECT_DIR / "assets" / "images"
REPORT_FILE = SCRIPTS_DIR / "validation_report.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

REQUIRED_POST_FIELDS = ["layout", "title", "date", "lang", "permalink"]
REQUIRED_PAGE_FIELDS = ["layout", "title", "lang", "permalink"]


def collect_files():
    """Collect all generated Jekyll files."""
    files = {"posts_en": [], "posts_es": [], "pages_en": [], "pages_es": []}

    for lang in ["en", "es"]:
        post_dir = POSTS_DIR / lang
        if post_dir.exists():
            files[f"posts_{lang}"] = sorted(post_dir.glob("*.html"))

        page_dir = PAGES_DIR / lang
        if page_dir.exists():
            files[f"pages_{lang}"] = sorted(page_dir.glob("*.html"))

    return files


def parse_file(filepath):
    """Parse a Jekyll file and return (front_matter, body, errors)."""
    errors = []
    content = filepath.read_text(encoding="utf-8", errors="replace")

    parts = content.split("---", 2)
    if len(parts) < 3:
        errors.append("Missing or malformed front matter delimiters")
        return None, content, errors

    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error: {e}")
        return None, parts[2] if len(parts) > 2 else "", errors

    if fm is None:
        errors.append("Empty front matter")
        return {}, parts[2], errors

    body = parts[2]
    return fm, body, errors


def check_required_fields(fm, required_fields, filepath):
    """Check that required front matter fields are present."""
    errors = []
    for field in required_fields:
        if field not in fm or fm[field] is None or fm[field] == "":
            errors.append(f"Missing required field: {field}")
    return errors


def check_date(fm, filepath):
    """Validate the date field."""
    errors = []
    date_val = fm.get("date")
    if date_val is None:
        return ["Missing date"]

    try:
        if isinstance(date_val, datetime):
            d = date_val
        elif isinstance(date_val, str):
            d = datetime.fromisoformat(date_val.replace(" ", "T"))
        else:
            d = datetime.fromisoformat(str(date_val))

        if d.year < 2000 or d.year > 2027:
            errors.append(f"Date out of expected range: {d.year}")
    except (ValueError, TypeError) as e:
        errors.append(f"Invalid date format: {date_val} ({e})")

    return errors


def check_images(body, filepath):
    """Check that image references in content point to existing files."""
    errors = []
    warnings = []
    baseurl = "/iloveepoetry"

    img_pattern = re.compile(r'(?:src|href)=["\']([^"\']+)["\']', re.I)

    for match in img_pattern.finditer(body):
        url = match.group(1)

        # Only check local image references
        if url.startswith(baseurl + "/assets/images/"):
            local_path = PROJECT_DIR / url.replace(baseurl + "/", "")
            if not local_path.exists():
                warnings.append(f"Missing local image: {url}")
        elif url.startswith("/assets/images/"):
            local_path = PROJECT_DIR / url.lstrip("/")
            if not local_path.exists():
                warnings.append(f"Missing local image: {url}")

    return errors, warnings


def check_encoding(body, filepath):
    """Check for encoding issues in content."""
    errors = []

    # Double-encoded entities
    if "&amp;amp;" in body:
        errors.append("Double-encoded ampersand (&amp;amp;)")
    if "&amp;lt;" in body:
        errors.append("Double-encoded less-than (&amp;lt;)")
    if "&amp;gt;" in body:
        errors.append("Double-encoded greater-than (&amp;gt;)")
    if "&amp;#" in body:
        errors.append("Double-encoded numeric entity (&amp;#...)")

    # Stray CDATA markers
    if "CDATA[" in body or "]]>" in body:
        errors.append("Stray CDATA markers in content")

    return errors


def check_empty_content(body, filepath):
    """Check for empty or trivially short content."""
    # Strip HTML tags and whitespace
    text = re.sub(r'<[^>]+>', '', body)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) == 0:
        return ["Empty content (no text after stripping HTML)"]
    if len(text) < 10:
        return [f"Very short content ({len(text)} chars): '{text[:50]}'"]
    return []


def check_permalink_duplicates(all_permalinks):
    """Check for duplicate permalinks."""
    seen = {}
    duplicates = []
    for filepath, permalink in all_permalinks:
        if permalink in seen:
            duplicates.append(f"Duplicate permalink '{permalink}': {filepath.name} and {seen[permalink].name}")
        else:
            seen[permalink] = filepath
    return duplicates


def main():
    logger.info("=== Validation Script ===")

    files = collect_files()
    total_posts = len(files["posts_en"]) + len(files["posts_es"])
    total_pages = len(files["pages_en"]) + len(files["pages_es"])

    logger.info(f"English posts: {len(files['posts_en'])}")
    logger.info(f"Spanish posts: {len(files['posts_es'])}")
    logger.info(f"English pages: {len(files['pages_en'])}")
    logger.info(f"Spanish pages: {len(files['pages_es'])}")
    logger.info(f"Total posts: {total_posts}")
    logger.info(f"Total pages: {total_pages}")

    report = {
        "counts": {
            "posts_en": len(files["posts_en"]),
            "posts_es": len(files["posts_es"]),
            "pages_en": len(files["pages_en"]),
            "pages_es": len(files["pages_es"]),
            "total_posts": total_posts,
            "total_pages": total_pages,
        },
        "checks": {},
        "errors": [],
        "warnings": [],
    }

    all_permalinks = []
    files_with_errors = 0
    files_with_warnings = 0

    # Process all files
    all_files = []
    for key in ["posts_en", "posts_es", "pages_en", "pages_es"]:
        is_post = "posts" in key
        required = REQUIRED_POST_FIELDS if is_post else REQUIRED_PAGE_FIELDS
        for fp in files[key]:
            all_files.append((fp, required, key))

    for filepath, required_fields, category in all_files:
        file_errors = []
        file_warnings = []

        fm, body, parse_errors = parse_file(filepath)
        file_errors.extend(parse_errors)

        if fm is not None:
            # Required fields
            file_errors.extend(check_required_fields(fm, required_fields, filepath))

            # Date validation
            if "posts" in category:
                file_errors.extend(check_date(fm, filepath))

            # Permalink tracking
            permalink = fm.get("permalink", "")
            if permalink:
                all_permalinks.append((filepath, permalink))

            # Image references
            img_errors, img_warnings = check_images(body, filepath)
            file_errors.extend(img_errors)
            file_warnings.extend(img_warnings)

            # Encoding
            file_errors.extend(check_encoding(body, filepath))

            # Empty content
            file_errors.extend(check_empty_content(body, filepath))

        if file_errors:
            files_with_errors += 1
            for err in file_errors:
                report["errors"].append(f"{filepath.name}: {err}")

        if file_warnings:
            files_with_warnings += 1
            for warn in file_warnings:
                report["warnings"].append(f"{filepath.name}: {warn}")

    # Duplicate permalink check
    duplicates = check_permalink_duplicates(all_permalinks)
    if duplicates:
        for dup in duplicates:
            report["errors"].append(f"DUPLICATE: {dup}")

    # Summary checks
    report["checks"] = {
        "post_count_expected": 1297,
        "post_count_actual": total_posts,
        "post_count_match": total_posts >= 1200,  # Allow some tolerance
        "files_with_errors": files_with_errors,
        "files_with_warnings": files_with_warnings,
        "duplicate_permalinks": len(duplicates),
        "total_errors": len(report["errors"]),
        "total_warnings": len(report["warnings"]),
    }

    # Write report
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    logger.info("=== Validation Results ===")
    logger.info(f"Post count: {total_posts} (expected ~1297)")
    logger.info(f"Page count: {total_pages}")
    logger.info(f"Files with errors: {files_with_errors}")
    logger.info(f"Files with warnings: {files_with_warnings}")
    logger.info(f"Duplicate permalinks: {len(duplicates)}")
    logger.info(f"Total errors: {len(report['errors'])}")
    logger.info(f"Total warnings: {len(report['warnings'])}")

    if report["errors"]:
        logger.error("Sample errors:")
        for err in report["errors"][:20]:
            logger.error(f"  {err}")
        if len(report["errors"]) > 20:
            logger.error(f"  ... and {len(report['errors']) - 20} more")

    logger.info(f"Full report: {REPORT_FILE}")

    # Exit code
    if files_with_errors > 0:
        logger.warning("Validation completed with errors")
        return 1
    logger.info("Validation passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
