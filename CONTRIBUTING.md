# Contributing

Thank you for your interest in Muse–Polar. Bug reports, questions and pull requests are welcome.

## Reporting problems and asking for help

Open a GitHub issue with:

- what you did (command, options, operating system, Python version, device firmware if known),
- what you expected and what happened (copy the terminal log; `python -m musepolar -v` gives details),
- if relevant, a **synthetic** recording that shows the problem (for example made with `--sim`).

**Never attach recordings of real participants** or any personal data (names, dates of birth,
identifiable session names) to issues or pull requests.

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

Node.js ≥ 18 enables the tests that compare the browser engine (`research/web/engine.js`) with the
Python pipeline. After changing `research/app/static/` or `research/web/engine.js`, rebuild the
single-file app with `python research/web/build.py` and commit the result.

## Pull requests

- Keep changes focused; add or update tests for behaviour you change. CI must pass.
- Follow the style of the surrounding code (no new runtime dependencies without discussion).
- Do not change the B1 reference PPG pipeline (`research/src/muse2_pipeline/ppg_b1.py`); propose
  alternative pipelines as separate, clearly labelled modules.
- Report forehead-PPG variability as pulse-rate variability (PRV), not HRV.

## Code of conduct

Be respectful and constructive. Harassment or discrimination of any kind is not accepted. The
maintainer may remove comments or contributions that do not follow this.

## Contact

Maintainer: I Putu Adiartha Griadhi (Universitas Udayana), via GitHub issues.
