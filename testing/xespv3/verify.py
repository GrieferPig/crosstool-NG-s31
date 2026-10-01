"""Verify actual Xespv encoding, all pinned opcode rows, and installed dispatch.

Usage: python3 testing/xespv3/verify.py /path/to/riscv32-esp-linux-musl
This is host-side assembly/link validation, not execution on S31 hardware.
"""
from pathlib import Path
import argparse
import json
import os
import re
import struct
import subprocess

parser = argparse.ArgumentParser(__doc__)
parser.add_argument('prefix', type=Path)
parser.add_argument('--binutils-only', action='store_true')
opts = parser.parse_args()
prefix = opts.prefix.resolve()
here = Path(__file__).resolve().parent
out = Path(os.environ.get('XESPV_TEST_OUTPUT', 'xespv3-results')).resolve()
out.mkdir(exist_ok=True)
target = 'riscv32-esp-linux-musl'
tools = {name: str(prefix/'bin'/(target+'-'+name)) for name in ['as', 'objdump', 'objcopy', 'readelf', 'gcc', 'g++', 'ar']}
arch = 'rv32imafc_zicsr_zifencei_xesploop_xespdsp2p1_xespv'
records = []

def run(label, command, success=True):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    (out/(label+'.log')).write_text(repr(command)+'\n'+result.stdout+result.stderr)
    records.append({'test':label, 'exit':result.returncode})
    (out/'commands.json').write_text(json.dumps(records, indent=2)+'\n')
    assert (result.returncode == 0) == success, f'{label}: see {out/(label+".log")}'
    return result.stdout

def text_bytes(label, obj):
    binary = out/(label+'.bin')
    run(label+'-extract', [tools['objcopy'], '-O', 'binary', '-j', '.text', obj, binary])
    return binary.read_bytes()

def attributes(label, obj, version):
    attr = run(label+'-attributes', [tools['readelf'], '-A', obj])
    assert '_xespv'+version in attr, attr

probe = out/'probe with spaces.S'
probe.write_text('.text\n.option norvc\nesp.vld.128.ip q0,a0,0\nesp.vld.128.ip q0,a0,16\nesp.vld.128.ip q0,a0,-16\nesp.vst.128.ip q2,a2,0\nesp.vst.128.ip q0,a0,16\nesp.vcmp.eq.u8 q2,q0,q1\nesp.vadd.u32 q2,q0,q1\nesp.vadd.u8 q2,q0,q1\n')
golden = bytes.fromhex('3f60011abf60011abf63f15a3f68029abf60019a3fed0807bf662907bf602907')

for version in ('2p1', '2p2', '3p0'):
    direct = tools['as']+'-xespv'+version
    obj = out/('direct-'+version+'.o')
    run('direct-'+version, [direct, '-march='+arch+version, '-mabi=ilp32', probe, '-o', obj])
    expected = text_bytes('direct-'+version, obj)
    if version == '3p0': assert expected == golden, expected.hex()
    if version == '2p2': assert expected[:4].hex() == '1f001103'
    attributes('direct-'+version, obj, version)
    for mode in ('march', 'selector', 'response'):
        label = version+'-'+mode
        flags = ['-march='+arch+version, '-mabi=ilp32']
        if mode != 'march': flags.append('-mespv-spec='+version)
        assembled = out/(label+'.o')
        args = flags + [str(probe), '-o', str(assembled)]
        if mode == 'response':
            # Nested response file plus a source path containing spaces.
            nested = out/(label+' nested.rsp')
            nested.write_text(' '.join('"'+s+'"' for s in args))
            response = out/(label+'.rsp')
            response.write_text('"@'+str(nested)+'"')
            args = ['@'+str(response)]
        run(label, [tools['as']]+args)
        assert text_bytes(label, assembled) == expected, label
        attributes(label, assembled, version)
        dis = run(label+'-objdump', [tools['objdump'], '-d', assembled])
        assert 'esp.vld.128.ip' in dis and 'esp.vcmp.eq.u8' in dis, dis

# Default dispatch and unversioned Xespv must really generate 3.0.
obj = out/'default.o'
run('default', [tools['as'], '-march='+arch, probe, '-o', obj])
assert text_bytes('default', obj) == golden
attributes('default', obj, '3p0')
for name in ('as', 'objdump'):
    installed = prefix/target/'bin'/name
    run('target-bin-'+name, [installed, '--version'])
run('target-bin-assemble', [prefix/target/'bin/as', '-march='+arch+'3p0', probe, '-o', out/'target-bin.o'])
assert text_bytes('target-bin', out/'target-bin.o') == golden
dis = run('target-bin-disassemble', [prefix/target/'bin/objdump', '-d', out/'target-bin.o'])
assert 'esp.vcmp.eq.u8' in dis
cycle = out/'cycle.rsp'
cycle.write_text('@'+str(cycle))
run('response-cycle-rejected', [tools['as'], '@'+str(cycle)], success=False)

manifest = json.loads((here/'corpus.json').read_text())
rows = manifest['rows']
corpus = out/'corpus.o'
run('all-opcode-rows', [tools['as'], '-march='+arch+'3p0', here/'corpus.S', '-o', corpus])
binary = text_bytes('all-opcode-rows', corpus)
assert len(binary) == 4*len(rows), (len(binary),len(rows))
for index, row in enumerate(rows):
    word, = struct.unpack_from('<I', binary, index*4)
    assert word & int(row['mask'],16) == int(row['match'],16), (index, row, hex(word))
dis = run('all-opcode-disassembly', [tools['objdump'], '-d', corpus])
instructions = re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+(esp\.[^\n]+)', dis, re.M)
assert len(instructions) == len(rows), (len(instructions),len(rows))
roundtrip = out/'roundtrip.S'
assembly = []
for word, asm in instructions:
    # Espressif's HWLoop disassembler prints a relative displacement, while gas
    # takes an absolute target expression. Restore its PC-relative meaning.
    if asm.split()[0] in ('esp.lp.setupi', 'esp.lp.setup', 'esp.lp.starti', 'esp.lp.endi'):
        head, displacement = asm.split('#')[0].strip().rsplit(',', 1)
        asm = head + ',.+' + displacement
    assembly.append(asm)
roundtrip.write_text('.text\n.option norvc\n'+'\n'.join(assembly)+'\n')
run('all-opcode-roundtrip', [tools['as'], '-march='+arch+'3p0', roundtrip, '-o', out/'roundtrip.o'])
assert text_bytes('roundtrip', out/'roundtrip.o') == binary
run('archive-create', [tools['ar'], 'rcs', out/'corpus.a', corpus])
dis = run('archive-disassembly', [tools['objdump'], '-d', out/'corpus.a'])
assert len(re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+esp\.', dis, re.M)) == len(rows)
for mnemonic in ('esp.addx2', 'esp.addx4', 'esp.subx2', 'esp.subx4'):
    removed = out/(mnemonic+'.S')
    removed.write_text('.text\n'+mnemonic+' a0,a1,a2\n')
    run(mnemonic+'-removed-in-3p0', [tools['as'], '-march='+arch+'3p0', removed, '-o', out/'removed.o'], success=False)
    run(mnemonic+'-legacy-2p2', [tools['as'], '-march='+arch+'2p2', removed, '-o', out/'legacy.o'])

if not opts.binutils_only:
    empty = out/'empty.c'
    empty.write_text('')
    for version in ('2p1', '2p2', '3p0'):
        obj = out/('gcc-'+version+'.o')
        run('gcc-'+version, [tools['gcc'], '-march='+arch+version, '-mespv-spec='+version, '-mabi=ilp32', '-c', probe, '-o', obj])
        assert text_bytes('gcc-'+version,obj) == (out/('direct-'+version+'.bin')).read_bytes()
        attributes('gcc-'+version,obj,version)
        macros = run('gcc-'+version+'-macros', [tools['gcc'], '-march='+arch+version, '-mabi=ilp32', '-dM', '-E', empty])
        value = {'2p1':2001000, '2p2':2002000, '3p0':3000000}[version]
        assert re.search(r'^#define __riscv_xespv '+str(value)+r'$', macros, re.M), macros
    for version in ('3p0', ''):
        obj = out/('gcc-default-'+version+'.o')
        run('gcc-default-'+version, [tools['gcc'], '-march='+arch+version, '-mabi=ilp32', '-c', probe, '-o', obj])
        assert text_bytes('gcc-default-'+version,obj) == golden
        attributes('gcc-default-'+version,obj,'3p0')
    run('gcc-all-opcode-rows', [tools['gcc'], '-march='+arch+'3p0', '-mespv-spec=3p0', '-mabi=ilp32', '-c', here/'corpus.S', '-o', out/'gcc-corpus.o'])
    assert text_bytes('gcc-corpus',out/'gcc-corpus.o') == binary
    run('gcc-shared-link', [tools['gcc'], '-march='+arch+'3p0', '-mabi=ilp32', '-nostdlib', '-shared', out/'gcc-corpus.o', '-o', out/'corpus.so'])
    attributes('shared',out/'corpus.so','3p0')
    cpp = out/'cxx-link.cc'
    cpp.write_text('#include <vector>\nvoid simd() { __asm__ volatile("esp.vadd.u8 q2,q0,q1" ::: "memory"); }\nint main() { std::vector<unsigned> v(8,42); return v.at(0); }\n')
    run('cxx-runtime-link', [tools['g++'], '-march='+arch+'3p0', '-mespv-spec=3p0', '-mabi=ilp32', cpp, '-o', out/'cxx-link'])
    attributes('cxx-link',out/'cxx-link','3p0')
    dis = run('cxx-inline-asm', [tools['objdump'], '-d', out/'cxx-link'])
    assert re.search(r'072960bf\s+esp\.vadd\.u8',dis), dis

summary = {'result':'PASS', 'opcode_rows':len(rows), 'mnemonics':len(set(row['asm'].split()[0] for row in rows)), 'binutils_revision':manifest['binutils_revision'], 'gcc_tested':not opts.binutils_only, 'hardware_execution':False}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
