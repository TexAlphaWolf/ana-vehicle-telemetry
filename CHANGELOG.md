# Changelog

## 1.0.0

First release.

- A strict reader for OBD-II drive logs in CSV (ISO or epoch time, missing cells, aliases, a mass air flow column), with errors
  that name the line.
- The analysis: out-of-range values and spikes removed, short holes interpolated, trips cut by parking and by logger gaps, and for
  every trip distance, duration, standing time, fuel consumption, harsh accelerations and braking, high rpm and maximum temperature;
  overheating and stuck sensors for the whole log.
- A plain Python implementation of the same analysis and `vtel verify`, which compares the two on random and hostile logs.
- A synthetic vehicle with a known truth (trips, fuel, harsh ramps, injected faults) and a scoring of the analysis against it.
- A report (JSON, Markdown, figure) rebuilt exactly from its JSON, and a benchmark of speed, accuracy and agreement.
- A command line (`generate`, `validate`, `analyze`, `verify`, `bench`, `render`) with exit codes for a pipeline.
- Docker image (no network, read-only, no capabilities); CI on Python 3.11 to 3.14, Linux, Windows and macOS.
