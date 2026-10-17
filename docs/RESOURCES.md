# Resources

Dr. Adewole Olagoke · 25 September 2026 · revised 17 October 2026

Companion to [`ARCHITECTURE.md`](ARCHITECTURE.md) and `RUNBOOK.md`.

> **How to use this list.** Every entry has a **when** column tied to a runbook
> stage. Read it in that week, not before. A reading list is the most
> comfortable possible substitute for `git init`, and this project has already
> spent seven weeks proving that.

---

## 1 · Stack mechanics

| Resource | What it gives you | When |
|---|---|---|
| [dbt Core quickstart with DuckDB](https://docs.getdbt.com/guides/duckdb) | The official walkthrough: install, `profiles.yml`, first models. Start here. | Stage 6 · WE 5–6, by 15.11. |
| [dbt on DuckDB — thomassie.me](https://thomassie.me/2026-04-04-dbt-on-duckdb/) | Sources over Parquet, staging → marts, generic tests, `dbt docs generate`. Two to three hours. Follow it with **your** Stage 3 Parquet, not its customer tables. | Stage 6 · WE 5–6, by 15.11. |
| [DuckDB spatial extension](https://duckdb.org/docs/lts/core_extensions/spatial/overview) | Geometry types, GeoParquet, GDAL formats. The piece that lets Project B share this warehouse. | Project B |
| [Quarto → GitHub Pages](https://quarto.org/docs/publishing/github-pages.html) | Publishing the report site. You already know Quarto; this is only the deploy step. | Stage 10 |
| [GitHub Actions billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions) | Confirms free, uncapped minutes on public repos with standard runners. | Stage 9 |
| [Azure SQL Database free offer](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer?view=azuresql) | Lifetime-free tier, auto-pause behaviour, the irreversible setting. | Stage 6b, dropped and archived in `archive/azure-excursion/` |

---

## 2 · Reference projects worth reading

Study how these are *organised*. Do not copy their content.

| Project | Why it is worth an hour |
|---|---|
| [dbt-labs/jaffle_shop_duckdb](https://github.com/dbt-labs/jaffle_shop_duckdb) | Clone to `dbt docs serve` in about a minute, entirely local. The fastest way to see a working lineage graph before you build your own. |
| [dbt-labs/jaffle-shop-template](https://github.com/dbt-labs/jaffle-shop-template) | DuckDB plus **Evidence** for code-first BI. This is the shape of a modern, fully open portfolio repo — worth seeing even though you are publishing with Quarto. |
| [GitLab data team — public dbt project](https://gitlab.com/gitlab-data/analytics/-/tree/master/transform/snowflake-dbt) | A real production dbt project, open to read. Model naming, folder depth, test density, documentation discipline at scale. The closest thing to seeing inside an employer's repo. |
| [GitLab dbt guide (handbook)](https://handbook.gitlab.com/handbook/business-technology/data-team/platform/dbt-guide/) | The written conventions behind that repo. Useful language for interviews, because it is how an analytics team actually talks about its own standards. |

---

## 3 · Structure and conventions

| Resource | Use |
|---|---|
| [How we structure our dbt projects](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview) | Read before creating `models/`. Staging / intermediate / marts naming, file layout, one-model-per-source rule. |
| [dbt best-practice guides (index)](https://docs.getdbt.com/best-practices) | Materialisation strategy, testing depth, CI patterns. Skim the index, read the two that apply. |

---

## 4 · Domain — Project A, power market

| Resource | Use |
|---|---|
| [Security token — how to get it](https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188-How-to-get-security-token) | Access granted 7 Aug 2026 (ticket #9465462). Token is generated under My Account. |
| [API rate limit](https://transparencyplatform.zendesk.com/hc/en-us/articles/12783148966036) | 400 req/min per token, 429 with ~10 min auto-unban. `SLEEP_SECONDS = 1.5` is ten times under. |
| [Transparency Platform area list](https://transparencyplatform.zendesk.com/hc/en-us/articles/15885757676308) | Verify every EIC in `config/zones.csv` against this before trusting it. |
| [EnergieID/entsoe-py](https://github.com/EnergieID/entsoe-py) | **Do not switch to it.** See the note below. Use it as an independent cross-check. |
| IPCC AR5 WG3 Annex III, Table A.III.2 | The factor source. Stage 4 requires verifying every row of `config/ipcc_ar5_factors.csv` against it by hand. |
| Electricity Maps (free tier) | Independent published intensity series for the Stage 5 cross-check. Its default figures are life-cycle intensities of the consumed, flow-traced mix, so expect differences from imports and from the factor sets, not from lifecycle versus combustion. |
| SMARD (Bundesnetzagentur) | German generation and load, as a second opinion when ENTSO-E looks wrong. |

### The entsoe-py question, and how to answer it

Someone will ask why you wrote your own client when `entsoe-py` exists. The
answer is in what it returns: pandas DataFrames, with the XML already parsed
away. That is a good library and a bad fit here, because the XML is the point —
A03 curve compression, the `outBiddingZone_Domain` direction split, PT15M DST
step counts and MAW-to-MWh conversion are all decisions it makes for you and
does not show you. Your client also lands an immutable raw copy with a SHA-256
manifest and redacts the token in logs, which a convenience wrapper does not do.

**The stronger move:** pull one period with both, compare row by row, and put
the result in `docs/METHODOLOGY.md`. Agreement is validation evidence.
Disagreement is a finding. Either outcome turns an awkward interview question
into a prepared answer.

---

## 5 · Domain — Project B, Sentinel-2 biomass MRV

Carried forward from Implementation Protocol v2. Re-verify access terms before
relying on any of them.

| Source | Use |
|---|---|
| Copernicus Data Space Ecosystem — `dataspace.copernicus.eu` | Full Sentinel-2 L2A archive. STAC, OData, openEO, Sentinel Hub APIs. Free account with quotas. |
| Microsoft Planetary Computer — `planetarycomputer.microsoft.com` | STAC-indexed Sentinel-2, Landsat, WorldCover, Copernicus DEM. Data and APIs free; the hosted compute Hub was retired June 2024, so compute is local either way. |
| Copernicus Land Monitoring Service — `land.copernicus.eu` | CORINE, tree cover density, forest type. |
| Global Forest Change (Hansen / UMD) | Annual forest loss — what the EUDR 31 Dec 2020 cut-off is assessed against. |
| HessenForst published mortality figures | Ground truth for the 2018–2022 spruce dieback in Lahn-Dill-Bergland and Vogelsberg. |
| Your own allometry | Olagoke, Proisy, Féret, Blanchard, Fromard, Mehlig, Menezes, Santos & Berger (2016). *Trees* **30**: 935–947. |
| IPCC 2006 Guidelines / 2019 Refinement, Vol. 4 AFOLU — `ipcc-nggip.iges.or.jp` | Carbon fraction (0.47) and root-to-shoot ratios with published uncertainty ranges. Cite the tier you apply. |

Python stack: `pystac-client`, `planetary-computer`, `odc-stac` or `stackstac`,
`xarray`, `rioxarray`, `geopandas`, `rasterio`, `scikit-learn`.

Endpoints, so Stage 1 does not start with a hunt. Carried forward from
Implementation Protocol v2 before it was archived:

- Copernicus Data Space STAC — `https://catalogue.dataspace.copernicus.eu/stac`
- Copernicus Data Space OData — `https://catalogue.dataspace.copernicus.eu/odata/v1/Products`
- AWS Earth Search STAC — `https://earth-search.aws.element84.com/v1`
  (note: the bare `element84.com` homepage is **not** a STAC endpoint)
- ENTSO-E Transparency API — `https://web-api.tp.entsoe.eu/api`

---

## 6 · Domain — Project C, Scope 3 agricultural value chain *(archived)*

> Project C was replaced by **Project D** on 27 September 2026 and its runbook
> moved to `_archiv_2026-09/projects/`. This table stays live: the factor sources
> below are the best open reference set for any carbon-accounting work, and the
> MRV/Carbon CV claims rest on them.

Also carried forward from Implementation Protocol v2.

| Source | Use |
|---|---|
| Agribalyse (ADEME) — `agribalyse.ademe.fr` | ~2,500 French and EU agri-food LCA datasets, cradle-to-gate. Free CSV. |
| UK DEFRA / DESNZ GHG conversion factors — `gov.uk` | Official annual factors. The methodology paper is as useful as the numbers. |
| EXIOBASE 3 — `exiobase.eu` | Multi-regional input-output, spend-based factors for the supply-chain tail. |
| IPCC Emission Factor Database — `ipcc-nggip.iges.or.jp/EFDB` | Factors together with their uncertainty ranges. |
| FAOSTAT — `fao.org/faostat` | Production, yield, land use, agricultural emissions by country and crop. API available. |
| Eurostat (`apro_cpsh1`, `ef_` series) | EU crop production and farm structure. |
| EEA EU ETS data viewer — `eea.europa.eu` | Verified installation-level emissions for benchmarking. |

---

## 8 · Carried forward from the archived source list

`open_source_datasets_germany.md` was archived on 27 September 2026. Its useful
entries are recorded here; the rest were duplicates of the tables above.

| Source | Use | Caveat |
|---|---|---|
| Deutscher Wetterdienst open data — `opendata.dwd.de` | Station and gridded climate series. Temperature against load for Project A; drought indices for Project B | Free, no key. Station metadata is a separate download from the series |
| Geofabrik Germany extracts — `download.geofabrik.de/europe/germany.html` | OpenStreetMap extracts by Bundesland, for spatial joins and basemaps in Project B | Large files. Take the Hessen extract, not Germany |
| EU Open Data Portal — `data.europa.eu` | Catalogue across EU institutions when a dataset's home is unclear | A catalogue, not a source. Follow through to the publisher |
| EU ETS — `climate.ec.europa.eu` | The Commission's ETS pages | The **EEA ETS data viewer** in §6 is the better access route for installation-level data |
| ~~Open Power System Data — `open-power-system-data.org`~~ | — | **Do not use.** Not updated since 2020. It appears in two of the archived plans as a recommended source; it is stale and ENTSO-E supersedes it |

### Regulatory vocabulary worth being able to place

Not data sources — the acronyms that appear in MRV and ESG job descriptions, and
that the archived Implementation Protocol used without definition:

- **EFRAG** — sets the ESRS standards that operationalise CSRD reporting.
- **CSDDD** — the EU due-diligence directive; supply-chain obligations that sit
  beside CSRD and drive the Scope 3 work the archived Project C specified.
- **ICVCM** — Core Carbon Principles; the integrity benchmark for carbon
  credits, relevant to anything claiming removals or avoided emissions.
- **XBRL** — the digital tagging format for CSRD filings. Why a reporting
  pipeline has a structured-output requirement rather than a PDF at the end.

---

## 7 · Platforms learned elsewhere

Databricks, Snowflake, Fabric, ADF and AWS appear in the Greenbootcamps curriculum but are
deliberately not part of this portfolio: none has a durable free tier, and a repository that
cannot be run is not a portfolio. No tutorials for them are
listed here, because they are timetabled hours rather than a gap to close.

They belong in the **Technical Stack** row of the CV, not in this architecture.
The distinction matters and is worth being able to state in an interview:

- The **CV** lists platforms you can work in. Breadth is an asset there.
- The **portfolio** demonstrates engineering judgement. It runs on DuckDB
  because the artefact has to survive every account closing, be reproducible by
  a stranger with `git clone`, and cost nothing to keep online. Those are the
  properties being demonstrated.

Choosing a heavier platform for a two-zone, few-million-row dataset would
demonstrate the opposite of judgement. Power BI on the exported Parquet carries
the Microsoft-stack evidence without the architecture depending on it; the
Azure excursion (Stage 6b) was dropped in October 2026.

What stays off the list: generic "data analyst portfolio" roundups. Your
differentiator is a domain nobody else in the cohort has and a parser handling
five documented pathologies. Generic portfolio advice pulls the other way.
