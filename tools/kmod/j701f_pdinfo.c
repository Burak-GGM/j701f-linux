// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-09 (J701F). Prints the CONFIGURATION and STATUS
 * registers of the four Exynos7870 power domains named in the vendor device
 * tree, and nothing else. Exists because dumping the whole PMU regmap through
 * debugfs faults. Load, read dmesg, unload.
 */
#include <linux/delay.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>

static const struct { const char *name; unsigned int off; } pds[] = {
	{ "g3d", 0x4000 }, { "dispaud", 0x4020 }, { "cam0", 0x4040 }, { "mfcmscl", 0x4060 },
};

/*
 * Optional experiment: "insmod j701f_pdinfo.ko off=cam0" (or on=cam0) writes the
 * domain's CONFIGURATION register (0 = off, 0xf = on) and waits up to 100 ms
 * for the low four STATUS bits to follow. Only domains that no driver uses
 * should ever be switched this way.
 */
static char *off;
module_param(off, charp, 0);
static char *on;
module_param(on, charp, 0);

static void j701f_pd_switch(struct regmap *pmu, const char *name, unsigned int want)
{
	unsigned int st = 0;
	int i, t;

	for (i = 0; i < ARRAY_SIZE(pds); i++)
		if (!strcmp(pds[i].name, name))
			break;
	if (i == ARRAY_SIZE(pds)) {
		pr_info("j701f_pdinfo: unknown domain %s\n", name);
		return;
	}
	regmap_write(pmu, pds[i].off, want);
	for (t = 0; t < 100; t++) {
		regmap_read(pmu, pds[i].off + 4, &st);
		if ((st & 0xf) == want)
			break;
		usleep_range(1000, 1100);
	}
	pr_info("j701f_pdinfo: %s -> %#x: status %#x after %d ms%s\n", name, want, st, t,
		(st & 0xf) == want ? "" : " (did NOT follow)");
}

static int __init j701f_pdinfo_init(void)
{
	struct device_node *np = of_find_compatible_node(NULL, NULL, "samsung,exynos7870-pmu");
	struct regmap *pmu;
	unsigned int cfg, st;
	int i;

	if (!np)
		return -ENODEV;
	pmu = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(pmu))
		return PTR_ERR(pmu);
	if (off)
		j701f_pd_switch(pmu, off, 0);
	if (on)
		j701f_pd_switch(pmu, on, 0xf);
	for (i = 0; i < ARRAY_SIZE(pds); i++) {
		cfg = st = 0xdeadbeef;
		regmap_read(pmu, pds[i].off, &cfg);
		regmap_read(pmu, pds[i].off + 4, &st);
		pr_info("j701f_pdinfo: %s configuration %#x status %#x\n", pds[i].name, cfg, st);
	}
	return 0;
}

static void __exit j701f_pdinfo_exit(void) { }

module_init(j701f_pdinfo_init);
module_exit(j701f_pdinfo_exit);
MODULE_DESCRIPTION("Print Exynos7870 power-domain state (J701F diagnostic)");
MODULE_LICENSE("GPL");
