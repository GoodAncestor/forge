"""Fetch Chronicling America OCR text, 1930-1963, into the forge data root.
Sequential + rate-limited (LoC etiquette). Resumable: keeps a done-pages file."""
import json
import time
from pathlib import Path

import requests

from forge import config

BASE = "https://chroniclingamerica.loc.gov/search/pages/results/"
PARAMS = {"date1": "1930", "date2": "1963", "dateFilterType": "yearRange",
          "format": "json", "rows": 100}
DEST = Path(config.DATA_ROOT) / "chronicling-america"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    done_file = DEST / ".done-pages"
    done = set(done_file.read_text().split()) if done_file.exists() else set()
    page = 1
    while True:
        r = requests.get(BASE, params={**PARAMS, "page": page}, timeout=60)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            break
        batch = []
        for it in items:
            pid = it.get("id", "")
            if pid in done or not it.get("ocr_eng"):
                continue
            batch.append({"id": pid, "date": it.get("date"),
                          "title": it.get("title"), "text": it["ocr_eng"]})
            done.add(pid)
        if batch:
            out = DEST / f"batch-{page:06d}.jsonl"
            out.write_text("\n".join(json.dumps(b) for b in batch))
            done_file.write_text("\n".join(sorted(done)))
        page += 1
        time.sleep(1.0)  # polite pacing


if __name__ == "__main__":
    main()
