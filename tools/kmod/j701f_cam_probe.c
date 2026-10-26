// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-10 (J701F, goal: a working camera). First
 * milestone only: power the rear camera sensor (Samsung S5K3L2) in the
 * vendor's order, read its model and revision registers, power it down again.
 * No image, no streaming, nothing left switched on.
 *
 * Order and delays from the vendor fimc-is-device-module-3l2.c
 * (build/kernel/vendor-camera-reference/, GPL-2.0): reset low, AVDD 2.8 V,
 * 2 ms, DVDD 1.2 V, AF 2.8 V, 9 ms, IO 1.8 V, 2 ms, MCLK, 3 ms, reset high.
 * Identity registers from fimc-is-cis-3l2.c: 0x0000 (16 bit) and 0x0002.
 *
 * Result: kernel log and /sys/module/j701f_cam_probe/parameters/.
 */
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>

static int result = -EINPROGRESS;	/* 0: both registers were read */
static unsigned int model_id, revision;
static unsigned long mclk_hz;
module_param(result, int, 0444);
module_param(model_id, uint, 0444);
module_param(revision, uint, 0444);
module_param(mclk_hz, ulong, 0444);

static int cam_read(struct i2c_client *i2c, u16 reg, u8 *buf, unsigned int len)
{
	u8 addr[2] = { reg >> 8, reg & 0xff };
	struct i2c_msg msgs[2] = {
		{ .addr = i2c->addr, .len = 2, .buf = addr },
		{ .addr = i2c->addr, .flags = I2C_M_RD, .len = len, .buf = buf },
	};
	int ret = i2c_transfer(i2c->adapter, msgs, 2);

	return ret == 2 ? 0 : ret < 0 ? ret : -EIO;
}

static int cam_probe(struct i2c_client *i2c)
{
	struct device *dev = &i2c->dev;
	struct gpio_desc *reset, *dvdd, *iovdd, *afvdd;
	struct regulator *avdd;
	struct clk *mclk;
	u8 buf[2];
	int ret;

	avdd = devm_regulator_get(dev, "avdd");
	if (IS_ERR(avdd))
		return dev_err_probe(dev, PTR_ERR(avdd), "no AVDD regulator\n");
	/* logical 1 = reset asserted (the line is active low) */
	reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(reset))
		return dev_err_probe(dev, PTR_ERR(reset), "no reset GPIO\n");
	dvdd = devm_gpiod_get(dev, "dvdd", GPIOD_OUT_LOW);
	if (IS_ERR(dvdd))
		return dev_err_probe(dev, PTR_ERR(dvdd), "no DVDD enable GPIO\n");
	iovdd = devm_gpiod_get(dev, "iovdd", GPIOD_OUT_LOW);
	if (IS_ERR(iovdd))
		return dev_err_probe(dev, PTR_ERR(iovdd), "no IO supply enable GPIO\n");
	afvdd = devm_gpiod_get_optional(dev, "afvdd", GPIOD_OUT_LOW);
	if (IS_ERR(afvdd))
		return dev_err_probe(dev, PTR_ERR(afvdd), "AF supply GPIO\n");
	mclk = devm_clk_get(dev, "mclk");
	if (IS_ERR(mclk))
		return dev_err_probe(dev, PTR_ERR(mclk), "no MCLK\n");

	ret = regulator_enable(avdd);
	if (ret)
		return dev_err_probe(dev, ret, "AVDD did not switch on\n");
	usleep_range(2000, 2500);
	gpiod_set_value_cansleep(dvdd, 1);
	gpiod_set_value_cansleep(afvdd, 1);
	usleep_range(9000, 9500);
	gpiod_set_value_cansleep(iovdd, 1);
	usleep_range(2000, 2500);
	ret = clk_set_rate(mclk, 26000000);
	if (ret)
		dev_warn(dev, "MCLK rate request failed: %d\n", ret);
	ret = clk_prepare_enable(mclk);
	if (ret) {
		dev_err(dev, "MCLK did not start: %d\n", ret);
		goto off;
	}
	mclk_hz = clk_get_rate(mclk);
	usleep_range(3000, 3500);
	gpiod_set_value_cansleep(reset, 0);
	usleep_range(10000, 11000);

	ret = cam_read(i2c, 0x0000, buf, 2);
	if (!ret) {
		model_id = buf[0] << 8 | buf[1];
		ret = cam_read(i2c, 0x0002, buf, 1);
		if (!ret)
			revision = buf[0];
	}
	result = ret;
	if (ret)
		dev_err(dev, "sensor did not answer: %d (MCLK %lu Hz)\n", ret, mclk_hz);
	else
		dev_info(dev, "rear sensor answers: model %#06x revision %#04x (MCLK %lu Hz)\n",
			 model_id, revision, mclk_hz);

	gpiod_set_value_cansleep(reset, 1);
	clk_disable_unprepare(mclk);
off:
	gpiod_set_value_cansleep(iovdd, 0);
	gpiod_set_value_cansleep(afvdd, 0);
	gpiod_set_value_cansleep(dvdd, 0);
	regulator_disable(avdd);
	/* Stay bound either way: the answer is in the parameters and the log. */
	return 0;
}

static const struct of_device_id cam_match[] = {
	{ .compatible = "j701f,s5k3l2-probe" },
	{ }
};
MODULE_DEVICE_TABLE(of, cam_match);

static struct i2c_driver cam_driver = {
	.driver = { .name = "j701f-cam-probe", .of_match_table = cam_match },
	.probe = cam_probe,
};
module_i2c_driver(cam_driver);

MODULE_DESCRIPTION("J701F: power the rear camera sensor once and read its identity");
MODULE_LICENSE("GPL");
