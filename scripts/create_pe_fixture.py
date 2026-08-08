#!/usr/bin/env python3
"""Create the deterministic, code-free PE inspection contract fixture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def put_u16(image: bytearray, offset: int, value: int) -> None:
    image[offset : offset + 2] = value.to_bytes(2, "little")


def put_u32(image: bytearray, offset: int, value: int) -> None:
    image[offset : offset + 4] = value.to_bytes(4, "little")


def put_u64(image: bytearray, offset: int, value: int) -> None:
    image[offset : offset + 8] = value.to_bytes(8, "little")


def build_fixture() -> bytes:
    image = bytearray(0x400)
    image[0:2] = b"MZ"
    put_u32(image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"

    coff = 0x84
    put_u16(image, coff, 0x8664)
    put_u16(image, coff + 2, 1)
    put_u16(image, coff + 16, 0xF0)
    put_u16(image, coff + 18, 0x0022)

    optional = coff + 20
    put_u16(image, optional, 0x020B)
    put_u32(image, optional + 20, 0x1000)
    put_u64(image, optional + 24, 0x140000000)
    put_u32(image, optional + 32, 0x1000)
    put_u32(image, optional + 36, 0x200)
    put_u32(image, optional + 56, 0x2000)
    put_u32(image, optional + 60, 0x200)
    put_u16(image, optional + 68, 3)
    put_u32(image, optional + 108, 16)
    put_u32(image, optional + 120, 0x1000)
    put_u32(image, optional + 124, 40)

    section = optional + 0xF0
    image[section : section + 8] = b".rdata\0\0"
    put_u32(image, section + 8, 0x200)
    put_u32(image, section + 12, 0x1000)
    put_u32(image, section + 16, 0x200)
    put_u32(image, section + 20, 0x200)
    put_u32(image, section + 36, 0x40000040)

    put_u32(image, 0x20C, 0x1040)
    image[0x240:0x24D] = b"KERNEL32.dll\0"
    return bytes(image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    expected = build_fixture()

    if arguments.check:
        try:
            actual = arguments.output.read_bytes()
        except OSError as error:
            print(f"could not read PE fixture: {error}", file=sys.stderr)
            return 1
        if actual != expected:
            print("PE fixture does not match its deterministic generator", file=sys.stderr)
            return 1
        return 0

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
