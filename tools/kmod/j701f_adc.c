// SPDX-License-Identifier: GPL-2.0-only
/*
 * Battery and board temperature of the SM-J701F from the SoC's ADC.
 *
 * Written by Claude 2026-10-13 for the J701F project. The conversion sequence
 * and register offsets follow the "exynos-adc-v3" variant in the vendor 3.18
 * drivers/iio/adc/exynos_adc.c (Samsung Electronics, GPL-2.0), polled instead
 * of interrupt driven; the thermistor tables are the factory device tree's
 * (j701f-adc-tables.h). Not an upstream driver.
 *
 * The mainline exynos7870.dtsi has no ADC node. To avoid a new BOOT image the
 * module applies a small device-tree overlay (j701f-adc-overlay.dtso) that
 * adds one, and binds to it itself. Result: a hwmon device "j701f_adc" with
 *   temp1 "battery" - ADC channel 1, the battery pack's thermistor,
 *   temp2 "board"   - ADC channel 0, the vendor's "AP" thermistor.
 * Each reading is the median of three conversions.
 *
 * No module_exit: the overlay stays until the next boot.
 */
#include <linux/clk.h>
#include <linux/hwmon.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include "adc-overlay-blob.h"
#include "j701f-adc-tables.h"

#define ADC_CON1		0x00
#define  CON1_SOFT_RESET	BIT(2)
#define  CON1_SOFT_NON_RESET	BIT(1)
#define  CON1_START		BIT(0)
#define ADC_CON2		0x04
#define  CON2_C_TIME(x)		(((x) & 7) << 4)
#define ADC_DAT			0x08
#define  DAT_FLAG		BIT(31)
#define  DAT_MASK		0xfff
#define ADC_INT_EN		0x10
#define ADC_INT_ST		0x14

#define CH_BOARD		0
#define CH_BATTERY		1

struct j701f_adc {
	void __iomem *regs;
	struct mutex lock;
};

static int overlay_id;
module_param(overlay_id, int, 0400);
static int result = -EAGAIN;
module_param(result, int, 0400);

static int j701f_adc_convert(struct j701f_adc *adc, unsigned int ch)
{
	u32 v;
	int ret;

	writel(CON1_SOFT_RESET, adc->regs + ADC_CON1);
	writel(CON1_SOFT_NON_RESET, adc->regs + ADC_CON1);
	writel(0, adc->regs + ADC_INT_EN);
	writel(CON2_C_TIME(6) | ch, adc->regs + ADC_CON2);
	writel(readl(adc->regs + ADC_CON1) | CON1_START, adc->regs + ADC_CON1);
	ret = readl_poll_timeout(adc->regs + ADC_DAT, v, v & DAT_FLAG, 200, 100000);
	writel(1, adc->regs + ADC_INT_ST);
	writel(ch, adc->regs + ADC_CON2);	/* vendor's exit: conversion time field cleared */
	return ret ? ret : (v & DAT_MASK);
}

static int j701f_adc_median(struct j701f_adc *adc, unsigned int ch)
{
	int v[3], i;

	mutex_lock(&adc->lock);
	for (i = 0; i < 3; i++) {
		v[i] = j701f_adc_convert(adc, ch);
		if (v[i] < 0)
			break;
	}
	mutex_unlock(&adc->lock);
	if (i < 3)
		return v[i];
	if (v[0] > v[1])
		swap(v[0], v[1]);
	if (v[1] > v[2])
		swap(v[1], v[2]);
	if (v[0] > v[1])
		swap(v[0], v[1]);
	return v[1];
}

/* Linear interpolation in a { reading, 0.1 degC } table; result in millidegrees. */
static long j701f_adc_lookup(const s16 (*tab)[2], int n, int raw)
{
	int i;

	if (raw <= tab[0][0])
		return tab[0][1] * 100L;
	for (i = 1; i < n; i++) {
		if (raw <= tab[i][0])
			return tab[i - 1][1] * 100L +
			       (long)(tab[i][1] - tab[i - 1][1]) * 100 *
			       (raw - tab[i - 1][0]) / (tab[i][0] - tab[i - 1][0]);
	}
	return tab[n - 1][1] * 100L;
}

static umode_t j701f_adc_visible(const void *data, enum hwmon_sensor_types type,
				 u32 attr, int channel)
{
	return 0444;
}

static int j701f_adc_read(struct device *dev, enum hwmon_sensor_types type,
			  u32 attr, int channel, long *val)
{
	struct j701f_adc *adc = dev_get_drvdata(dev);
	int raw;

	if (type != hwmon_temp || attr != hwmon_temp_input)
		return -EOPNOTSUPP;
	raw = j701f_adc_median(adc, channel ? CH_BOARD : CH_BATTERY);
	if (raw < 0)
		return raw;
	if (channel)
		*val = j701f_adc_lookup(j701f_board_table, ARRAY_SIZE(j701f_board_table), raw);
	else
		*val = j701f_adc_lookup(j701f_batt_table, ARRAY_SIZE(j701f_batt_table), raw);
	return 0;
}

static int j701f_adc_read_string(struct device *dev, enum hwmon_sensor_types type,
				 u32 attr, int channel, const char **str)
{
	*str = channel ? "board" : "battery";
	return 0;
}

static const struct hwmon_ops j701f_adc_hwmon_ops = {
	.is_visible = j701f_adc_visible,
	.read = j701f_adc_read,
	.read_string = j701f_adc_read_string,
};

static const struct hwmon_channel_info * const j701f_adc_hwmon_info[] = {
	HWMON_CHANNEL_INFO(temp, HWMON_T_INPUT | HWMON_T_LABEL,
			   HWMON_T_INPUT | HWMON_T_LABEL),
	NULL
};

static const struct hwmon_chip_info j701f_adc_chip = {
	.ops = &j701f_adc_hwmon_ops,
	.info = j701f_adc_hwmon_info,
};

static int j701f_adc_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct j701f_adc *adc;
	struct device *hwmon;
	struct clk *clk;
	int raw;

	adc = devm_kzalloc(dev, sizeof(*adc), GFP_KERNEL);
	if (!adc)
		return -ENOMEM;
	mutex_init(&adc->lock);
	adc->regs = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(adc->regs))
		return PTR_ERR(adc->regs);
	clk = devm_clk_get_enabled(dev, "adc");
	if (IS_ERR(clk))
		return dev_err_probe(dev, PTR_ERR(clk), "bus clock\n");
	clk = devm_clk_get_enabled(dev, "osc");
	if (IS_ERR(clk))
		return dev_err_probe(dev, PTR_ERR(clk), "conversion clock\n");
	raw = j701f_adc_median(adc, CH_BATTERY);
	if (raw < 0)
		return dev_err_probe(dev, raw, "no conversion result\n");
	hwmon = devm_hwmon_device_register_with_info(dev, "j701f_adc", adc,
						     &j701f_adc_chip, NULL);
	if (IS_ERR(hwmon))
		return PTR_ERR(hwmon);
	dev_info(dev, "battery thermistor reads %d (%ld m°C)\n", raw,
		 j701f_adc_lookup(j701f_batt_table, ARRAY_SIZE(j701f_batt_table), raw));
	return 0;
}

static const struct of_device_id j701f_adc_of_match[] = {
	{ .compatible = "j701f,exynos7870-adc" },
	{ }
};

static struct platform_driver j701f_adc_driver = {
	.probe = j701f_adc_probe,
	.driver = {
		.name = "j701f-adc",
		.of_match_table = j701f_adc_of_match,
		.suppress_bind_attrs = true,
	},
};

static int __init j701f_adc_init(void)
{
	struct device_node *np;
	int ret;

	if (!of_machine_is_compatible("samsung,j7velte"))
		return -ENODEV;
	np = of_find_node_by_path("/soc@0/adc@10550000");
	if (np) {
		of_node_put(np);
		return -EEXIST;
	}
	ret = platform_driver_register(&j701f_adc_driver);
	if (ret)
		return ret;
	/* Whatever the result, stay loaded: a changeset must not be freed under its users. */
	result = of_overlay_fdt_apply(adc_overlay_blob, sizeof(adc_overlay_blob),
				      &overlay_id, NULL);
	pr_info("j701f_adc: overlay result=%d id=%d\n", result, overlay_id);
	return 0;
}
module_init(j701f_adc_init);

MODULE_DESCRIPTION("J701F: battery and board temperature from the SoC ADC");
MODULE_LICENSE("GPL");
