#!/usr/bin/env python3

"""
Translation System Tests
Tests for translation file integrity, duplicate keys, and key consistency
"""

import json
import os
import sys
from collections import Counter

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.language import detect_user_language


def load_translation_file(file_path):
    """Load and parse a translation JSON file"""
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Translation file not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {file_path}: {e}")
        return None


def check_duplicate_keys(file_path, translations):
    """Check for duplicate keys in translation file"""
    print(f"🔍 Checking for duplicate keys in {os.path.basename(file_path)}...")

    # Read raw file content to check for duplicates
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return False

    # Extract all keys from the raw JSON content
    keys = []
    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if line.startswith('"') and '":' in line:
            # Extract key from line like "key": "value"
            key_end = line.find('":')
            if key_end > 0:
                key = line[1:key_end]  # Remove opening quote
                keys.append((key, line_num))

    # Check for duplicates
    key_counts = Counter([key for key, _ in keys])
    duplicates = {key: count for key, count in key_counts.items() if count > 1}

    if duplicates:
        print(f"❌ Found duplicate keys in {os.path.basename(file_path)}:")
        for key, count in duplicates.items():
            print(f"   - '{key}' appears {count} times")
            # Show line numbers where duplicates occur
            duplicate_lines = [line_num for k, line_num in keys if k == key]
            print(f"     Lines: {', '.join(map(str, duplicate_lines))}")
        return False

    print(f"✅ No duplicate keys found in {os.path.basename(file_path)}")
    return True


def check_key_consistency(en_translations, nl_translations):
    """Check that both translation files have the same keys"""
    print("🔍 Checking key consistency between en.json and nl.json...")

    en_keys = set(en_translations.keys())
    nl_keys = set(nl_translations.keys())

    # Keys in English but not in Dutch
    missing_in_nl = en_keys - nl_keys
    # Keys in Dutch but not in English
    missing_in_en = nl_keys - en_keys

    success = True

    if missing_in_nl:
        print("❌ Keys present in en.json but missing in nl.json:")
        for key in sorted(missing_in_nl):
            print(f"   - '{key}'")
        success = False

    if missing_in_en:
        print("❌ Keys present in nl.json but missing in en.json:")
        for key in sorted(missing_in_en):
            print(f"   - '{key}'")
        success = False

    if success:
        print("✅ All keys are consistent between translation files")
        print(f"   Total keys: {len(en_keys)}")

    return success


def check_translation_placeholders(en_translations, nl_translations):
    """Check that placeholders in translations match between languages"""
    print("🔍 Checking placeholder consistency...")

    import re

    placeholder_pattern = r"\{[^}]+\}"

    mismatched = []

    for key in en_translations:
        if key not in nl_translations:
            continue

        en_text = en_translations[key]
        nl_text = nl_translations[key]

        en_placeholders = set(re.findall(placeholder_pattern, en_text))
        nl_placeholders = set(re.findall(placeholder_pattern, nl_text))

        if en_placeholders != nl_placeholders:
            mismatched.append({"key": key, "en_placeholders": en_placeholders, "nl_placeholders": nl_placeholders})

    if mismatched:
        print("❌ Placeholder mismatches found:")
        for item in mismatched:
            print(f"   - '{item['key']}':")
            print(f"     EN: {item['en_placeholders']}")
            print(f"     NL: {item['nl_placeholders']}")
        return False

    print("✅ All placeholders are consistent between languages")
    return True


def test_language_detection():
    """Test the language detection function"""
    print("🔍 Testing language detection...")

    test_cases = [
        ({"language_code": "nl"}, "nl"),
        ({"language_code": "nl-NL"}, "nl"),
        ({"language_code": "en"}, "en"),
        ({"language_code": "en-US"}, "en"),
        ({"language_code": "fr"}, "nl"),  # Default to Dutch
        ({}, "nl"),  # Default to Dutch
    ]

    success = True
    for user_data, expected in test_cases:
        result = detect_user_language(user_data)
        if result != expected:
            print(f"❌ Language detection failed for {user_data}: expected {expected}, got {result}")
            success = False

    if success:
        print("✅ Language detection working correctly")

    assert success, "Language detection tests failed"


def check_translation_structure():
    """Check that translation values are properly formatted strings"""
    print("🔍 Checking translation value structure...")

    translations_dir = os.path.join(os.path.dirname(__file__), "..", "src", "translations")

    success = True
    for lang in ["en", "nl"]:
        file_path = os.path.join(translations_dir, f"{lang}.json")
        translations = load_translation_file(file_path)

        if not translations:
            success = False
            continue

        for key, value in translations.items():
            if not isinstance(value, str):
                print(f"❌ Non-string value in {lang}.json for key '{key}': {type(value)}")
                success = False
            elif not value.strip():
                print(f"❌ Empty value in {lang}.json for key '{key}'")
                success = False

    if success:
        print("✅ All translation values are properly formatted strings")

    return success


def main():
    """Run all translation tests"""
    print("🧪 Running Translation System Tests\n")

    # Get translation file paths
    translations_dir = os.path.join(os.path.dirname(__file__), "..", "src", "translations")
    en_file = os.path.join(translations_dir, "en.json")
    nl_file = os.path.join(translations_dir, "nl.json")

    # Load translation files
    en_translations = load_translation_file(en_file)
    nl_translations = load_translation_file(nl_file)

    if not en_translations or not nl_translations:
        print("💥 Failed to load translation files")
        return 1

    # Run all tests
    tests = [
        lambda: check_duplicate_keys(en_file, en_translations),
        lambda: check_duplicate_keys(nl_file, nl_translations),
        lambda: check_key_consistency(en_translations, nl_translations),
        lambda: check_translation_placeholders(en_translations, nl_translations),
        lambda: check_translation_structure(),
        lambda: test_language_detection(),
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
            print()  # Add spacing between tests
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            print()

    print(f"📊 Results: {passed}/{total} tests passed")

    if passed != total:
        print("💥 Some translation tests failed!")
        return 1

    print("🎉 All translation tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
