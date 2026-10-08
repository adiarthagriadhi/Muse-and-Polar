# Release plan (v1.0.0 → Zenodo DOI)

Prepared, **not executed**. Each step that makes something public needs the author's explicit
approval at the time it is done. The repository stays private until then.

## A. Decisions

Taken by the author on 8 Oct 2026:

- Licence: **MIT**, copyright I Putu Adiartha Griadhi (`LICENSE`, `CITATION.cff`).
- `research/legacy/` removed from `main` (the original import stays in git history, commit `224f88e`).
- Research View heart analysis switched to the B1 pipeline (`ppg_b1.py`), Python and browser version.
- Condition labels (Tenang/Fokus/Teraktivasi) removed from the Research View.

Still open:

1. Third-party items in `docs/THIRD-PARTY.md` checked, including the patent note on "Muse Dashboard".
   Ask Sentra HKI / LPPM Universitas Udayana (a) whether anything should be filed as a patent before
   the open release (filing must precede publication) and (b) who holds the copyright for software
   made in the course of employment (author or university); update `LICENSE` and `CITATION.cff`
   accordingly.
2. Whether the git history is published as is or only a squashed `main`. The history contains no
   participant data, but older commits contain the removed condition labels and legacy front-ends,
   and a local OneDrive path of the research data folder (no data) in an early version of
   `research/app/api.py`.
3. Project name: keep "Muse–Polar" (trademark question in `docs/THIRD-PARTY.md`) or rename.

## B. Before going public (in the private repository)

Status 8 Oct 2026:

- [x] All work merged into `main`; every `claude/*` branch is contained in `main`
      (`git branch -r --no-merged origin/main` is empty).
- [x] CI green on `main` (Linux 3.11–3.13, macOS 3.13).
- [x] Privacy audit of the full history: no data files; no participant names or dates of birth.
- [x] `CHANGELOG.md` with the 1.0.0 entry; `CITATION.cff` validated (cffconvert, schema 1.2.0).
- [ ] Author: GitHub → Settings → General → Default branch → `main`.
- [ ] After that, delete the old branches (`claude/muse-polar-live-dashboard-te8izt`,
      `claude/pensive-allen-aw72zm`, `claude/focused-gauss-5arkdx`); nothing is lost, all are in `main`.
- [ ] At release time: `version: 1.0.0` and `date-released` in `CITATION.cff`, date in `CHANGELOG.md`.

## C. Going public (needs approval)

1. GitHub → Settings → General → Danger zone → *Change repository visibility* → Public.
   (Alternative: create a new public repository and push only `main`, if the history should not be
   published.)
2. Enable Issues; add topics (eeg, muse, polar-h10, ppg, hrv, ble, psychophysiology).

## D. Zenodo DOI (needs approval)

1. Log in to <https://zenodo.org> with GitHub (ORCID linked to the Zenodo account).
2. Zenodo → *GitHub* → switch **on** `adiarthagriadhi/Muse-and-Polar` (repository must be public).
3. Optional `.zenodo.json` (otherwise Zenodo uses `CITATION.cff`): creators with ORCID and affiliation,
   licence, keywords, `"upload_type": "software"`, related identifiers (B1/B2 DOIs, e.g.
   10.5281/zenodo.23099932 for B2, as `isSupplementTo`/`references` where appropriate).
4. GitHub → *Releases* → *Draft a new release* → tag `v1.0.0` on `main`, title "v1.0.0", notes from
   `CHANGELOG.md` → Publish. Zenodo archives the release and mints a version DOI plus a concept DOI.
5. Add the concept DOI badge to `README.md` and `doi:` to `CITATION.cff` (commit as v1.0.1 or as
   documentation-only change).

## E. JOSS (later, manuscript B3)

After B2 is submitted: write `paper.md` + `paper.bib` (in the hub `Article-Preparation`, new folder),
check the current JOSS submission requirements (open licence, public repository with issue tracker,
tests, statement of need, community guidelines, and any minimum period of public development), then
submit at <https://joss.theoj.org/papers/new> with the repository URL and the Zenodo DOI of the
reviewed version.
