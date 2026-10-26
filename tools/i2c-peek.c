/* Written by Claude 2026-10-08.
 * One-byte I2C register read/write through i2c-dev for mainline bring-up
 * diagnostics. No libc. Usage (all numbers hex):
 *   i2c-peek /dev/i2c-N ADDR r REG
 *   i2c-peek /dev/i2c-N ADDR w REG VALUE
 * Prints "0xNN" on success, "ERR -errno" on failure (exit 1).
 */
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
/* AArch64 Linux asm-generic/unistd.h ABI. Do not use host asm/unistd.h. */
enum { A64_IOCTL=29, A64_OPENAT=56, A64_WRITE=64, A64_EXIT_GROUP=94 };

static long sys(long number, long a, long b, long c, long d)
{
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x8 __asm__("x8") = number;
    __asm__ volatile ("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3), "r"(x8) : "memory", "cc");
    return x0;
}

static void out(const char *s)
{
    unsigned long n = 0;
    while (s[n]) n++;
    sys(A64_WRITE, 1, (long)s, (long)n, 0);
}

static void out_hex(unsigned long v, int digits)
{
    char b[20]; int i = 0;
    b[i++] = '0'; b[i++] = 'x';
    for (int d = digits - 1; d >= 0; d--) b[i++] = "0123456789abcdef"[(v >> (4 * d)) & 15];
    b[i++] = '\n'; b[i] = 0;
    out(b);
}

static __attribute__((noreturn)) void die(long error)
{
    char b[24]; int i = 0; unsigned long v = (unsigned long)-error;
    char t[12]; int n = 0;
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    b[i++]='E'; b[i++]='R'; b[i++]='R'; b[i++]=' '; b[i++]='-';
    while (n) b[i++] = t[--n];
    b[i++] = '\n'; b[i] = 0;
    out(b);
    sys(A64_EXIT_GROUP, 1, 0, 0, 0);
    for (;;) {}
}

static long hex(const char *s)
{
    long v = 0; int n = 0;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) s += 2;
    for (; *s; s++, n++) {
        int d = *s >= '0' && *s <= '9' ? *s - '0' : *s >= 'a' && *s <= 'f' ? *s - 'a' + 10 :
                *s >= 'A' && *s <= 'F' ? *s - 'A' + 10 : -1;
        if (d < 0 || n >= 2) return -1;
        v = v * 16 + d;
    }
    return n ? v : -1;
}

void entry(unsigned long *sp)
{
    long argc = (long)sp[0];
    char **argv = (char **)(sp + 1);
    if (argc < 5) die(-22);
    int write = argv[3][0] == 'w' && !argv[3][1];
    if (!write && !(argv[3][0] == 'r' && !argv[3][1])) die(-22);
    if (argc != (write ? 6 : 5)) die(-22);
    long addr = hex(argv[2]), reg = hex(argv[4]), value = write ? hex(argv[5]) : 0;
    if (addr < 0x03 || addr > 0x77 || reg < 0 || value < 0) die(-22);
    long fd = sys(A64_OPENAT, -100, (long)argv[1], 2 /* O_RDWR */, 0);
    if (fd < 0) die(fd);
    unsigned char tx[2] = { (unsigned char)reg, (unsigned char)value }, rx = 0;
    struct i2c_msg msgs[2] = {
        { .addr = (unsigned short)addr, .flags = 0, .len = write ? 2 : 1, .buf = tx },
        { .addr = (unsigned short)addr, .flags = I2C_M_RD, .len = 1, .buf = &rx },
    };
    struct i2c_rdwr_ioctl_data data = { .msgs = msgs, .nmsgs = write ? 1 : 2 };
    long r = sys(A64_IOCTL, fd, I2C_RDWR, (long)&data, 0);
    if (r < 0) die(r);
    out_hex(write ? (unsigned long)value : rx, 2);
    sys(A64_EXIT_GROUP, 0, 0, 0, 0);
    for (;;) {}
}
__asm__(".global _start\n_start:\nmov x0, sp\nbl entry\n");
