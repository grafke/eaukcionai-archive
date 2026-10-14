# eaukcionai-archive — plan

A nightly archive of auctions from <https://www.eaukcionai.lt>, plus a friendlier view of them. When an auction expires it drops out of the site's search, but its page still loads if you know the URL. This repo keeps those URLs and their key metadata so they aren't lost.

- Repo: `grafke/eaukcionai-archive` (public)
- Local clone: `~/Documents/grf/eaukcionai-archive`

## Decisions

| Topic | Decision |
|---|---|
| Scope | Every auction type (vehicles, movable property, real estate, …). Filtering happens in the view. |
| Storage | Two JSONL files (one object per line, sorted by ID), linked by `auction_id` as one-to-many. |
| Detail fetching | Every live auction is fetched every night. After an auction leaves the listing it is re-fetched until its status is final, then **once more**, then never again. If no final status appears within 30 days, it stops anyway. |
| Changes | Only the latest values are kept, plus `first_seen`/`last_seen`. Git history is the audit trail. |
| Personal data | Owner names (`Savininkai`), bailiff/contact persons and free-text descriptions are **never** stored. |
| Backfill | Not in v1 (see Later). |
| View | Static GitHub Pages site with one row per item, joined to its auction. No map in v1. |
| Schedule | 00:30 UTC nightly, plus `workflow_dispatch`. |

## Site facts (probed 2026-10-09)

- **Listing:** `https://www.eaukcionai.lt/evs/pages/auctions.do?stateType=PASKELBTA-IR-VYKSTA&advancedSearch=true&sortBy=endDate.ASC&page=N`
  - `page` starts at 0. The size is fixed at 20 per page; size params are ignored.
  - About 61 pages, roughly 1,220 live auctions.
  - The last page number is in the `a.paginationLink[data-page]` elements.
- **Detail:** `https://www.eaukcionai.lt/evs/pages/auction.do?id=<id>`. `number` is optional.
  - Auction links in the listing look like `/evs/pages/auction.do?id=337594&number=336875`.
  - A missing or deleted ID returns **HTTP 400**.
  - IDs are roughly sequential (~339k as of 2026-10). Records go back to 2013, and about 60% of IDs are real auctions.
- **Response time and limits:** about 0.5 s per page. There is no robots.txt.
- **Detail page layout:** label/value pairs.
  - Auction-level labels: `Tipas:`, `Būsena:`, `Pradžios data:`, `Pabaigos data:`, `Registracijos pradžia:`, `Registracijos pabaiga:`, `Pradinė pardavimo kaina:`, `Didžiausia pasiūlyta kaina:`.
  - Bailiff auctions ("Antstolių varžytynės") have **no** registration fields. They only exist for "Kiti aukcionai".
- **Items:** an auction can have several items. Each item block starts at `Parduodamas turtas: <name>` and contains `Parduodama turto dalis:`, `Bendras turto plotas:`, `Parduodamo turto dalies plotas:`, `Turto potipis:`, `Unikalus Nr.:` (real estate only) and `Adresas:`.
- **Listing card:** also shows the `Turtas:` list, one `<li>` per item with the address in `span.small`, plus the type label (e.g. `Antstolių varžytynės`).
- **Status values seen:**
  - Live: `Paskelbtas`, `Vykstančios`.
  - Final: `Įvykusios`, `Įvykęs`, `Neįvykusios`, `Neįvykęs`, `Atšauktos`.
  - Treat anything outside the live set as final, and log statuses we haven't seen before.
- **Number formats:** prices look like `54 670 Eur` (space as thousands separator, possibly a `,` decimal). Areas look like `524,67` followed by `kv. m`.

## Data model

`data/auctions.jsonl` (one auction per line):

| field | notes |
|---|---|
| `auction_id` | int, the `id` query param, primary key |
| `number` | int, `Nr.` |
| `url` | `https://www.eaukcionai.lt/evs/pages/auction.do?id=<id>` |
| `kind` | bailiff (`Antstolių varžytynės`) / other (`Kiti aukcionai`) |
| `type` | `Tipas:` (e.g. `Antrosios`, `Pirminis kiti aukcionai`) |
| `status` | `Būsena:` |
| `start_date`, `end_date` | ISO local time (Europe/Vilnius), as the site shows it |
| `registration_start`, `registration_end` | ISO or `null` (bailiff auctions have none) |
| `starting_price_eur` | number |
| `highest_bid_eur` | number or `null` |
| `first_seen`, `last_seen` | UTC date: first and last time the auction appeared in the listing |
| `last_fetched` | UTC timestamp |
| `final_status_seen_at` | UTC timestamp when a final status was first recorded, or `null` |
| `done` | bool. Set after the one extra fetch that follows the final status, or after the 30-day cap. |

`data/items.jsonl` (one item per line, key `(auction_id, item_no)`):

| field | notes |
|---|---|
| `auction_id` | FK to auctions |
| `item_no` | 1-based position on the detail page |
| `name` | `Parduodamas turtas:` / `Turtas:` entry |
| `share_sold` | `Parduodama turto dalis:` (e.g. `1/1`, `25/82`) |
| `subtype` | `Turto potipis:` |
| `area_m2` | `Bendras turto plotas:` as a number, or `null` |
| `share_area_m2` | `Parduodamo turto dalies plotas:` or `null` |
| `address` | `Adresas:` |
| `unique_nr` | `Unikalus Nr.:` or `null` |

On every write, both files are sorted by key and use stable key order, so git diffs only show the rows that changed.

## Nightly job (`.github/workflows/nightly.yml`)

1. Crawl listing pages 0..last to collect the live IDs and update `last_seen` (and `first_seen` for new IDs).
2. For every live ID, fetch the detail page, parse it, and upsert the auction plus all of its items. Replace all of that auction's items each time.
3. For IDs that are not live and not `done`, fetch the detail page:
   - If the status is final and `final_status_seen_at` is `null`, set it.
   - If `final_status_seen_at` was already set **before this run**, this is the one extra fetch, so set `done = true`.
   - If more than 30 days have passed since `last_seen` and there is still no final status, set `done = true`.
4. Write the files. Commit only if something changed (as `github-actions[bot]`), then trigger the Pages deploy.

HTTP rules:
- 1 request/s, using a `User-Agent` that names the repo URL.
- Retries with exponential backoff on 5xx and timeouts.
- HTTP 400 means the auction is missing: record it, don't retry.

Failure guard: the run fails, so GitHub's failure email is sent, if a page that returns 200 parses with no core fields (`Pradžios data`/`Pabaigos data`). Comparing the live count with the listing count catches layout changes.

Expected runtime is about 20–25 minutes.

## View (GitHub Pages, `.github/workflows/pages.yml`)

- At deploy time a step builds `site/auctions.sqlite` from the JSONL files. The file is an artifact and is **not committed**.
  - Tables: `auctions`, `items`, a view `item_rows` joining the two. Search uses LIKE with a diacritic-folding function; at this size no index is needed.
- `site/index.html` is a single static page with sql.js and a small table component, with no build framework. It loads the whole SQLite file, about 5 MB per year. If the file grows too big, switch to sql.js-httpvfs range requests.
- **Rows:** one row per item, with its auction's fields.
- **Search:** full text over item name and address.
- **Filters:**
  - kind, asset subtype, status
  - municipality (parsed from the start of `address`, `… r. sav.` / `… m. sav.`)
  - starting price range
  - end-date range
- **Columns:** sortable, with a link to the original page.
- **Default filter:** live auctions plus those ended in the last 90 days.

## Repo layout

```
pyproject.toml / uv.lock
src/eaukcionai/
  fetch.py      # httpx client, rate limit, retries
  listing.py    # parse listing pages -> live ids (+ listing fields)
  detail.py     # parse detail page -> auction + items (selectolax)
  store.py      # load/upsert/sort/write JSONL
  run.py        # nightly orchestration (steps 1–4)
  build_site.py # JSONL -> SQLite
tests/fixtures/ # saved HTML: bailiff auction, other auction with multiple items, finished auction, HTTP 400 response
tests/
site/index.html
data/auctions.jsonl
data/items.jsonl
.github/workflows/nightly.yml
.github/workflows/pages.yml
```

Stack: Python with `uv`, `httpx`, `selectolax` and `pytest`.

## Risks

- **The site may block GitHub's runners**, which are mostly US-hosted. Check with the first `workflow_dispatch` run. If it is blocked, run the same job on a local machine and push.
- **A change to the page layout breaks the parser.** The failure guard above catches it, and the fixture tests pin down the expected parsing.

## Later (not in v1)

- **Backfill.** Walk old IDs: about 340k back to 2013, 1 request/s, about 94 h total. That means several resumable chunks of at most 5 h each in a separate `workflow_dispatch` workflow, with a progress cursor saved in the repo.
- **Map.** The detail pages contain no coordinates, so addresses would have to be geocoded.
