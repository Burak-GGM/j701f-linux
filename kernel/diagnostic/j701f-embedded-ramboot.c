// SPDX-License-Identifier: GPL-2.0
/* Paired, RAM-only diagnostic handoff. No partition or firmware operations. */
#include <command.h>
#include <env.h>
#include <image.h>
#include <init.h>
#include <limits.h>
#include <linux/libfdt.h>
#include <u-boot/sha256.h>
#include <asm/global_data.h>
#include "j701f-fit-payload.h"

DECLARE_GLOBAL_DATA_PTR;

static bool measured_ram(ulong start, ulong bytes)
{
	if (!bytes || bytes > ULONG_MAX - start)
		return false;
	return (start >= 0x40000000UL && start + bytes <= 0x7e400000UL) ||
	       (start >= 0x80000000UL && start + bytes <= 0xc0000000UL);
}

/* The paired FIT is part of the relocated read-only loader image. */
extern const unsigned char j701f_embedded_fit[], j701f_embedded_fit_end[];

static int do_j701f_ramboot(struct cmd_tbl *cmdtp, int flag, int argc,
			  char *const argv[])
{
	ulong previous = get_prev_bl_fdt_addr();
	ulong start = (ulong)j701f_embedded_fit, end = (ulong)j701f_embedded_fit_end;
	const void *prev = (const void *)previous;
	const void *fit;
	u8 digest[SHA256_SUM_LEN];
	
	const char *board = env_get("board");

	/* The earlier board matcher also requires J701F firmware/revision 3. */
	if (!board || strcmp(board, "j7velte") ||
	    gd->bd->bi_dram[0].start != 0x40000000UL ||
	    gd->bd->bi_dram[0].size != 0x3e400000UL ||
	    gd->bd->bi_dram[1].start != 0x80000000UL ||
	    gd->bd->bi_dram[1].size != 0x40000000UL ||
	    gd->relocaddr < 0xb8400000UL || gd->relocaddr >= 0xc0000000UL ||
	    !gd->mon_len || gd->mon_len > 0xc0000000UL - gd->relocaddr)
		goto refuse;
	if (previous & 7 || !measured_ram(previous, sizeof(struct fdt_header)) ||
	    fdt_check_header(prev) || fdt_totalsize(prev) > 0x200000 ||
	    !measured_ram(previous, fdt_totalsize(prev)))
		goto refuse;
	if (fdt_path_offset(prev, "/chosen") < 0)
		goto refuse;
	/* All component targets are in lower RAM; source must be in this loader's
	 * relocated upper-RAM allocation, above measured firmware reservations. */
	if (start & 7 || end <= start || end - start != J701F_FIT_BYTES ||
	    start < gd->relocaddr || end > gd->relocaddr + gd->mon_len ||
	    !measured_ram(start, end - start) || start < 0xb8400000UL ||
	    J701F_TARGETS_END > 0x7e400000UL)
		goto refuse;
	fit = (const void *)start;
	if (fdt_check_header(fit) || fdt_totalsize(fit) != J701F_FIT_BYTES ||
	    fit_check_format(fit, J701F_FIT_BYTES))
		goto refuse;
	sha256_csum_wd(fit, J701F_FIT_BYTES, digest, CHUNKSZ_SHA256);
	if (memcmp(digest, j701f_fit_sha256, sizeof(digest)))
		goto refuse;
	if (env_set("verify", "yes") ||
	    env_set("fdt_high", "ffffffffffffffff") ||
	    env_set("initrd_high", "ffffffffffffffff") ||
	    env_set("bootargs", "rdinit=/init console=tty0 console=ttySAC2,115200n8 loglevel=8 "
		    "ignore_loglevel clk_ignore_unused regulator_ignore_unused panic=10 "
		    /* Claude 2026-10-09: SoC watchdog armed from probe; the kernel
		     * feeds it, so a hung kernel resets after its 30 s timeout. */
		    "s3c2410_wdt.tmr_atboot=1 s3c2410_wdt.keep_on_shutdown=1"))
		goto refuse;
	printf("J701F: paired RAM payload verified; handing off to Linux\n");
	/* Explicit config, no removable-media scan or storage fallback. */
	run_commandf("bootm %lx#conf-j701f-diagnostic", start);
refuse:
	printf("J701F: diagnostic handoff stopped; no storage fallback\n");
	return CMD_RET_FAILURE;
}

U_BOOT_CMD(j701f_ramboot, 1, 0, do_j701f_ramboot,
	   "boot the paired diagnostic FIT embedded in the relocated loader", "");
