// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-10 (J701F, goal: a working camera). Continuous
 * raw frames from one camera sensor, for the project's own camera service
 * (system/camera/j701f-camd.c), which turns them into pictures and into an
 * ordinary video device. Not a V4L2 driver.
 *
 *   /dev/j701f-cam-rear or /dev/j701f-cam-front   (module parameter only=)
 *     open     powers the sensor, programs the mode, starts the receiver
 *     read     waits for the next complete frame and returns it: 10-bit Bayer
 *              (GRBG), two samples in three bytes, little-endian 12-bit packing,
 *              (width rounded up to 16) * 1.5 bytes per line
 *     close    stops and powers everything down
 *   sysfs, next to the device: exposure_lines, analog_gain (0x20 = 1x), info
 *
 * The receiver's DMA alternates between two buffers; a small polling thread
 * notices each finished frame (the receiver's interrupt is not wired up in our
 * device tree). Everything about the sensors and the receiver is as in
 * j701f_cam_frame.c, where the findings are described; register map and order
 * from the vendor fimc-is sources (build/kernel/vendor-camera-reference/).
 */
#include <linux/bitfield.h>
#include <linux/clk.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/uaccess.h>
#include <linux/wait.h>
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

#define FRAME_MAGIC	0x4a373031	/* "J701": first bytes of a buffer not yet rewritten */

struct cam_state {
	const struct cam_cfg *cfg;
	struct device *dev;
	struct i2c_client *i2c;
	struct miscdevice misc;
	char name[24];
	struct mutex lock;		/* open/close and sensor writes */
	bool open;
	/* resources */
	struct gpio_desc *reset, *dvdd, *iovdd, *afvdd;
	struct regulator *avdd;
	struct clk *mclk;
	struct phy *phy;
	void __iomem *csis, *mmu, *cmu, *sysreg;
	u32 mux_before[3], mmu_ctrl;
	unsigned int user_mux[3];
	/* frames */
	void *buf[2];
	dma_addr_t dma[2];
	unsigned int frame_bytes;
	struct task_struct *poller;
	wait_queue_head_t wait;
	unsigned int seq;		/* complete frames so far */
	int ready;			/* buffer holding the newest complete frame, -1: none */
	u32 errors;			/* receiver error bits seen */
};

static unsigned int exposure_lines = 600;
static unsigned int analog_gain = 64;
module_param(exposure_lines, uint, 0444);
module_param(analog_gain, uint, 0444);
static char *only = "rear";
module_param(only, charp, 0444);

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
	if (!ret)
		ret = cam_write(i2c, 0x0202, exposure_lines, 2);
	if (!ret)
		ret = cam_write(i2c, 0x0204, analog_gain, 2);
	return ret;
}

static void csis_setup(void __iomem *csis, const struct cam_cfg *cfg, u32 dma, u32 dma2)
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
	writel(DMA_PACK12, csis + CSIS_DMA0_FMT);
	/* eight frame pointers that the receiver steps through: the two buffers in turn */
	for (i = 0; i < 8; i++)
		writel(i & 1 ? dma2 : dma, csis + CSIS_DMA0_ADDR1 + 4 * i);
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

static int cam_poll_thread(void *data)
{
	struct cam_state *st = data;
	int guess = 0;
	u32 v;

	while (!kthread_should_stop()) {
		usleep_range(1500, 2500);
		v = readl(st->csis + CSIS_INT_SRC0);
		if (v) {
			writel(v, st->csis + CSIS_INT_SRC0);
			st->errors |= v & 0x000fffff;
		}
		v = readl(st->csis + CSIS_INT_SRC1);
		if (!v)
			continue;
		writel(v, st->csis + CSIS_INT_SRC1);
		if (!(v & GENMASK(11, 8)))	/* DMA frame end */
			continue;
		/* The finished buffer is the one whose marker has been overwritten. */
		if (*(u32 *)st->buf[0] != FRAME_MAGIC && *(u32 *)st->buf[1] == FRAME_MAGIC)
			guess = 0;
		else if (*(u32 *)st->buf[1] != FRAME_MAGIC && *(u32 *)st->buf[0] == FRAME_MAGIC)
			guess = 1;
		else
			guess = !guess;		/* both or neither: assume strict alternation */
		*(u32 *)st->buf[guess] = FRAME_MAGIC;	/* costs the first two pixels of the frame */
		st->ready = guess;
		st->seq++;
		wake_up_interruptible(&st->wait);
	}
	return 0;
}

static int cam_start(struct cam_state *st)
{
	const struct cam_cfg *cfg = st->cfg;
	u16 out_w = 0, out_h = 0;
	unsigned int i;
	int ret;

	st->mmu_ctrl = readl(st->mmu + SYSMMU_CTRL);
	if (st->mmu_ctrl & 1)
		writel(0, st->mmu + SYSMMU_CTRL);
	ret = regulator_enable(st->avdd);
	if (ret)
		return ret;
	usleep_range(2000, 2500);
	gpiod_set_value_cansleep(st->dvdd, 1);
	gpiod_set_value_cansleep(st->afvdd, 1);
	usleep_range(9000, 9500);
	gpiod_set_value_cansleep(st->iovdd, 1);
	usleep_range(2000, 2500);
	clk_set_rate(st->mclk, 26000000);
	ret = clk_prepare_enable(st->mclk);
	if (ret)
		goto power_off;
	usleep_range(3000, 3500);
	gpiod_set_value_cansleep(st->reset, 0);
	usleep_range(10000, 11000);

	ret = sensor_setup(st->i2c, cfg);
	if (!ret)
		ret = cam_read16(st->i2c, 0x034c, &out_w);
	if (!ret)
		ret = cam_read16(st->i2c, 0x034e, &out_h);
	if (!ret && (out_w != cfg->width || out_h != cfg->height))
		ret = -EIO;	/* never start the DMA for a mode the buffers were not sized for */
	if (ret)
		goto clk_off;

	phy_power_on(st->phy);
	if (cfg->sysreg_option)
		writel(readl(st->sysreg) | cfg->sysreg_option, st->sysreg);
	for (i = 0; i < ARRAY_SIZE(st->user_mux); i++) {
		st->mux_before[i] = readl(st->cmu + st->user_mux[i]);
		writel(st->mux_before[i] | CMU_MUX_USER, st->cmu + st->user_mux[i]);
	}
	usleep_range(1000, 1500);
	*(u32 *)st->buf[0] = FRAME_MAGIC;
	*(u32 *)st->buf[1] = FRAME_MAGIC;
	st->ready = -1;
	st->seq = 0;
	st->errors = 0;
	csis_setup(st->csis, cfg, lower_32_bits(st->dma[0]), lower_32_bits(st->dma[1]));
	cam_write(st->i2c, 0x6028, 0x4000, 2);
	cam_write(st->i2c, 0x0100, 0x01, 1);
	cam_write(st->i2c, 0x0216, 0x00, 1);
	st->poller = kthread_run(cam_poll_thread, st, "%s", st->name);
	if (IS_ERR(st->poller)) {
		ret = PTR_ERR(st->poller);
		st->poller = NULL;
	}
	return ret;
clk_off:
	gpiod_set_value_cansleep(st->reset, 1);
	clk_disable_unprepare(st->mclk);
power_off:
	gpiod_set_value_cansleep(st->iovdd, 0);
	gpiod_set_value_cansleep(st->afvdd, 0);
	gpiod_set_value_cansleep(st->dvdd, 0);
	regulator_disable(st->avdd);
	if (st->mmu_ctrl & 1)
		writel(st->mmu_ctrl, st->mmu + SYSMMU_CTRL);
	return ret;
}

static void cam_stop(struct cam_state *st)
{
	unsigned int i;

	if (st->poller)
		kthread_stop(st->poller);
	st->poller = NULL;
	cam_write(st->i2c, 0x0100, 0x00, 1);
	msleep(40);
	csis_stop(st->csis);
	for (i = 0; i < ARRAY_SIZE(st->user_mux); i++)
		writel(st->mux_before[i], st->cmu + st->user_mux[i]);
	if (st->cfg->sysreg_option)
		writel(readl(st->sysreg) & ~st->cfg->sysreg_option, st->sysreg);
	phy_power_off(st->phy);
	gpiod_set_value_cansleep(st->reset, 1);
	clk_disable_unprepare(st->mclk);
	gpiod_set_value_cansleep(st->iovdd, 0);
	gpiod_set_value_cansleep(st->afvdd, 0);
	gpiod_set_value_cansleep(st->dvdd, 0);
	regulator_disable(st->avdd);
	if (st->mmu_ctrl & 1)
		writel(st->mmu_ctrl, st->mmu + SYSMMU_CTRL);
}

static struct cam_state *to_state(struct file *file)
{
	return container_of(file->private_data, struct cam_state, misc);
}

static int cam_open(struct inode *inode, struct file *file)
{
	struct cam_state *st = to_state(file);
	int ret = 0;

	mutex_lock(&st->lock);
	if (st->open)
		ret = -EBUSY;
	else
		ret = cam_start(st);
	if (!ret)
		st->open = true;
	mutex_unlock(&st->lock);
	return ret;
}

static int cam_release(struct inode *inode, struct file *file)
{
	struct cam_state *st = to_state(file);

	mutex_lock(&st->lock);
	cam_stop(st);
	st->open = false;
	mutex_unlock(&st->lock);
	return 0;
}

/* One read = one frame: waits for a frame newer than the last one this reader got. */
static ssize_t cam_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
	struct cam_state *st = to_state(file);
	unsigned int seen = (unsigned long)*pos;
	int ret;

	ret = wait_event_interruptible_timeout(st->wait, st->seq != seen && st->ready >= 0, 2 * HZ);
	if (ret < 0)
		return ret;
	if (!ret)
		return -ETIMEDOUT;
	count = min_t(size_t, count, st->frame_bytes);
	if (copy_to_user(buf, st->buf[st->ready], count))
		return -EFAULT;
	*pos = st->seq;
	return count;
}

static const struct file_operations cam_fops = {
	.owner = THIS_MODULE,
	.open = cam_open,
	.release = cam_release,
	.read = cam_read,
	.llseek = noop_llseek,
};

static ssize_t info_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct cam_state *st = container_of(dev_get_drvdata(dev), struct cam_state, misc);

	return sysfs_emit(buf, "%s %ux%u frame_bytes=%u frames=%u receiver_errors=%#x\n",
			  st->cfg->name, st->cfg->width, st->cfg->height, st->frame_bytes,
			  st->seq, st->errors);
}
static DEVICE_ATTR_RO(info);

static ssize_t reg_store(struct device *dev, const char *buf, size_t count, u16 reg,
			 unsigned int *keep)
{
	struct cam_state *st = container_of(dev_get_drvdata(dev), struct cam_state, misc);
	unsigned int val;
	int ret = kstrtouint(buf, 0, &val);

	if (ret || val > 0xffff)
		return -EINVAL;
	mutex_lock(&st->lock);
	*keep = val;
	if (st->open)
		ret = cam_write(st->i2c, reg, val, 2);
	mutex_unlock(&st->lock);
	return ret ? ret : count;
}

static ssize_t exposure_lines_store(struct device *dev, struct device_attribute *attr,
				    const char *buf, size_t count)
{
	return reg_store(dev, buf, count, 0x0202, &exposure_lines);
}
static ssize_t exposure_lines_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%u\n", exposure_lines);
}
static DEVICE_ATTR_RW(exposure_lines);

static ssize_t analog_gain_store(struct device *dev, struct device_attribute *attr,
				 const char *buf, size_t count)
{
	return reg_store(dev, buf, count, 0x0204, &analog_gain);
}
static ssize_t analog_gain_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%u\n", analog_gain);
}
static DEVICE_ATTR_RW(analog_gain);

static struct attribute *cam_attrs[] = {
	&dev_attr_info.attr, &dev_attr_exposure_lines.attr, &dev_attr_analog_gain.attr, NULL
};
ATTRIBUTE_GROUPS(cam);

static int cam_probe(struct i2c_client *i2c)
{
	const struct cam_cfg *cfg = of_device_get_match_data(&i2c->dev);
	struct device *dev = &i2c->dev;
	struct cam_state *st;
	int i, ret;

	if (strcmp(only, cfg->name))
		return -ENODEV;
	st = devm_kzalloc(dev, sizeof(*st), GFP_KERNEL);
	if (!st)
		return -ENOMEM;
	st->cfg = cfg;
	st->dev = dev;
	st->i2c = i2c;
	st->ready = -1;
	mutex_init(&st->lock);
	init_waitqueue_head(&st->wait);
	st->user_mux[0] = CMU_ISP_MUX_CAM_USER;
	st->user_mux[1] = CMU_ISP_MUX_ISP_USER;
	st->user_mux[2] = cfg->rx_mux;
	st->frame_bytes = (cfg->width + 15) / 16 * 16 * 3 / 2 * cfg->height;

	st->avdd = devm_regulator_get(dev, "avdd");
	st->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	st->dvdd = devm_gpiod_get(dev, "dvdd", GPIOD_OUT_LOW);
	st->iovdd = devm_gpiod_get(dev, "iovdd", GPIOD_OUT_LOW);
	st->afvdd = devm_gpiod_get_optional(dev, "afvdd", GPIOD_OUT_LOW);
	st->mclk = devm_clk_get(dev, "mclk");
	st->phy = devm_phy_get(dev, "csis");
	if (IS_ERR(st->avdd) || IS_ERR(st->reset) || IS_ERR(st->dvdd) || IS_ERR(st->iovdd) ||
	    IS_ERR(st->afvdd) || IS_ERR(st->mclk) || IS_ERR(st->phy))
		return dev_err_probe(dev, -ENODEV, "a supply, GPIO, clock or PHY is missing\n");
	if (IS_ERR(devm_clk_get_optional_enabled(dev, "cam")) ||
	    IS_ERR(devm_clk_get_optional_enabled(dev, "isp")))
		return dev_err_probe(dev, -ENODEV, "camera block clocks\n");
	st->csis = devm_ioremap(dev, cfg->csis_base, CSIS_SIZE);
	st->mmu = devm_ioremap(dev, SYSMMU_BASE, 0x1000);
	st->cmu = devm_ioremap(dev, CMU_ISP_BASE, 0x1000);
	st->sysreg = devm_ioremap(dev, CAM0_SYSREG, 4);
	if (!st->csis || !st->mmu || !st->cmu || !st->sysreg)
		return -ENOMEM;

	if (!dev->dma_mask)
		dev->dma_mask = &dev->coherent_dma_mask;
	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(32));
	if (ret)
		return ret;
	for (i = 0; i < 2; i++) {
		st->buf[i] = dmam_alloc_coherent(dev, PAGE_ALIGN(st->frame_bytes), &st->dma[i],
						 GFP_KERNEL);
		if (!st->buf[i])
			return dev_err_probe(dev, -ENOMEM, "no contiguous buffer %d of %u bytes\n",
					     i, st->frame_bytes);
	}

	snprintf(st->name, sizeof(st->name), "j701f-cam-%s", cfg->name);
	st->misc.minor = MISC_DYNAMIC_MINOR;
	st->misc.name = st->name;
	st->misc.fops = &cam_fops;
	st->misc.parent = dev;
	st->misc.groups = cam_groups;
	st->misc.mode = 0600;
	i2c_set_clientdata(i2c, st);
	ret = misc_register(&st->misc);
	if (ret)
		return ret;
	dev_info(dev, "/dev/%s: %ux%u, %u bytes per frame\n", st->name, cfg->width, cfg->height,
		 st->frame_bytes);
	return 0;
}

static void cam_remove(struct i2c_client *i2c)
{
	struct cam_state *st = i2c_get_clientdata(i2c);

	misc_deregister(&st->misc);
}

static const struct of_device_id cam_match[] = {
	{ .compatible = "j701f,s5k3l2-probe", .data = &rear_cfg },
	{ .compatible = "j701f,s5k5e3-frame", .data = &front_cfg },
	{ }
};
MODULE_DEVICE_TABLE(of, cam_match);

static struct i2c_driver cam_driver = {
	.driver = { .name = "j701f-cam-stream", .of_match_table = cam_match },
	.probe = cam_probe,
	.remove = cam_remove,
};
module_i2c_driver(cam_driver);

MODULE_DESCRIPTION("J701F: continuous raw frames from one camera sensor");
MODULE_LICENSE("GPL");
