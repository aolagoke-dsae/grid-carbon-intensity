# Resources

Dr. Adewole Olagoke · 25 September 2026 · revised 18 October 2026

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
| ENTSO-E Transparency API — `https://web-api.tp.entsoe.eu/api` | The endpoint `src/ingest/entsoe_client.py` calls. |
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

## 5 · Carried forward from the archived source list

`open_source_datasets_germany.md` was archived on 27 September 2026. Its useful
entries are recorded here; the rest were duplicates of the tables above. The
entries for other projects left with them on 18 October 2026.

| Source | Use | Caveat |
|---|---|---|
| Deutscher Wetterdienst open data — `opendata.dwd.de` | Station and gridded climate series, for temperature against load | Free, no key. Station metadata is a separate download from the series |
| EU Open Data Portal — `data.europa.eu` | Catalogue across EU institutions when a dataset's home is unclear | A catalogue, not a source. Follow through to the publisher |
| ~~Open Power System Data — `open-power-system-data.org`~~ | — | **Do not use.** Not updated since 2020. It appears in two of the archived plans as a recommended source; it is stale and ENTSO-E supersedes it |

---

## 6 · Platforms learned elsewhere

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
