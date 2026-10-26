// SPDX-License-Identifier: GPL-2.0-only
/*
 * Codex, 2026-10-10: one-shot, read-only snapshot of J701F display state.
 * Offsets are from the pinned Samsung decon_7870 regs-decon.h/regs-dsim.h
 * and the SysMMU control/status definitions. No FIFO, interrupt status,
 * clear-on-read, power-control or clock-control writes are performed.
 *
 * Load only while firmware scanout is active. A domain-on check does not
 * establish that every clock is available; this is a bring-up diagnostic.
 */
#include <linux/io.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>
#include <linux/sizes.h>

struct display_reg {
	const char *name;
	u32 offset;
};

static const struct display_reg decon_regs[] = {
	{ "VIDCON0", 0x0000 },
	{ "VIDOUTCON0", 0x0004 },
	{ "VCLKCON1", 0x0014 },
	{ "VCLKCON2", 0x0018 },
	{ "WINCON0", 0x0050 },
	{ "VIDTCON0", 0x0610 },
	{ "VIDTCON1", 0x0614 },
	{ "VIDTCON2", 0x0618 },
	{ "VIDTCON3", 0x061c },
	{ "VIDTCON4", 0x0620 },
	{ "VIDW_ADD0", 0x0880 },
};

static const struct display_reg dsim_regs[] = {
	{ "LINK_STATUS", 0x04 },
	{ "DPHY_STATUS", 0x08 },
	{ "CLKCTRL", 0x10 },
	{ "RESOL", 0x20 },
	{ "VPORCH", 0x24 },
	{ "HPORCH", 0x28 },
	{ "SYNC", 0x2c },
	{ "CONFIG", 0x30 },
	{ "PLLCTRL", 0x94 },
};

static const struct display_reg sysmmu_regs[] = {
	{ "CTRL", 0x00 },
	{ "CONFIG", 0x04 },
	{ "STATUS", 0x08 },
	{ "VERSION", 0x34 },
};

static int display_snapshot(const char *block, phys_addr_t addr,
			    const struct display_reg *regs, size_t count)
{
	void __iomem *base;
	size_t i;

	base = ioremap(addr, SZ_4K);
	if (!base)
		return -ENOMEM;
	for (i = 0; i < count; i++)
		pr_info("j701f-display-info: %s %s offset=%#x value=%#010x\n",
			block, regs[i].name, regs[i].offset,
			readl(base + regs[i].offset));
	iounmap(base);
	return 0;
}

static int __init j701f_display_info_init(void)
{
	struct device_node *np;
	struct regmap *pmu;
	unsigned int status;
	int ret;

	if (!of_machine_is_compatible("samsung,j7velte"))
		return -ENODEV;
	np = of_find_compatible_node(NULL, NULL, "samsung,exynos7870-pmu");
	if (!np)
		return -ENODEV;
	pmu = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(pmu))
		return PTR_ERR(pmu);
	ret = regmap_read(pmu, 0x4024, &status);
	if (ret)
		return ret;
	pr_info("j701f-display-info: DISPAUD status=%#x\n", status);
	if ((status & 0xf) != 0xf)
		return -EHOSTDOWN;
	ret = display_snapshot("DECON", 0x14830000, decon_regs, ARRAY_SIZE(decon_regs));
	if (ret)
		return ret;
	ret = display_snapshot("DSIM", 0x14800000, dsim_regs, ARRAY_SIZE(dsim_regs));
	if (ret)
		return ret;
	return display_snapshot("SYSMMU", 0x14860000, sysmmu_regs, ARRAY_SIZE(sysmmu_regs));
}

static void __exit j701f_display_info_exit(void)
{
}

module_init(j701f_display_info_init);
module_exit(j701f_display_info_exit);
MODULE_DESCRIPTION("Read-only snapshot of known J701F display registers");
MODULE_LICENSE("GPL v2");
