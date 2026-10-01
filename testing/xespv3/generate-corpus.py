"""Generate one legal operand example per pinned upstream opcode-table row.

Usage: python3 generate-corpus.py /path/to/binutils-37a65a3.../source
The manifest records upstream match/mask predicates independently of gas output.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve()
out = Path(__file__).resolve().parent
table = source / 'opcodes/esp/latest/riscv-opc.c'
rows = re.findall(r'\{"([^"]+)"\s*,\s*0,\s*INSN_CLASS_(\w+),\s*"([^"]*)",\s*([^,]+),\s*([^,]+),', table.read_text())
assert len(rows) == 748, len(rows)

def operand(token):
    if token.startswith('Xeq'): return 'q0'
    if token.startswith('Xer'): return 'x8'
    if token.startswith('Xef'): return 'f8'
    if token.startswith('Xevs'): return 'sat'
    if token.startswith('Xevr'): return 'dyn'
    if token.startswith('Xelo'): return '.+4'
    if token == 'Xeli': return '0'
    if token.startswith('Xe'): return '0'
    if token in ('d', 's', 't'): return 'x8'
    if token in ('D', 'T'): return 'f8'
    if token == 'r': return 'x8'
    if token == '': return ''
    raise ValueError(token)

lines = [name + (' ' if args else '') + ','.join(operand(x) for x in args.split(',')) for name, cls, args, match, mask in rows]
mask_macros = '\n'.join(line for line in (source/'opcodes/esp/latest/riscv-opc.h').read_text().splitlines() if line.startswith('#define MASK_ESP'))
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    program = '#include <stdio.h>\n#include <stdint.h>\n#include "opcode/riscv.h"\n' + mask_macros + '\nint main(void) {\n'
    for name, cls, args, match, mask in rows:
        program += f'printf("%08x %08x\\n", (unsigned)({match}), (unsigned)({mask}));\n'
    program += '}\n'
    (tmp/'predicates.c').write_text(program)
    subprocess.run(['cc', '-I'+str(source/'include'), str(tmp/'predicates.c'), '-o', str(tmp/'predicates')], check=True)
    predicates = subprocess.check_output([str(tmp/'predicates')], text=True).splitlines()

manifest = [{'asm':asm, 'class':row[1], 'match':pred.split()[0], 'mask':pred.split()[1]} for asm, row, pred in zip(lines, rows, predicates)]
(out/'corpus.json').write_text(json.dumps({'binutils_revision':'37a65a3e908599f625f94bd382ea06079a64a543', 'rows':manifest}, indent=2)+'\n')
(out/'corpus.S').write_text('.text\n.option norvc\n'+ '\n'.join(lines)+'\n')
print(f'Generated {len(lines)} rows / {len(set(row[0] for row in rows))} mnemonics')
