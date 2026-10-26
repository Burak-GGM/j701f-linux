// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-13 for the J701F project. First step of the modem
 * work: look, do not touch.
 *
 * Reports the state of the integrated modem ("CP", Samsung Shannon 315, an
 * SS310AP-type modem in the vendor's terms) as the boot loader left it:
 * CP_CTRL (non-secure and secure view), read through the secure monitor with
 * the same call the vendor's drivers/soc/samsung/pmu-cp.c uses (SMC
 * 0x82000700, function 3 = read).
 * The CP registers of the PMU are NOT read directly: they are secure-only, and
 * the first version of this module, which did, took a synchronous external
 * abort on the first of them (2026-10-13).
 * Nothing is written anywhere: no SMC write function, no register write, the
 * modem's memory and the mailbox are not touched. Loading prints the values
 * and fails on purpose (-ENODEV), so that nothing stays loaded.
 *
 * Register names and bits: include/soc/samsung/pmu-cp.h of the vendor tree
 * (build/kernel/vendor-modem-reference/).
 */
#include <linux/arm-smccc.h>
#include <linux/module.h>
#include <linux/of.h>

#define SMC_CP_CTRL	0x82000700
#define  CP_CTRL_READ	3
#define  REG_CP_CTRL_S	0
#define  REG_CP_CTRL_NS	1

static void decode(const char *what, unsigned long v)
{
	pr_info("j701f_modem_probe: %s = %#lx%s%s%s%s%s\n", what, v,
		v & BIT(1) ? " PWRON" : "", v & BIT(2) ? " RESET_SET" : "",
		v & BIT(3) ? " START" : "", v & BIT(5) ? " ACTIVE_REQ_EN" : "",
		v & BIT(7) ? " RESET_REQ_EN" : "");
}

static int __init j701f_modem_probe_init(void)
{
	struct arm_smccc_res res;

	if (!of_machine_is_compatible("samsung,j7velte"))
		return -ENODEV;
	arm_smccc_smc(SMC_CP_CTRL, CP_CTRL_READ, 0, REG_CP_CTRL_NS, 0, 0, 0, 0, &res);
	pr_info("j701f_modem_probe: SMC read CP_CTRL_NS: a0=%#lx a1=%#lx\n", res.a0, res.a1);
	if (!(res.a0 >> 32))
		decode("CP_CTRL_NS (secure monitor)", res.a0);
	arm_smccc_smc(SMC_CP_CTRL, CP_CTRL_READ, 0, REG_CP_CTRL_S, 0, 0, 0, 0, &res);
	pr_info("j701f_modem_probe: SMC read CP_CTRL_S: a0=%#lx a1=%#lx\n", res.a0, res.a1);
	if (!(res.a0 >> 32))
		decode("CP_CTRL_S (secure monitor)", res.a0);
	/* On purpose: a look, nothing to keep loaded. */
	return -ENODEV;
}
module_init(j701f_modem_probe_init);

MODULE_DESCRIPTION("J701F: read-only look at the modem's power and reset state");
MODULE_LICENSE("GPL");
