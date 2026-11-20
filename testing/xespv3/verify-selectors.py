"""Check the public S31 assembler rejects a revision/ELF tag contradiction."""
import argparse
import pathlib
import subprocess
import tempfile

args = argparse.ArgumentParser(description=__doc__)
args.add_argument('prefix', type=pathlib.Path)
args.add_argument('--staged-bin', type=pathlib.Path,
                  help='test an isolated rebuilt wrapper, without editing the SDK')
opts = args.parse_args()
target = 'riscv32-esp-linux-musl'
tools = opts.prefix.resolve() / 'bin'
gcc = [str(tools / (target + '-gcc'))]
assembler = tools / (target + '-as')
if opts.staged_bin:
    stage = opts.staged_bin.resolve()
    assembler = stage / 'as'
    gcc.append('-B' + str(stage) + '/')
readelf = tools / (target + '-readelf')
objcopy = tools / (target + '-objcopy')
isa = '-march=rv32imafc_zicsr_zifencei_xespv'
with tempfile.TemporaryDirectory() as temp:
    d = pathlib.Path(temp)
    source = d / 'instruction.S'
    source.write_text('.text\nesp.vadd.u8 q2,q0,q1\n')
    output = d / 'test.o'
    flags = [isa + '2p2', '-mespv-spec=3p0']
    nested = d / 'inner.rsp'
    nested.write_text(' '.join(flags))
    outer = d / 'outer.rsp'
    outer.write_text('@' + str(nested))
    for driver, argv in [([assembler], flags), ([assembler], flags[::-1]),
                         ([assembler], ['@' + str(outer)]),
                         ([assembler], [isa + '3', '-mespv-spec=2p2']),
                         (gcc + ['-mabi=ilp32', '-c'], flags)]:
        r = subprocess.run(driver + argv + [source, '-o', output], capture_output=True, text=True)
        assert r.returncode and 'conflicting XEspV revisions:' in r.stderr and not output.exists(), (driver, argv, r.stderr)
    for extension, rev, word in [('2p1', '2p1', 0x06a0045f),
                                 ('2p2', '2p2', 0x06a1231b),
                                 ('3', '3p0', 0x072960bf),
                                 ('', '2p2', 0x06a1231b)]:
        subprocess.run([assembler, isa + extension, '-mespv-spec=' + rev, source, '-o', output], check=True)
        attr = subprocess.check_output([readelf, '-A', output], text=True)
        assert '_xespv' + rev in attr, attr
        raw = d / 'test.bin'
        subprocess.run([objcopy, '-O', 'binary', '-j', '.text', output, raw], check=True)
        assert raw.read_bytes() == word.to_bytes(4, 'little')
print('XEspV selector guard PASS: five mismatches rejected and four matching tag/word pairs verified')
