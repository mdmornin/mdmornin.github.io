#!/usr/bin/env python3
"""Fetch publications for Mitchell D. Morningstar from OpenAlex and render them.

Writes:
  data/publications.json  - normalised publication list + citation metrics
  index.html              - the block between the PUBLICATIONS / METRICS markers

Manual corrections live in data/publications_overrides.json (hide a DOI, mark
co-first authorship, attach code links, add something OpenAlex is missing).

Standard library only, so it runs anywhere: `python scripts/update_publications.py`
Optional env vars: OPENALEX_API_KEY, OPENALEX_MAILTO.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ORCID = "0000-0002-3847-192X"
SELF_NAME = "Morningstar"

ROOT = Path(__file__).resolve().parent.parent
DATA_JSON = ROOT / "data" / "publications.json"
OVERRIDES_JSON = ROOT / "data" / "publications_overrides.json"
INDEX_HTML = ROOT / "index.html"

API = "https://api.openalex.org"
KEEP_TYPES = {"article", "review", "preprint", "letter", "book-chapter", "dissertation"}
PARTICLES = {"de", "da", "del", "della", "di", "du", "van", "von", "der", "den", "la", "le", "dos", "das"}
SERVER = re.compile(r"biorxiv|medrxiv|arxiv|psyarxiv|research square|ssrn", re.I)
TYPE_LABELS = {
    "article": "Article",
    "review": "Review",
    "letter": "Letter",
    "book-chapter": "Chapter",
    "preprint": "Preprint",
    "dissertation": "Thesis",
}


# --------------------------------------------------------------------------- fetch

def _get(path: str, params: dict) -> dict:
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    if os.environ.get("OPENALEX_MAILTO"):
        params["mailto"] = os.environ["OPENALEX_MAILTO"]
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "mdmornin.github.io publication updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_author() -> dict:
    return _get(f"/authors/orcid:{ORCID}", {})


def fetch_works(author_id: str) -> list[dict]:
    works, cursor = [], "*"
    while cursor:
        page = _get("/works", {
            "filter": f"author.id:{author_id}",
            "per-page": 100,
            "cursor": cursor,
            "sort": "publication_date:desc",
        })
        works += page["results"]
        cursor = page["meta"].get("next_cursor") if page["results"] else None
    return works


# ----------------------------------------------------------------------- normalise

def bare_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip()).lower()


def short_name(display: str) -> str:
    """'Mitchell D. Morningstar' -> 'Morningstar MD'."""
    parts = display.replace(".", " ").split()
    if len(parts) < 2:
        return display
    i = len(parts) - 1
    while i > 1 and parts[i - 1].lower() in PARTICLES:  # "Elisa De Falco" -> "De Falco E"
        i -= 1
    last = " ".join(parts[i:])
    initials = "".join(p[0].upper() for p in parts[:i] if p[0].isalpha())
    return f"{last} {initials}"


def page_range(first: str | None, last: str | None) -> str:
    if first and last and first != last:
        # OpenAlex sometimes splits article ids like "ENEURO.0379-24.2024" on the hyphen.
        return f"{first}–{last}" if first.isdigit() and last.isdigit() else ""
    return first or ""


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"<[^>]+>", "", t or "").lower()).strip()


def is_meeting_abstract(w: dict) -> bool:
    # Conference abstracts in journal supplements show up as one-page "articles"
    # with no abstract. Elsevier article numbers (e.g. 110522) look the same, so
    # only treat low page numbers as abstracts.
    b = w.get("biblio") or {}
    page = b.get("first_page") or ""
    one_page = page.isdigit() and page == b.get("last_page") and int(page) < 5000
    return bool(one_page and not w.get("abstract_inverted_index") and w.get("type") == "article")


def normalise(w: dict, author_id: str) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    b = w.get("biblio") or {}
    authors, self_pos = [], None
    for i, a in enumerate(w.get("authorships") or []):
        au = a.get("author") or {}
        name = short_name(au.get("display_name") or "")
        is_self = (au.get("id") or "").endswith(author_id) or (au.get("orcid") or "").endswith(ORCID)
        if is_self:
            self_pos = i
        authors.append({"name": name, "self": is_self})
    if self_pos is None:  # fall back to name match
        for i, a in enumerate(authors):
            if a["name"].startswith(SELF_NAME):
                a["self"], self_pos = True, i
                break

    venue = src.get("display_name") or loc.get("raw_source_name") or ""
    venue = re.sub(r"\s*\([^)]*\)$", "", venue)  # "bioRxiv (Cold Spring Harbor Laboratory)"
    oa = w.get("open_access") or {}
    best = w.get("best_oa_location") or {}
    title = html.unescape(re.sub(r"<[^>]+>", "", w.get("title") or "")).strip()
    return {
        "id": w["id"].rsplit("/", 1)[-1],
        "doi": bare_doi(w.get("doi")),
        "title": title,
        "date": w.get("publication_date"),
        "year": w.get("publication_year"),
        "type": w.get("type"),
        "venue": venue,
        "volume": b.get("volume"),
        "issue": b.get("issue"),
        "pages": page_range(b.get("first_page"), b.get("last_page")),
        "authors": authors,
        "first_author": self_pos == 0,
        "co_first": False,
        "cited_by": w.get("cited_by_count") or 0,
        "oa_url": best.get("pdf_url") or (oa.get("oa_url") if oa.get("is_oa") else None),
        "url": f"https://doi.org/{bare_doi(w.get('doi'))}" if w.get("doi") else loc.get("landing_page_url"),
        "preprint": None,
        "links": [],
    }


def same_work(a: dict, b: dict) -> bool:
    ta, tb = norm_title(a["title"]), norm_title(b["title"])
    if ta == tb or SequenceMatcher(None, ta, tb).ratio() > 0.85:
        return True
    # Preprint -> paper where the title changed: same first author, near-identical
    # author list, and the paper came out within ~3 years of the preprint.
    na = [x["name"] for x in a["authors"]]
    nb = [x["name"] for x in b["authors"]]
    if not na or not nb or na[0] != nb[0]:
        return False
    sa, sb = set(na), set(nb)
    overlap = len(sa & sb) / len(sa | sb)
    years = abs((a["year"] or 0) - (b["year"] or 0))
    return overlap >= 0.75 and years <= 3


def doi_root(doi: str | None) -> str | None:
    # eLife and others mint versioned DOIs: 10.7554/elife.99930.1 -> 10.7554/elife.99930
    return re.sub(r"(\.\d+)+$", "", doi) if doi and doi.startswith("10.7554/") else doi


def build(works: list[dict], author: dict, overrides: dict) -> dict:
    hide = {d.lower() for d in overrides.get("hide", [])}
    co_first = {d.lower() for d in overrides.get("co_first", [])}
    links = {k.lower(): v for k, v in overrides.get("links", {}).items()}
    author_id = author["id"].rsplit("/", 1)[-1]

    pubs = []
    for w in works:
        if w.get("type") not in KEEP_TYPES or w.get("is_retracted") or is_meeting_abstract(w):
            continue
        p = normalise(w, author_id)
        if p["doi"] in hide or not p["title"]:
            continue
        pubs.append(p)
    for extra in overrides.get("extra", []):
        pubs.append({"authors": [], "links": [], "preprint": None, "cited_by": 0,
                     "first_author": False, "co_first": False, **extra})

    # Collapse duplicate records (versioned DOIs, preprint + published paper).
    published = [p for p in pubs if p["type"] != "preprint"]
    preprints = sorted((p for p in pubs if p["type"] == "preprint"), key=lambda p: p["date"] or "", reverse=True)
    kept_preprints: list[dict] = []
    for pre in preprints:
        match = next((p for p in published if p["type"] != "dissertation" and same_work(pre, p)), None)
        if match:
            match["preprint"] = match["preprint"] or pre["url"]
            match["cited_by"] = max(match["cited_by"], pre["cited_by"])
            continue
        twin = next((k for k in kept_preprints if doi_root(k["doi"]) == doi_root(pre["doi"]) or same_work(k, pre)), None)
        if twin:
            # Prefer the journal-hosted record (e.g. eLife reviewed preprint) over bioRxiv.
            if SERVER.search(twin["venue"] or "") and not SERVER.search(pre["venue"] or ""):
                twin["preprint"] = twin["url"]
                twin.update({k: pre[k] for k in ("doi", "url", "venue", "oa_url", "date", "year")})
            elif SERVER.search(pre["venue"] or ""):
                twin["preprint"] = twin["preprint"] or pre["url"]
            twin["cited_by"] = max(twin["cited_by"], pre["cited_by"])
            continue
        kept_preprints.append(pre)
    pubs = published + kept_preprints

    for p in pubs:
        p["co_first"] = (p.get("doi") or "") in co_first
        p["links"] = links.get(p.get("doi") or "", p.get("links", []))
        p["type_label"] = TYPE_LABELS.get(p["type"], p["type"].title())
    pubs.sort(key=lambda p: p.get("date") or f"{p.get('year', 0)}", reverse=True)

    stats = author.get("summary_stats") or {}
    return {
        "updated": dt.date.today().isoformat(),
        "source": "OpenAlex",
        "author": {"orcid": ORCID, "openalex": author_id},
        "metrics": {
            "publications": sum(p["type"] in ("article", "review", "letter", "book-chapter") for p in pubs),
            "preprints": sum(p["type"] == "preprint" for p in pubs),
            "first_author": sum(p["first_author"] or p["co_first"] for p in pubs if p["type"] != "dissertation"),
            "citations": author.get("cited_by_count", 0),
            "h_index": stats.get("h_index", 0),
            "i10_index": stats.get("i10_index", 0),
        },
        "publications": pubs,
    }


# -------------------------------------------------------------------------- render

def e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def render_authors(p: dict) -> str:
    out = []
    for i, a in enumerate(p["authors"]):
        name = e(a["name"])
        if a.get("self"):
            mark = "<sup title=\"Co-first author\">†</sup>" if p.get("co_first") else ""
            name = f"<strong>{name}{mark}</strong>"
        out.append(name)
    if len(out) > 8:
        hidden = ", ".join(out[6:-1])
        return (", ".join(out[:6]) +
                f"<span class=\"more-authors\" hidden>, {hidden}</span>"
                f"<button class=\"expand-authors\" type=\"button\">, … +{len(out) - 7} more</button>, "
                + out[-1])
    return ", ".join(out)


def citation_text(p: dict) -> str:
    names = [a["name"] for a in p["authors"]]
    who = ", ".join(names[:6]) + (", et al." if len(names) > 6 else "")
    bits = [f"{who} ({p.get('year')}). {p['title']}."]
    venue = p.get("venue") or ""
    if p.get("volume"):
        venue += f", {p['volume']}"
        if p.get("issue"):
            venue += f"({p['issue']})"
    if p.get("pages"):
        venue += f", {p['pages']}"
    if venue:
        bits.append(f"{venue}.")
    if p.get("doi"):
        bits.append(f"https://doi.org/{p['doi']}")
    return " ".join(bits)


def render_pub(p: dict) -> str:
    tags = [p["type"]]
    if p["first_author"] or p["co_first"]:
        tags.append("first")
    venue = e(p.get("venue"))
    if p.get("volume"):
        venue += f", {e(p['volume'])}"
        if p.get("issue"):
            venue += f"({e(p['issue'])})"
    links = []
    if p.get("url"):
        links.append(f"<a href=\"{e(p['url'])}\">{'DOI' if p.get('doi') else 'Link'}</a>")
    if p.get("oa_url") and p.get("oa_url") != p.get("url"):
        links.append(f"<a href=\"{e(p['oa_url'])}\">PDF</a>")
    if p.get("preprint"):
        links.append(f"<a href=\"{e(p['preprint'])}\">Preprint</a>")
    for l in p.get("links", []):
        links.append(f"<a href=\"{e(l['url'])}\">{e(l['label'])}</a>")
    links.append(f"<button class=\"cite\" type=\"button\" data-cite=\"{e(citation_text(p))}\">Cite</button>")
    cites = f"<span class=\"pub-cites\">{p['cited_by']} citation{'s' if p['cited_by'] != 1 else ''}</span>" if p.get("cited_by") else ""
    badge = f"<span class=\"badge badge-{e(p['type'])}\">{e(p['type_label'])}</span>" if p["type"] != "article" else ""
    return f"""<li class="pub" data-tags="{' '.join(tags)}" data-year="{e(p.get('year'))}">
  <p class="pub-title">{badge}{e(p['title'])}</p>
  <p class="pub-authors">{render_authors(p)}</p>
  <p class="pub-meta"><em>{venue}</em> · {e(p.get('year'))}{(' · ' + cites) if cites else ''}</p>
  <p class="pub-links">{' '.join(links)}</p>
</li>"""


def render_list(data: dict) -> str:
    out, year = [], None
    for p in data["publications"]:
        if p.get("year") != year:
            if year is not None:
                out.append("</ol>")
            year = p.get("year")
            out.append(f"<h3 class=\"pub-year\" data-year=\"{e(year)}\">{e(year)}</h3>\n<ol class=\"pubs\">")
        out.append(render_pub(p))
    out.append("</ol>")
    return "\n".join(out)


def render_metrics(data: dict) -> str:
    m = data["metrics"]
    items = [
        (m["publications"], "peer-reviewed papers"),
        (m["first_author"], "first-author"),
        (m["citations"], "citations"),
        (m["h_index"], "h-index"),
    ]
    return "\n".join(f"<div><dt>{e(v)}</dt><dd>{e(k)}</dd></div>" for v, k in items)


def splice(doc: str, name: str, content: str) -> str:
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(doc):
        raise SystemExit(f"marker {name} not found in index.html")
    return pat.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", doc)


def main() -> int:
    overrides = json.loads(OVERRIDES_JSON.read_text(encoding="utf-8")) if OVERRIDES_JSON.exists() else {}
    author = fetch_author()
    works = fetch_works(author["id"].rsplit("/", 1)[-1])
    if not works:
        print("OpenAlex returned no works; leaving files untouched.", file=sys.stderr)
        return 1
    data = build(works, author, overrides)

    # Don't churn the repo when only the date stamp would change.
    if DATA_JSON.exists():
        old = json.loads(DATA_JSON.read_text(encoding="utf-8"))
        if {**old, "updated": None} == {**data, "updated": None}:
            data["updated"] = old["updated"]

    DATA_JSON.parent.mkdir(exist_ok=True)
    DATA_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    doc = INDEX_HTML.read_text(encoding="utf-8")
    doc = splice(doc, "PUBLICATIONS", render_list(data))
    doc = splice(doc, "METRICS", render_metrics(data))
    doc = re.sub(r'(<time id="pubs-updated" datetime=")[^"]*(">)[^<]*(</time>)',
                 lambda m: f"{m.group(1)}{data['updated']}{m.group(2)}{data['updated']}{m.group(3)}", doc)
    INDEX_HTML.write_text(doc, encoding="utf-8", newline="\n")
    print(f"{len(data['publications'])} items, {data['metrics']['citations']} citations, h-index {data['metrics']['h_index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
