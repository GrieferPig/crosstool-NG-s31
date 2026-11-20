# S31 Xespv 3.0 toolchain validation

The Linux sample uses the merged Espressif `esp-1.28.x` build scripts with:

* binutils `37a65a3e908599f625f94bd382ea06079a64a543` (the commit behind
  `esp-2.47.0_20260914`);
* the S31 GCC 15 source `0dbf584943ac179894690b389f3a37926bb4cd33`, preserving
  both existing HWLoop patches and adding the `-mespv-spec=3p0` option and
  unversioned Xespv 3.0 default;
* musl 1.2.5 with scalar implementations, F-only hardware and soft-float `ilp32` calling convention;
* separate assembler/disassembler variants for Xespv 2.1, 2.2 and 3.0.

The upstream ct-ng wrapper gitlink `11094a6eb2b2e7893747faac49012d0e9fb76921`
was unavailable from the public Espressif wrapper repository when this change
was prepared. The fork pins the public `d8844fa7d904aefcb9484ff3a37f4f5c476321f6`
instead, uses an absolute public submodule URL, and patches an isolated build
copy. The bundled Cargo lockfile makes Rust dependency resolution reproducible.
The patch also expands nested response files before stripping wrapper-only
`-mespv-spec` arguments, including quoted file names containing spaces.

## Build

```sh
git submodule update --init esp-toolchain-bin-wrappers
./bootstrap
./configure --enable-local
make -j6
./ct-ng defconfig DEFCONFIG="$PWD/samples/riscv32-esp-linux-musl/crosstool.config"
./ct-ng build.6
python3 testing/xespv3/verify.py x-tools/riscv32-esp-linux-musl
```

The portable sample downloads Linux 6.12 headers. The S31 workflow overrides
this with its checked-out S31 kernel. Choose a new `CT_PREFIX_DIR` when testing
beside an installed toolchain. The S31 default ISA now includes XEspV 3.0:
a plain compiler invocation accepts hand-written SIMD and stamps the ELF with
`_xespv3p0`. Plain C is not auto-vectorized into this vendor ISA, and the musl
build must remain free of vendor instructions. An explicit scalar `-march`
still opts out; existing downstream flags are not overridden. This default
makes assembly available, **not** safe to execute on any hart or across context
switches. Code that uses vector registers must follow the OS context policy.

An explicit equivalent for assembling SIMD is:

```sh
riscv32-esp-linux-musl-gcc -march=rv32imafc_zicsr_zifencei_xespv3p0 \
  -mabi=ilp32 -mespv-spec=3p0 -c simd.S
```

`-march=..._xespv3p0` alone also selects 3.0. Use consistent explicit versions
for `-march` and `-mespv-spec` when selecting 2.1 or 2.2. GCC support here means
assembly and inline-assembly generation, not automatic SIMD vectorization or
an RVV ABI.

## Evidence and limits

`corpus.json` and `corpus.S` cover **every one of the 748 rows / 494 mnemonics**
in the pinned upstream `opcodes/esp/latest/riscv-opc.c`, including aliases,
Xespv, DSP and HWLoop forms. Regenerate from that exact source revision with:

```sh
python3 testing/xespv3/generate-corpus.py /path/to/binutils-source
```

The verifier checks the upstream match/mask predicates for each assembled
instruction, decodes all rows, and reassembles the disassembly byte for byte.
It also checks independently fixed probe instruction words, ELF ISA attributes,
default/explicit/response-file wrapper dispatch, both installed tool directories,
all three GCC selectors and ISA macros, static archive decoding, a shared-object
link and a C++ runtime link with inline SIMD assembly. The workflow additionally
checks scalar libc, F-only code generation and HWLoop control-flow regressions.
Raw commands, outputs and `summary.json` go to `xespv3-results/`.

The earlier, scalar-default S31 Linux C/C++ toolchain was built and its then-current checks passed on
2026-09-30 with an x86_64 Ubuntu 24.04 WSL host. Scalar musl, F-only code
generation, early-exit/branch-end HWLoop rejection and simple HWLoop generation
also passed. The four removed `addx2/addx4/subx2/subx4` mnemonics were rejected
in 3.0 and accepted in the compatibility 2.2 assembler.

This is complete coverage of the **published opcode-table forms**, using one
legal operand example per row. It is not exhaustive testing of operand values
or instruction behavior on hardware. It does not change S31 Linux/OpenSBI context handling. The pinned board
[OpenSBI save/restore routine](https://github.com/GrieferPig/opensbi-esp32-s31/blob/c8d6e92c70e9679b9e8d1a4ab95acd13ea04b5b5/platform/generic/espressif/esp32s31_coproc.S)
skips PIE on hart 0 and embeds old instruction words on hart 1. For example,
it saves `esp.movx.r.sar.bytes a1` as `0x88c0219b` (2.2); assembling
the same operands for 3.0 gives `0x4e4861bf`. The board's
[existing SIMD library](https://github.com/GrieferPig/esp32-s31-linux/blob/7b36565d02662436d2cc041dd40a24d65a06a18d/buildroot-external/package/esp-simd/esp-simd.mk)
explicitly requests 2.2; its initialization binds the calling thread to CPU1.
An ELF 3.0 tag or successful scalar Linux boot does **not** validate 3.0
execution/preemption. Qualify OS state preservation and silicon separately
before deploying code that actually executes these instructions.

The public S31 wrapper rejects a versioned `-march=..._xespv2p2` combined
with a contradictory `-mespv-spec=3p0`, in either argument order and inside
response files. Bare `xespv` in direct GAS still accepts a matching backend
selector. Run `python3 testing/xespv3/verify-selectors.py /path/to/sdk` to
check rejected combinations and verify the emitted word plus ELF tag for
valid ones. This check applies to the public wrapper, not direct internal
backend executables or ISA changes inside handwritten assembly.
