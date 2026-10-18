# mdmornin.github.io

Personal site of Mitchell D. Morningstar, PhD: **https://mdmornin.github.io**

A static, single-page site (no build step) served by GitHub Pages from `master`.

## How publications update

`.github/workflows/update-publications.yml` runs every Monday (and on demand from the
**Actions** tab → *Update publications* → *Run workflow*). It runs
`scripts/update_publications.py`, which:

1. looks up ORCID `0000-0002-3847-192X` on [OpenAlex](https://openalex.org/authors/orcid:0000-0002-3847-192X),
2. drops peer-review reports, supplementary files and meeting abstracts, and folds each
   preprint into its published paper (shown as a *Preprint* link),
3. writes `data/publications.json` and rewrites the publication list and metrics in
   `index.html` between the `<!-- PUBLICATIONS:START/END -->` and `<!-- METRICS:START/END -->` markers,
4. commits the result if anything changed.

Run it locally with `python scripts/update_publications.py` (standard library only).

### Fixing what OpenAlex gets wrong

Edit `data/publications_overrides.json` (DOIs bare and lower-case); pushing it re-runs the workflow.

| key        | use                                                                 |
|------------|---------------------------------------------------------------------|
| `hide`     | DOIs to leave off the site                                          |
| `co_first` | DOIs where you are co-first author (adds †)                         |
| `links`    | extra buttons for a paper, e.g. `{"label": "Code", "url": "..."}`   |
| `extra`    | items OpenAlex is missing, in the same shape as `data/publications.json` |

Keeping your ORCID record up to date is the most reliable way to make new papers appear.

## Editing everything else

All other content (bio, research themes, talks, experience) is plain HTML in `index.html`;
styles are in `assets/css/style.css`. When you replace the CV, update the `morningstarCV_2025.pdf`
links in `index.html` and `sitemap.xml`.

Optional repository secrets: `OPENALEX_API_KEY` (free key from openalex.org/settings/api) and
`OPENALEX_MAILTO`.
