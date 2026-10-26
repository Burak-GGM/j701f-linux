// Explicit local trial helper; no block devices or firmware are written here.
#include <linux/reboot.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc != 2 || strcmp(argv[1], "--execute")) {
        puts("PLAN: Linux RESTART2 with recovery destination; use --execute as root.");
        return 0;
    }
    if (geteuid() != 0) { fputs("Root is required\n", stderr); return 1; }
    sync();
    puts("J701F_REQUESTING_RECOVERY_BOOT");
    fflush(stdout);
    syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
            LINUX_REBOOT_CMD_RESTART2, "recovery");
    perror("recovery restart");
    return 1;
}
