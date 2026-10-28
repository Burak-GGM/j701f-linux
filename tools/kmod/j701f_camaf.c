// SPDX-License-Identifier: GPL-2.0-only
/*
 * Rear camera focus motor bus of the SM-J701F.
 *
 * Written by Claude 2026-10-28 for the J701F project. Not an upstream driver.
 * The rear camera's DW9807 focus motor sits on hsi2c@138b0000 at 0x0c, a
 * controller the mainline device tree leaves disabled. This module applies
 * a small overlay (j701f-camaf-overlay.dtso) that enables it, so an I2C bus
 * appears for j701f_camera to set the lens position on. The motor only has
 * power while the rear camera streams (afvdd, switched by j701f_camera).
 *
 * No module_exit: the overlay stays until the next boot.
 */
#include <linux/module.h>
#include <linux/of.h>
#include "camaf-overlay-blob.h"

static int overlay_id;
module_param(overlay_id, int, 0400);
static int result = -EAGAIN;
module_param(result, int, 0400);

static int __init j701f_camaf_init(void)
{
	struct device_node *np;

	if (!of_machine_is_compatible("samsung,j7velte"))
		return -ENODEV;
	np = of_find_node_by_path("/soc@0/i2c@138b0000");
	if (!np)
		return -ENODEV;
	if (of_device_is_available(np)) {
		of_node_put(np);
		return -EEXIST;
	}
	of_node_put(np);
	/* Whatever the result, stay loaded: a changeset must not be freed under its users. */
	result = of_overlay_fdt_apply(camaf_overlay_blob, sizeof(camaf_overlay_blob),
				      &overlay_id, NULL);
	pr_info("j701f_camaf: overlay result=%d id=%d\n", result, overlay_id);
	return 0;
}
module_init(j701f_camaf_init);

MODULE_DESCRIPTION("J701F: enable the rear camera focus motor's I2C bus");
MODULE_LICENSE("GPL");
