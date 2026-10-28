// SPDX-License-Identifier: GPL-2.0-only
/*
 * J701F Shannon 315 first-stage state snapshot. Reads only; does not start CP.
 *
 * MBOX base and CP2AP indices are from the factory J701F DT. The register
 * offsets match Samsung's GPL mcu_ipc driver. CP power is read only through
 * the secure monitor: directly reading its secure PMU register caused an
 * external abort in the earlier prototype.
 */
#include <linux/arm-smccc.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/sizes.h>

#define MBOX_BASE		0x10500000
#define MBOX_INTSR0		0x14
#define MBOX_ISSR(n)		(0x80 + 4 * (n))
#define MBX_CP2AP_MSG		1
#define MBX_CP2AP_STATUS	5
#define MBX_CP2AP_ACTIVE	9

#define SMC_CP_CTRL		0x82000700
#define CP_CTRL_READ		3
#define REG_CP_CTRL_NS		1

static int __init j701f_modem_state_init(void)
{
	struct arm_smccc_res res;
	void __iomem *mbox;
	u32 pending, message, status, active;

	if (!of_machine_is_compatible("samsung,j7velte"))
		return -ENODEV;

	arm_smccc_smc(SMC_CP_CTRL, CP_CTRL_READ, 0, REG_CP_CTRL_NS,
		      0, 0, 0, 0, &res);
	pr_info("j701f_modem_state: CP_CTRL_NS via SMC: a0=%#lx a1=%#lx\n",
		res.a0, res.a1);

	mbox = ioremap(MBOX_BASE, SZ_4K);
	if (!mbox) {
		pr_err("j701f_modem_state: mailbox mapping failed\n");
		return -ENOMEM;
	}
	pending = readl(mbox + MBOX_INTSR0);
	message = readl(mbox + MBOX_ISSR(MBX_CP2AP_MSG));
	status = readl(mbox + MBOX_ISSR(MBX_CP2AP_STATUS));
	active = readl(mbox + MBOX_ISSR(MBX_CP2AP_ACTIVE));
	iounmap(mbox);
	pr_info("j701f_modem_state: MBOX pending=%#x cp_msg=%#x cp_status=%#x cp_active=%#x\n",
		pending, message, status, active);
	/* No handler, mapping or driver remains after the one-shot snapshot. */
	return -ENODEV;
}
module_init(j701f_modem_state_init);

MODULE_DESCRIPTION("J701F Shannon 315: one-shot read-only mailbox snapshot");
MODULE_LICENSE("GPL");
