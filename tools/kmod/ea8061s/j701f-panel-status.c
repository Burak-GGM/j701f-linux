// SPDX-License-Identifier: GPL-2.0-only
/* One-shot DCS GET_POWER_MODE read while an explicit KMS test holds the panel
 * enabled. No writes, no reset, no factory-calibration or arbitrary commands.
 */
#include <linux/module.h>
#include <linux/of.h>

#include <drm/drm_mipi_dsi.h>

static bool allow_read;
module_param(allow_read, bool, 0400);
static int power_mode = -1;
module_param(power_mode, int, 0400);
static int result = -EAGAIN;
module_param(result, int, 0400);

static int __init j701f_status_init(void)
{
	struct device_node *np;
	struct mipi_dsi_device *dsi;
	u8 mode = 0;

	if (!allow_read || !of_machine_is_compatible("samsung,j7velte"))
		return -EPERM;
	np = of_find_node_by_path("/soc@0/dsi@14800000/panel@0");
	if (!np)
		return -ENODEV;
	dsi = of_find_mipi_dsi_device_by_node(np);
	of_node_put(np);
	if (!dsi)
		return -ENODEV;
	result = mipi_dsi_dcs_get_power_mode(dsi, &mode);
	if (!result)
		power_mode = mode;
	pr_info("J701F_PANEL_DCS_POWER_MODE result=%d value=0x%02x\n", result, mode);
	put_device(&dsi->dev);
	return 0;
}

static void __exit j701f_status_exit(void)
{
}
module_init(j701f_status_init);
module_exit(j701f_status_exit);
MODULE_DESCRIPTION("J701F one-shot standard DCS power-mode read; no panel writes");
MODULE_LICENSE("GPL v2");
