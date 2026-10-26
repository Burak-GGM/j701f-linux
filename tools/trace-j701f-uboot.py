#!/usr/bin/env python3
"""Run the built second stage to the Linux entry boundary in QEMU, without phone I/O.

QEMU virt supplies CPU/RAM only: this is not Exynos peripheral or S-BOOT emulation.
A saved vendor DT supplies measured board identity and RAM for this software test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def trace(loader, output):
    loader, output = loader.resolve(), output.resolve()
    if not all(p.is_relative_to(ROOT / 'build/kernel') for p in (loader, output)):
        raise ValueError('Paths must be inside build/kernel')
    output.mkdir(parents=True, exist_ok=True)
    elf, image, dt = loader/'u-boot', loader/'u-boot.bin', ROOT/'build/kernel/j701f-live.dtb'
    symbols = {line.split()[2]: int(line.split()[0], 16)
               for line in subprocess.check_output(['llvm-nm', str(elf)], text=True).splitlines()
               if len(line.split()) == 3}
    initial = 0x40080000
    with tempfile.TemporaryDirectory(prefix='j701f-loader-trace-') as temp:
        work = Path(temp); sock = work/'gdb.sock'
        command = ['qemu-system-aarch64', '-machine', 'virt,virtualization=on', '-cpu', 'cortex-a53',
                   '-m', '2048', '-smp', '1', '-display', 'none', '-serial', 'none', '-monitor', 'none',
                   '-net', 'none', '-S', '-gdb', f'unix:{sock},server=on,wait=off',
                   '-device', f'loader,addr={initial:#x},cpu-num=0',
                   '-device', f'loader,file={dt},addr=0x42000000']
        script = f'''set pagination off
set confirm off
set architecture aarch64
add-symbol-file {elf} -o {initial:#x}
target remote {sock}
restore {image} binary {initial:#x}
set $x0=0x42000000
set $pc={initial:#x}
python
class Console(gdb.Breakpoint):
 def stop(self):
  try:
   ptr=int(gdb.parse_and_eval('$x0'))
   data=gdb.selected_inferior().read_memory(ptr,1024).tobytes().split(b'\\0',1)[0]
   gdb.write('CONSOLE: '+data.decode(errors='replace')+'\\n')
  except Exception:pass
  return False
Console('*{initial+symbols['puts']:#x}')
end
break *{initial+symbols['relocate_code']:#x}
break *{initial+symbols['hang']:#x}
continue
python
pc=int(gdb.parse_and_eval('$pc'))
if pc != {initial+symbols['relocate_code']}:
 raise gdb.GdbError('Stopped before relocation: '+hex(pc))
base=int(gdb.parse_and_eval('((gd_t*)$x18)->relocaddr'))
gdb.write('RELOCATED_BASE='+hex(base)+'\\n')
Console('*'+hex(base+{symbols['puts']}))
gdb.Breakpoint('*'+hex(base+{symbols['cli_loop']}))
gdb.Breakpoint('*'+hex(base+{symbols['hang']}))
gdb.Breakpoint('*0x40000000',type=gdb.BP_HARDWARE_BREAKPOINT)
end
continue
python
pc=int(gdb.parse_and_eval('$pc'))
gdb.write('FINAL_PC='+hex(pc)+'\\n')
if pc == 0x40000000:
 gdb.write('LINUX_ENTRY_BOUNDARY_REACHED\\n')
 gdb.write('LINUX_X0_DTB='+hex(int(gdb.parse_and_eval('$x0')))+'\\n')
 gdb.execute('dump binary memory {output}/linux-entry-header.bin 0x40000000 0x40000040')
else:
 gdb.write('LOADER_STOPPED_BEFORE_LINUX\\n')
end
quit
'''
        (work/'trace.gdb').write_text(script)
        with (output/'qemu.txt').open('w') as qlog:
            proc = subprocess.Popen(command, stdout=qlog, stderr=subprocess.STDOUT)
            try:
                for _ in range(50):
                    if sock.exists():break
                    if proc.poll() is not None:raise RuntimeError('QEMU failed; see qemu.txt')
                    time.sleep(.1)
                result = subprocess.run(['gdb','-nx','-batch','-x',str(work/'trace.gdb')],
                                        capture_output=True, text=True, timeout=45)
                console = result.stdout+result.stderr
            finally:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
        (output/'trace.gdb').write_text(script)
    (output/'gdb-console.txt').write_text(console)
    reached = 'LINUX_ENTRY_BOUNDARY_REACHED' in console
    if reached and (output/'linux-entry-header.bin').read_bytes()[56:60] != b'ARM\x64':
        raise ValueError('Reached address does not contain an ARM64 Linux header')
    report = dict(status='linux-entry-reached' if reached else 'stopped-before-linux',
                  loader_sha256=sha(image), source_dt_sha256=sha(dt), gdb_exit_status=result.returncode,
                  linux_entry_boundary_reached=reached, phone_modified=False,
                  limits=['CPU/RAM software execution only; not S-BOOT or Exynos peripheral emulation.',
                          'Stops at the first Linux instruction, without executing the kernel.',
                          'Saved firmware DT substitutes for the live S-BOOT overlay.'])
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    for line in console.splitlines():
        if line.startswith(('CONSOLE:', 'RELOCATED_BASE=', 'FINAL_PC=', 'LINUX_', 'LOADER_')):
            print(line)
    if result.returncode:raise SystemExit(result.returncode)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loader-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(); trace(args.loader_dir,args.output_dir)
