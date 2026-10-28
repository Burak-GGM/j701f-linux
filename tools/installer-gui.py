#!/usr/bin/env python3
"""Host-side GUI for the J701F release, SD staging and recovery ZIP tools.

The default action only checks or previews. Writing requires an explicit switch
and a separate confirmation for the selected operation. This tool never runs
Odin or writes directly to a phone partition; install-release.py owns the
guarded recovery workflow.
"""

import hashlib
import importlib.util
import ipaddress
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


ROOT = Path(__file__).resolve().parents[1]
SERIAL_ID = 'j701f-diagnostic'
DEFAULT_RELEASE = ROOT / 'build/release'
DEFAULT_BUNDLE = ROOT / 'build/first-install'
DEFAULT_ZIP = ROOT / 'build/j701f-install.zip'


def diagnostic_ports(sys_tty=Path('/sys/class/tty'), dev_root=Path('/dev')):
    """Accept only ACM ports whose USB parent has this project's serial ID."""
    ports = []
    for node in sorted(sys_tty.glob('ttyACM*')):
        device = (node / 'device').resolve()
        for parent in (device, *device.parents):
            serial = parent / 'serial'
            if serial.is_file():
                if serial.read_text().strip() == SERIAL_ID:
                    port = dev_root / node.name
                    if port.exists():
                        ports.append(port)
                break
    return ports


def require_one_phone(ports):
    if len(ports) != 1:
        raise ValueError(f'Expected one USB serial device with ID {SERIAL_ID}; found {len(ports)}.')
    return ports[0]


def path_arg(value, label):
    value = value.strip()
    if not value:
        raise ValueError(f'{label} is required.')
    return str(Path(value).expanduser().resolve())


def build_command(mode, values, *, write=False):
    """Return an argv list. Dry-run argv never has a destructive switch."""
    if mode == 'release':
        command = [sys.executable, '-u', str(ROOT / 'scripts/install-release.py'),
                   '--release', path_arg(values['release'], 'Release directory')]
        if values.get('from_recovery'):
            command.append('--from-recovery')
        elif values.get('phone_ip', '').strip():
            ip = values['phone_ip'].strip()
            ipaddress.IPv4Address(ip)
            command += ['--phone-ip', ip]
        if values.get('known_hosts', '').strip():
            command += ['--known-hosts', path_arg(values['known_hosts'], 'Pinned SSH keys')]
        if values.get('mtp_sd', '').strip():
            command += ['--mtp-sd', path_arg(values['mtp_sd'], 'MTP SD directory')]
        if write:
            if not values.get('from_recovery') and not values.get('phone_ip', '').strip():
                raise ValueError('A phone IPv4 address is required to start from the running system.')
            command += ['--execute', '--erase-userdata']
            if values.get('backup_userdata'):
                command.append('--backup-userdata')
            if values.get('reboot'):
                command.append('--reboot')
        return command
    if mode == 'first':
        command = [sys.executable, '-u', str(ROOT / 'scripts/first-install.py'),
                   '--bundle', path_arg(values['bundle'], 'First-install bundle'),
                   '--release', path_arg(values['release'], 'Release directory')]
        if values.get('sd', '').strip():
            command += ['--sd', path_arg(values['sd'], 'microSD mount')]
        if write:
            if not values.get('sd', '').strip():
                raise ValueError('A mounted microSD card is required for staging.')
            command.append('--stage')
        return command
    if mode == 'zip':
        command = [sys.executable, '-u', str(ROOT / 'tools/build-recovery-zip.py'),
                   path_arg(values['output'], 'ZIP output')]
        if values.get('embed'):
            command += ['--embed', path_arg(values['release'], 'Release directory')]
        return command
    raise ValueError(f'Unknown installer page: {mode}')


def check_zip_inputs(values):
    """ZIP builder has no dry-run option; validate its local inputs instead."""
    spec = importlib.util.spec_from_file_location('j701f_zip_builder', ROOT / 'tools/build-recovery-zip.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not module.BUSYBOX.is_file():
        raise ValueError(f'Pinned BusyBox is missing: {module.BUSYBOX}')
    with module.BUSYBOX.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != module.BUSYBOX_SHA256:
        raise ValueError('Pinned BusyBox checksum differs; ZIP build would refuse it.')
    for name in ('update-binary', 'updater-script', 'installer.sh'):
        if not (module.SRC / name).is_file():
            raise ValueError(f'Recovery ZIP input is missing: {name}')
    if values.get('embed'):
        spec = importlib.util.spec_from_file_location('j701f_install_release', ROOT / 'scripts/install-release.py')
        release_tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release_tool)
        release_tool.preflight(Path(path_arg(values['release'], 'Release directory')))


def confirm_write(mode, values, ask_yesno, ask_string):
    """Return True only after operation-specific, reviewable confirmations."""
    if mode == 'release':
        if not values.get('backup_userdata') and not ask_yesno(
                'No backup selected', 'The old USERDATA will not be backed up. Continue?'):
            return False
        if values.get('reboot') and not ask_yesno(
                'Reboot after installation', 'Reboot only after verified installation succeeds?'):
            return False
        if not ask_yesno('Erase USERDATA',
                         'This will erase all 11.12 GiB of USERDATA on SM-J701F, including internal storage. '
                         'A verified backup is attempted first only when selected. Continue?'):
            return False
        return ask_string('Confirm phone wipe', 'Type ERASE USERDATA to approve the partition write:') == 'ERASE USERDATA'
    if mode == 'first':
        if not ask_yesno('Stage to microSD',
                         'Files in the card\'s j701f-release directory may be replaced. Continue?'):
            return False
        return ask_string('Confirm SD write', 'Type STAGE SD to approve copying onto the card:') == 'STAGE SD'
    if mode == 'zip':
        output = Path(path_arg(values['output'], 'ZIP output'))
        if output.exists() or output.with_name(output.name + '.sha256').exists():
            if not ask_yesno('Replace host ZIP', f'{output} or its checksum file exists. Replace it?'):
                return False
            return ask_string('Confirm replacement', 'Type REPLACE ZIP to approve overwriting:') == 'REPLACE ZIP'
        return ask_yesno('Build recovery ZIP', f'Create {output} on this computer?')
    raise ValueError(f'Unknown installer page: {mode}')


class InstallerApp:
    def __init__(self, window):
        self.window = window
        window.title('J701F Linux installer')
        window.minsize(760, 610)
        self.events = queue.Queue()
        self.busy = False
        self.write_enabled = tk.BooleanVar(value=False)
        self.phone_status = tk.StringVar(value='USB phone: not checked')
        self.message = tk.StringVar(value='Dry run is the default. No phone partition is written without confirmation.')
        self.release = tk.StringVar(value=str(DEFAULT_RELEASE))
        self.phone_ip = tk.StringVar(value='')
        self.known_hosts = tk.StringVar(value=str(ROOT / 'build/phone-ssh-known-hosts'))
        self.mtp_sd = tk.StringVar(value='')
        self.from_recovery = tk.BooleanVar(value=False)
        self.backup_userdata = tk.BooleanVar(value=True)
        self.reboot = tk.BooleanVar(value=False)
        self.bundle = tk.StringVar(value=str(DEFAULT_BUNDLE))
        self.sd = tk.StringVar(value='')
        self.output = tk.StringVar(value=str(DEFAULT_ZIP))
        self.embed = tk.BooleanVar(value=False)

        outer = ttk.Frame(window, padding=12)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Samsung SM-J701F / j7velte · host installer',
                  font=('Sans', 14, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Release reinstall erases USERDATA. First-install staging and ZIP building '
                  'prepare files only; neither flashes BOOT or RECOVERY.').pack(anchor='w', pady=(4, 10))
        top = ttk.Frame(outer)
        top.pack(fill='x')
        ttk.Label(top, textvariable=self.phone_status).pack(side='left')
        self.scan_button = ttk.Button(top, text='Detect USB phone', command=self.scan_phone)
        self.scan_button.pack(side='right')
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill='x', pady=10)
        self._release_tab()
        self._first_tab()
        self._zip_tab()
        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(2, 8))
        self.preview_button = ttk.Button(controls, text='Dry run / inspect', command=lambda: self.start(False))
        self.preview_button.pack(side='left')
        ttk.Checkbutton(controls, text='Enable writing for one step', variable=self.write_enabled,
                        command=self._set_write_button).pack(side='left', padx=15)
        self.write_button = ttk.Button(controls, text='Run write step', command=lambda: self.start(True))
        self.write_button.pack(side='left')
        self._set_write_button()
        ttk.Label(outer, textvariable=self.message, wraplength=720).pack(anchor='w')
        log_frame = ttk.Frame(outer)
        log_frame.pack(fill='both', expand=True, pady=(8, 0))
        self.log = tk.Text(log_frame, wrap='word', height=16, state='disabled')
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.after(100, self._drain)
        self.scan_phone()

    def _row(self, frame, row, label, variable, *, browse=None):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=4)
        ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky='ew', padx=8, pady=4)
        if browse:
            ttk.Button(frame, text='Browse', command=lambda: self._browse(variable, browse)).grid(row=row, column=2)

    def _browse(self, variable, kind):
        selected = filedialog.askdirectory() if kind == 'dir' else filedialog.asksaveasfilename(
            defaultextension='.zip', filetypes=[('ZIP', '*.zip')])
        if selected:
            variable.set(selected)

    def _tab(self, title):
        frame = ttk.Frame(self.tabs, padding=10)
        frame.columnconfigure(1, weight=1)
        self.tabs.add(frame, text=title)
        return frame

    def _release_tab(self):
        frame = self._tab('Reinstall release')
        self._row(frame, 0, 'Release directory', self.release, browse='dir')
        self._row(frame, 1, 'Phone IPv4 (running Linux)', self.phone_ip)
        self._row(frame, 2, 'Pinned SSH known-hosts', self.known_hosts)
        self._row(frame, 3, 'MTP external SD (optional)', self.mtp_sd, browse='dir')
        ttk.Checkbutton(frame, text='Already in held RAM recovery (--from-recovery)',
                        variable=self.from_recovery).grid(row=4, column=0, columnspan=3, sticky='w')
        ttk.Checkbutton(frame, text='Back up complete USERDATA on external SD first',
                        variable=self.backup_userdata).grid(row=5, column=0, columnspan=3, sticky='w')
        ttk.Checkbutton(frame, text='Reboot after verified installation',
                        variable=self.reboot).grid(row=6, column=0, columnspan=3, sticky='w')

    def _first_tab(self):
        frame = self._tab('First-install SD staging')
        self._row(frame, 0, 'First-install bundle', self.bundle, browse='dir')
        self._row(frame, 1, 'Release directory', self.release, browse='dir')
        self._row(frame, 2, 'Mounted microSD (FAT32)', self.sd, browse='dir')
        ttk.Label(frame, text='This checks BOOT/RECOVERY archives and can copy files to SD. '
                  'Odin and recovery installation remain manual.', wraplength=690).grid(
                      row=3, column=0, columnspan=3, sticky='w', pady=8)

    def _zip_tab(self):
        frame = self._tab('TWRP / OrangeFox ZIP')
        self._row(frame, 0, 'ZIP output on computer', self.output, browse='file')
        self._row(frame, 1, 'Release directory', self.release, browse='dir')
        ttk.Checkbutton(frame, text='Embed release payload in ZIP (otherwise use adjacent j701f-release/)',
                        variable=self.embed).grid(row=2, column=0, columnspan=3, sticky='w')
        ttk.Label(frame, text='Building a ZIP does not install it on the phone.', wraplength=690).grid(
            row=3, column=0, columnspan=3, sticky='w', pady=8)

    def _mode(self):
        return ('release', 'first', 'zip')[self.tabs.index(self.tabs.select())]

    def _values(self):
        return {'release': self.release.get(), 'phone_ip': self.phone_ip.get(),
                'known_hosts': self.known_hosts.get(), 'mtp_sd': self.mtp_sd.get(),
                'from_recovery': self.from_recovery.get(), 'backup_userdata': self.backup_userdata.get(),
                'reboot': self.reboot.get(), 'bundle': self.bundle.get(), 'sd': self.sd.get(),
                'output': self.output.get(), 'embed': self.embed.get()}

    def scan_phone(self):
        try:
            ports = diagnostic_ports()
            self.phone_status.set(f'USB phone: {", ".join(map(str, ports))}' if ports else
                                  f'USB phone: no {SERIAL_ID} device found')
            return ports
        except OSError as exc:
            self.phone_status.set(f'USB phone scan failed: {exc}')
            return []

    def _set_write_button(self):
        self.write_button.configure(state='normal' if self.write_enabled.get() and not self.busy else 'disabled')

    def _append(self, line):
        self.log.configure(state='normal')
        self.log.insert('end', line + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def start(self, write):
        if self.busy or (write and not self.write_enabled.get()):
            return
        mode, values = self._mode(), self._values()
        try:
            command = build_command(mode, values, write=write)
            if write and mode == 'release':
                require_one_phone(self.scan_phone())
            if write and not confirm_write(mode, values, messagebox.askyesno, simpledialog.askstring):
                self.message.set('Write cancelled; nothing started.')
                return
        except (ValueError, OSError) as exc:
            messagebox.showerror('Cannot start', str(exc))
            return
        self._append(('$ ' if write else 'DRY RUN $ ') + shlex.join(command))
        self.busy = True
        self.preview_button.configure(state='disabled')
        self.scan_button.configure(state='disabled')
        self.write_button.configure(state='disabled')
        self.message.set('Running. Keep this window open; a recovery write may continue after USB disconnects.')
        threading.Thread(target=self._worker, args=(mode, values, command, write), daemon=True).start()

    def _worker(self, mode, values, command, write):
        try:
            if mode == 'zip' and not write:
                check_zip_inputs(values)
                self.events.put(('line', 'ZIP inputs verified; preview only. No file was created.'))
                code = 0
            else:
                with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
                    for line in process.stdout:
                        self.events.put(('line', line.rstrip('\n')))
                    code = process.wait()
            self.events.put(('done', code))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'line':
                    self._append(payload)
                else:
                    self.busy = False
                    self.preview_button.configure(state='normal')
                    self.scan_button.configure(state='normal')
                    self.write_enabled.set(False)
                    self._set_write_button()
                    if kind == 'error':
                        self.message.set(f'Failed: {payload}')
                        self._append(f'ERROR: {payload}')
                    elif payload:
                        self.message.set(f'Command failed (exit {payload}). Inspect the log before any retry.')
                    else:
                        self.message.set('Completed. A dry run made no writes; check the log for the result.')
        except queue.Empty:
            pass
        self.window.after(100, self._drain)

    def close(self):
        if self.busy:
            messagebox.showwarning('Operation in progress',
                'Keep this window open. A detached recovery job may continue even if the USB link drops.')
            return
        self.window.destroy()


def main():
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
