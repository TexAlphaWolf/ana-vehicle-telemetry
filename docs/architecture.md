# Architecture

```text
drive.csv --> logio.py (strict reader: errors name the line)        generate.py --> log + truth
                  |                                                       |
                  v                                                       |
   +--------------+---------------------+                                 |
   v                                    v                                 |
pipeline.py (NumPy)              reference.py (plain loops)               |
   |                                    |                                 |
   |                                    +--> verify.py <-- compares the two
   v
analysis.py (one dictionary) <-- score.py <-- the truth
   |
   v
report.json --> report.py (Markdown, figures)          bench.py (speed, accuracy sweep) --> bench.json
```

| File | Role |
|---|---|
| `params.py` | The thresholds, validated: finite, positive, and `max_fill_s` not above `gap_s`. |
| `logio.py` | Reads and writes the CSV: ISO or epoch time that must increase, empty cells as missing, aliases for common column names, a mass air flow column converted to fuel flow. Numbers are written with `repr`, so a log read back is bit for bit the log written. |
| `pipeline.py` | The analysis on arrays: range, spikes, fill, intervals, parking, trips, metrics, events. |
| `reference.py` | The same, one sample at a time. Shares nothing with the pipeline but the definitions and the code that adds up the totals. |
| `verify.py` | Compares the two on random and hostile logs. |
| `generate.py` | The synthetic vehicle, its trips and its injected faults, with the truth. |
| `score.py` | Compares an analysis with the truth. |
| `analysis.py` | A report: the analysis, the score when there is a truth, a speed trace to draw. |
| `report.py` | Markdown and figures from a report or a benchmark. Pure functions of the JSON: `vtel render` rebuilds them exactly. |
| `bench.py` | Times, accuracy over many seeds, agreement of the two implementations. |
| `cli.py` | The command line. |

## Decisions

- **Two implementations, not one and a lot of tests.** Hand-computed cases catch what the author thought of; a second implementation
  written differently and compared on random logs catches the rest. Both are in `tests/test_pipeline.py`, which runs every case
  through the two.
- **A truth that the analysis cannot see.** The generator draws the speed as a piecewise linear function and integrates it on a
  fine grid; the analysis sees 1 Hz samples with noise and holes. Their difference is the real error.
- **Holes are explicit.** A missing speed is never guessed beyond `max_fill_s`; the trip reports its covered share instead.
- **No pandas.** NumPy and the standard `csv` module are enough, and keep the image small.
- **The report is data first.** `report.json` holds everything (including a downsampled trace); the Markdown and the figure are
  functions of it.
