// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-10 (J701F, goal: a working camera). Second
 * milestone: one raw frame from the rear sensor, without any V4L2 plumbing.
 *
 * On load: power the Samsung S5K3L2 in the vendor's order, write the vendor's
 * initial tables and the 2072x1552 30 fps mode, point the DMA output of the
 * CSI-2 receiver (CSIS v4.1 at 0x14420000) at one contiguous buffer, start the
 * sensor, wait for frames, stop everything and switch the sensor off again.
 * The buffer is then readable as /sys/kernel/debug/j701f_cam/frame and what
 * the receiver reported as .../status. Nothing stays powered.
 *
 * Needs the CAM0 power domain on (unload j701f_cam0_off first) and the clocks
 * of the block as the boot loader left them (cmu_isp is disabled in our tree).
 *
 * Register map, field positions and the order of the receiver's set-up follow
 * the vendor fimc-is-hw-csi-v4_0.[ch] and fimc-is-device-csi_v2.c; sensor
 * tables are machine-converted (s5k3l2-tables.h). All from
 * build/kernel/vendor-camera-reference/ (Samsung, GPL-2.0).
 */
#include <linux/bitfield.h>
#include <linux/clk.h>
#include <linux/debugfs.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/phy/phy.h>
#include <linux/regulator/consumer.h>

struct cam_reg {
	u16 addr;
	u16 val;
	u8 len;
};
#include "s5k3l2-tables.h"
#include "s5k5e3-tables.h"

/* One per sensor; chosen by the node's compatible. */
struct cam_cfg {
	const char *name;
	u32 csis_base;			/* its CSI-2 receiver */
	unsigned int rx_mux;		/* cmu_isp multiplexer of that receiver's byte clock */
	unsigned int lanes, settle;	/* vendor FIMC_IS_SENSOR_CFG of the mode */
	unsigned int width, height;
	/* Buffer: more than the mode needs at 12 bits per pixel. A buffer for a sensor's
	 * largest mode could not be allocated, so the receiver is only started after
	 * the sensor has confirmed this mode's output size - its DMA must not run past
	 * the buffer into other memory. */
	unsigned int buf_bytes;
	/* Bit of the CAM0 system register (0x144f1040) that the vendor PHY driver sets
	 * for this receiver ("option" in the vendor device tree, phy_set() in its CSI
	 * code); the mainline PHY driver knows the reset bits there but not this one. */
	u32 sysreg_option;
	bool s5k3l2_init;		/* reset, patch and analogue tables before the mode */
	const struct cam_reg *mode;
	unsigned int mode_len;
};

#define CSIS_SIZE	0x2000
#define CSIS_VERSION	0x0000
#define CSIS_CMN_CTRL	0x0004
#define  CMN_UPDATE_SHADOW	GENMASK(19, 16)
#define  CMN_LANE_NUMBER	GENMASK(9, 8)
#define  CMN_SW_RESET		BIT(1)
#define  CMN_CSI_EN		BIT(0)
#define CSIS_INT_MSK0	0x0010
#define CSIS_INT_SRC0	0x0014
#define CSIS_INT_MSK1	0x0018
#define CSIS_INT_SRC1	0x001c
#define CSIS_DPHY_STATUS	0x0020
#define CSIS_DPHY_CMN_CTRL	0x0024
#define  DPHY_HSSETTLE		GENMASK(31, 24)
#define  DPHY_ENABLE_DAT	GENMASK(4, 1)
#define  DPHY_ENABLE_CLK	BIT(0)
#define CSIS_ISP_CONFIG_CH0	0x0040
#define  ISP_DATAFORMAT		GENMASK(7, 2)
#define CSIS_ISP_RESOL_CH0	0x0044
#define CSIS_FRM_CNT_CH0	0x0100
#define CSIS_DMA0_CTRL	0x1000
#define  DMA_UPDT_PTR_EN	BIT(1)
#define  DMA_DISABLE		BIT(0)
#define CSIS_DMA0_FMT	0x1004
#define  DMA_PACK12		BIT(14)
#define CSIS_DMA0_ADDR1	0x1010
#define CSIS_DMA0_BYTE_CNT	0x1040
#define HW_FORMAT_RAW10	0x2b

/* The SysMMU in front of the camera block: as with the video decoder it may
 * come out of reset enabled with no page table; CTRL = 0 lets addresses pass. */
/* The block's clock controller (cmu_isp) is not driven by a driver in our tree.
 * As the boot loader leaves it, every "user" multiplexer selects the 26 MHz
 * oscillator (registers read 0x00200000): the receiver then samples the lanes
 * with the wrong clock - the first attempt saw frames with CRC, ECC and lost
 * frame-start errors. Bit 12 selects the real source. */
#define CMU_ISP_BASE	0x144d0000
#define CMU_ISP_MUX_CAM_USER		0x214
#define CMU_ISP_MUX_ISP_USER		0x218
#define CMU_ISP_MUX_RXBYTECLKHS0_S0	0x230
#define CMU_ISP_MUX_RXBYTECLKHS0_S1	0x234
#define  CMU_MUX_USER			BIT(12)

#define CAM0_SYSREG	0x144f1040
#define SYSMMU_BASE	0x14470000
#define SYSMMU_CTRL	0x000
#define SYSMMU_STATUS	0x008

static const struct cam_cfg rear_cfg = {
	.name = "rear", .csis_base = 0x14420000, .rx_mux = CMU_ISP_MUX_RXBYTECLKHS0_S0,
	.lanes = 4, .settle = 30, .width = 2072, .height = 1552, .buf_bytes = 6 << 20,
	.s5k3l2_init = true,
	.mode = s5k3l2_mode_2072x1552_30fps, .mode_len = ARRAY_SIZE(s5k3l2_mode_2072x1552_30fps),
};

static const struct cam_cfg front_cfg = {
	.name = "front", .csis_base = 0x14460000, .rx_mux = CMU_ISP_MUX_RXBYTECLKHS0_S1,
	.lanes = 2, .settle = 19, .width = 1280, .height = 960, .buf_bytes = 3 << 20,
	/* vendor option bit 3; without it the sensor streamed (its frame counter ran)
	 * and the second receiver saw no lane activity at all */
	.sysreg_option = BIT(3),
	.mode = s5k5e3_mode_1280x960_30fps, .mode_len = ARRAY_SIZE(s5k5e3_mode_1280x960_30fps),
};

struct cam_state {
	const struct cam_cfg *cfg;
	struct device *dev;
	struct dentry *dir;
	struct debugfs_blob_wrapper frame_blob, status_blob;
	void *frame_cpu;
	dma_addr_t frame_dma;
	char status_text[1280];
};

static struct dentry *dbg_root;

/* Exposure in lines (0: what the mode table sets) and analogue gain in the
 * sensors' units (0x20 = 1x), written to the standard registers 0x0202 and
 * 0x0204 after the mode table. The tables alone give an almost black picture
 * indoors. */
static unsigned int exposure_lines;
static unsigned int analog_gain;
module_param(exposure_lines, uint, 0444);
module_param(analog_gain, uint, 0444);
/* "rear" (default) or "front": the sensor to capture from */
static char *only = "rear";
module_param(only, charp, 0444);

/* 0: the receiver's other DMA layout, to see what it is */
static bool pack12 = true;
module_param(pack12, bool, 0444);

static int cam_write(struct i2c_client *i2c, u16 reg, u16 val, unsigned int len)
{
	u8 buf[4] = { reg >> 8, reg & 0xff, len == 2 ? val >> 8 : val & 0xff, val & 0xff };
	int ret = i2c_master_send(i2c, buf, 2 + len);

	return ret == 2 + len ? 0 : ret < 0 ? ret : -EIO;
}

static int cam_write_table(struct i2c_client *i2c, const struct cam_reg *t, unsigned int n)
{
	unsigned int i;
	int ret;

	for (i = 0; i < n; i++) {
		ret = cam_write(i2c, t[i].addr, t[i].val, t[i].len);
		if (ret)
			return ret;
	}
	return 0;
}

static int cam_write_burst(struct i2c_client *i2c, const u16 *words, unsigned int n)
{
	u8 buf[2 + 2 * 32];
	unsigned int i, chunk;
	int ret;

	while (n) {
		chunk = min(n, 32U);
		buf[0] = 0x6f;
		buf[1] = 0x12;
		for (i = 0; i < chunk; i++) {
			buf[2 + 2 * i] = words[i] >> 8;
			buf[3 + 2 * i] = words[i] & 0xff;
		}
		ret = i2c_master_send(i2c, buf, 2 + 2 * chunk);
		if (ret != 2 + 2 * chunk)
			return ret < 0 ? ret : -EIO;
		words += chunk;
		n -= chunk;
	}
	return 0;
}

static int cam_read16(struct i2c_client *i2c, u16 reg, u16 *val)
{
	u8 addr[2] = { reg >> 8, reg & 0xff }, buf[2];
	struct i2c_msg msgs[2] = {
		{ .addr = i2c->addr, .len = 2, .buf = addr },
		{ .addr = i2c->addr, .flags = I2C_M_RD, .len = 2, .buf = buf },
	};
	int ret = i2c_transfer(i2c->adapter, msgs, 2);

	if (ret != 2)
		return ret < 0 ? ret : -EIO;
	*val = buf[0] << 8 | buf[1];
	return 0;
}

static int sensor_setup(struct i2c_client *i2c, const struct cam_cfg *cfg)
{
	int ret = 0;

	if (cfg->s5k3l2_init) {
		/* vendor sensor_3l2_cis_init: page select, software reset, 3 ms */
		ret = cam_write(i2c, 0xfcfc, 0xd000, 2);
		if (!ret)
			ret = cam_write(i2c, 0x6010, 0x0001, 2);
		if (ret)
			return ret;
		usleep_range(3000, 3500);
		ret = cam_write_table(i2c, s5k3l2_initial_reset, ARRAY_SIZE(s5k3l2_initial_reset));
		if (!ret)
			ret = cam_write_burst(i2c, s5k3l2_initial_burst,
					      ARRAY_SIZE(s5k3l2_initial_burst));
		if (!ret)
			ret = cam_write_table(i2c, s5k3l2_initial_other,
					      ARRAY_SIZE(s5k3l2_initial_other));
	}
	if (!ret)
		ret = cam_write_table(i2c, cfg->mode, cfg->mode_len);
	if (!ret && exposure_lines)
		ret = cam_write(i2c, 0x0202, exposure_lines, 2);
	if (!ret && analog_gain)
		ret = cam_write(i2c, 0x0204, analog_gain, 2);
	return ret;
}

static void csis_setup(void __iomem *csis, const struct cam_cfg *cfg, u32 dma)
{
	unsigned int i;
	u32 val;

	/* reset; the bit clears itself */
	writel(readl(csis + CSIS_CMN_CTRL) | CMN_SW_RESET, csis + CSIS_CMN_CTRL);
	for (i = 0; i < 10 && (readl(csis + CSIS_CMN_CTRL) & CMN_SW_RESET); i++)
		udelay(10);
	writel(readl(csis + CSIS_DMA0_CTRL) | DMA_DISABLE, csis + CSIS_DMA0_CTRL);

	val = readl(csis + CSIS_DPHY_CMN_CTRL) & ~DPHY_HSSETTLE;
	writel(val | FIELD_PREP(DPHY_HSSETTLE, cfg->settle), csis + CSIS_DPHY_CMN_CTRL);
	val = readl(csis + CSIS_CMN_CTRL) & ~CMN_LANE_NUMBER;
	writel(val | FIELD_PREP(CMN_LANE_NUMBER, cfg->lanes - 1), csis + CSIS_CMN_CTRL);
	val = readl(csis + CSIS_DPHY_CMN_CTRL) & ~DPHY_ENABLE_DAT;
	writel(val | FIELD_PREP(DPHY_ENABLE_DAT, BIT(cfg->lanes) - 1), csis + CSIS_DPHY_CMN_CTRL);
	/* channel 0: virtual channel 0, RAW10, not parallel, no doubled clock (7870) */
	writel(FIELD_PREP(ISP_DATAFORMAT, HW_FORMAT_RAW10), csis + CSIS_ISP_CONFIG_CH0);
	writel(cfg->height << 16 | cfg->width, csis + CSIS_ISP_RESOL_CH0);
	/* no interrupt handler here: everything masked, sources are polled */
	writel(0, csis + CSIS_INT_MSK0);
	writel(0, csis + CSIS_INT_MSK1);
	/* DMA: two-dimensional, the vendor's packing for 10-bit Bayer */
	writel(pack12 ? DMA_PACK12 : 0, csis + CSIS_DMA0_FMT);
	for (i = 0; i < 8; i++)
		writel(dma, csis + CSIS_DMA0_ADDR1 + 4 * i);
	val = readl(csis + CSIS_DMA0_CTRL) & ~DMA_DISABLE;
	writel(val | DMA_UPDT_PTR_EN, csis + CSIS_DMA0_CTRL);
	/* enable: shadow update, clock lane, receiver */
	writel(readl(csis + CSIS_CMN_CTRL) | CMN_UPDATE_SHADOW, csis + CSIS_CMN_CTRL);
	writel(readl(csis + CSIS_DPHY_CMN_CTRL) | DPHY_ENABLE_CLK, csis + CSIS_DPHY_CMN_CTRL);
	writel(readl(csis + CSIS_CMN_CTRL) | CMN_CSI_EN, csis + CSIS_CMN_CTRL);
}

static void csis_stop(void __iomem *csis)
{
	writel(readl(csis + CSIS_DMA0_CTRL) | DMA_DISABLE, csis + CSIS_DMA0_CTRL);
	writel(readl(csis + CSIS_DPHY_CMN_CTRL) & ~(DPHY_ENABLE_CLK | DPHY_ENABLE_DAT),
	       csis + CSIS_DPHY_CMN_CTRL);
	writel(readl(csis + CSIS_CMN_CTRL) & ~CMN_CSI_EN, csis + CSIS_CMN_CTRL);
}

static int cam_probe(struct i2c_client *i2c)
{
	struct device *dev = &i2c->dev;
	struct gpio_desc *reset, *dvdd, *afvdd;
	struct regulator *iovdd;
	const struct cam_cfg *cfg = of_device_get_match_data(&i2c->dev);
	const unsigned int user_mux[] = { CMU_ISP_MUX_CAM_USER, CMU_ISP_MUX_ISP_USER, cfg->rx_mux };
	struct cam_state *st;
	void __iomem *csis, *mmu, *cmu, *pmu;
	u32 phy_before = 0;
	struct clk *cam_clk, *isp_clk;
	u32 mux_before[ARRAY_SIZE(user_mux)];
	struct regulator *avdd;
	struct clk *mclk;
	struct phy *phy;
	u32 src0 = 0, src1 = 0, v, mmu_ctrl, mmu_status, frames = 0, bytes = 0, dphy = 0;
	u16 id = 0, fll = 0, llp = 0, out_w = 0, out_h = 0, fc1 = 0, fc2 = 0, mode_sel = 0;
	u32 dphy_ctrl = 0, dphy_seen = 0;
	bool size_ok;
	unsigned int i, nonzero = 0;
	int ret, sensor_ret = 0;

	if (strcmp(only, cfg->name))
		return -ENODEV;

	avdd = devm_regulator_get(dev, "avdd");
	if (IS_ERR(avdd))
		return dev_err_probe(dev, PTR_ERR(avdd), "no AVDD regulator\n");
	reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	dvdd = devm_gpiod_get(dev, "dvdd", GPIOD_OUT_LOW);
	/* The 1.8 V interface supply switch is shared by the two sensors: a fixed
	 * regulator in the device tree (requesting the GPIO from two devices, even
	 * "non-exclusively", ended in a kernel oops after a module reload). */
	iovdd = devm_regulator_get(dev, "iovdd");
	afvdd = devm_gpiod_get_optional(dev, "afvdd", GPIOD_OUT_LOW);
	if (IS_ERR(reset) || IS_ERR(dvdd) || IS_ERR(iovdd) || IS_ERR(afvdd))
		return dev_err_probe(dev, -ENODEV, "GPIOs: reset %d dvdd %d iovdd %d afvdd %d\n",
				     PTR_ERR_OR_ZERO(reset), PTR_ERR_OR_ZERO(dvdd),
				     PTR_ERR_OR_ZERO(iovdd), PTR_ERR_OR_ZERO(afvdd));
	mclk = devm_clk_get(dev, "mclk");
	if (IS_ERR(mclk))
		return dev_err_probe(dev, PTR_ERR(mclk), "no MCLK\n");
	phy = devm_phy_get(dev, "csis");
	if (IS_ERR(phy))
		return dev_err_probe(dev, PTR_ERR(phy), "no CSI D-PHY\n");
	st = devm_kzalloc(dev, sizeof(*st), GFP_KERNEL);
	if (!st)
		return -ENOMEM;
	st->cfg = cfg;
	st->dev = dev;
	i2c_set_clientdata(i2c, st);
	csis = devm_ioremap(dev, cfg->csis_base, CSIS_SIZE);
	mmu = devm_ioremap(dev, SYSMMU_BASE, 0x1000);
	cmu = devm_ioremap(dev, CMU_ISP_BASE, 0x1000);
	pmu = devm_ioremap(dev, CAM0_SYSREG, 4);
	if (!csis || !mmu || !cmu || !pmu)
		return -ENOMEM;
	cam_clk = devm_clk_get_optional_enabled(dev, "cam");
	isp_clk = devm_clk_get_optional_enabled(dev, "isp");
	if (IS_ERR(cam_clk) || IS_ERR(isp_clk))
		return dev_err_probe(dev, -ENODEV, "camera block clocks\n");

	/* an I2C client has no DMA mask of its own (first attempt: -EIO here) */
	if (!dev->dma_mask)
		dev->dma_mask = &dev->coherent_dma_mask;
	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(32));
	if (ret)
		return ret;
	st->frame_cpu = dma_alloc_coherent(dev, cfg->buf_bytes, &st->frame_dma, GFP_KERNEL);
	if (!st->frame_cpu)
		return dev_err_probe(dev, -ENOMEM, "no %u-byte contiguous buffer\n", cfg->buf_bytes);
	memset(st->frame_cpu, 0, cfg->buf_bytes);

	mmu_ctrl = readl(mmu + SYSMMU_CTRL);
	mmu_status = readl(mmu + SYSMMU_STATUS);
	if (mmu_ctrl & 1)
		writel(0, mmu + SYSMMU_CTRL);

	/* sensor power, as in j701f_cam_probe.c */
	ret = regulator_enable(avdd);
	if (ret)
		goto free;
	usleep_range(2000, 2500);
	gpiod_set_value_cansleep(dvdd, 1);
	gpiod_set_value_cansleep(afvdd, 1);
	usleep_range(9000, 9500);
	if (regulator_enable(iovdd))
		dev_warn(dev, "interface supply did not switch on\n");
	usleep_range(2000, 2500);
	clk_set_rate(mclk, 26000000);
	ret = clk_prepare_enable(mclk);
	if (ret)
		goto power_off;
	usleep_range(3000, 3500);
	gpiod_set_value_cansleep(reset, 0);
	usleep_range(10000, 11000);

	cam_read16(i2c, 0x0000, &id);
	sensor_ret = sensor_setup(i2c, cfg);
	cam_read16(i2c, 0x0340, &fll);
	cam_read16(i2c, 0x0342, &llp);

	cam_read16(i2c, 0x034c, &out_w);
	cam_read16(i2c, 0x034e, &out_h);
	size_ok = !sensor_ret && out_w == cfg->width && out_h == cfg->height;

	ret = phy_power_on(phy);
	if (ret)
		dev_warn(dev, "D-PHY power on: %d\n", ret);
	phy_before = readl(pmu);
	if (cfg->sysreg_option)
		writel(phy_before | cfg->sysreg_option, pmu);
	for (i = 0; i < ARRAY_SIZE(user_mux); i++) {
		mux_before[i] = readl(cmu + user_mux[i]);
		writel(mux_before[i] | CMU_MUX_USER, cmu + user_mux[i]);
	}
	usleep_range(1000, 1500);
	if (size_ok)
		csis_setup(csis, cfg, lower_32_bits(st->frame_dma));

	/* vendor stream on */
	if (size_ok) {
		cam_write(i2c, 0x6028, 0x4000, 2);
		cam_write(i2c, 0x0100, 0x01, 1);
		cam_write(i2c, 0x0216, 0x00, 1);
	}
	/* about half a second of frames; sources are write-1-to-clear */
	for (i = 0; i < 50; i++) {
		msleep(10);
		v = readl(csis + CSIS_INT_SRC0);
		writel(v, csis + CSIS_INT_SRC0);
		src0 |= v;
		v = readl(csis + CSIS_INT_SRC1);
		writel(v, csis + CSIS_INT_SRC1);
		src1 |= v;
		dphy_seen |= readl(csis + CSIS_DPHY_STATUS);
		if (i == 20) {
			dphy = readl(csis + CSIS_DPHY_STATUS);
			/* is the sensor itself producing frames? (frame counter, mode select) */
			cam_read16(i2c, 0x0004, &fc1);
		}
		if (i == 45) {
			cam_read16(i2c, 0x0004, &fc2);
			cam_read16(i2c, 0x0100, &mode_sel);
			dphy_ctrl = readl(csis + CSIS_DPHY_CMN_CTRL);
		}
	}
	frames = readl(csis + CSIS_FRM_CNT_CH0);
	bytes = readl(csis + CSIS_DMA0_BYTE_CNT);

	cam_write(i2c, 0x0100, 0x00, 1);
	msleep(40);
	csis_stop(csis);
	for (i = 0; i < ARRAY_SIZE(user_mux); i++)
		writel(mux_before[i], cmu + user_mux[i]);
	if (cfg->sysreg_option)
		writel(readl(pmu) & ~cfg->sysreg_option, pmu);
	phy_power_off(phy);
	gpiod_set_value_cansleep(reset, 1);
	clk_disable_unprepare(mclk);
power_off:
	regulator_disable(iovdd);
	gpiod_set_value_cansleep(afvdd, 0);
	gpiod_set_value_cansleep(dvdd, 0);
	regulator_disable(avdd);
	if (mmu_ctrl & 1)
		writel(mmu_ctrl, mmu + SYSMMU_CTRL);

	for (i = 0; i < cfg->buf_bytes; i += 4096)
		nonzero += !!memchr_inv(st->frame_cpu + i, 0, 64);
	snprintf(st->status_text, sizeof(st->status_text),
		 "sensor_id=%#06x sensor_tables=%d output=%ux%u (receiver started: %d) frame_length_lines=%u line_length_pck=%u\n"
		 "csis_version=%#010x int_src0=%#010x int_src1=%#010x dphy_status=%#x\n"
		 "frame_count=%u dma_byte_count=%u\n"
		 "sysmmu_ctrl_before=%#x sysmmu_status_before=%#x cam_clk=%lu isp_clk=%lu mux_before=%#x cam0_sysreg_with_phy_on=%#x\n"
		 "sensor_frame_counter=%#x then %#x mode_select=%#x dphy_ctrl=%#x dphy_status_seen=%#x\n"
		 "buffer_dma=%pad bytes=%u pages_with_data=%u of %u\n",
		 id, sensor_ret, out_w, out_h, size_ok, fll, llp, readl(csis + CSIS_VERSION), src0, src1, dphy,
		 frames, bytes, mmu_ctrl, mmu_status, cam_clk ? clk_get_rate(cam_clk) : 0,
		 isp_clk ? clk_get_rate(isp_clk) : 0, mux_before[0], phy_before,
		 fc1, fc2, mode_sel, dphy_ctrl, dphy_seen, &st->frame_dma, cfg->buf_bytes, nonzero,
		 cfg->buf_bytes / 4096);
	dev_info(dev, "%s capture attempt: frames=%u int0=%#x int1=%#x bytes=%u pages_with_data=%u\n",
		 cfg->name, frames, src0, src1, bytes, nonzero);

	st->frame_blob.data = st->frame_cpu;
	st->frame_blob.size = cfg->buf_bytes;
	st->status_blob.data = st->status_text;
	st->status_blob.size = strlen(st->status_text);
	st->dir = debugfs_create_dir(cfg->name, dbg_root);
	debugfs_create_blob("frame", 0400, st->dir, &st->frame_blob);
	debugfs_create_blob("status", 0444, st->dir, &st->status_blob);
	return 0;
free:
	dma_free_coherent(dev, cfg->buf_bytes, st->frame_cpu, st->frame_dma);
	st->frame_cpu = NULL;
	return ret;
}

static void cam_remove(struct i2c_client *i2c)
{
	struct cam_state *st = i2c_get_clientdata(i2c);

	debugfs_remove_recursive(st->dir);
	if (st->frame_cpu)
		dma_free_coherent(st->dev, st->cfg->buf_bytes, st->frame_cpu, st->frame_dma);
}

static const struct of_device_id cam_match[] = {
	{ .compatible = "j701f,s5k3l2-probe", .data = &rear_cfg },
	{ .compatible = "j701f,s5k5e3-frame", .data = &front_cfg },
	{ }
};
MODULE_DEVICE_TABLE(of, cam_match);

static struct i2c_driver cam_driver = {
	.driver = { .name = "j701f-cam-frame", .of_match_table = cam_match },
	.probe = cam_probe,
	.remove = cam_remove,
};

static int __init cam_init(void)
{
	dbg_root = debugfs_create_dir("j701f_cam", NULL);
	return i2c_add_driver(&cam_driver);
}

static void __exit cam_exit(void)
{
	i2c_del_driver(&cam_driver);
	debugfs_remove_recursive(dbg_root);
}
module_init(cam_init);
module_exit(cam_exit);

MODULE_DESCRIPTION("J701F: one raw frame from the rear camera sensor (test)");
MODULE_LICENSE("GPL");
