// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-10 (J701F). The bootloader leaves the CAM0 power
 * domain switched on, and nothing on mainline uses the camera block. Loading
 * this module switches the domain off (PMU CONFIGURATION 0x4040 = 0) and
 * reports the STATUS register; unloading switches it back on. It is loaded at
 * boot from ~/j701f-misc-modules by the guarded local.d script.
 * Remove it before any camera driver work.
 */
#include <linux/delay.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>

#define CAM0_CONFIGURATION	0x4040
#define CAM0_STATUS		0x4044

static struct regmap *pmu;

static void j701f_cam0_set(unsigned int want)
{
	unsigned int st = 0;
	int t;

	regmap_write(pmu, CAM0_CONFIGURATION, want);
	for (t = 0; t < 100; t++) {
		regmap_read(pmu, CAM0_STATUS, &st);
		if ((st & 0xf) == want)
			break;
		usleep_range(1000, 1100);
	}
	pr_info("j701f_cam0_off: CAM0 power domain %s, status %#x%s\n", want ? "on" : "off", st,
		(st & 0xf) == want ? "" : " (did not follow)");
}

static int __init j701f_cam0_off_init(void)
{
	struct device_node *np = of_find_compatible_node(NULL, NULL, "samsung,exynos7870-pmu");

	if (!np)
		return -ENODEV;
	pmu = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(pmu))
		return PTR_ERR(pmu);
	j701f_cam0_set(0);
	return 0;
}

static void __exit j701f_cam0_off_exit(void)
{
	j701f_cam0_set(0xf);
}

module_init(j701f_cam0_off_init);
module_exit(j701f_cam0_off_exit);
MODULE_DESCRIPTION("Switch the unused CAM0 power domain off (J701F local)");
MODULE_LICENSE("GPL");
