#!/usr/bin/env python3
"""Written by Claude 2026-10-09. USERSPACE PROTOTYPE of Exynos7870 CPU frequency
switching on the J701F. NOT RUN YET: Claude's tool sandbox refused to execute it
on the phone, so it is untested.

Intended use: as root on the mainline kernel with the SoC watchdog armed (a hang
then resets the phone back to the bootloader's 902 MHz). It pokes CMU_CPUCL0/1
through /dev/mem and BUCK1 through raw I2C, following the vendor sequence: raise
voltage, park the cluster on the MIF switch clock, reprogram and relock the PLL,
return to the PLL, lower voltage if going down.

Usage: cpufreq-prototype.py status
       cpufreq-prototype.py set <cl0|cl1|both> <MHz>
Voltages are the BUCK1 values measured on this phone under the vendor 3.18
kernel (build/kernel/vendor-opp-measurement.txt) plus 12.5 mV.
"""
import ctypes, fcntl, glob, mmap, os, struct, sys, time

OPP_UV = {546: 625000, 676: 668750, 757: 693750, 839: 712500, 902: 737500, 1014: 781250,
          1144: 825000, 1248: 868750, 1352: 906250, 1482: 956250, 1586: 1006250}
MARGIN_UV = 12500
BASE = {'cl0': 0x10900000, 'cl1': 0x10800000}
PLL_LOCK, PLL_CON0, MUX_SWUSER, MUX_CLK, STAT_SWUSER, STAT_CLK = 0x0, 0x100, 0x204, 0x208, 0x604, 0x608
SEL, STAT0, STAT1 = 1 << 12, 0x1000, 0x2000

fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
maps = {k: mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=b) for k, b in BASE.items()}


def rd(c, o):
    return struct.unpack_from('<I', maps[c], o)[0]


def wr(c, o, v):
    struct.pack_into('<I', maps[c], o, v)


class Msg(ctypes.Structure):
    _fields_ = [('addr', ctypes.c_uint16), ('flags', ctypes.c_uint16), ('len', ctypes.c_uint16), ('buf', ctypes.c_char_p)]


class Rdwr(ctypes.Structure):
    _fields_ = [('msgs', ctypes.POINTER(Msg)), ('nmsgs', ctypes.c_uint32)]


i2c = os.open('/dev/i2c-' + glob.glob('/sys/devices/platform/soc@0/10510000.i2c/i2c-*')[0].rsplit('-', 1)[1], os.O_RDWR)
B1CTRL2 = 0x1b      # S2MPU05 BUCK1 voltage selector; read back as 0x36 = 737.5 mV at 902 MHz


def pmic_rd(reg):
    w = ctypes.create_string_buffer(bytes([reg]), 1)
    r = ctypes.create_string_buffer(1)
    fcntl.ioctl(i2c, 0x0707, Rdwr((Msg * 2)(Msg(0x66, 0, 1, ctypes.cast(w, ctypes.c_char_p)),
                                            Msg(0x66, 1, 1, ctypes.cast(r, ctypes.c_char_p))), 2))
    return r.raw[0]


def pmic_wr(reg, val):
    w = ctypes.create_string_buffer(bytes([reg, val]), 2)
    fcntl.ioctl(i2c, 0x0707, Rdwr((Msg * 1)(Msg(0x66, 0, 2, ctypes.cast(w, ctypes.c_char_p))), 1))


def buck1_uv():
    return 400000 + pmic_rd(B1CTRL2) * 6250


def set_buck1(uv):
    sel = (uv - 400000 + 6249) // 6250
    assert 0x20 <= sel <= 0x68, 'BUCK1 selector out of the 600-1050 mV window'
    pmic_wr(B1CTRL2, sel)
    time.sleep(0.005)
    assert pmic_rd(B1CTRL2) == sel, 'BUCK1 read-back mismatch'


def pll_mhz(c):
    v = rd(c, PLL_CON0)
    m, p, s = (v >> 16) & 0x3ff, (v >> 8) & 0x3f, v & 7
    return 26 * m / (p * (1 << s))


def wait(c, off, want, what):
    for _ in range(2000):
        if rd(c, off) & 0x7000 == want:
            return
    raise SystemExit('timeout waiting for ' + what)


def status():
    print('BUCK1 %d uV' % buck1_uv())
    for c in BASE:
        print(c, 'PLL %.0f MHz CON0=%08x MUX_CLK=%08x stat=%04x SWUSER stat=%04x' % (
            pll_mhz(c), rd(c, PLL_CON0), rd(c, MUX_CLK), rd(c, STAT_CLK) & 0xffff, rd(c, STAT_SWUSER) & 0xffff))


def pms(mhz):
    if mhz == 902:
        return 347, 5, 1                      # the bootloader's own setting
    m = mhz * 5 // 26
    assert m * 26 // 5 == mhz and 64 <= m <= 1023, 'no exact PMS with P=5,S=0'
    return m, 5, 0


def set_rate(c, mhz):
    m, p, s = pms(mhz)
    # Measured idle state: SWUSER and MUX_CLK both select input 0 (stat 0x1000);
    # MIF feeds the switch input (enable=1, divider=0, taken to be bus_pll/2 = 800 MHz).
    wr(c, MUX_SWUSER, rd(c, MUX_SWUSER) | SEL)
    wait(c, STAT_SWUSER, STAT1, 'switch user mux')
    wr(c, MUX_CLK, rd(c, MUX_CLK) | SEL)
    wait(c, STAT_CLK, STAT1, 'cpu mux -> switch')
    wr(c, PLL_LOCK, p * 150)
    wr(c, PLL_CON0, (1 << 31) | (m << 16) | (p << 8) | s)
    for _ in range(100000):
        if rd(c, PLL_CON0) & (1 << 29):
            break
    else:
        raise SystemExit('PLL did not lock (cluster stays on the switch clock)')
    wr(c, MUX_CLK, rd(c, MUX_CLK) & ~SEL)
    wait(c, STAT_CLK, STAT0, 'cpu mux -> pll')


if len(sys.argv) < 2 or sys.argv[1] == 'status':
    status()
    sys.exit(0)
which, mhz = sys.argv[2], int(sys.argv[3])
assert mhz in OPP_UV
clusters = list(BASE) if which == 'both' else [which]
other = [c for c in BASE if c not in clusters]
need = max([OPP_UV[mhz]] + [OPP_UV.get(round(pll_mhz(c)), OPP_UV[1586]) for c in other]) + MARGIN_UV
if need > buck1_uv():
    set_buck1(need)          # raise first when going up
for c in clusters:
    set_rate(c, mhz)
if need < buck1_uv():
    set_buck1(need)          # lower afterwards when going down
status()
