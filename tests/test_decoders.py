import csv
import json
import math

import numpy as np

from musepolar.analysis import EegBands, Hrv
from musepolar.muse import (
    ACC_SCALE,
    EEG_SCALE,
    PacketJoiner,
    decode_eeg,
    decode_imu,
    decode_ppg,
    decode_telemetry,
    encode_command,
)
from musepolar.polar import decode_ecg, decode_hr
from musepolar.recorder import Recorder
from musepolar.streams import SampleClock, seq_gap


def pack12(values):
    out = bytearray()
    for a, b in zip(values[0::2], values[1::2]):
        out += bytes([a >> 4, ((a & 0xF) << 4) | (b >> 8), b & 0xFF])
    return bytes(out)


def test_encode_command():
    assert encode_command("p50") == bytes([4, ord("p"), ord("5"), ord("0"), ord("\n")])
    assert encode_command("d") == b"\x02d\n"


def test_decode_eeg():
    raw = [0x800, 0x000, 0xFFF, 0x801, 0x123, 0xABC, 0x800, 0x800, 0x7FF, 0x001, 0x999, 0x456]
    seq, uv = decode_eeg((513).to_bytes(2, "big") + pack12(raw))
    assert seq == 513
    assert uv == [EEG_SCALE * (r - 0x800) for r in raw]
    assert uv[0] == 0 and uv[1] == -1000.0


def test_decode_ppg_imu_telemetry():
    vals = [1, 2, 0xFFFFFF, 70000, 0, 123456]
    seq, out = decode_ppg(b"\x00\x07" + b"".join(v.to_bytes(3, "big") for v in vals))
    assert seq == 7 and out == [float(v) for v in vals]

    ints = [100, -100, 16384, 0, 1, -1, 5, 6, 7]
    seq, rows = decode_imu(b"\x00\x01" + b"".join(v.to_bytes(2, "big", signed=True) for v in ints), ACC_SCALE)
    assert len(rows) == 3 and math.isclose(rows[0][2], 16384 * ACC_SCALE)
    assert math.isclose(rows[0][1], -100 * ACC_SCALE)

    tele = decode_telemetry(b"".join(v.to_bytes(2, "big") for v in [1, 512 * 80, 1000, 0, 25]) + bytes(10))
    assert tele[0] == 80.0 and math.isclose(tele[1], 2200.0)


def test_packet_joiner_and_wraparound():
    j = PacketJoiner(2)
    assert j.add(10, 0, [1, 2]) is None
    assert j.add(10, 1, [3, 4]) == [[1, 3], [2, 4]]
    assert j.add(65535, 0, [0]) is None
    assert j.add(0, 0, [5]) is None
    assert j.add(0, 1, [6]) == [[5, 6]]
    assert 65535 not in j.pending  # stale older packet dropped


def test_seq_gap():
    assert seq_gap(None, 5) == 0
    assert seq_gap(5, 6) == 0
    assert seq_gap(5, 8) == 2
    assert seq_gap(65535, 1) == 1
    assert seq_gap(10, 9) == 0


def test_sample_clock_monotonic_and_spaced():
    c = SampleClock(256)
    t = 1000.0
    last = None
    for k in range(200):
        ts = c.stamps(12, t + k * 12 / 256 + (0.01 if k % 3 else 0))
        assert len(ts) == 12
        if last is not None:
            assert ts[0] > last
        assert all(math.isclose(b - a, 1 / 256) for a, b in zip(ts, ts[1:]))
        last = ts[-1]
    # gap of 2 packets moves the clock forward
    ts = c.stamps(12, t + 202 * 12 / 256, skipped=24)
    assert ts[0] - last > 20 / 256


def test_decode_hr():
    # uint8 HR, contact supported+detected, 2 RR values
    data = bytes([0x16, 72]) + (1024).to_bytes(2, "little") + (820).to_bytes(2, "little")
    hr, contact, rr = decode_hr(data)
    assert hr == 72 and contact == 1
    assert rr[0] == 1000.0 and math.isclose(rr[1], 820 / 1024 * 1000)
    # uint16 HR, contact not supported, energy expended present, no RR
    hr, contact, rr = decode_hr(bytes([0x09]) + (150).to_bytes(2, "little") + b"\x00\x00")
    assert hr == 150 and contact == -1 and rr == []


def test_decode_ecg():
    samples = [0, 1, -1, 1500, -2000]
    frame = bytes([0x00]) + (123).to_bytes(8, "little") + bytes([0x00])
    frame += b"".join(s.to_bytes(3, "little", signed=True) for s in samples)
    assert decode_ecg(frame) == [float(s) for s in samples]
    assert decode_ecg(bytes([0x02]) + frame[1:]) is None  # accelerometer frame


def test_eeg_bands_detect_alpha():
    bands = EegBands()
    t = np.arange(512) / 256
    sig = 800 + 30 * np.sin(2 * np.pi * 10 * t) + np.random.default_rng(0).normal(0, 1, 512)
    for k in range(0, 512, 12):
        bands.add([[v] * 4 for v in sig[k:k + 12]])
    res = bands.compute()
    assert res is not None
    assert max(res["relative"], key=res["relative"].get) == "alpha"
    assert res["relative"]["alpha"] > 0.8


def test_hrv():
    h = Hrv()
    for k, rr in enumerate([800, 850, 800, 850, 800, 850]):
        h.add(k * 0.8, rr)
    r = h.compute()
    assert math.isclose(r["rmssd"], 50.0)
    assert r["pnn50"] == 0.0
    h.add(6, 5000)  # implausible, ignored
    assert h.compute()["n"] == 6


def test_recorder(tmp_path):
    rec = Recorder(tmp_path, "subjek 01/test", devices={"muse": {"state": "streaming"}})
    rec.write("muse_eeg", [1.0, 2.0], [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]])
    rec.write("marker", [1.5], [["Mata tertutup"]])
    rec.close()
    assert rec.dir.name.endswith("subjek_01_test")
    with open(rec.dir / "muse_eeg.csv") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["timestamp", "TP9", "AF7", "AF8", "TP10"]
    assert rows[2] == ["2.000000", "5.0", "6.0", "7.0", "8.0"]
    meta = json.loads((rec.dir / "session.json").read_text())
    assert meta["samples"] == {"muse_eeg": 2, "marker": 1}
    assert meta["end_unix"] is not None
