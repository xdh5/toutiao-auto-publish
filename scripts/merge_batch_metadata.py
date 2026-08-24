#!/usr/bin/env python3
"""Merge one generated/published batch into the repository metadata file."""

import argparse
import json
from pathlib import Path


def _read(path):
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_unique(old_items, new_items, key):
    merged = list(old_items or [])
    seen = {key(item) for item in merged}
    for item in new_items or []:
        identity = key(item)
        if identity not in seen:
            merged.append(item)
            seen.add(identity)
    return merged


def merge_metadata(old, new, batch):
    merged = dict(old)
    for field, value in new.items():
        if field not in {"articles", "topics", "micro_posts", "batches_completed"}:
            merged[field] = value

    merged["articles"] = _merge_unique(
        old.get("articles"),
        new.get("articles"),
        lambda item: (
            item.get("title", ""),
            item.get("content_type", ""),
            item.get("batch_name", ""),
        ),
    )
    merged["topics"] = _merge_unique(
        old.get("topics"), new.get("topics"), lambda item: item.get("title", "")
    )

    old_posts = [item for item in old.get("micro_posts", []) if item.get("batch") != batch]
    new_posts = [item for item in new.get("micro_posts", []) if item.get("batch") == batch]
    merged["micro_posts"] = old_posts + new_posts

    completed = set(old.get("batches_completed", []))
    completed.update(new.get("batches_completed", []))
    if batch:
        completed.add(batch)
    merged["batches_completed"] = sorted(completed)
    merged["last_batch"] = batch
    merged["total_articles"] = len(merged["articles"])
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", type=Path)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()

    merged = merge_metadata(_read(args.old), _read(args.new), args.batch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"merged articles={len(merged['articles'])}, "
        f"batches={','.join(merged['batches_completed'])}"
    )


if __name__ == "__main__":
    main()
