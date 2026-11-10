# Security

## Model

vtel is a command line program that **reads a CSV log, computes metrics, and writes files**. It starts no service, opens no
network connection and runs no code from its input.

- **What it reads:** the log CSV, parsed with the standard `csv` module and checked field by field (a bad number, a bad time or a
  row of the wrong width is an error that names the line, exit code 2); the truth JSON of a synthetic log; a `report.json` or
  `bench.json` given to `render`, parsed as JSON of which only known fields are read.
- **What it writes:** only where the options say: `generate -o` (it refuses to overwrite a file), `--truth`, `analyze --out`,
  `bench --out`, `render -o` and `--figure`.
- **The Docker image** runs as an unprivileged user and works with a read-only root filesystem (plus `--tmpfs /tmp` for
  matplotlib's cache), no capabilities and no network (`--network none`); see `tools/docker_e2e.sh`.
- **No real data** is in the repository: the logs are synthetic. A log of your own can hold your location habits (when and how long
  you drive); analyse it locally, as the image is built to be run.

## Reporting

If you find a vulnerability, please open a private security advisory on the GitHub repository (Security tab) rather than a
public issue.
