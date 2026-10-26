// SPDX-License-Identifier: GPL-2.0-only
/*
 * Experimental EA8061S J7VE panel driver, prepared by Codex 2026-10-10.
 * Commands/delays derived from Samsung's GPLv2 ea8061s_j7lite_lcd_ctrl.c
 * and ea8061s_j7lite_param.h, SIMPLE commit 29223d295a58ebe82e95347c8eb8468ea2b1c336.
 * Board timing and power sequence: captured j701f-live.dtb and dsim_drv.c.
 *
 * This is the vendor's fixed initial gamma, NOT its calibrated brightness
 * implementation. Requires explicit allow_init=1.
 *
 * Claude 2026-10-10: brightness. The vendor dims this AMOLED panel in two ways:
 * a gamma table per level (needs the panel's factory calibration, not done
 * here) and the AOR ("AID") register 0xB2, the number of scan lines per frame
 * during which the pixels are off. Only the second is used: backlight level
 * 1..255 maps linearly onto the range of the vendor's own AOR_TABLE, 0x04e6
 * (darkest) .. 0x000c (the value the init sequence ends with). Colours stay
 * those of the fixed gamma. Backlight device: "j701f-panel", the name the
 * software backlight of the firmware framebuffer used.
 */
#include <linux/backlight.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>

#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>

static bool allow_init;
module_param(allow_init, bool, 0400);
MODULE_PARM_DESC(allow_init, "Allow experimental panel reset and fixed-gamma initialisation");

struct j701f_ea8061s {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi;
	struct regulator *vddio;
	struct regulator *vci;
	struct gpio_desc *reset;
	bool reset_output;
	struct backlight_device *backlight;
	struct mutex lock;	/* enabled, and the DSI writes that depend on it */
	bool enabled;
};

#define EA8061S_AOR_DARKEST	0x04e6
#define EA8061S_AOR_BRIGHTEST	0x000c

static u16 ea8061s_aor(unsigned int level)
{
	if (level < 1)
		level = 1;	/* 0 is "off" for the backlight core; blanking is DRM's job */
	if (level > 255)
		level = 255;
	return EA8061S_AOR_DARKEST -
	       (EA8061S_AOR_DARKEST - EA8061S_AOR_BRIGHTEST) * (level - 1) / 254;
}

static struct j701f_ea8061s *to_ea8061s(struct drm_panel *panel)
{
	return container_of(panel, struct j701f_ea8061s, panel);
}

static void ea8061s_lock_keys(struct mipi_dsi_device *dsi)
{
	/* Independent attempts: a failed transfer must not skip the other lock. */
	static const u8 f0[] = { 0xf0, 0xa5, 0xa5 };
	static const u8 fc[] = { 0xfc, 0xa5, 0xa5 };

	mipi_dsi_dcs_write_buffer(dsi, f0, sizeof(f0));
	mipi_dsi_dcs_write_buffer(dsi, fc, sizeof(fc));
}

static int ea8061s_init_sequence(struct mipi_dsi_device *dsi)
{
	struct mipi_dsi_multi_context ctx = { .dsi = dsi };

	mipi_dsi_usleep_range(&ctx, 5000, 6000);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xf0, 0x5a, 0x5a);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xfc, 0x5a, 0x5a);
	/* Vendor common settings. */
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xcf, 0x30, 0x09);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xba, 0x77);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xb2, 0x00, 0x00, 0x00, 0x0c);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xf7, 0x03);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xb8, 0x19, 0x00);
	mipi_dsi_dcs_exit_sleep_mode_multi(&ctx);
	mipi_dsi_usleep_range(&ctx, 10000, 11000);
	/* Power sequence and maximum AOR, followed by vendor settling delays. */
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xb1,
				     0x3c, 0x89, 0x00, 0x05, 0x33, 0x31, 0x14);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xb2, 0x00, 0x00, 0x05, 0x10);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xf7, 0x03);
	mipi_dsi_usleep_range(&ctx, 10000, 11000);
	mipi_dsi_msleep(&ctx, 150);
	/* Fixed vendor initial gamma (33 data bytes), not panel MTP calibration. */
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xca,
				     0x01, 0x00, 0x01, 0x00, 0x01, 0x00,
				     0x80, 0x80, 0x80, 0x80, 0x80, 0x80,
				     0x80, 0x80, 0x80, 0x80, 0x80, 0x80,
				     0x80, 0x80, 0x80, 0x80, 0x80, 0x80,
				     0x80, 0x80, 0x80, 0x80, 0x80, 0x80,
				     0x00, 0x00, 0x00);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xb2, 0x00, 0x00, 0x00, 0x0c);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xb6,
				     0xdc, 0x84, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0x55, 0x00);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xf7, 0x03);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xb8, 0x19);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xf0, 0xa5, 0xa5);
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xfc, 0xa5, 0xa5);
	if (ctx.accum_err)
		ea8061s_lock_keys(dsi);

	return ctx.accum_err;
}

static void ea8061s_power_off(struct j701f_ea8061s *ctx)
{
	int ret;

	/* A failed direction change does not establish a usable output. */
	if (ctx->reset_output)
		gpiod_set_value_cansleep(ctx->reset, 1); /* active-low reset asserted */
	usleep_range(10000, 11000);
	ret = regulator_disable(ctx->vci);
	if (ret)
		dev_warn(&ctx->dsi->dev, "VCI disable failed: %d\n", ret);
	ret = regulator_disable(ctx->vddio);
	if (ret)
		dev_warn(&ctx->dsi->dev, "VDDIO disable failed: %d\n", ret);
}

/* Vendor order: unlock, AID set, gamma update, lock. Caller holds ctx->lock. */
static int ea8061s_write_aor(struct j701f_ea8061s *ctx, unsigned int level)
{
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi };
	u16 aor = ea8061s_aor(level);
	/* not the _seq macro: its data must be compile-time constants */
	const u8 aid[] = { 0xb2, 0x00, 0x00, aor >> 8, aor & 0xff };

	mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xf0, 0x5a, 0x5a);
	mipi_dsi_dcs_write_buffer_multi(&dsi_ctx, aid, sizeof(aid));
	mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xf7, 0x03);
	mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xf0, 0xa5, 0xa5);
	if (dsi_ctx.accum_err)
		ea8061s_lock_keys(ctx->dsi);
	return dsi_ctx.accum_err;
}

static int ea8061s_backlight_update(struct backlight_device *bl)
{
	struct j701f_ea8061s *ctx = bl_get_data(bl);
	int ret = 0;

	mutex_lock(&ctx->lock);
	/* While the panel is off the level is only remembered; enable applies it. */
	if (ctx->enabled)
		ret = ea8061s_write_aor(ctx, bl->props.brightness);
	mutex_unlock(&ctx->lock);
	return ret;
}

static const struct backlight_ops ea8061s_backlight_ops = {
	.update_status = ea8061s_backlight_update,
};

static int ea8061s_prepare(struct drm_panel *panel)
{
	struct j701f_ea8061s *ctx = to_ea8061s(panel);
	int ret;

	/* Keep the vendor's ordered power sequence; do not bulk-enable rails. */
	ret = regulator_enable(ctx->vddio);
	if (ret)
		return ret;
	ret = regulator_enable(ctx->vci);
	if (ret) {
		regulator_disable(ctx->vddio);
		return ret;
	}
	msleep(25);
	/* Vendor raw HIGH / LOW / HIGH with 5 / 5 / 10 ms waits.
	 * reset-gpios must be GPIO_ACTIVE_LOW: logical 0 means raw HIGH.
	 */
	ret = gpiod_direction_output(ctx->reset, 0);
	if (ret)
		goto fail;
	ctx->reset_output = true;
	usleep_range(5000, 6000);
	gpiod_set_value_cansleep(ctx->reset, 1);
	usleep_range(5000, 6000);
	gpiod_set_value_cansleep(ctx->reset, 0);
	usleep_range(10000, 11000);
	ret = ea8061s_init_sequence(ctx->dsi);
	if (ret)
		goto fail;
	return 0;

fail:
	ea8061s_power_off(ctx);
	return ret;
}

static int ea8061s_enable(struct drm_panel *panel)
{
	struct j701f_ea8061s *ctx = to_ea8061s(panel);
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi };

	mipi_dsi_dcs_set_display_on_multi(&dsi_ctx);
	mipi_dsi_usleep_range(&dsi_ctx, 10000, 11000);
	mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xf0, 0x5a, 0x5a);
	mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xf7, 0x03);
	mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xf0, 0xa5, 0xa5);
	if (dsi_ctx.accum_err) {
		ea8061s_lock_keys(ctx->dsi);
		return dsi_ctx.accum_err;
	}
	mutex_lock(&ctx->lock);
	ctx->enabled = true;
	/* A failed brightness write must not fail the modeset: full brightness stays. */
	if (ctx->backlight && ea8061s_write_aor(ctx, ctx->backlight->props.brightness))
		dev_warn(&ctx->dsi->dev, "Could not apply the brightness level\n");
	mutex_unlock(&ctx->lock);
	return 0;
}

static int ea8061s_disable(struct drm_panel *panel)
{
	struct j701f_ea8061s *ctx = to_ea8061s(panel);
	int ret;

	mutex_lock(&ctx->lock);
	ctx->enabled = false;
	mutex_unlock(&ctx->lock);
	ret = mipi_dsi_dcs_set_display_off(ctx->dsi);

	/* Also wait on error, before unprepare can send SLEEP_IN. */
	usleep_range(20000, 21000);
	return ret;
}

static int ea8061s_unprepare(struct drm_panel *panel)
{
	struct j701f_ea8061s *ctx = to_ea8061s(panel);
	int ret = mipi_dsi_dcs_enter_sleep_mode(ctx->dsi);

	msleep(100);
	usleep_range(5000, 6000);
	ea8061s_power_off(ctx);
	if (ret)
		dev_warn(&ctx->dsi->dev, "Sleep command failed before power-off: %d\n", ret);
	/* Reset/power-off completes unprepare even if the DCS command failed.
	 * Returning its error would leave DRM's prepared flag set and could
	 * cause a second, unbalanced regulator_disable on a later teardown.
	 */
	return 0;
}

static const struct drm_display_mode ea8061s_mode = {
	.clock = (720 + 56 + 4 + 48) * (1280 + 9 + 2 + 5) * 60 / 1000,
	.hdisplay = 720,
	.hsync_start = 720 + 56,
	.hsync_end = 720 + 56 + 4,
	.htotal = 720 + 56 + 4 + 48,
	.vdisplay = 1280,
	.vsync_start = 1280 + 9,
	.vsync_end = 1280 + 9 + 2,
	.vtotal = 1280 + 9 + 2 + 5,
	.width_mm = 68,
	.height_mm = 121,
};

static int ea8061s_get_modes(struct drm_panel *panel,
			     struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &ea8061s_mode);
	if (!mode)
		return -ENOMEM;
	drm_mode_set_name(mode);
	mode->type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED;
	connector->display_info.width_mm = mode->width_mm;
	connector->display_info.height_mm = mode->height_mm;
	drm_mode_probed_add(connector, mode);
	return 1;
}

static const struct drm_panel_funcs ea8061s_funcs = {
	.prepare = ea8061s_prepare,
	.enable = ea8061s_enable,
	.disable = ea8061s_disable,
	.unprepare = ea8061s_unprepare,
	.get_modes = ea8061s_get_modes,
};

static int ea8061s_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct j701f_ea8061s *ctx;
	int ret;

	if (!allow_init)
		return dev_err_probe(dev, -EPERM, "Experimental panel requires allow_init=1\n");
	ctx = devm_drm_panel_alloc(dev, struct j701f_ea8061s, panel,
				   &ea8061s_funcs, DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);
	/* DSIM rejects DCS transfers until its pre-enable has resumed the host. */
	ctx->panel.prepare_prev_first = true;
	ctx->dsi = dsi;
	ctx->vddio = devm_regulator_get(dev, "vddio");
	if (IS_ERR(ctx->vddio))
		return dev_err_probe(dev, PTR_ERR(ctx->vddio), "Cannot get VDDIO\n");
	ctx->vci = devm_regulator_get(dev, "vci");
	if (IS_ERR(ctx->vci))
		return dev_err_probe(dev, PTR_ERR(ctx->vci), "Cannot get VCI\n");
	/* Acquiring the descriptor must not reset the firmware's active panel. */
	ctx->reset = devm_gpiod_get(dev, "reset", GPIOD_ASIS);
	if (IS_ERR(ctx->reset))
		return dev_err_probe(dev, PTR_ERR(ctx->reset), "Cannot get reset GPIO\n");
	if (!gpiod_is_active_low(ctx->reset))
		return dev_err_probe(dev, -EINVAL, "reset-gpios must be active low\n");

	mutex_init(&ctx->lock);
	{
		struct backlight_properties props = {
			.type = BACKLIGHT_RAW,
			.max_brightness = 255,
			.brightness = 255,
		};

		ctx->backlight = devm_backlight_device_register(dev, "j701f-panel", dev, ctx,
								&ea8061s_backlight_ops, &props);
		if (IS_ERR(ctx->backlight))
			return dev_err_probe(dev, PTR_ERR(ctx->backlight), "Cannot register backlight\n");
	}

	mipi_dsi_set_drvdata(dsi, ctx);
	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	/* Vendor DSIM: burst=1, HFP disabled, HSA/HBP/HSE enabled. */
	dsi->mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |
			  MIPI_DSI_MODE_VIDEO_NO_HFP | MIPI_DSI_MODE_LPM;
	drm_panel_add(&ctx->panel);
	ret = mipi_dsi_attach(dsi);
	if (ret)
		drm_panel_remove(&ctx->panel);
	return ret;
}

static void ea8061s_shutdown(struct mipi_dsi_device *dsi)
{
	struct j701f_ea8061s *ctx = mipi_dsi_get_drvdata(dsi);

	drm_panel_disable(&ctx->panel);
	drm_panel_unprepare(&ctx->panel);
}

static void ea8061s_remove(struct mipi_dsi_device *dsi)
{
	struct j701f_ea8061s *ctx = mipi_dsi_get_drvdata(dsi);

	ea8061s_shutdown(dsi);
	mipi_dsi_detach(dsi);
	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id ea8061s_of_match[] = {
	{ .compatible = "samsung,j701f-ea8061s" },
	{ }
};
MODULE_DEVICE_TABLE(of, ea8061s_of_match);

static struct mipi_dsi_driver ea8061s_driver = {
	.probe = ea8061s_probe,
	.remove = ea8061s_remove,
	.shutdown = ea8061s_shutdown,
	.driver = {
		.name = "panel-j701f-ea8061s",
		.of_match_table = ea8061s_of_match,
	},
};
module_mipi_dsi_driver(ea8061s_driver);

MODULE_DESCRIPTION("Experimental J701F EA8061S panel, fixed initial gamma, AOR brightness");
MODULE_LICENSE("GPL v2");
