/* Written by Claude 2026-10-10. LVGL 9.2 configuration for the J701F recovery UI.
 * Everything not set here keeps LVGL's default (lv_conf_internal.h). */
#ifndef LV_CONF_H
#define LV_CONF_H

#define LV_COLOR_DEPTH 32
#define LV_MEM_SIZE (2 * 1024 * 1024U)
#define LV_DEF_REFR_PERIOD 16
#define LV_DPI_DEF 280              /* 720x1280 on a 5.5 inch panel */

#define LV_USE_LOG 1
#define LV_LOG_LEVEL LV_LOG_LEVEL_WARN
#define LV_LOG_PRINTF 1

#define LV_FONT_MONTSERRAT_20 1
#define LV_FONT_MONTSERRAT_28 1
#define LV_FONT_MONTSERRAT_40 1
/* font_tr_*: the Turkish letters on top of the built-in fonts (gen-tr-font.py). */
#define LV_FONT_CUSTOM_DECLARE LV_FONT_DECLARE(font_tr_20) LV_FONT_DECLARE(font_tr_28) LV_FONT_DECLARE(font_tr_40)
#define LV_FONT_DEFAULT &font_tr_28

#define LV_USE_SYSMON 0

/* Files page: LVGL's file explorer on top of the POSIX file-system driver.
 * LVGL paths are "A:/..." and map to the real root directory. */
#define LV_USE_FS_POSIX 1
#define LV_FS_POSIX_LETTER 'A'
#define LV_FS_POSIX_PATH ""
#define LV_FS_POSIX_CACHE_SIZE 0
#define LV_USE_FILE_EXPLORER 1
#define LV_FILE_EXPLORER_PATH_MAX_LEN 256
#define LV_FILE_EXPLORER_QUICK_ACCESS 0
#define LV_BUILD_EXAMPLES 0

/* Back-ends: the phone build uses the framebuffer device and evdev
 * (make TARGET=phone); the computer build renders into memory for snapshots. */
#ifdef J701F_PHONE
#define LV_USE_LINUX_FBDEV 1
#define LV_USE_EVDEV 1
#endif

#endif
