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

static int chosen_addr(const void *fdt, int node, const char *name, ulong *addr)
{
	int len;
	const void *p = fdt_getprop(fdt, node, name, &len);

	if (!p)
		return -1;
	if (len == sizeof(fdt32_t))
		*addr = fdt32_to_cpu(*(const fdt32_t *)p);
	else if (len == sizeof(fdt64_t))
		/* FDT properties are only four-byte aligned. */
		*addr = (ulong)fdt32_to_cpu(((const fdt32_t *)p)[0]) << 32 |
			fdt32_to_cpu(((const fdt32_t *)p)[1]);
	else
		return -1;
	return 0;
}

static int do_j701f_ramboot(struct cmd_tbl *cmdtp, int flag, int argc,
			  char *const argv[])
{
	ulong previous = get_prev_bl_fdt_addr(), start, end;
	const void *prev = (const void *)previous;
	const void *fit;
	u8 digest[SHA256_SUM_LEN];
	int node;
	const char *board = env_get("board");

	/* The earlier board matcher also requires J701F firmware/revision 3. */
	if (!board || strcmp(board, "j7velte") ||
	    gd->bd->bi_dram[0].start != 0x40000000UL ||
	    gd->bd->bi_dram[0].size != 0x3e400000UL ||
	    gd->bd->bi_dram[1].start != 0x80000000UL ||
	    gd->bd->bi_dram[1].size != 0x40000000UL ||
	    gd->relocaddr < 0xb8000000UL || gd->relocaddr >= 0xc0000000UL)
		goto refuse;
	if (previous & 7 || !measured_ram(previous, sizeof(struct fdt_header)) ||
	    fdt_check_header(prev) || fdt_totalsize(prev) > 0x200000 ||
	    !measured_ram(previous, fdt_totalsize(prev)))
		goto refuse;
	node = fdt_path_offset(prev, "/chosen");
	if (node < 0 || chosen_addr(prev, node, "linux,initrd-start", &start) ||
	    chosen_addr(prev, node, "linux,initrd-end", &end))
		goto refuse;
	/* Never let component loads overwrite the FIT or vendor debug area. */
	if (start & 7 || start < J701F_TARGETS_END || end <= start ||
	    end > J701F_SOURCE_LIMIT || end - start != J701F_FIT_BYTES)
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
	    env_set("bootargs", "rdinit=/init console=ttySAC2,115200n8 loglevel=8 "
		    "ignore_loglevel clk_ignore_unused regulator_ignore_unused panic=10"))
		goto refuse;
	printf("J701F: paired RAM payload verified; handing off to Linux\n");
	/* Explicit config, no removable-media scan or storage fallback. */
	run_commandf("bootm %lx#conf-j701f-diagnostic", start);
refuse:
	printf("J701F: diagnostic handoff stopped; no storage fallback\n");
	return CMD_RET_FAILURE;
}

U_BOOT_CMD(j701f_ramboot, 1, 0, do_j701f_ramboot,
	   "boot the paired diagnostic FIT supplied in Samsung's RAM initrd", "");
