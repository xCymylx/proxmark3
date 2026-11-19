#!/usr/bin/env python3
"""Prepare a Kirby Air Riders (amiibo v3, NTAG I2C plus 2K) dump for Proxmark3 emulation.

Needs firmware with NTAG I2C plus 2K support in `hf mfu sim -t 7` (branch
ntag-i2c-plus-sim). The output is a 56 byte Ultralight/NTAG dump header whose
GET_VERSION says NTAG I2C plus 2K, followed by the 2048 byte dump, padded to a
multiple of 16 so `hf mf eload --4k` loads it as is (`hf mfu eload` stops at
page 254, and these tags have 512 pages).

    amiibo_v3_emu.py "Kirby & Warp.bin" -o kirby.eml.bin
    amiibo_v3_emu.py kirby.bin --machine "Machines/Winged Star.bin" -o kirby-winged.bin

then in the Proxmark3 client:

    hf mf eload --4k -f kirby.eml.bin
    hf mfu sim -t 7 -u <uid printed by this script>
"""

import argparse
import sys
from pathlib import Path

IMAGE_SIZE = 2048
MACHINE_POS, MACHINE_SIZE = 0x3C0, 64
VERSION = bytes.fromhex("0004040502021503")      # NTAG I2C plus 2K
HEADER_SIZE = 56


def crc16_mcrf4xx(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


def machine_ok(block: bytes) -> bool:
    return (len(block) == MACHINE_SIZE and block != bytes(MACHINE_SIZE)
            and crc16_mcrf4xx(block[:62]) == int.from_bytes(block[62:], "big"))


def build(image: bytes) -> bytes:
    header = (VERSION
              + bytes(3)             # tbo, tbo1
              + bytes([0xFF])        # pages (max page number of sector 0)
              + bytes(32)            # READ_SIG: zeros, accepted by the game
              + bytes(12))           # counters / tearing flags
    assert len(header) == HEADER_SIZE
    out = header + image
    return out + bytes(-len(out) % 16)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dump", type=Path, help="2048 byte Air Riders dump (rider + machine)")
    ap.add_argument("--machine", type=Path, help="64 byte machine block to put the rider on")
    ap.add_argument("-o", "--out", type=Path, required=True, help="file for `hf mf eload --4k`")
    a = ap.parse_args()

    image = a.dump.read_bytes()
    if len(image) != IMAGE_SIZE or image[0x10] != 0xA5 or image[0x0C:0x10] != bytes.fromhex("F110FFEE"):
        sys.exit(f"{a.dump}: not a 2048 byte Kirby Air Riders dump")
    if a.machine:
        block = a.machine.read_bytes()
        if not machine_ok(block):
            sys.exit(f"{a.machine}: not a valid 64 byte machine block (size or checksum)")
        image = image[:MACHINE_POS] + block + image[MACHINE_POS + MACHINE_SIZE:]
    elif not machine_ok(image[MACHINE_POS:MACHINE_POS + MACHINE_SIZE]):
        print("warning: the dump's machine block is empty or its checksum is wrong", file=sys.stderr)

    a.out.write_bytes(build(image))
    uid = image[:7].hex().upper()        # no BCC bytes on NTAG I2C: page 0-1 hold the UID as is
    print(f"wrote {a.out} ({a.out.stat().st_size} bytes), amiibo id {image[0x54:0x5C].hex()}")
    print(f"  hf mf eload --4k -f {a.out}")
    print(f"  hf mfu sim -t 7 -u {uid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
