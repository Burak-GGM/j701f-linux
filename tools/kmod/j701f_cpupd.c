// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-10 (J701F). Exynos 7870 CPU power-down helper for
 * the PSCI idle state in kernel/dts/exynos7870-j7velte-cpuidle.dts.
 *
 * The vendor 3.18 kernel (drivers/soc/samsung/exynos-pmu.c, exynos_cpu_down()
 * and exynos_cpu_up(), called from enter_c2()/wakeup_from_c2()) clears the low
 * four bits of the core's PMU CPU_CONFIGURATION register before PSCI
 * CPU_SUSPEND and sets them again after wake-up. Without that write the core
 * is only clock-gated. This module does the same from a CPU PM notifier:
 *   CONFIGURATION = 0x2000 + 0x80 * ((cluster << 2) | core), STATUS = +4.
 * Unloading restores 0xf for every core. Statistics: /sys/module/j701f_cpupd/parameters/
 */
#include <linux/cpu_pm.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>
#include <asm/cputype.h>

#define PMU_CPU_CONFIG_BASE	0x2000
#define PMU_CPU_ADDR_OFFSET	0x80
#define CPU_LOCAL_PWR_CFG	0xf

static struct regmap *pmu;
static unsigned long enters, exits;
module_param(enters, ulong, 0444);
module_param(exits, ulong, 0444);

/* Register of the core this code runs on, from its MPIDR as the vendor does. */
static unsigned int j701f_this_cpu_reg(void)
{
	u64 mpidr = read_cpuid_mpidr();

	return PMU_CPU_CONFIG_BASE + PMU_CPU_ADDR_OFFSET *
		((MPIDR_AFFINITY_LEVEL(mpidr, 1) << 2) | MPIDR_AFFINITY_LEVEL(mpidr, 0));
}

/* Logical cores 0-3 are cluster 0 and 4-7 cluster 1 on this SoC, so the index is the same. */
static unsigned int j701f_cpu_reg(unsigned int cpu)
{
	return PMU_CPU_CONFIG_BASE + PMU_CPU_ADDR_OFFSET * cpu;
}

static int j701f_cpupd_notify(struct notifier_block *nb, unsigned long action, void *data)
{
	unsigned int reg = j701f_this_cpu_reg();

	switch (action) {
	case CPU_PM_ENTER:
		regmap_update_bits(pmu, reg, CPU_LOCAL_PWR_CFG, 0);
		enters++;
		break;
	case CPU_PM_ENTER_FAILED:
	case CPU_PM_EXIT:
		regmap_update_bits(pmu, reg, CPU_LOCAL_PWR_CFG, CPU_LOCAL_PWR_CFG);
		exits++;
		break;
	}
	return NOTIFY_OK;
}

static struct notifier_block j701f_cpupd_nb = { .notifier_call = j701f_cpupd_notify };

static int __init j701f_cpupd_init(void)
{
	struct device_node *np = of_find_compatible_node(NULL, NULL, "samsung,exynos7870-pmu");
	unsigned int cpu, v = 0;

	if (!np)
		return -ENODEV;
	pmu = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(pmu))
		return PTR_ERR(pmu);
	for_each_possible_cpu(cpu) {
		regmap_read(pmu, j701f_cpu_reg(cpu), &v);
		pr_info("j701f_cpupd: cpu%u CONFIGURATION %#x = %#x\n", cpu, j701f_cpu_reg(cpu), v);
	}
	return cpu_pm_register_notifier(&j701f_cpupd_nb);
}

static void __exit j701f_cpupd_exit(void)
{
	unsigned int cpu;

	cpu_pm_unregister_notifier(&j701f_cpupd_nb);
	for_each_possible_cpu(cpu)
		regmap_update_bits(pmu, j701f_cpu_reg(cpu), CPU_LOCAL_PWR_CFG, CPU_LOCAL_PWR_CFG);
	pr_info("j701f_cpupd: removed after %lu enters, %lu exits\n", enters, exits);
}

module_init(j701f_cpupd_init);
module_exit(j701f_cpupd_exit);
MODULE_DESCRIPTION("J701F: Exynos 7870 PMU core power-down around PSCI CPU_SUSPEND");
MODULE_LICENSE("GPL");
