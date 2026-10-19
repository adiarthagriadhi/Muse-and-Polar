# Third-party terms to be checked by the author

This file lists third-party protocols, trademarks and libraries that the software depends on or
refers to. It records **what needs to be checked**, not a legal conclusion. The author should review
each item (if needed with the university's legal/IP office) before the public release.

## Device protocols

| Item | How it is used here | To check |
|---|---|---|
| **Muse 2 BLE protocol** (Interaxon Inc.) | `musepolar/muse.py` talks to the headband directly over BLE (service/characteristic UUIDs, command strings such as `p50`/`p21`, packet decoding). Interaxon does not publish this protocol; the implementation follows the open-source projects **muse-js** (MIT licence) and **muselsl** (BSD-3-Clause licence). | Interaxon's end-user licence / terms of use and developer terms for Muse 2 (whether direct BLE access by third-party software is restricted); whether code or only protocol facts were taken from muse-js/muselsl, and whether their licence notices should be reproduced. |
| **Polar H10 BLE** (Polar Electro Oy) | `musepolar/polar.py` uses the standard Bluetooth Heart Rate Service and the Polar Measurement Data (PMD) service for ECG and accelerometer. Polar documents PMD in its public **Polar BLE SDK**. | The licence/terms of the Polar BLE SDK and its documentation (attribution, permitted use); Polar's product terms. |
| **Polar Sensor Logger** files | `research/src/muse2_pipeline/polar.py` reads text files exported by this third-party app. | Nothing expected (only the file format is read); confirm. |
| **Mind Monitor, OpenBCI, muselsl CSV formats; EDF/EDF+/BDF** | Read by the Research View. | Nothing expected (open/public formats); confirm. |

## Trademarks

- "Muse" and "Muse 2" are trademarks of Interaxon Inc.; "Polar" and "H10" of Polar Electro Oy.
  The software name "Muse–Polar" contains both names. To check: whether using the marks in the
  project/repository name is acceptable (descriptive use) or whether a neutral name is preferable,
  and that the README disclaimer of affiliation is sufficient.
- The Research View is titled "Muse 2 Research View"; same question.

## Libraries

| Library | Licence (as published by the project) | Use |
|---|---|---|
| bleak | MIT | BLE (live dashboard) |
| aiohttp | Apache-2.0 | web server (live dashboard) |
| numpy, scipy, pandas, matplotlib | BSD-style / PSF-based | analysis, figures |
| FastAPI, uvicorn, python-multipart | MIT / BSD-3 / Apache-2.0 | Research View server |
| python-docx | MIT | Word reports |
| JSZip 3.10.1 | MIT or GPLv3 (dual) | loaded from cdnjs by `research/web/research-view.html` for ZIP files |

Libraries are installed by the user and not redistributed, except that the single-file web app
loads JSZip from a CDN at run time. To check: licence compatibility with the chosen licence (all of
the above are permissive) and whether the version list in `requirements-lock.txt` changes this.

## Related internal notes

- `studi-muse-polar-hospitality-2026/analisis/README.md` says the Muse 2 recorder v8 (`perekam/`)
  must not be published in `Muse-and-Polar` "before the patent status of Muse Dashboard is clear".
  The recorder v8 was **not** copied into this repository. The author should confirm that the
  patent question does not also cover the live dashboard (`musepolar`) or the Research View before
  the repository is made public: publication before a patent filing can destroy novelty.
