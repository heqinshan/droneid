#!/usr/bin/env python3
"""One-shot Windows-friendly DroneID offline decoder.

This script wraps the successful DroneSecurity path used in the local Mini 2
capture experiment:

    Packet -> get_symbol_data(skip_zc=True) -> qpsk.Decoder -> DroneIDPacket

It does not modify DroneSecurity's PHY/packet logic.  The wrapper only makes
the path repeatable from Windows, records every attempted phase/parameter
combination, and writes JSON/CSV artifacts for later review.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_DRONESECURITY_SRC = Path(__file__).resolve().parents[1] / "dronesecurity"


def parse_csv_floats(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def add_dronesecurity_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"DroneSecurity src path not found: {path}. "
            "This minimal repository should contain a local dronesecurity/ "
            "directory, or pass --dronesecurity-src."
        )
    sys.path.insert(0, str(path))


def load_iq(path: Path, sample_type: str) -> np.ndarray:
    if sample_type == "fc32":
        return np.memmap(path, mode="r", dtype="<f4").astype(np.float32).view(np.complex64)
    if sample_type == "sc16":
        raw = np.memmap(path, mode="r", dtype="<i2").astype(np.float32)
        if raw.size % 2:
            raw = raw[:-1]
        return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64) / 32768.0
    raise ValueError(f"Unsupported sample type: {sample_type}")


def payload_to_row(payload: Any, raw: bytes) -> dict[str, str]:
    droneid = payload.droneid
    return {
        "crc_ok": str(payload.check_crc()),
        "pkt_len": str(droneid.get("pkt_len", "")),
        "version": str(droneid.get("version", "")),
        "sequence_number": str(droneid.get("sequence_number", "")),
        "serial_number": str(droneid.get("serial_number", "")),
        "device_type": str(droneid.get("device_type", "")),
        "uuid": str(droneid.get("uuid", "")),
        "latitude": str(droneid.get("latitude", "")),
        "longitude": str(droneid.get("longitude", "")),
        "latitude_home": str(droneid.get("latitude_home", "")),
        "longitude_home": str(droneid.get("longitude_home", "")),
        "height": str(droneid.get("height", "")),
        "altitude": str(droneid.get("altitude", "")),
        "crc_packet": str(droneid.get("crc-packet", "")),
        "crc_calculated": str(droneid.get("crc-calculated", "")),
        "hex_prefix": raw.hex()[:96],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Decode a DroneID fc32/sc16 IQ file with DroneSecurity")
    parser.add_argument("--input", required=True, help="Input interleaved IQ file")
    parser.add_argument("--sample-rate", type=float, default=15.36e6, help="Sample rate in Hz")
    parser.add_argument("--sample-type", choices=["fc32", "sc16"], default="fc32")
    parser.add_argument("--dronesecurity-src", default=str(DEFAULT_DRONESECURITY_SRC))
    parser.add_argument("--out-dir", default="decode_out")
    parser.add_argument("--linear-rotations", default="0", help="Comma-separated linear_rotation values")
    parser.add_argument("--sample-offsets", default="0", help="Comma-separated extra sampling offsets")
    parser.add_argument("--tunes", default="0", help="Comma-separated tune values in Hz")
    parser.add_argument("--phases", default="0,1,2,3", help="Comma-separated QPSK phase corrections")
    parser.add_argument("--disable-zc-detection", action="store_true")
    parser.add_argument("--stop-on-crc-ok", action="store_true", default=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    add_dronesecurity_path(Path(args.dronesecurity_src))
    from Packet import Packet  # type: ignore
    from qpsk import Decoder  # type: ignore
    from droneid_packet import DroneIDPacket  # type: ignore

    raw_samples = load_iq(input_path, args.sample_type)
    init_log = io.StringIO()
    with contextlib.redirect_stdout(init_log):
        packet = Packet(
            raw_samples.copy(),
            Fs=args.sample_rate,
            enable_zc_detection=not args.disable_zc_detection,
            debug=False,
        )

    linear_values = parse_csv_floats(args.linear_rotations)
    sample_offsets = parse_csv_floats(args.sample_offsets)
    tunes = parse_csv_floats(args.tunes)
    phases = [int(value) for value in parse_csv_floats(args.phases)]

    attempts: list[dict[str, Any]] = []
    crc_ok_payloads: list[dict[str, Any]] = []
    for linear in linear_values:
        for sample_offset in sample_offsets:
            for tune in tunes:
                symbols = packet.get_symbol_data(
                    linear_rotation=linear,
                    _sampling_offset=sample_offset,
                    tune=tune,
                    skip_zc=True,
                )
                for phase in phases:
                    decoder = Decoder(symbols)
                    decoder.raw_data_to_symbol_bits(phase)
                    decoded = decoder.magic()
                    row: dict[str, Any] = {
                        "input": str(input_path),
                        "sample_rate": args.sample_rate,
                        "sample_type": args.sample_type,
                        "linear_rotation": linear,
                        "sampling_offset": sample_offset,
                        "tune_hz": tune,
                        "phase": phase,
                        "decoded_len": len(decoded),
                        "first_byte": decoded[0] if decoded else "",
                        "likely_len": bool(decoded and 0 < decoded[0] <= 91),
                        "error": "",
                    }
                    try:
                        payload = DroneIDPacket(decoded)
                        row.update(payload_to_row(payload, decoded))
                        row["droneid"] = payload.droneid
                        if payload.check_crc():
                            crc_ok_payloads.append(row)
                    except Exception as exc:  # Keep failed attempts for diagnostics.
                        row.update(
                            {
                                "crc_ok": "False",
                                "crc_packet": "",
                                "crc_calculated": "",
                                "hex_prefix": decoded.hex()[:96],
                                "error": repr(exc),
                            }
                        )
                    attempts.append(row)
                    print(
                        "phase={phase} linear={linear_rotation} sample_offset={sampling_offset} "
                        "tune={tune_hz} crc_ok={crc_ok} first_byte={first_byte}".format(**row)
                    )
                    if row.get("crc_ok") == "True" and args.stop_on_crc_ok:
                        break
                if crc_ok_payloads and args.stop_on_crc_ok:
                    break
            if crc_ok_payloads and args.stop_on_crc_ok:
                break
        if crc_ok_payloads and args.stop_on_crc_ok:
            break

    result = {
        "input": str(input_path),
        "dronesecurity_src": str(Path(args.dronesecurity_src)),
        "packet_init_log": init_log.getvalue(),
        "attempt_count": len(attempts),
        "crc_ok_count": len(crc_ok_payloads),
        "crc_ok_payloads": crc_ok_payloads,
        "attempts": attempts,
    }

    json_path = out_dir / f"{input_path.stem}_decode_result.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out_dir / f"{input_path.stem}_decode_attempts.csv"
    fieldnames = [
        "input",
        "sample_rate",
        "sample_type",
        "linear_rotation",
        "sampling_offset",
        "tune_hz",
        "phase",
        "decoded_len",
        "first_byte",
        "likely_len",
        "crc_ok",
        "pkt_len",
        "version",
        "sequence_number",
        "serial_number",
        "device_type",
        "uuid",
        "latitude",
        "longitude",
        "latitude_home",
        "longitude_home",
        "height",
        "altitude",
        "crc_packet",
        "crc_calculated",
        "hex_prefix",
        "error",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(attempts)

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    if crc_ok_payloads:
        best = crc_ok_payloads[0]["droneid"]
        print("CRC OK")
        print(json.dumps(best, ensure_ascii=False, indent=2))
        return 0

    print("No CRC-valid DroneID payload found")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
