"""Independent streaming audit of a processed hourly dump (no Spark)."""

import gzip
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = json.loads((root / "data/processed/bulk-report.json").read_text())
count = 0
valid = 0
english_views = 0
for name in report["files"]:
    with gzip.open(root / "data/raw/hourly" / name, "rt", encoding="utf-8") as source:
        for line in source:
            count += 1
            parts = line.split()
            if len(parts) == 4:
                try:
                    views, byte_count = int(parts[2]), int(parts[3])
                except ValueError:
                    continue
                if views >= 0 and byte_count >= 0:
                    valid += 1
                    if parts[0] in ("en", "en.m"):
                        english_views += views
assert count == report["records"], (count, report["records"])
assert valid == report["validRecords"], (valid, report["validRecords"])
print(
    json.dumps(
        {
            "sourceRecords": count,
            "validRecords": valid,
            "englishViews": english_views,
            "matchesSparkReport": True,
        },
        indent=2,
    )
)
