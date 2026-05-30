# DJI DroneID Windows CRC Decoder

This is the minimal Windows/offline decoder package extracted from the local
Mini 2 experiment.  It keeps only the code needed to reproduce the CRC-valid
DroneID decode path.

## What is different from the original projects?

The CRC-valid decode uses the original DroneSecurity algorithm path:

- `dronesecurity/Packet.py` for timing, fine frequency offset, ZC detection,
  channel estimation, sampling offset correction, and OFDM symbol extraction.
- `dronesecurity/qpsk.py` for QPSK hard decisions, Gold descrambling, cyclic
  buffer extraction, and rate-matching reversal.
- `dronesecurity/droneid_packet.py` for DJI DroneID field parsing and CRC.

The core DroneSecurity PHY/packet code is intentionally kept as-is.  The new
code in this repository is the Windows reproducibility layer:

- `tools/windows_droneid_decode.py`
- `tools/windows_decode_droneid.ps1`

Those wrappers make the successful path one-command repeatable on Windows and
write JSON/CSV outputs for every phase/parameter attempt.

The proto17/dji_droneid MATLAB path was useful for diagnosis, but it did not
produce the final CRC-valid payload in this experiment.

## Install dependencies

Use the same Python environment that can run numpy/scipy on Windows:

```powershell
python -m pip install -r requirements.txt
```

On the local machine this was run with:

```powershell
D:\anconda3\envs\sdr\python.exe
```

## One-command offline decode

Input format defaults to interleaved float32 IQ (`I0,Q0,I1,Q1,...`) at
15.36 MSPS.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows_decode_droneid.ps1 `
  -InputFile "D:\path\to\live_5796p5_rx2_zc80ms_fc32.cfile" `
  -OutDir ".\decode_out"
```

Known-good local sample result:

- `phase=1`
- `linear_rotation=0`
- `sampling_offset=0`
- `tune=0`
- `crc-packet=0e7e`
- `crc-calculated=0e7e`
- `device_type=Mini 2`

The wrapper stops after the first CRC-valid payload and writes:

- `*_decode_result.json`
- `*_decode_attempts.csv`

## Offline vs online decoding

The current package is an offline decoder: it expects a short IQ file already
cropped around a DroneID burst.  A live receiver has to do more work because
the drone can hop frequency and the RF channel can change between bursts.

A practical online path should:

1. Stream 15.36 MSPS IQ from USRP B210 into a ring buffer.
2. Scan known DroneID centers:
   `2399.5`, `2414.5`, `2429.5`, `2444.5`, `2459.5`,
   `5756.5`, `5776.5`, `5796.5` MHz.
3. Use a fast root-600 ZC detector as the trigger.
4. Crop a short window around each candidate peak.
5. Re-estimate CFO, sample offset, ZC roots, and channel for every burst.
6. Run this decoder on the crop.
7. Accept only CRC-valid payloads.

The changing channel is not fatal.  DroneID frames contain ZC reference symbols,
so a live receiver should refresh timing, CFO, and channel estimates per burst
instead of reusing an old channel estimate.

## Attribution and license

The `dronesecurity/` code is from RUB-SysSec/DroneSecurity and is distributed
under its original GPL license.  See `LICENSE.DroneSecurity`.

