/* Written by Claude 2026-10-08.
 * Freestanding initramfs helper: sync, then Linux RESTART2 with the "recovery"
 * argument (syscon-reboot-mode writes 0x12345674, Samsung's recovery reason).
 * Used when the mainline image lives in BOOT and the vendor 3.18 system is the
 * fallback in RECOVERY. No libc; writes no block device itself.
 */
#include <linux/reboot.h>
/* AArch64 Linux asm-generic/unistd.h ABI. Do not use host asm/unistd.h. */
enum { A64_WRITE=64, A64_SYNC=81, A64_EXIT_GROUP=94, A64_REBOOT=142 };

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

void entry(void)
{
    static const char note[] = "J701F_REQUESTING_RECOVERY_BOOT\n";
    static const char failed[] = "recovery restart failed\n";
    sys(A64_WRITE, 1, (long)note, sizeof note - 1, 0);
    sys(A64_SYNC, 0, 0, 0, 0);
    sys(A64_REBOOT, (long)LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
        LINUX_REBOOT_CMD_RESTART2, (long)"recovery");
    sys(A64_WRITE, 2, (long)failed, sizeof failed - 1, 0);
    sys(A64_EXIT_GROUP, 1, 0, 0, 0);
    for (;;) {}
}
__asm__(".global _start\n_start:\nbl entry\n");
