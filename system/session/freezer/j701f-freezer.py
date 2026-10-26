#!/usr/bin/python3
# Written by Claude 2026-10-10. Background-application freezer for the J701F
# Plasma Mobile session: an application that has not been in the foreground for
# a while is stopped (SIGSTOP, whole process tree) and continued the moment its
# window is activated again. Stopped applications use no CPU and their memory
# goes cold, so the kernel can move it to compressed swap.
# Installed as ~/.local/lib/j701f-freezer/j701f-freezer.py, started by
# ~/.config/autostart/j701f-freezer.desktop. Notes: wiki/reference/performance.md
#
# KWin tells this daemon about windows through freezer.js (loaded from here).
# Never frozen: the shell, the compositor, the keyboard, terminals, anything
# playing or recording sound, anything named in the configuration file.
# Nothing is frozen while the home screen is in front. The lock screen counts
# as an ordinary foreground: applications left open behind it are stopped after
# the idle time and continued when they come back to the front.
import json, os, signal, subprocess, sys, time
import dbus, dbus.service, dbus.mainloop.glib
from gi.repository import GLib

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.expanduser('~/.config/j701f-freezer.conf')
NAME, PATH, IFACE = 'org.j701f.Freezer', '/Freezer', 'org.j701f.Freezer'
SHELL = {'plasmashell'}
# kwin_wayland owns the window that is in front while the screen is locked or off.
NEVER = {'plasmashell', 'kwin_wayland', 'kscreenlocker_g', 'plasma-keyboard', 'Xwayland',
         'foot', 'qmlkonsole', 'konsole', 'plasma-dialer', 'spacebar', 'sddm-greeter'}


def read_conf():
    c = {'enabled': '1', 'idle_seconds': '300', 'exclude': ''}
    try:
        for line in open(CONF):
            line = line.split('#', 1)[0].strip()
            if '=' in line:
                k, v = line.split('=', 1)
                c[k.strip()] = v.strip()
    except OSError:
        pass
    return c


def comm(pid):
    try:
        return open('/proc/%d/comm' % pid).read().strip()
    except OSError:
        return ''


def tree(root):
    """root and all its descendants, parents before children."""
    kids = {}
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                s = open('/proc/%s/stat' % d).read()
                kids.setdefault(int(s.rsplit(')', 1)[1].split()[1]), []).append(int(d))
            except (OSError, IndexError, ValueError):
                pass
    out, todo = [], [root]
    while todo:
        p = todo.pop(0)
        out.append(p)
        todo += kids.get(p, [])
    return out


def sound_pids():
    """Processes with a running playback or capture stream (query only)."""
    pids = set()
    for what in ('sink-inputs', 'source-outputs'):
        try:
            r = subprocess.run(['pactl', '-f', 'json', 'list', what], capture_output=True, text=True, timeout=5)
            for s in json.loads(r.stdout or '[]'):
                if not s.get('corked', False):
                    p = s.get('properties', {}).get('application.process.id')
                    if p:
                        pids.add(int(p))
        except (OSError, ValueError, subprocess.SubprocessError):
            return None     # cannot tell: freeze nothing this round
    return pids


class Freezer(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(dbus.service.BusName(NAME, bus), PATH)
        self.last = {}      # pid -> time it was last in front (or first seen)
        self.frozen = {}    # pid -> list of stopped pids
        self.front = 0
        self.bus = bus
        self.log('started')

    def log(self, msg):
        print(time.strftime('%H:%M:%S'), msg, flush=True)

    # --- called by the KWin script; everything arrives as strings ---
    @dbus.service.method(IFACE, in_signature='ss')
    def Activated(self, pid, cls):
        pid = int(pid or 0)
        if self.front in self.last:   # idle time counts from leaving the foreground
            self.last[self.front] = time.time()
        self.front = pid
        if pid:
            self.last[pid] = time.time()
            self.thaw(pid, 'activated')
        if not pid or comm(pid) in SHELL:
            self.thaw_all('home screen in front')

    @dbus.service.method(IFACE, in_signature='ss')
    def Seen(self, pid, cls):
        pid = int(pid or 0)
        if pid:
            self.last.setdefault(pid, time.time())

    @dbus.service.method(IFACE, in_signature='ss')
    def Unresponsive(self, pid, cls):
        pid = int(pid or 0)
        if pid in self.frozen:        # KWin wants an answer from it (close request, ping)
            self.last[pid] = time.time()
            self.thaw(pid, 'KWin is waiting for it')

    @dbus.service.method(IFACE, out_signature='s')
    def Status(self):
        now = time.time()
        return json.dumps({'front': self.front, 'frozen': sorted(self.frozen),
                           'idle': {str(p): int(now - t) for p, t in self.last.items()}})

    # --- mechanics ---
    def freeze(self, pid):
        pids = tree(pid)
        done = []
        for p in pids:
            try:
                os.kill(p, signal.SIGSTOP)
                done.append(p)
            except OSError:
                pass
        self.frozen[pid] = done
        self.log('froze %s (%d, %d processes)' % (comm(pid), pid, len(done)))

    def thaw(self, pid, why):
        if pid not in self.frozen:
            return
        for p in reversed(sorted(set(self.frozen.pop(pid) + tree(pid)))):
            try:
                os.kill(p, signal.SIGCONT)
            except OSError:
                pass
        self.log('continued %s (%d): %s' % (comm(pid), pid, why))

    def thaw_all(self, why):
        for pid in list(self.frozen):
            self.thaw(pid, why)

    def tick(self):
        try:                          # KWin may have been restarted
            load_kwin_script(self.bus, only_if_missing=True)
        except dbus.DBusException:
            pass
        c = read_conf()
        now = time.time()
        for pid in [p for p in self.last if not os.path.exists('/proc/%d' % p)]:
            self.last.pop(pid, None)
            self.frozen.pop(pid, None)
        if c['enabled'] != '1':
            self.thaw_all('disabled in ' + CONF)
            return True
        fc = comm(self.front) if self.front else ''
        if not self.front or fc in SHELL:
            self.thaw_all('home screen in front')
            return True
        try:
            idle = max(20, int(c['idle_seconds']))
        except ValueError:
            idle = 300
        never = NEVER | {x.strip() for x in c['exclude'].split(',') if x.strip()}
        due = [p for p, t in self.last.items()
               if p != self.front and p not in self.frozen and now - t > idle and comm(p) not in never]
        if due:
            loud = sound_pids()
            if loud is None:
                return True
            for pid in due:
                if loud & set(tree(pid)):
                    self.last[pid] = now      # look again after another idle period
                else:
                    self.freeze(pid)
        return True


def continue_leftovers():
    """After a crash of an earlier instance: continue every stopped process of this user."""
    me = os.getuid()
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                if os.stat('/proc/' + d).st_uid == me and open('/proc/%s/stat' % d).read().rsplit(')', 1)[1].split()[0] == 'T':
                    os.kill(int(d), signal.SIGCONT)
            except (OSError, IndexError):
                pass


def load_kwin_script(bus, only_if_missing=False):
    s = dbus.Interface(bus.get_object('org.kde.KWin', '/Scripting'), 'org.kde.kwin.Scripting')
    if only_if_missing and s.isScriptLoaded('j701f-freezer', signature='s'):
        return
    try:
        s.unloadScript('j701f-freezer', signature='s')
    except dbus.DBusException:
        pass
    # loadScript is overloaded on the bus; name the two-string form explicitly.
    s.loadScript(os.path.join(HERE, 'freezer.js'), 'j701f-freezer', signature='ss')
    s.start(signature='')


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    continue_leftovers()
    f = Freezer(bus)
    loop = GLib.MainLoop()

    def stop(*_):
        f.thaw_all('daemon stopping')
        loop.quit()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    for i in range(30):                      # KWin may not be on the bus yet
        try:
            load_kwin_script(bus)
            break
        except dbus.DBusException as e:
            if i == 29:
                f.log('could not load the KWin script: %s' % e)
            time.sleep(2)
    GLib.timeout_add_seconds(15, f.tick)
    try:
        loop.run()
    finally:
        f.thaw_all('daemon exit')


if __name__ == '__main__':
    main()
