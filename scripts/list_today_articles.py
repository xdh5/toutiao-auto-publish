#!/usr/bin/env python3
"""List today's published articles from metadata."""
import json, os, sys
from pathlib import Path

today = sys.argv[1] if len(sys.argv) > 1 else ""
content_app = (os.environ.get("CONTENT_APP") or "finance").strip().lower()
meta_path = Path("output") / content_app / today / "metadata.json"
if not meta_path.exists():
    sys.exit(0)

meta = json.loads(meta_path.read_text())
for a in meta.get("articles", []):
    ct = a.get("content_type", "?")
    title = a.get("title", "?")[:50]
    print(f"  [{ct}] {title}")
