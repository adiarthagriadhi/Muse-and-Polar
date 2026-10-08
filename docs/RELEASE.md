# Release plan (v1.0.0 → Zenodo DOI)

Prepared, **not executed**. Each step that makes something public needs the author's explicit
approval at the time it is done. The repository stays private until then.

## A. Decisions the author must make first

1. Licence: MIT or Apache-2.0 (copyright holder: I Putu Adiartha Griadhi). Add `LICENSE` and the
   `license:` field in `CITATION.cff`.
2. Keep or remove `research/legacy/` (old front-ends kept for comparison; original import is
   preserved in git history at commit `224f88e` either way).
3. Research View heart pipeline: switch the display to the B1 pipeline (`ppg_b1.py`) or keep the
   exploratory pipeline with its label (see README, "Heart-rate and pulse-rate variability").
4. Condition labels (Tenang/Fokus/Teraktivasi from EEG + heart rate): confirm they do not conflict
   with the decision of 1 Oct 2026 (no cortex–autonomic quadrant mapping claims), or remove them.
5. Third-party items in `docs/THIRD-PARTY.md` checked, including the patent note on "Muse Dashboard".
6. Whether the git history is published as is (it contains no participant data; see the audit in
   the hand-over report) or squashed.

## B. Before going public (in the private repository)

1. Merge all work into `main`; set `main` as the default branch on GitHub
   (Settings → General → Default branch); delete the old `claude/*` branches after checking that
   nothing is lost (`git branch -r --no-merged origin/main` should be empty).
2. CI green on `main` (Actions → tests).
3. Re-run the privacy audit on the full history:
   `git log --all --name-only --format= | sort -u` (no data files) and
   `git grep -n -i -E "nama|birth|lahir|onedrive" $(git rev-list --all)` (review hits).
4. Update `CITATION.cff` (`version: 1.0.0`, `date-released`) and add a `CHANGELOG.md` entry.

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
