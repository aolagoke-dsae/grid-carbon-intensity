# docs/figures

Each figure sits beside a CSV of every value it draws, so the picture can be
checked against its numbers. The data behind them is ENTSO-E's, processed by
this repository's pipeline: the source is named on each figure and here, as
the Transparency Platform's Terms of Use ask of every re-use (clause 3.1).
The terms are summarised under **Licence** in the repository README.

| Figure | Values | Data and method |
|---|---|---|
| `stage5_week_de_lu_2025.png` | `stage5_week_de_lu_2025.csv` | ENTSO-E Transparency Platform, actual generation per production type (A75), DE-LU, 2025, retrieved 17.10.2026. Intensity at the median factors of `config/ipcc_ar5_factors.csv` (IPCC AR5; lignite and hard coal from Itten et al. 2023); solar is B16 and wind B18 plus B19, in GW. Made by `notebooks/stage5_week.py` |

The CSVs are not ENTSO-E's data as ENTSO-E publishes it: generation is
summed by fuel group and converted to GW, and the intensities, withheld
steps and marks are this project's.
