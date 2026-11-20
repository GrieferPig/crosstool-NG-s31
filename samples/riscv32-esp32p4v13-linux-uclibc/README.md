# ESP32-P4 rev1.3 Linux userspace SDK

This sample targets **rev1.3, the pre-v3 XEspV 2.1 encoding**. The scalar userspace baseline is RV32IMAC + Zicsr/Zifencei, ILP32 (integer calling convention, no F/D). This is a no-MMU, static uClibc-ng/LinuxThreads toolchain. It is not the S31 MMU/musl SDK, the P4 bare-metal or kernel profile, or a generic SDK for every P4 revision.

[ESP-IDF a602e67b](https://github.com/espressif/esp-idf/blob/a602e67b0bf9ee0806dc4e1df7afc9affedf5c33/components/soc/project_include.cmake#L63-L68) appends 2p1 for a PIE-capable P4 with `CONFIG_ESP32P4_SELECTS_REV_LESS_V3`. This profile sets both GCC's default ISA and the assembler/disassembler's actual instruction tables. For example `esp.vadd.u8 q2,q0,q1` is `0x0280045f | (2 << 20) | (0 << 29) | (1 << 26) = 0x06a0045f`; v3 encodes the same mnemonic as `0x072960bf`. A profile-local binutils check rejects incompatible XEspV versions rather than mislabeling 2.1 bytes. Write `_xespv2p1` explicitly if supplying a custom `-march`; do not pass `-mespv-spec` (a dispatcher option). An explicit scalar-only ISA remains supported.

After bootstrapping/configuring crosstool-NG as usual, in a **separate build directory**:

```sh
ct-ng riscv32-esp32p4v13-linux-uclibc
ct-ng build
export P4_SDK="$PWD/x-tools/riscv32-esp32p4v13-linux-uclibc"
"$CTNG_SRC/samples/riscv32-esp32p4v13-linux-uclibc/verify-sdk.sh" "$P4_SDK" "$PWD/check"
```

Build application objects as PIC, and link with `-static -Wl,-elf2flt=-r`. ELF objects, archives and the .gdb debugger companion are **not** installable programs. Deploy the bFLT v4 executable. The verifier checks independent opcode bytes, ELF attributes, ABI, rejection of incorrect versions, libc configuration and a libc-linked bFLT with relocations. It does not claim the code was executed or that Linux saves vector registers across task/signal switches.

A minimal Buildroot external-toolchain config is included for [Buildroot 2026.05.1](https://github.com/buildroot/buildroot/tree/cb857ba4c87a93e5265a9e4a3f32071abf39e14a). From a clean Buildroot output, with `P4_SDK` exported:

```sh
make -C "$BUILDROOT_SRC" O="$PWD/out-p4" BR2_DEFCONFIG="$CTNG_SRC/samples/riscv32-esp32p4v13-linux-uclibc/buildroot_defconfig" defconfig
make -C "$BUILDROOT_SRC" O="$PWD/out-p4"
```

The stock sample uses 6.12 UAPI headers. When validating against a custom P4 Linux tree, select the matching external header series in Buildroot as well. Output is uncompressed newc cpio for embedding and gzip compression by the kernel. The board's independently verified kernel/DTB and boot firmware are separate inputs. This sample does not import any old rootfs, S31 peripherals, flash layout or existing images.
