// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-10 (J701F, goal: a working camera). The phone's
 * two cameras as ordinary Linux cameras: for each sensor node one media
 * device with a sensor sub-device and a capture video node, so that libcamera
 * (and through it Plasma Camera and other applications) can use them.
 *
 *   sensor sub-device   one fixed mode, 10-bit Bayer (GRBG); controls for
 *                       exposure, analogue gain and the read-only blanking and
 *                       pixel-rate values libcamera asks for
 *   video node          V4L2_PIX_FMT_SGRBG10 (16-bit little-endian samples), the
 *                       layout the receiver's DMA writes when its 12-bit packing
 *                       is switched off
 *
 * Everything about the hardware - power order, sensor tables, the CSI-2
 * receiver with its DMA output, the clock selectors, the IOMMU bypass, the
 * extra system-register bit of the front camera - is as found with the test
 * module j701f_cam_frame.c and described there; register map and order from
 * the vendor fimc-is sources (build/kernel/vendor-camera-reference/, GPL-2.0).
 *
 * Simplifications that should go one day:
 *  - The receiver's DMA writes into two buffers of this driver in turn and a
 *    polling thread copies each finished frame into the application's buffer
 *    (the receiver's interrupt is not in our device tree; handing the
 *    application's buffers to the DMA directly needs its frame-pointer logic).
 *  - The media device calls itself "qcom-camss": libcamera's generic pipeline
 *    only accepts a fixed list of platform drivers, and that entry is one with
 *    software image processing switched on. Nothing else here is Qualcomm's.
 *  - The camera block's clocks, power domain and IOMMU are handled by direct
 *    register writes while streaming, not by proper drivers.
 */
#include <linux/bitfield.h>
#include <linux/clk.h>
#include <linux/kthread.h>
#include <linux/mutex.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/phy/phy.h>
#include <linux/regulator/consumer.h>
#include <media/media-device.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-device.h>
#include <media/v4l2-fwnode.h>
#include <media/v4l2-ioctl.h>
#include <media/v4l2-subdev.h>
#include <media/videobuf2-v4l2.h>
#include <media/videobuf2-vmalloc.h>

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
	unsigned int fll, llp;		/* frame length in lines, line length in pixel clocks */
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
	.lanes = 4, .settle = 30, .width = 2072, .height = 1552, .fll = 3174, .llp = 4512, .buf_bytes = 6 << 20,
	.s5k3l2_init = true,
	.mode = s5k3l2_mode_2072x1552_30fps, .mode_len = ARRAY_SIZE(s5k3l2_mode_2072x1552_30fps),
};

static const struct cam_cfg front_cfg = {
	.name = "front", .csis_base = 0x14460000, .rx_mux = CMU_ISP_MUX_RXBYTECLKHS0_S1,
	.lanes = 2, .settle = 19, .width = 1280, .height = 960, .fll = 2027, .llp = 2942, .buf_bytes = 3 << 20,
	/* vendor option bit 3; without it the sensor streamed (its frame counter ran)
	 * and the second receiver saw no lane activity at all */
	.sysreg_option = BIT(3),
	.mode = s5k5e3_mode_1280x960_30fps, .mode_len = ARRAY_SIZE(s5k5e3_mode_1280x960_30fps),
};


struct cam_buffer {
	struct vb2_v4l2_buffer vb;
	struct list_head list;
};

struct cam_state {
	const struct cam_cfg *cfg;
	struct device *dev;
	struct i2c_client *i2c;
	/* resources */
	struct gpio_desc *reset, *dvdd, *afvdd;
	struct regulator *avdd, *iovdd;
	struct clk *mclk;
	struct phy *phy;
	void __iomem *csis, *mmu, *cmu, *sysreg;
	u32 mux_before[3], mmu_ctrl;
	unsigned int user_mux[3];
	/* V4L2 */
	struct media_device mdev;
	struct v4l2_device v4l2;
	struct v4l2_subdev sd;
	struct media_pad sd_pad, vid_pad;
	struct v4l2_ctrl_handler ctrls;
	struct v4l2_ctrl *exposure, *gain;
	struct video_device vdev;
	struct vb2_queue queue;
	struct mutex lock;		/* video node and queue */
	spinlock_t qlock;		/* pending */
	struct list_head pending;
	unsigned int sequence;
	bool streaming;
	/* the receiver's two DMA targets */
	struct page *pages[2];
	void *buf[2];
	dma_addr_t dma[2];
	unsigned int frame_bytes;
	struct task_struct *poller;
};

#define FRAME_MAGIC	0x4a373031	/* first bytes of a DMA buffer not yet rewritten */

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
	/* not the 12-bit packing: plain 16-bit little-endian samples (V4L2 "SGRBG10") */
	writel(0, csis + CSIS_DMA0_FMT);
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

static void cam_return_buffers(struct cam_state *st, enum vb2_buffer_state state)
{
	struct cam_buffer *b, *tmp;
	unsigned long flags;

	spin_lock_irqsave(&st->qlock, flags);
	list_for_each_entry_safe(b, tmp, &st->pending, list) {
		list_del(&b->list);
		vb2_buffer_done(&b->vb.vb2_buf, state);
	}
	spin_unlock_irqrestore(&st->qlock, flags);
}

/* Notices each finished frame and copies it into the next waiting buffer. */
static int cam_poll_thread(void *data)
{
	struct cam_state *st = data;
	struct cam_buffer *b;
	unsigned long flags;
	int done = 0;
	u32 v;

	while (!kthread_should_stop()) {
		usleep_range(1500, 2500);
		v = readl(st->csis + CSIS_INT_SRC0);
		if (v)
			writel(v, st->csis + CSIS_INT_SRC0);
		v = readl(st->csis + CSIS_INT_SRC1);
		if (!v)
			continue;
		writel(v, st->csis + CSIS_INT_SRC1);
		if (!(v & GENMASK(11, 8)))	/* DMA frame end */
			continue;
		/* The finished buffer is the one whose marker has been overwritten. */
		if (*(u32 *)st->buf[0] != FRAME_MAGIC && *(u32 *)st->buf[1] == FRAME_MAGIC)
			done = 0;
		else if (*(u32 *)st->buf[1] != FRAME_MAGIC && *(u32 *)st->buf[0] == FRAME_MAGIC)
			done = 1;
		else
			done = !done;

		spin_lock_irqsave(&st->qlock, flags);
		b = list_first_entry_or_null(&st->pending, struct cam_buffer, list);
		if (b)
			list_del(&b->list);
		spin_unlock_irqrestore(&st->qlock, flags);
		if (b) {
			dma_sync_single_for_cpu(st->dev, st->dma[done], st->frame_bytes,
						DMA_FROM_DEVICE);
			memcpy(vb2_plane_vaddr(&b->vb.vb2_buf, 0), st->buf[done], st->frame_bytes);
			vb2_set_plane_payload(&b->vb.vb2_buf, 0, st->frame_bytes);
			b->vb.vb2_buf.timestamp = ktime_get_ns();
			b->vb.sequence = st->sequence;
			b->vb.field = V4L2_FIELD_NONE;
			vb2_buffer_done(&b->vb.vb2_buf, VB2_BUF_STATE_DONE);
		}
		st->sequence++;
		*(u32 *)st->buf[done] = FRAME_MAGIC;
		dma_sync_single_for_device(st->dev, st->dma[done], 64, DMA_FROM_DEVICE);
	}
	return 0;
}

static int cam_hw_start(struct cam_state *st)
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
	ret = regulator_enable(st->iovdd);
	if (ret)
		goto avdd_off;
	usleep_range(2000, 2500);
	clk_set_rate(st->mclk, 26000000);
	ret = clk_prepare_enable(st->mclk);
	if (ret)
		goto io_off;
	usleep_range(3000, 3500);
	gpiod_set_value_cansleep(st->reset, 0);
	usleep_range(10000, 11000);

	ret = sensor_setup(st->i2c, cfg);
	if (!ret)
		ret = cam_read16(st->i2c, 0x034c, &out_w);
	if (!ret)
		ret = cam_read16(st->i2c, 0x034e, &out_h);
	if (!ret && (out_w != cfg->width || out_h != cfg->height))
		ret = -EIO;	/* never start the DMA for a size the buffers were not made for */
	if (ret)
		goto clk_off;
	cam_write(st->i2c, 0x0202, st->exposure->val, 2);
	cam_write(st->i2c, 0x0204, st->gain->val, 2);

	phy_power_on(st->phy);
	if (cfg->sysreg_option)
		writel(readl(st->sysreg) | cfg->sysreg_option, st->sysreg);
	for (i = 0; i < ARRAY_SIZE(st->user_mux); i++) {
		st->mux_before[i] = readl(st->cmu + st->user_mux[i]);
		writel(st->mux_before[i] | CMU_MUX_USER, st->cmu + st->user_mux[i]);
	}
	usleep_range(1000, 1500);
	for (i = 0; i < 2; i++) {
		*(u32 *)st->buf[i] = FRAME_MAGIC;
		dma_sync_single_for_device(st->dev, st->dma[i], st->frame_bytes, DMA_FROM_DEVICE);
	}
	st->sequence = 0;
	csis_setup(st->csis, cfg, lower_32_bits(st->dma[0]), lower_32_bits(st->dma[1]));
	cam_write(st->i2c, 0x6028, 0x4000, 2);
	cam_write(st->i2c, 0x0100, 0x01, 1);
	cam_write(st->i2c, 0x0216, 0x00, 1);
	st->poller = kthread_run(cam_poll_thread, st, "j701f-cam-%s", cfg->name);
	if (IS_ERR(st->poller)) {
		ret = PTR_ERR(st->poller);
		st->poller = NULL;
		return ret;
	}
	st->streaming = true;
	return 0;
clk_off:
	gpiod_set_value_cansleep(st->reset, 1);
	clk_disable_unprepare(st->mclk);
io_off:
	regulator_disable(st->iovdd);
avdd_off:
	gpiod_set_value_cansleep(st->afvdd, 0);
	gpiod_set_value_cansleep(st->dvdd, 0);
	regulator_disable(st->avdd);
	if (st->mmu_ctrl & 1)
		writel(st->mmu_ctrl, st->mmu + SYSMMU_CTRL);
	return ret;
}

static void cam_hw_stop(struct cam_state *st)
{
	unsigned int i;

	st->streaming = false;
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
	regulator_disable(st->iovdd);
	gpiod_set_value_cansleep(st->afvdd, 0);
	gpiod_set_value_cansleep(st->dvdd, 0);
	regulator_disable(st->avdd);
	if (st->mmu_ctrl & 1)
		writel(st->mmu_ctrl, st->mmu + SYSMMU_CTRL);
}

/* ---- buffer queue ---- */

static int cam_queue_setup(struct vb2_queue *q, unsigned int *nbuffers, unsigned int *nplanes,
			   unsigned int sizes[], struct device *alloc_devs[])
{
	struct cam_state *st = vb2_get_drv_priv(q);

	if (*nplanes)
		return sizes[0] < st->frame_bytes ? -EINVAL : 0;
	*nplanes = 1;
	sizes[0] = st->frame_bytes;
	return 0;
}

static void cam_buf_queue(struct vb2_buffer *vb)
{
	struct cam_state *st = vb2_get_drv_priv(vb->vb2_queue);
	struct cam_buffer *b = container_of(to_vb2_v4l2_buffer(vb), struct cam_buffer, vb);
	unsigned long flags;

	spin_lock_irqsave(&st->qlock, flags);
	list_add_tail(&b->list, &st->pending);
	spin_unlock_irqrestore(&st->qlock, flags);
}

static int cam_start_streaming(struct vb2_queue *q, unsigned int count)
{
	struct cam_state *st = vb2_get_drv_priv(q);
	int ret = cam_hw_start(st);

	if (ret)
		cam_return_buffers(st, VB2_BUF_STATE_QUEUED);
	return ret;
}

static void cam_stop_streaming(struct vb2_queue *q)
{
	struct cam_state *st = vb2_get_drv_priv(q);

	cam_hw_stop(st);
	cam_return_buffers(st, VB2_BUF_STATE_ERROR);
}

static const struct vb2_ops cam_vb2_ops = {
	.queue_setup = cam_queue_setup,
	.buf_queue = cam_buf_queue,
	.start_streaming = cam_start_streaming,
	.stop_streaming = cam_stop_streaming,
};

/* ---- video node ---- */

static void cam_fill_pix(struct cam_state *st, struct v4l2_pix_format *pix)
{
	pix->width = st->cfg->width;
	pix->height = st->cfg->height;
	pix->pixelformat = V4L2_PIX_FMT_SGRBG10;
	pix->field = V4L2_FIELD_NONE;
	pix->bytesperline = st->cfg->width * 2;
	pix->sizeimage = st->frame_bytes;
	pix->colorspace = V4L2_COLORSPACE_RAW;
}

static int cam_querycap(struct file *file, void *priv, struct v4l2_capability *cap)
{
	struct cam_state *st = video_drvdata(file);

	strscpy(cap->driver, "j701f-camera", sizeof(cap->driver));
	snprintf(cap->card, sizeof(cap->card), "J701F %s camera", st->cfg->name);
	return 0;
}

static int cam_enum_fmt(struct file *file, void *priv, struct v4l2_fmtdesc *f)
{
	if (f->index)
		return -EINVAL;
	f->pixelformat = V4L2_PIX_FMT_SGRBG10;
	return 0;
}

static int cam_g_fmt(struct file *file, void *priv, struct v4l2_format *f)
{
	cam_fill_pix(video_drvdata(file), &f->fmt.pix);
	return 0;
}

static int cam_enum_framesizes(struct file *file, void *priv, struct v4l2_frmsizeenum *fsize)
{
	struct cam_state *st = video_drvdata(file);

	if (fsize->index || fsize->pixel_format != V4L2_PIX_FMT_SGRBG10)
		return -EINVAL;
	fsize->type = V4L2_FRMSIZE_TYPE_DISCRETE;
	fsize->discrete.width = st->cfg->width;
	fsize->discrete.height = st->cfg->height;
	return 0;
}

static const struct v4l2_ioctl_ops cam_ioctl_ops = {
	.vidioc_querycap = cam_querycap,
	.vidioc_enum_fmt_vid_cap = cam_enum_fmt,
	.vidioc_g_fmt_vid_cap = cam_g_fmt,
	.vidioc_s_fmt_vid_cap = cam_g_fmt,
	.vidioc_try_fmt_vid_cap = cam_g_fmt,
	.vidioc_enum_framesizes = cam_enum_framesizes,
	.vidioc_reqbufs = vb2_ioctl_reqbufs,
	.vidioc_create_bufs = vb2_ioctl_create_bufs,
	.vidioc_prepare_buf = vb2_ioctl_prepare_buf,
	.vidioc_querybuf = vb2_ioctl_querybuf,
	.vidioc_qbuf = vb2_ioctl_qbuf,
	.vidioc_dqbuf = vb2_ioctl_dqbuf,
	.vidioc_expbuf = vb2_ioctl_expbuf,
	.vidioc_streamon = vb2_ioctl_streamon,
	.vidioc_streamoff = vb2_ioctl_streamoff,
};

static const struct v4l2_file_operations cam_v4l2_fops = {
	.owner = THIS_MODULE,
	.open = v4l2_fh_open,
	.release = vb2_fop_release,
	.unlocked_ioctl = video_ioctl2,
	.mmap = vb2_fop_mmap,
	.poll = vb2_fop_poll,
	.read = vb2_fop_read,
};

/* ---- sensor sub-device ---- */

static void cam_fill_mbus(struct cam_state *st, struct v4l2_mbus_framefmt *fmt)
{
	fmt->width = st->cfg->width;
	fmt->height = st->cfg->height;
	fmt->code = MEDIA_BUS_FMT_SGRBG10_1X10;
	fmt->field = V4L2_FIELD_NONE;
	fmt->colorspace = V4L2_COLORSPACE_RAW;
}

static int cam_sd_init_state(struct v4l2_subdev *sd, struct v4l2_subdev_state *state)
{
	cam_fill_mbus(v4l2_get_subdevdata(sd), v4l2_subdev_state_get_format(state, 0));
	return 0;
}

static int cam_sd_enum_mbus_code(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
				 struct v4l2_subdev_mbus_code_enum *code)
{
	if (code->index)
		return -EINVAL;
	code->code = MEDIA_BUS_FMT_SGRBG10_1X10;
	return 0;
}

static int cam_sd_enum_frame_size(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
				  struct v4l2_subdev_frame_size_enum *fse)
{
	struct cam_state *st = v4l2_get_subdevdata(sd);

	if (fse->index || fse->code != MEDIA_BUS_FMT_SGRBG10_1X10)
		return -EINVAL;
	fse->min_width = fse->max_width = st->cfg->width;
	fse->min_height = fse->max_height = st->cfg->height;
	return 0;
}

static int cam_sd_set_fmt(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
			  struct v4l2_subdev_format *format)
{
	/* one mode: whatever is asked for, this is what there is */
	cam_fill_mbus(v4l2_get_subdevdata(sd), &format->format);
	*v4l2_subdev_state_get_format(state, 0) = format->format;
	return 0;
}

static int cam_sd_get_selection(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
				struct v4l2_subdev_selection *sel)
{
	struct cam_state *st = v4l2_get_subdevdata(sd);

	switch (sel->target) {
	case V4L2_SEL_TGT_CROP:
	case V4L2_SEL_TGT_CROP_DEFAULT:
	case V4L2_SEL_TGT_CROP_BOUNDS:
	case V4L2_SEL_TGT_NATIVE_SIZE:
		sel->r.left = sel->r.top = 0;
		sel->r.width = st->cfg->width;
		sel->r.height = st->cfg->height;
		return 0;
	}
	return -EINVAL;
}

static const struct v4l2_subdev_pad_ops cam_sd_pad_ops = {
	.enum_mbus_code = cam_sd_enum_mbus_code,
	.enum_frame_size = cam_sd_enum_frame_size,
	.get_fmt = v4l2_subdev_get_fmt,
	.set_fmt = cam_sd_set_fmt,
	.get_selection = cam_sd_get_selection,
};

static const struct v4l2_subdev_ops cam_sd_ops = { .pad = &cam_sd_pad_ops };
static const struct v4l2_subdev_internal_ops cam_sd_internal_ops = {
	.init_state = cam_sd_init_state,
};

static int cam_s_ctrl(struct v4l2_ctrl *ctrl)
{
	struct cam_state *st = container_of(ctrl->handler, struct cam_state, ctrls);

	if (!st->streaming)
		return 0;	/* applied when the sensor is next powered */
	switch (ctrl->id) {
	case V4L2_CID_EXPOSURE:
		return cam_write(st->i2c, 0x0202, ctrl->val, 2);
	case V4L2_CID_ANALOGUE_GAIN:
		return cam_write(st->i2c, 0x0204, ctrl->val, 2);
	}
	return 0;
}

static const struct v4l2_ctrl_ops cam_ctrl_ops = { .s_ctrl = cam_s_ctrl };

static int cam_init_controls(struct cam_state *st)
{
	const struct cam_cfg *cfg = st->cfg;
	struct v4l2_fwnode_device_properties props;
	struct v4l2_ctrl *c;
	s64 rate = (s64)cfg->llp * cfg->fll * 30;
	int ret;

	v4l2_ctrl_handler_init(&st->ctrls, 8);
	st->exposure = v4l2_ctrl_new_std(&st->ctrls, &cam_ctrl_ops, V4L2_CID_EXPOSURE,
					 4, cfg->fll - 8, 1, 1000);
	/* the sensors' units: 0x20 = 1x, up to 16x */
	st->gain = v4l2_ctrl_new_std(&st->ctrls, &cam_ctrl_ops, V4L2_CID_ANALOGUE_GAIN,
				     32, 512, 1, 64);
	c = v4l2_ctrl_new_std(&st->ctrls, &cam_ctrl_ops, V4L2_CID_VBLANK,
			      cfg->fll - cfg->height, cfg->fll - cfg->height, 1,
			      cfg->fll - cfg->height);
	if (c)
		c->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	c = v4l2_ctrl_new_std(&st->ctrls, &cam_ctrl_ops, V4L2_CID_HBLANK,
			      cfg->llp - cfg->width, cfg->llp - cfg->width, 1,
			      cfg->llp - cfg->width);
	if (c)
		c->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	c = v4l2_ctrl_new_std(&st->ctrls, &cam_ctrl_ops, V4L2_CID_PIXEL_RATE, rate, rate, 1, rate);
	if (c)
		c->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	ret = v4l2_fwnode_device_parse(st->dev, &props);
	/* The device tree's first guesses (90 and 270) gave the owner photographs
	 * upside down; until the next image carries the corrected values the driver
	 * supplies them. Rear confirmed by that report, front mirrored by assumption. */
	if (!ret)
		props.rotation = cfg->s5k3l2_init ? 270 : 90;
	if (!ret)
		v4l2_ctrl_new_fwnode_properties(&st->ctrls, &cam_ctrl_ops, &props);
	return st->ctrls.error;
}

/* ---- probe ---- */

static int cam_probe(struct i2c_client *i2c)
{
	const struct cam_cfg *cfg = of_device_get_match_data(&i2c->dev);
	struct device *dev = &i2c->dev;
	struct cam_state *st;
	int i, ret;

	st = devm_kzalloc(dev, sizeof(*st), GFP_KERNEL);
	if (!st)
		return -ENOMEM;
	st->cfg = cfg;
	st->dev = dev;
	st->i2c = i2c;
	mutex_init(&st->lock);
	spin_lock_init(&st->qlock);
	INIT_LIST_HEAD(&st->pending);
	st->user_mux[0] = CMU_ISP_MUX_CAM_USER;
	st->user_mux[1] = CMU_ISP_MUX_ISP_USER;
	st->user_mux[2] = cfg->rx_mux;
	st->frame_bytes = cfg->width * cfg->height * 2;
	i2c_set_clientdata(i2c, st);

	st->avdd = devm_regulator_get(dev, "avdd");
	st->iovdd = devm_regulator_get(dev, "iovdd");
	st->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	st->dvdd = devm_gpiod_get(dev, "dvdd", GPIOD_OUT_LOW);
	st->afvdd = devm_gpiod_get_optional(dev, "afvdd", GPIOD_OUT_LOW);
	st->mclk = devm_clk_get(dev, "mclk");
	st->phy = devm_phy_get(dev, "csis");
	if (IS_ERR(st->avdd) || IS_ERR(st->iovdd) || IS_ERR(st->reset) || IS_ERR(st->dvdd) ||
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
	/* ordinary (cached) pages, so that copying a frame out of them is fast */
	for (i = 0; i < 2; i++) {
		st->pages[i] = dma_alloc_pages(dev, PAGE_ALIGN(st->frame_bytes), &st->dma[i],
					       DMA_FROM_DEVICE, GFP_KERNEL);
		if (!st->pages[i]) {
			ret = dev_err_probe(dev, -ENOMEM, "no contiguous buffer of %u bytes\n",
					    st->frame_bytes);
			goto free_pages;
		}
		st->buf[i] = page_address(st->pages[i]);
	}

	/* media device, sensor sub-device, video node */
	st->mdev.dev = dev;
	strscpy(st->mdev.driver_name, "qcom-camss", sizeof(st->mdev.driver_name));
	snprintf(st->mdev.model, sizeof(st->mdev.model), "J701F %s camera", cfg->name);
	media_device_init(&st->mdev);
	st->v4l2.mdev = &st->mdev;
	ret = v4l2_device_register(dev, &st->v4l2);
	if (ret)
		goto cleanup_media;

	v4l2_subdev_init(&st->sd, &cam_sd_ops);
	st->sd.internal_ops = &cam_sd_internal_ops;
	st->sd.owner = THIS_MODULE;
	st->sd.dev = dev;
	st->sd.flags |= V4L2_SUBDEV_FL_HAS_DEVNODE;
	snprintf(st->sd.name, sizeof(st->sd.name), "%s %d-%04x",
		 cfg->s5k3l2_init ? "s5k3l2" : "s5k5e3", i2c_adapter_id(i2c->adapter), i2c->addr);
	v4l2_set_subdevdata(&st->sd, st);
	st->sd.entity.function = MEDIA_ENT_F_CAM_SENSOR;
	st->sd_pad.flags = MEDIA_PAD_FL_SOURCE;
	ret = media_entity_pads_init(&st->sd.entity, 1, &st->sd_pad);
	if (ret)
		goto unregister_v4l2;
	ret = cam_init_controls(st);
	if (ret)
		goto free_ctrls;
	st->sd.ctrl_handler = &st->ctrls;
	ret = v4l2_subdev_init_finalize(&st->sd);
	if (ret)
		goto free_ctrls;
	ret = v4l2_device_register_subdev(&st->v4l2, &st->sd);
	if (ret)
		goto subdev_cleanup;

	st->queue.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	st->queue.io_modes = VB2_MMAP | VB2_READ;
	st->queue.drv_priv = st;
	st->queue.buf_struct_size = sizeof(struct cam_buffer);
	st->queue.ops = &cam_vb2_ops;
	st->queue.mem_ops = &vb2_vmalloc_memops;
	st->queue.timestamp_flags = V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC;
	st->queue.lock = &st->lock;
	st->queue.min_queued_buffers = 1;
	st->queue.dev = dev;
	ret = vb2_queue_init(&st->queue);
	if (ret)
		goto unregister_subdev;

	snprintf(st->vdev.name, sizeof(st->vdev.name), "j701f %s capture", cfg->name);
	st->vdev.fops = &cam_v4l2_fops;
	st->vdev.ioctl_ops = &cam_ioctl_ops;
	st->vdev.release = video_device_release_empty;
	st->vdev.v4l2_dev = &st->v4l2;
	st->vdev.queue = &st->queue;
	st->vdev.lock = &st->lock;
	st->vdev.device_caps = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING | V4L2_CAP_READWRITE |
			       V4L2_CAP_IO_MC;
	st->vdev.entity.function = MEDIA_ENT_F_IO_V4L;
	st->vid_pad.flags = MEDIA_PAD_FL_SINK;
	video_set_drvdata(&st->vdev, st);
	ret = media_entity_pads_init(&st->vdev.entity, 1, &st->vid_pad);
	if (ret)
		goto unregister_subdev;
	ret = video_register_device(&st->vdev, VFL_TYPE_VIDEO, -1);
	if (ret)
		goto unregister_subdev;
	ret = media_create_pad_link(&st->sd.entity, 0, &st->vdev.entity, 0,
				    MEDIA_LNK_FL_ENABLED | MEDIA_LNK_FL_IMMUTABLE);
	if (!ret)
		ret = v4l2_device_register_subdev_nodes(&st->v4l2);
	if (!ret)
		ret = media_device_register(&st->mdev);
	if (ret)
		goto unregister_video;
	dev_info(dev, "%s camera: %s, %ux%u, /dev/%s\n", cfg->name, st->sd.name, cfg->width,
		 cfg->height, video_device_node_name(&st->vdev));
	return 0;

unregister_video:
	video_unregister_device(&st->vdev);
unregister_subdev:
	v4l2_device_unregister_subdev(&st->sd);
subdev_cleanup:
	v4l2_subdev_cleanup(&st->sd);
free_ctrls:
	v4l2_ctrl_handler_free(&st->ctrls);
	media_entity_cleanup(&st->sd.entity);
unregister_v4l2:
	v4l2_device_unregister(&st->v4l2);
cleanup_media:
	media_device_cleanup(&st->mdev);
free_pages:
	for (i = 0; i < 2; i++)
		if (st->pages[i])
			dma_free_pages(dev, PAGE_ALIGN(st->frame_bytes), st->pages[i], st->dma[i],
				       DMA_FROM_DEVICE);
	return ret;
}

static void cam_remove(struct i2c_client *i2c)
{
	struct cam_state *st = i2c_get_clientdata(i2c);
	int i;

	media_device_unregister(&st->mdev);
	video_unregister_device(&st->vdev);
	v4l2_device_unregister_subdev(&st->sd);
	v4l2_subdev_cleanup(&st->sd);
	v4l2_ctrl_handler_free(&st->ctrls);
	media_entity_cleanup(&st->sd.entity);
	v4l2_device_unregister(&st->v4l2);
	media_device_cleanup(&st->mdev);
	for (i = 0; i < 2; i++)
		dma_free_pages(st->dev, PAGE_ALIGN(st->frame_bytes), st->pages[i], st->dma[i],
			       DMA_FROM_DEVICE);
}

static const struct of_device_id cam_match[] = {
	{ .compatible = "j701f,s5k3l2", .data = &rear_cfg },
	{ .compatible = "j701f,s5k5e3", .data = &front_cfg },
	{ }
};
MODULE_DEVICE_TABLE(of, cam_match);

static struct i2c_driver cam_driver = {
	.driver = { .name = "j701f-camera", .of_match_table = cam_match },
	.probe = cam_probe,
	.remove = cam_remove,
};
module_i2c_driver(cam_driver);

MODULE_DESCRIPTION("J701F rear and front cameras as V4L2 / media devices");
MODULE_LICENSE("GPL");
MODULE_IMPORT_NS("DMA_BUF");
