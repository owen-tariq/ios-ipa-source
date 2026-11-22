#!/usr/bin/env python3
"""Disable only WebGL in Yozora's ARM64 app settings, preserving JavaScript.

The user's crash logs consistently end at Apple's GLEngine, reached through
Yozora's GL_GetInternalformativRobustANGLE adapter, which incorrectly drops
the bufSize argument expected by native glGetInternalformativ.

The YZSettings +applyToCore compiled method initializes two adjacent
32-bit options:
    movi v0.2s, #1
    str d0, [sp, #0x18]
They are options.webgl and options.external_links, respectively.

Replace these two ARM64 instructions with:
    movz x8, #1, lsl #32
    str x8, [sp, #0x18]
The first setting becomes 0 (WebGL disabled), the second stays 1.

This binary workaround is limited to explicitly audited upstream releases.
If the relevant method bytes or layout change, abort without output.
"""
import re
import struct
import subprocess
import sys
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

if len(sys.argv) != 3:
    raise SystemExit("usage: disable_webgl_arm64.py ARM64_EXECUTABLE UPSTREAM_RELEASE_TAG")

path = Path(sys.argv[1])
tag = sys.argv[2]
if tag not in {"v1.1.0-stable", "v1.2.0-stable"}:
    raise SystemExit(f"Unknown upstream release {tag}, refusing binary patch")

data = bytearray(path.read_bytes())
if data[:4] != bytes.fromhex("cffaedfe"):
    raise SystemExit("Not a thin ARM64 Mach-O executable")
ncmds = struct.unpack_from("<I", data, 16)[0]
lc_offset = 32
text_segment = None
for _ in range(ncmds):
    cmd, cmdsize = struct.unpack_from("<II", data, lc_offset)
    if cmd == 0x19:
        segment_name = bytes(data[lc_offset+8:lc_offset+24]).rstrip(b"\0")
        if segment_name == b"__TEXT":
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, lc_offset+24)
            text_segment = (vmaddr, vmsize, fileoff, filesize)
    lc_offset += cmdsize

if text_segment is None:
    raise SystemExit("Cannot locate Mach-O __TEXT segment")
vmaddr, vmsize, fileoff, filesize = text_segment

# Extract the class method implementation address from the actual Objective-C
# metadata, so adding UI features in v1.2 does not invalidate a hardcoded offset.
metadata = subprocess.check_output(
    ["xcrun", "llvm-objdump", "--macho", "--objc-meta-data", str(path)],
    stderr=subprocess.DEVNULL, text=True
)
matches = re.findall(
    r"name\s+0x[0-9a-fA-F]+\s+applyToCore\s*\n\s*types\s+[^\n]+\n\s*imp\s+(0x[0-9a-fA-F]+)",
    metadata,
)
if len(matches) != 1:
    raise SystemExit(f"Expected one +[YZSettings applyToCore] method, found {matches}")
method_va = int(matches[0], 16)
if not (vmaddr <= method_va < vmaddr + vmsize):
    raise SystemExit("Method address not inside __TEXT segment")
method_offset = fileoff + (method_va-vmaddr)

# Check that the two consecutive instructions are in this exact method.
before = bytes.fromhex("2004000fe00f00fd")
after = bytes.fromhex("2800c0d2e80f00f9")
section = bytes(data[method_offset:method_offset+0x230])
positions = [i for i in range(0, len(section)-7, 4) if section[i:i+8] == before]
if len(positions) != 1:
    raise SystemExit(f"Expected unique WebGL+external_links initialization in method, found {positions}")
patch_offset = method_offset+positions[0]
patch_va = method_va+positions[0]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
decoded_before = [(i.mnemonic, i.op_str) for i in md.disasm(before, patch_va)]
decoded_after = [(i.mnemonic, i.op_str) for i in md.disasm(after, patch_va)]
if len(decoded_before) != 2 or decoded_before[0][0] != "movi" or decoded_before[1][0] != "str":
    raise SystemExit(f"Unexpected WebGL option initialization: {decoded_before}")
if len(decoded_after) != 2 or decoded_after[0][0] not in ("mov", "movz") or decoded_after[1][0] != "str":
    raise SystemExit(f"Failed to validate patched instructions: {decoded_after}")
data[patch_offset:patch_offset+8] = after
path.write_bytes(data)
print(f"Validated +[YZSettings applyToCore] at {method_va:#x}")
print(f"Patched ARM64 instructions at {patch_va:#x} (file offset {patch_offset:#x})")
print("Before:", decoded_before)
print("After:", decoded_after)
print("WebGL disabled, external-app links and JavaScript retained")
