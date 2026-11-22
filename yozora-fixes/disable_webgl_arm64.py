#!/usr/bin/env python3
"""Conservative binary workaround for sqmrak/yozora v1.1.0-stable ARM64.

On YZSettings +applyToCore the source initializes options.webgl and
options.external_links together with:
    movi v0.2s, #1
    str d0, [sp, #0x18]
This gives both fields the value 1.

Change the pair to:
    movz x8, #1, lsl #32
    str x8, [sp, #0x18]
so options.webgl = 0 but options.external_links = 1.

Both registers are caller-scratch here; the following instruction overwrites x8.
The patched binary still uses JavaScript, media, and regular 2D canvas.
This does not change the underlying WebGL shim, and only avoids invoking it.
Requires exact bytes from the audited v1.1.0-stable ARM64 executable.
"""
import sys
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

if len(sys.argv) != 2:
    raise SystemExit("usage: disable_webgl_arm64.py PATH_TO_ARM64_EXECUTABLE")

path = Path(sys.argv[1])
binary = bytearray(path.read_bytes())
if binary[:4] != bytes.fromhex("cffaedfe"):
    raise SystemExit("Not a thin ARM64 Mach-O executable")

# The official release binary uses vmaddr 0x100000000 for its __TEXT segment,
# with a file offset of zero. Method implementation from its ObjC metadata.
method_vmaddr = 0x10004101C
text_vmaddr = 0x100000000
patch_vmaddr = 0x100041100
file_offset = patch_vmaddr - text_vmaddr
before = bytes.fromhex("2004000fe00f00fd")
after = bytes.fromhex("2800c0d2e80f00f9")

if binary[file_offset:file_offset + 8] != before:
    observed = binary[file_offset:file_offset + 8].hex()
    raise SystemExit(
        "Upstream ARM64 code changed, refusing unsafe WebGL patch: "
        + observed + " != " + before.hex()
    )

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
decoded_before = [(i.mnemonic, i.op_str) for i in md.disasm(before, patch_vmaddr)]
if len(decoded_before) != 2 or decoded_before[0][0] != "movi" or decoded_before[1][0] != "str":
    raise SystemExit(f"Unexpected instruction pair at YZSettings +applyToCore: {decoded_before}")

decoded_after = [(i.mnemonic, i.op_str) for i in md.disasm(after, patch_vmaddr)]
assert len(decoded_after) == 2, decoded_after
assert decoded_after[0][0] in ("mov", "movz"), decoded_after
assert decoded_after[1][0] == "str", decoded_after
# ARM64 immediate x8 = (1 << 32), stored at sp + 24.
assert int.from_bytes(after[:4], "little") == 0xD2C00028
assert int.from_bytes(after[4:], "little") == 0xF9000FE8
binary[file_offset:file_offset + 8] = after
path.write_bytes(binary)
print(f"Safely patched {path} at 0x{file_offset:x}: WebGL OFF, external links ON")
print("Before:", decoded_before)
print("After:", decoded_after)
