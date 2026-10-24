# Reference observations

This is a real, freely obtained Wikimedia Analytics API snapshot, not generated demo data.

- `pageviews.jsonl`: 2,850 records, three curated events, 19 topics each, 50 UTC days per topic.
- `manifest.json`: exact public request URLs, per-response hashes, cache fetch times, assembly time, and input hash.
- License: CC0, per https://dumps.wikimedia.org/other/pageviews/readme.html.

Rebuild the analytics without network access to Wikimedia:

```bash
make reproduce
```

Dependencies must already be installed. To retrieve current source responses, use `make data` (which populates the ignored `data/raw` cache). Updating this reference snapshot is a deliberate separate action; fresh downloads do not silently replace it.

The large hourly dump is not included in Git. `make bulk` downloads it freely, and `docs/bulk-source-manifest.json` records the verified original file's hash.
