"""Fetch English and Japanese common names for the 109 species (one-off, needs internet).

Source per species: the English Wikipedia article in master CSV column wiki_url.
English name = article title (as Wikipedia shows it), Japanese name = the
interlanguage link to ja.wikipedia. Nothing is invented: a missing name stays
empty and the page falls back to the scientific name.

    /opt/anaconda3/bin/python3 scripts/hole_artnamen.py
Writes data/processed/hai_namen.csv. Exit 0 = all 109 rows written.
"""

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER_CSV = ROOT / "data" / "processed" / "hai_tiefenmodell_master.csv"
OUT_CSV = ROOT / "data" / "processed" / "hai_namen.csv"
API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "muros-week-shark-model/1.0 (educational exhibit)"}


def title_from_url(url):
    return urllib.parse.unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")


def fetch(titles):
    """Return {requested title: (resolved title, ja title or '')}."""
    params = {
        "action": "query", "format": "json", "redirects": 1, "prop": "langlinks",
        "lllang": "ja", "lllimit": "max", "titles": "|".join(titles),
    }
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as fh:
        data = json.load(fh)["query"]
    alias = {t: t for t in titles}
    for key in ("normalized", "redirects"):
        for m in data.get(key, []):
            for req_t, cur in list(alias.items()):
                if cur == m["from"]:
                    alias[req_t] = m["to"]
    pages = {p["title"]: p for p in data["pages"].values()}
    out = {}
    for req_t, resolved in alias.items():
        p = pages.get(resolved)
        if not p or "missing" in p:
            out[req_t] = ("", "")
            continue
        ja = next((ll["*"] for ll in p.get("langlinks", []) if ll["lang"] == "ja"), "")
        out[req_t] = (p["title"], ja)
    return out


def main():
    with MASTER_CSV.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    titles = {r["led_id"]: title_from_url(r["wiki_url"]) for r in rows if r["wiki_url"].strip()}
    found = {}
    uniq = sorted(set(titles.values()))
    for i in range(0, len(uniq), 40):
        found.update(fetch(uniq[i:i + 40]))
        time.sleep(1)
    out = []
    for r in rows:
        t = titles.get(r["led_id"], "")
        en, ja = found.get(t, ("", ""))
        # An article titled with the scientific name has no English common name.
        if en.lower() == r["species"].lower():
            en = ""
        out.append({"led_id": r["led_id"], "species": r["species"], "name_en": en,
                    "name_ja": ja, "quelle": f"en.wikipedia: {t}" if t else ""})
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    n_en = sum(1 for o in out if o["name_en"])
    n_ja = sum(1 for o in out if o["name_ja"])
    print(f"rows {len(out)}, English names {n_en}, Japanese names {n_ja} -> {OUT_CSV}")
    return 0 if len(out) == 109 else 1


if __name__ == "__main__":
    sys.exit(main())
