#!/usr/bin/env bash
# Usage: verify-sdk.sh /path/to/SDK /path/to/empty/results
set -euo pipefail
export LC_ALL=C
if [ "$#" != 2 ]; then echo "usage: $0 SDK RESULTS" >&2; exit 2; fi
sdk=$(cd "$1" && pwd)
mkdir -p "$2"
cd "$2"
t=riscv32-esp32p4v13-linux-uclibc
p="$sdk/bin/$t-"
test "$("${p}gcc" -dumpmachine)" = "$t"
"${p}gcc" -v 2>gcc-version.txt
"${p}gcc" -dM -E -x c /dev/null >macros.txt
for define in '__riscv_xespv 2001000' '__riscv_xlen 32' '__riscv_float_abi_soft 1'; do
  grep -Fx "#define $define" macros.txt
done
if grep -Eq '^#define __riscv_(flen|vector|xesploop|zba|zbb|zbc|zbs) ' macros.txt; then
  echo 'unexpected ISA extension in P4 userspace baseline' >&2; exit 1
fi
cat >probe.S <<'ASM'
.text
.option norvc
esp.vadd.u8 q2,q0,q1
ASM
for driver in gcc as; do
  args=()
  if [ "$driver" = gcc ]; then args=(-c); fi
  "${p}$driver" "${args[@]}" probe.S -o "$driver.o"
  "${p}readelf" -Ah "$driver.o" >"$driver.elf.txt"
  grep -F 'soft-float ABI' "$driver.elf.txt"
  grep -E 'Tag_RISCV_arch: "rv32i[^"]*_xespv2p1"' "$driver.elf.txt"
  "${p}objcopy" -j .text -O binary "$driver.o" "$driver.bin"
  test "$(od -An -tx1 -v "$driver.bin" | tr -d ' \n')" = 5f04a006
  "${p}objdump" -d "$driver.o" >"$driver.dis"
  grep -E '06a0045f[[:space:]]+esp\.vadd\.u8[[:space:]]+q2,q0,q1' "$driver.dis"
done
for rev in 2p2 3p0; do
  if "${p}gcc" "-march=rv32imac_zicsr_zifencei_xespv$rev" -c probe.S -o rejected.o >"reject-$rev.log" 2>&1; then
    echo "wrong backend accepted xespv$rev" >&2; exit 1
  fi
  grep -F 'requires xespv2p1' "reject-$rev.log"
done
{ echo '.option arch,+xespv3p0'; cat probe.S; } >wrong-option.S
if "${p}as" wrong-option.S -o rejected.o >reject-option.log 2>&1; then
  echo 'wrong .option arch was accepted' >&2; exit 1
fi
grep -F 'requires xespv2p1' reject-option.log
"${p}gcc" -march=rv32imac_zicsr_zifencei -c -x c /dev/null -o scalar.o
"${p}readelf" -A scalar.o >scalar.attrs
if grep -q xespv scalar.attrs; then echo 'explicit scalar build still tagged XEspV' >&2; exit 1; fi
sysroot=$("${p}gcc" -print-sysroot)
cfg="$sysroot/usr/include/bits/uClibc_config.h"
for k in TARGET_riscv32 UCLIBC_FORMAT_FLAT UCLIBC_HAS_LINUXTHREADS UCLIBC_HAS_IPV6; do
  grep -Fx "#define __${k}__ 1" "$cfg"
done
if grep -E '^#define __(ARCH_USE_MMU|HAVE_SHARED|UCLIBC_HAS_FPU)__ 1' "$cfg"; then exit 1; fi
cat >hello.c <<'C'
#include <stdio.h>
static const char *volatile msg = "P4_NEW_SDK_BFLT_EXEC_PASS";
int main(void) { return puts(msg) < 0; }
C
# No target ISA/ABI flags: defaults must survive into real code.
"${p}gcc" -Os -fPIC -static -Wl,-elf2flt=-r -o hello hello.c
"${p}flthdr" -p hello >hello.header.txt
"${p}readelf" -Ah hello.gdb >hello.elf.txt
grep -F 'soft-float ABI' hello.elf.txt
grep -F '_xespv2p1"' hello.elf.txt
python3 - <<'PY'
import struct
from pathlib import Path
b=Path('hello').read_bytes()
magic,rev,entry,data,end,bss,stack,r,n,flags=struct.unpack_from('>4s9I', b)
if not (magic==b'bFLT' and rev==4 and 64<=entry<data<=end<=bss
        and stack and r==end and n and r+4*n<=len(b) and (flags&1)):
    raise SystemExit("invalid or empty FLAT relocation table/header")
print(f"PASS static bFLT v{rev}, entry {entry:#x}, {n} relocations, {len(b)} bytes")
PY
