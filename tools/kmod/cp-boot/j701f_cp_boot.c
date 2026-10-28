// SPDX-License-Identifier: GPL-2.0-only
/*
 * J701F Shannon 315 modem (CP) boot, stage A: load and verify only.
 *
 * Written by Claude 2026-10-28 for the J701F project. Not an upstream driver.
 * The order follows Samsung's GPL modem_v1 driver (build/kernel/
 * vendor-modem-reference/): the boot daemon copies the RADIO partition's BOOT
 * image to the start of the CP's reserved memory and MAIN 0x10000 after it
 * (shmem_xmit_boot), then asks the secure monitor to check and accept them
 * (shmem_security_request: crypto-engine clock on, SMC 0x82000700 mode 0 with
 * the two sizes, clock off). Only after that is the CP powered and released.
 *
 * This stage stops after the security request and reports what the secure
 * monitor answered. It does not power, release or reset the CP, does not touch
 * the mailbox or the IPC area, and never reads or writes EFS or a partition:
 * the two images come through the firmware loader, from copies in RAM.
 *
 *   firmware j701f-cp/boot.bin   BOOT (RADIO TOC: 0x170c bytes for CP 0x40000000)
 *   firmware j701f-cp/main.bin   MAIN (RADIO TOC: 0x0250677c bytes for 0x40010000)
 *
 * Stage 0 refuses to stay loaded. Stage 1 stays loaded (unload it with rmmod):
 * busybox insmod loads a module a second time when the first load fails, and
 * a second copy and security request into memory the secure world may by then
 * have protected must not happen.
 */
#include <linux/arm-smccc.h>
#include <linux/firmware.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/sizes.h>

#define CP_MEM_BASE		0xb0000000	/* "modem-if" reserved, no-map */
#define CP_MEM_SIZE		0x07800000
#define CP_MAIN_OFFSET		0x10000		/* CP 0x40010000 - 0x40000000 */
#define CP_IPC_OFFSET		0x07400000	/* 4 MiB IPC area: left alone */

#define SMC_CP			0x82000700
#define  CP_BOOT_MODE_NORMAL	0
#define  CP_CTRL_READ		3
#define  REG_CP_CTRL_NS		1
#define SMC_SSS_CLK		0x82001011	/* modem_v1.h: SMC_ID_CLK */
#define  SSS_CLK_ENABLE		0
#define  SSS_CLK_DISABLE	1

static int stage;
module_param(stage, int, 0400);
MODULE_PARM_DESC(stage, "0 = check the images and the memory only, 1 = also copy and request verification");

static unsigned long cp_ctrl(void)
{
	struct arm_smccc_res res;

	arm_smccc_smc(SMC_CP, CP_CTRL_READ, 0, REG_CP_CTRL_NS, 0, 0, 0, 0, &res);
	return res.a0;
}

static int __init j701f_cp_boot_init(void)
{
	struct platform_device *pdev;
	const struct firmware *boot = NULL, *main = NULL;
	struct arm_smccc_res res;
	void __iomem *cp;
	int ret;

	if (!of_machine_is_compatible("samsung,j7velte"))
		return -ENODEV;
	pdev = platform_device_register_simple("j701f-cp-boot", -1, NULL, 0);
	if (IS_ERR(pdev))
		return PTR_ERR(pdev);
	ret = request_firmware(&boot, "j701f-cp/boot.bin", &pdev->dev);
	if (!ret)
		ret = request_firmware(&main, "j701f-cp/main.bin", &pdev->dev);
	if (ret) {
		pr_err("j701f_cp_boot: images not found: %d\n", ret);
		goto out;
	}
	pr_info("j701f_cp_boot: BOOT %zu bytes, MAIN %zu bytes, CP_CTRL %#lx\n",
		boot->size, main->size, cp_ctrl());
	if (!boot->size || boot->size > CP_MAIN_OFFSET ||
	    !main->size || main->size > CP_IPC_OFFSET - CP_MAIN_OFFSET) {
		pr_err("j701f_cp_boot: image sizes do not fit the CP memory layout\n");
		ret = -EINVAL;
		goto out;
	}
	cp = ioremap_wc(CP_MEM_BASE, CP_IPC_OFFSET);
	if (!cp) {
		ret = -ENOMEM;
		goto out;
	}
	pr_info("j701f_cp_boot: CP memory before: %08x %08x at BOOT, %08x %08x at MAIN\n",
		readl(cp), readl(cp + 4), readl(cp + CP_MAIN_OFFSET), readl(cp + CP_MAIN_OFFSET + 4));
	if (stage < 1) {
		iounmap(cp);
		pr_info("j701f_cp_boot: stage 0: nothing written\n");
		goto out;
	}
	memcpy_toio(cp, boot->data, boot->size);
	memcpy_toio(cp + CP_MAIN_OFFSET, main->data, main->size);
	wmb();
	pr_info("j701f_cp_boot: copied; CP memory now %08x %08x at BOOT, %08x %08x at MAIN\n",
		readl(cp), readl(cp + 4), readl(cp + CP_MAIN_OFFSET), readl(cp + CP_MAIN_OFFSET + 4));
	/* After the request the secure world may protect this memory: no more access. */
	iounmap(cp);

	arm_smccc_smc(SMC_SSS_CLK, SSS_CLK_ENABLE, 0, 0, 0, 0, 0, 0, &res);
	pr_info("j701f_cp_boot: crypto clock on: %#lx\n", res.a0);
	arm_smccc_smc(SMC_CP, CP_BOOT_MODE_NORMAL, boot->size, main->size, 0, 0, 0, 0, &res);
	pr_info("j701f_cp_boot: security request (mode 0, %zu, %zu): a0=%#lx a1=%#lx\n",
		boot->size, main->size, res.a0, res.a1);
	arm_smccc_smc(SMC_SSS_CLK, SSS_CLK_DISABLE, 0, 0, 0, 0, 0, 0, &res);
	pr_info("j701f_cp_boot: crypto clock off: %#lx; CP_CTRL %#lx\n", res.a0, cp_ctrl());
out:
	release_firmware(main);
	release_firmware(boot);
	platform_device_unregister(pdev);
	if (ret)
		return ret;
	return stage < 1 ? -ENODEV : 0;
}
module_init(j701f_cp_boot_init);

static void __exit j701f_cp_boot_exit(void)
{
}
module_exit(j701f_cp_boot_exit);

MODULE_DESCRIPTION("J701F: load the CP's BOOT and MAIN images and ask the secure monitor to verify them");
MODULE_LICENSE("GPL");
