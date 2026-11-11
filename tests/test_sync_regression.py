"""Regression tests for the v1.0.0 synchronisation failure (fixed in 1.0.1).

Cause 1 (timestamps): ``SampleClock`` re-anchored to a packet that arrived more than
0.25 s late and then refused to step back, so one Bluetooth delivery delay shifted
every later timestamp of that stream forward for the rest of the connection.
Cause 2 (matching): ``estimate_offset`` searched only ±1 s, so after such a shift the
jumps were seen by both sensors but reported as "korelasi rendah", and a peak near
the edge of the search range could be accepted with a wrong offset.

The end-to-end tests send real Muse / Polar packet bytes through ``Muse.on_acc`` and
``PolarH10.on_pmd_data`` with a patched receive clock, as on hardware.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

import musepolar.muse as M
import musepolar.polar as P
from musepolar.analysis import estimate_offset
from musepolar.hub import Hub
from musepolar.streams import SampleClock


# -- SampleClock ------------------------------------------------------------

def _clock_errors(rate, n, hold_at=None, hold=0.0, true_rate=None, lat=0.03, seconds=120, jitter=0.0, seed=0):
    """Feed packets with constant latency (+ optional jitter / one delivery hold); return stamp errors."""
    rng = np.random.default_rng(seed)
    true_rate = true_rate or rate
    c = SampleClock(rate)
    period = n / true_rate
    out, prev_recv, prev_last = [], 0.0, None
    for k in range(int(seconds / period)):
        t_last = 1000 + (k + 1) * period - 1 / true_rate  # true time of the packet's last sample
        recv = t_last + lat + (rng.exponential(jitter) if jitter else 0.0)
        if hold_at is not None and hold_at <= t_last < hold_at + hold:
            recv = hold_at + hold + lat  # packets held back, then released together
        recv = max(recv, prev_recv)  # BLE keeps notification order
        prev_recv = recv
        ts = c.stamps(n, recv)
        if prev_last is not None:
            assert ts[0] > prev_last  # strictly increasing
        prev_last = ts[-1]
        out.append((t_last, ts[-1] - t_last))
    return out


@pytest.mark.parametrize("rate,n", [(52, 3), (200, 36), (256, 12), (64, 6), (130, 73)])
@pytest.mark.parametrize("hold", [0.4, 1.0, 2.5])
def test_delivery_hold_does_not_shift_later_timestamps(rate, n, hold):
    errs = _clock_errors(rate, n, hold_at=1030.0, hold=hold)
    before = [e for t, e in errs if 1020 < t < 1030]
    after = [e for t, e in errs if t > 1030 + hold + 2]
    assert max(abs(e) for e in before) < 0.06
    # v1.0.0: every later stamp was ~hold seconds late
    assert max(abs(e) for e in after) < 0.06


@pytest.mark.parametrize("ppm", [-10000, -3000, 3000, 10000])
def test_crystal_drift_stays_bounded(ppm):
    errs = _clock_errors(52, 3, true_rate=52 * (1 + ppm * 1e-6), seconds=600, jitter=0.02)
    late = [e for t, e in errs if t > 1100]
    assert max(abs(e) for e in late) < 0.25


def test_skipped_samples_still_advance_and_large_gap_reanchors():
    c = SampleClock(52)
    a = c.stamps(3, 1000.0)
    b = c.stamps(3, 1000.0 + 6 / 52, skipped=3)  # one packet lost, reported by sequence number
    assert b[0] - a[-1] == pytest.approx(4 / 52, abs=1e-9)
    d = c.stamps(3, 1000.0 + 30)  # 30 s with no packets and no reported loss: re-anchor
    assert d[-1] == pytest.approx(1030.0, abs=1e-9)


def test_reset_restarts_device_time():
    c = SampleClock(200)
    c.stamps(36, 5000.0)
    c.reset()
    ts = c.stamps(36, 10.0)
    assert ts[-1] == pytest.approx(10.0)


# -- end to end: packets -> clocks -> Hub.compute_sync -------------------------

def _vertical(t, onsets, head):
    """Specific force (g) of counter-movement jumps; free fall reads 0 g on both sensors."""
    v = np.ones_like(t)
    for e in onsets:
        d = t - e
        v += -0.45 * np.exp(-((d + 0.45) ** 2) / (2 * 0.08 ** 2)) + 1.1 * np.exp(-((d + 0.18) ** 2) / (2 * 0.07 ** 2))
        v[(d >= 0) & (d < 0.3)] = 0.0
        w, imp = (0.035, 1.3) if head else (0.018, 3.0)
        v += imp * np.exp(-((d - 0.3 - w) ** 2) / (2 * w ** 2))
    return v


def _packets(kind, start, seconds, onsets, lat, holds, rng):
    rate, n = (52, 3) if kind == "muse" else (200, 36)
    t = start + np.arange(int(seconds * rate)) / rate
    vert = _vertical(t, onsets, kind == "muse")
    noise = rng.normal(0, 0.01, (len(t), 3))
    out, prev = [], 0.0
    for k in range(0, len(t) - n + 1, n):
        last = k + n - 1
        recv = t[last] + lat + rng.exponential(0.015)
        for h0, hd in holds:
            if h0 <= recv < h0 + hd:
                recv = h0 + hd
        recv = max(recv, prev)
        prev = recv
        if kind == "muse":
            xyz = np.clip(np.stack([0.03 + noise[k:k + n, 0], -0.1 + noise[k:k + n, 1], vert[k:k + n] + noise[k:k + n, 2]], 1), -2, 2)
            raw = np.round(xyz / M.ACC_SCALE).astype(int).clip(-32768, 32767)
            data = (k // n % 65536).to_bytes(2, "big") + b"".join(int(v).to_bytes(2, "big", signed=True) for v in raw.ravel())
        else:
            xyz = np.stack([-vert[k:k + n] + noise[k:k + n, 0], 0.05 + noise[k:k + n, 1], 0.12 + noise[k:k + n, 2]], 1)
            sensor_ns = int(7e17 + (t[last] - start) * 1e9)
            body = b"".join(int(round(v * 1000)).to_bytes(2, "little", signed=True) for v in xyz.ravel())
            data = bytes([P.PMD_ACC]) + sensor_ns.to_bytes(8, "little") + b"\x01" + body
        out.append((recv, kind, data))
    return out


def _session(muse_holds=(), polar_holds=(), muse_lat=0.06, polar_lat=0.04, seed=0):
    rng = np.random.default_rng(seed)
    hub = Hub("/nonexistent")
    muse, polar = M.Muse(hub), P.PolarH10(hub)
    t0 = 1.0e9
    onsets = [t0 + 2.0, t0 + 4.7, t0 + 7.1]
    start = t0 - 300  # devices connected 5 min before the sync
    events = _packets("muse", start, 312, onsets, muse_lat, [(t0 + a, d) for a, d in muse_holds], rng)
    events += _packets("polar", start, 312, onsets, polar_lat, [(t0 + a, d) for a, d in polar_holds], rng)
    events.sort(key=lambda e: e[0])
    for recv, kind, data in events:
        with mock.patch("time.time", return_value=float(recv)):
            (muse.on_acc if kind == "muse" else polar.on_pmd_data)(data)
    return hub.compute_sync(t0, t0 + 10)


def test_sync_ok_without_delivery_delays():
    r = _session()
    assert r["ok"], r
    assert abs(r["muse_minus_polar_s"]) < 0.1


@pytest.mark.parametrize("muse_holds,polar_holds", [
    ([(-200, 1.3)], []),                              # one Muse delay > 1 s (v1.0.0: "korelasi rendah")
    ([(-250, 0.6), (-120, 2.0)], [(-60, 0.5)]),       # several delays on both devices
    ([], [(-30, 1.6)]),                               # Polar delay
])
def test_sync_survives_earlier_delivery_delays(muse_holds, polar_holds):
    r = _session(muse_holds, polar_holds)
    assert r["ok"], r
    assert abs(r["muse_minus_polar_s"]) < 0.1  # the true shift is only the latency difference


# -- estimate_offset ----------------------------------------------------------------

def _acc(rate, delay, events, rng):
    t = np.arange(0, 10, 1 / rate) + 1000
    bump = sum(2.0 * np.exp(-((t - 1000 - e - delay) ** 2) / (2 * 0.03 ** 2)) for e in events)
    return t, np.stack([rng.normal(0, 0.01, len(t)), rng.normal(0, 0.01, len(t)), 1 + bump], 1)


@pytest.mark.parametrize("lag", [1.2, -1.6, 2.4])
def test_offsets_beyond_one_second_are_found(lag):
    rng = np.random.default_rng(3)
    ev = (2.0, 4.6, 7.3)
    r = estimate_offset(*_acc(52, lag, ev, rng), *_acc(200, 0.0, ev, rng))
    assert r["ok"], r
    assert abs(r["offset_s"] - lag) < 0.01


def test_peak_at_edge_of_search_is_not_accepted():
    rng = np.random.default_rng(4)
    ev = (2.0, 4.6, 7.3)
    r = estimate_offset(*_acc(52, 1.25, ev, rng), *_acc(200, 0.0, ev, rng), max_lag=1.0)
    assert not r["ok"]  # v1.0.0 could accept a wrong offset near ±1 s


def test_ambiguous_match_is_not_accepted():
    rng = np.random.default_rng(5)
    ev = (1.5, 4.0, 6.5, 9.0)  # perfectly regular jumps, shift = 1.5 s of a 2.5 s period
    r = estimate_offset(*_acc(52, 1.5, ev, rng), *_acc(200, 0.0, ev, rng))
    assert not r["ok"] and "ambigu" in r["reason"]


# -- offline diagnosis tool ----------------------------------------------------------

def _recorded_session(tmp_path, shift_muse_after=None, shift=0.0):
    """Record a session (with one sync) through Hub + Recorder; optionally mimic the v1.0.0
    timestamp fault by shifting Muse timestamps forward after a given time."""
    rng = np.random.default_rng(7)
    t0 = 1.0e9
    with mock.patch("time.time", return_value=t0 - 60):
        hub = Hub(tmp_path)
        hub.start_recording("P01_test")
    muse, polar = M.Muse(hub), P.PolarH10(hub)
    onsets = [t0 + 2.0, t0 + 4.7, t0 + 7.1]
    ev = _packets("muse", t0 - 60, 80, onsets, 0.06, [], rng) + _packets("polar", t0 - 60, 80, onsets, 0.04, [], rng)
    ev.sort(key=lambda e: e[0])
    for recv, kind, data in ev:
        with mock.patch("time.time", return_value=float(recv)):
            (muse.on_acc if kind == "muse" else polar.on_pmd_data)(data)
    res = hub.compute_sync(t0, t0 + 10)
    hub.recorder.add_sync(res)
    with mock.patch("time.time", return_value=t0 + 20.5):
        info = hub.stop_recording()
    folder = Path(info["dir"])
    if shift_muse_after is not None:
        rows = list(csv.reader(open(folder / "muse_acc.csv")))
        for r in rows[1:]:
            if float(r[0]) > shift_muse_after:
                r[0] = f"{float(r[0]) + shift:.6f}"
        with open(folder / "muse_acc.csv", "w", newline="") as f:
            csv.writer(f).writerows(rows)
        meta = json.loads((folder / "session.json").read_text())
        meta["sync"] = []  # as in the field: no usable sync result, only markers
        (folder / "session.json").write_text(json.dumps(meta))
        with open(folder / "marker.csv", "w", newline="") as f:
            csv.writer(f).writerows([["timestamp", "label"], [t0, "SYNC mulai"], [t0 + 30, "catatan bebas peserta"]])
    return folder, res



def test_diagnose_clean_session(tmp_path):
    from musepolar.diagnose import diagnose

    folder, res = _recorded_session(tmp_path)
    assert res["ok"]
    rep = diagnose(folder)
    assert rep["folder"].count("_") == 1 and "P01" not in json.dumps(rep)
    assert rep["polar_host_shift"]["polar_acc"]["max_sustained_ms"] < 100
    s = rep["syncs"][0]
    assert s["v1_0_1_window_3s"]["ok"] and s["v1_0_0_window_1s"]["ok_rule_v1_0_0"]


def test_diagnose_shows_shifted_timestamps(tmp_path):
    from musepolar.diagnose import diagnose

    folder, _ = _recorded_session(tmp_path, shift_muse_after=1.0e9 - 30, shift=1.4)
    rep = diagnose(folder)
    assert rep["sync_markers"] == [(1.0e9, "SYNC mulai")]  # free-text markers are not read
    s = rep["syncs"][0]
    assert not s["v1_0_0_window_1s"]["ok_rule_v1_0_0"]
    assert abs(s["wide_8s"]["offset_s"] - 1.4) < 0.1 and s["wide_8s"]["correlation"] > 0.7

