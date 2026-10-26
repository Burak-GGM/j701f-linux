// SPDX-License-Identifier: GPL-2.0-only
/* One-shot RAM-only native-display experiment. BOOT stays on the known-good
 * simpledrm image. A separate userspace deadline and the hardware watchdog
 * MUST be armed first. Reboot is the teardown, not overlay removal: the DRM
 * graph retains node references whose lifetime must not be guessed at here.
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>

#include "display-overlay-blob.h"

static bool allow_apply;
module_param(allow_apply, bool, 0400);
MODULE_PARM_DESC(allow_apply, "Apply one-shot display overlay; requires armed reboot and stopped GUI");
static int overlay_id;
module_param(overlay_id, int, 0400);
static int result = -EAGAIN;
module_param(result, int, 0400);

static int __init j701f_overlay_init(void)
{
	struct device_node *decon, *dsi, *mmu, *fb;
	struct platform_device *pdev;
	struct property *iommu;
	int ret = -EINVAL;

	if (!allow_apply || !of_machine_is_compatible("samsung,j7velte") ||
	    IS_ENABLED(CONFIG_EXYNOS_IOMMU))
		return -EPERM;
	decon = of_find_node_by_path("/soc@0/display-controller@14830000");
	dsi = of_find_node_by_path("/soc@0/dsi@14800000");
	mmu = of_find_node_by_path("/soc@0/iommu@14860000");
	fb = of_find_node_by_path("/chosen/framebuffer@67000000");
	if (!decon || !dsi || !mmu || !fb || of_device_is_available(decon) ||
	    of_device_is_available(dsi))
		goto out;
	/* bl7 has no SysMMU driver; its DT status may be absent (implicit okay).
	 * Refuse a bound MMU nonetheless, before the overlay disables the node.
	 */
	pdev = of_find_device_by_node(mmu);
	if (pdev) {
		bool bound = pdev->dev.driver != NULL;

		platform_device_put(pdev);
		if (bound) {
			ret = -EBUSY;
			goto out;
		}
	}
	/* Refuse to take away a firmware DRM device still bound to its driver. */
	pdev = of_find_device_by_node(fb);
	if (pdev) {
		bool bound = pdev->dev.driver != NULL;

		platform_device_put(pdev);
		if (bound) {
			ret = -EBUSY;
			goto out;
		}
	}
	iommu = of_find_property(decon, "iommus", NULL);
	if (iommu) {
		ret = of_remove_property(decon, iommu);
		if (ret)
			goto out;
	}
	/* Even an apply error may leave a partial changeset. Keep the module
	 * resident and report the result; the already armed reboot clears it.
	 */
	result = of_overlay_fdt_apply(display_overlay_blob,
				      sizeof(display_overlay_blob), &overlay_id, NULL);
	pr_info("J701F_DISPLAY_OVERLAY result=%d id=%d; reboot required\n",
		result, overlay_id);
	ret = 0;
out:
	of_node_put(fb);
	of_node_put(mmu);
	of_node_put(dsi);
	of_node_put(decon);
	return ret;
}
module_init(j701f_overlay_init);
/* Deliberately no module_exit: never free an active display graph in place. */
MODULE_DESCRIPTION("One-shot J701F native-display DT overlay; reboot to restore");
MODULE_LICENSE("GPL v2");
