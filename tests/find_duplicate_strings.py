#!/usr/bin/env python3
import json
from collections import defaultdict

with open("src/translations/en.json") as f:
    data = json.load(f)

duplicates = defaultdict(list)
for key, value in data.items():
    duplicates[value].append(key)

for value, keys in duplicates.items():
    if len(keys) > 1:
        print(f"'{value}' -> {keys}")
