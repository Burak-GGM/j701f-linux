// SPDX-License-Identifier: GPL-2.0-only
/*
 * Written by Claude 2026-10-10. J701F recovery UI, first skeleton (roadmap R.1).
 * Design: docs/recovery-design.md.
 *
 *   recovery-ui --snapshot FILE.ppm [kernel|power|files|terminal|flash:IMAGE]
 *                                     render the home screen (or the named
 *                                     page) once into a file (computer build)
 *   recovery-ui                       run on /dev/fb0 with the touchscreen
 *                                     (phone build, make TARGET=phone)
 *
 * This file only draws and dispatches. Anything that writes to storage lives
 * in separate helpers that are tested on image files first; nothing here
 * writes anywhere yet.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <pty.h>
#include <signal.h>
#include <sys/wait.h>
#include <sys/utsname.h>
#ifdef J701F_PHONE
#include <sys/ioctl.h>
#include <linux/input.h>
#endif

#include "lvgl.h"

#define W 720
#define H 1280

/* Two languages, English first (the owner's choice); see lang_load(). */
static int lang;
#define T(en, tr) (lang ? (tr) : (en))

enum page { P_BOOT, P_KERNEL, P_FILES, P_TERMINAL, P_BACKUP, P_MAINTENANCE, P_POWER };

struct tile {
	enum page page;
	const char *symbol;
	const char *title[2];
	const char *hint[2];
	uint32_t colour;
};

/* Order and wording follow the "Screens" table in docs/recovery-design.md. */
static const struct tile tiles[] = {
	{ P_BOOT, LV_SYMBOL_PLAY, { "Boot system", "Sistemi başlat" },
	  { "Start the installed Linux", "Kurulu Linux'u başlat" }, 0x2e7d32 },
	{ P_KERNEL, LV_SYMBOL_DOWNLOAD, { "Kernel", "Çekirdek" },
	  { "Installed image, flash, roll back", "Kurulu imaj, yazma, geri alma" }, 0x1565c0 },
	{ P_FILES, LV_SYMBOL_DIRECTORY, { "Files", "Dosyalar" },
	  { "Browse, copy, view", "Gözat, kopyala, görüntüle" }, 0x6a1b9a },
	{ P_TERMINAL, LV_SYMBOL_KEYBOARD, { "Terminal", "Terminal" },
	  { "Shell on screen and over USB", "Ekranda ve USB üzerinden kabuk" }, 0x37474f },
	{ P_BACKUP, LV_SYMBOL_SAVE, { "Backup", "Yedekleme" },
	  { "Save settings and folders", "Ayarları ve klasörleri kaydet" }, 0x00838f },
	{ P_MAINTENANCE, LV_SYMBOL_SETTINGS, { "Maintenance", "Bakım" },
	  { "Check filesystem, logs", "Dosya sistemi denetimi, günlükler" }, 0xef6c00 },
	{ P_POWER, LV_SYMBOL_POWER, { "Power", "Güç" },
	  { "Reboot, download mode, off", "Yeniden başlat, indirme kipi, kapat" }, 0xc62828 },
};

/*
 * The language is kept in the recovery's state directory (RAM; survives a
 * restart of this program) and, through scripts/settings.sh, in the RECOVERY
 * slot's settings block (survives a reboot).
 */
static void lang_path(char *path, size_t len)
{
	const char *dir = getenv("J701F_RECOVERY_STATE");

	snprintf(path, len, "%s/lang", dir && dir[0] ? dir : "/run/recovery-state");
}

static int run_script(const char *script, const char *args, char *out, size_t outlen);

/*
 * Order: what was chosen in this session (state directory), else
 * J701F_RECOVERY_LANG, else what scripts/settings.sh kept across reboots in
 * the RECOVERY slot's settings block, else English.
 */
static void lang_load(void)
{
	const char *env = getenv("J701F_RECOVERY_LANG");
	char path[300], word[80] = "";
	FILE *f;

	lang_path(path, sizeof(path));
	f = fopen(path, "r");
	if (f) {
		if (!fgets(word, sizeof(word), f))
			word[0] = 0;
		fclose(f);
	} else if (env) {
		snprintf(word, sizeof(word), "%s", env);
	} else if (!getenv("J701F_RECOVERY_DRYRUN")) {
		run_script("settings.sh", "get lang", word, sizeof(word));
	}
	lang = !strncmp(word, "tr", 2);
}

static void lang_save(void)
{
	char path[300];
	FILE *f;

	lang_path(path, sizeof(path));
	f = fopen(path, "w");
	if (f) {
		fputs(lang ? "tr\n" : "en\n", f);
		fclose(f);
	}
	/* and for the next boot; not when run as a program on the installed system */
	if (!getenv("J701F_RECOVERY_DRYRUN")) {
		char out[120];

		run_script("settings.sh", lang ? "set lang tr" : "set lang en", out, sizeof(out));
	}
}

/* The helper scripts print English labels; these are the ones shown as headings. */
static const char *label_tr(const char *en)
{
	static const char *const pairs[][2] = {
		{ "Running kernel", "Çalışan çekirdek" },
		{ "Built", "Derlenme" },
		{ "BOOT slot", "BOOT bölümü" },
		{ "BOOT SHA-256", "BOOT SHA-256" },
		{ "Installed image", "Kurulu imaj" },
		{ "Battery", "Pil" },
		{ "Memory", "Bellek" },
		{ "Root filesystem", "Kök dosya sistemi" },
		{ "Last crash log", "Son çökme günlüğü" },
	};
	unsigned int i;

	for (i = 0; lang && i < sizeof(pairs) / sizeof(pairs[0]); i++)
		if (!strcmp(en, pairs[i][0]))
			return pairs[i][1];
	return en;
}

static lv_obj_t *status_line;
static lv_obj_t *home_screen;

/* Helper scripts live next to the UI; J701F_RECOVERY_SCRIPTS overrides the place. */
static const char *script_dir(void)
{
	const char *d = getenv("J701F_RECOVERY_SCRIPTS");

	return d && d[0] ? d : "../scripts";
}

/* Everything the last helper script printed (its end, if it was long). */
static char script_text[3000];

/* Run "sh DIR/SCRIPT ARGS", return its last output line in @out and its exit status. */
static int run_script(const char *script, const char *args, char *out, size_t outlen)
{
	char cmd[900], line[300];
	size_t used = 0;
	FILE *f;
	int rc;

	out[0] = 0;
	script_text[0] = 0;
	snprintf(cmd, sizeof(cmd), "sh '%s/%s' %s 2>&1", script_dir(), script, args);
	f = popen(cmd, "r");
	if (!f)
		return -1;
	while (fgets(line, sizeof(line), f)) {
		size_t n = strlen(line);

		if (used + n >= sizeof(script_text)) {	/* keep the newer half */
			memmove(script_text, script_text + used / 2, used - used / 2);
			used -= used / 2;
		}
		memcpy(script_text + used, line, n + 1);
		used += n;
		line[strcspn(line, "\n")] = 0;
		if (line[0])
			snprintf(out, outlen, "%s", line);
	}
	rc = pclose(f);
	return WIFEXITED(rc) ? WEXITSTATUS(rc) : -1;
}

static void back_clicked(lv_event_t *e)
{
	lv_obj_t *page = lv_event_get_user_data(e);

	lv_screen_load(home_screen);
	lv_obj_delete_async(page);
}

/* A full-screen page with a title bar and a back button; returns its body. */
static lv_obj_t *open_page(const char *title)
{
	lv_obj_t *page = lv_obj_create(NULL);
	lv_obj_t *back = lv_button_create(page);
	lv_obj_t *arrow = lv_label_create(back);
	lv_obj_t *name = lv_label_create(page);
	lv_obj_t *body = lv_obj_create(page);

	lv_obj_set_style_bg_color(page, lv_color_hex(0x101418), 0);
	lv_obj_set_style_text_color(page, lv_color_hex(0xeceff1), 0);

	lv_obj_set_size(back, 110, 90);
	lv_obj_align(back, LV_ALIGN_TOP_LEFT, 20, 24);
	lv_obj_set_style_bg_color(back, lv_color_hex(0x263238), 0);
	lv_obj_set_style_shadow_width(back, 0, 0);
	lv_obj_add_event_cb(back, back_clicked, LV_EVENT_CLICKED, page);
	lv_label_set_text(arrow, LV_SYMBOL_LEFT);
	lv_obj_center(arrow);

	lv_obj_set_style_text_font(name, &font_tr_40, 0);
	lv_label_set_text(name, title);
	lv_obj_align(name, LV_ALIGN_TOP_LEFT, 156, 44);

	lv_obj_remove_style_all(body);
	lv_obj_set_size(body, W - 48, H - 170);
	lv_obj_align(body, LV_ALIGN_TOP_MID, 0, 150);
	lv_obj_set_flex_flow(body, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(body, 14, 0);

	lv_screen_load(page);
	return body;
}

static char selected_file[512];	/* set on the Files page */

/* One confirmed action: a helper script, its arguments, where to show the result. */
struct confirmed {
	const char *script;
	char args[600];
	lv_obj_t *result;
};

static struct confirmed pending;

static void confirm_yes(lv_event_t *e)
{
	lv_obj_t *box = lv_obj_get_parent(lv_obj_get_parent(lv_event_get_target(e)));
	char out[300];
	int rc;

	if (pending.result) {
		lv_label_set_text(pending.result, T("working...", "çalışıyor..."));
		lv_refr_now(NULL);
	}
	rc = run_script(pending.script, pending.args, out, sizeof(out));
	if (pending.result)
		lv_label_set_text_fmt(pending.result, "%s%s", rc == 0 ? "" : T("FAILED: ", "BAŞARISIZ: "),
				      out[0] ? out : T("done", "tamam"));
	lv_msgbox_close(box);
}

static void confirm_no(lv_event_t *e)
{
	lv_msgbox_close(lv_obj_get_parent(lv_obj_get_parent(lv_event_get_target(e))));
}

/* Ask once more, then run pending. */
static void ask(const char *title, const char *text)
{
	lv_obj_t *box = lv_msgbox_create(NULL);
	lv_obj_t *yes, *no;

	lv_obj_set_width(box, W - 96);
	lv_msgbox_add_title(box, title);
	lv_msgbox_add_text(box, text);
	yes = lv_msgbox_add_footer_button(box, T("Yes", "Evet"));
	no = lv_msgbox_add_footer_button(box, T("Cancel", "Vazgeç"));
	lv_obj_set_height(yes, 90);
	lv_obj_set_height(no, 90);
	lv_obj_add_event_cb(yes, confirm_yes, LV_EVENT_CLICKED, NULL);
	lv_obj_add_event_cb(no, confirm_no, LV_EVENT_CLICKED, NULL);
}

static lv_obj_t *kernel_result;

static void flash_clicked(lv_event_t *e)
{
	(void)e;
	if (!selected_file[0] || strchr(selected_file, '\'')) {
		lv_label_set_text(kernel_result, T("Choose an image on the Files page first", "Önce Dosyalar sayfasında bir imaj seçin"));
		return;
	}
	pending.script = "flash-boot.sh";
	snprintf(pending.args, sizeof(pending.args), "write '%s'", selected_file);
	pending.result = kernel_result;
	ask(T("Write this image to BOOT?", "Bu imaj BOOT'a yazılsın mı?"), selected_file);
}

static void rollback_clicked(lv_event_t *e)
{
	(void)e;
	pending.script = "flash-boot.sh";
	snprintf(pending.args, sizeof(pending.args), "rollback");
	pending.result = kernel_result;
	ask(T("Roll back", "Geri al"),
	    T("Write the previously kept image back to BOOT?", "Saklanan önceki imaj BOOT'a geri yazılsın mı?"));
}

static lv_obj_t *wide_button(lv_obj_t *parent, const char *text, uint32_t colour, lv_event_cb_t cb)
{
	lv_obj_t *b = lv_button_create(parent);
	lv_obj_t *l = lv_label_create(b);

	lv_obj_set_size(b, W - 48, 104);
	lv_obj_set_style_radius(b, 18, 0);
	lv_obj_set_style_bg_color(b, lv_color_hex(colour), 0);
	lv_obj_set_style_shadow_width(b, 0, 0);
	if (cb)
		lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, NULL);
	lv_label_set_text(l, text);
	lv_obj_align(l, LV_ALIGN_LEFT_MID, 16, 0);
	return b;
}

/*
 * Kernel page (roadmap R.3 and R.4): read-only facts from scripts/sysinfo.sh,
 * then the two actions of scripts/flash-boot.sh, each behind a confirmation.
 */
static void open_kernel_page(void)
{
	lv_obj_t *body = open_page(T("Kernel", "Çekirdek"));
	char sysinfo_cmd[700];
	char line[256];
	FILE *f;

	snprintf(sysinfo_cmd, sizeof(sysinfo_cmd), "sh '%s/sysinfo.sh'", script_dir());
	f = popen(sysinfo_cmd, "r");

	while (f && fgets(line, sizeof(line), f)) {
		char *value = strchr(line, '|');
		lv_obj_t *row, *k, *v;

		if (!value)
			continue;
		*value++ = 0;
		value[strcspn(value, "\n")] = 0;

		row = lv_obj_create(body);
		lv_obj_remove_style_all(row);
		lv_obj_set_size(row, W - 48, LV_SIZE_CONTENT);
		lv_obj_set_style_bg_color(row, lv_color_hex(0x1c2329), 0);
		lv_obj_set_style_bg_opa(row, LV_OPA_COVER, 0);
		lv_obj_set_style_radius(row, 14, 0);
		lv_obj_set_style_pad_all(row, 18, 0);
		lv_obj_set_flex_flow(row, LV_FLEX_FLOW_COLUMN);

		k = lv_label_create(row);
		lv_obj_set_style_text_font(k, &font_tr_20, 0);
		lv_obj_set_style_text_color(k, lv_color_hex(0x90a4ae), 0);
		lv_label_set_text(k, label_tr(line));

		v = lv_label_create(row);
		lv_label_set_long_mode(v, LV_LABEL_LONG_WRAP);
		lv_obj_set_width(v, W - 48 - 36);
		lv_label_set_text(v, value);
	}
	if (f)
		pclose(f);

	wide_button(body, T("Flash the selected image", "Seçili imajı yaz"), 0x1565c0, flash_clicked);
	wide_button(body, T("Roll back to the previous image", "Önceki imaja geri dön"), 0xef6c00, rollback_clicked);
	kernel_result = lv_label_create(body);
	lv_obj_set_width(kernel_result, W - 48);
	lv_label_set_long_mode(kernel_result, LV_LABEL_LONG_WRAP);
	lv_obj_set_style_text_font(kernel_result, &font_tr_20, 0);
	lv_obj_set_style_text_color(kernel_result, lv_color_hex(0x90a4ae), 0);
	lv_label_set_text(kernel_result, selected_file[0] ? selected_file : T("no image selected", "imaj seçilmedi"));
}

/*
 * Power page (roadmap R.7). Every action asks once more before it runs, and
 * runs through scripts/power.sh so that the same code path can be dry-run.
 */
struct power_action {
	const char *label[2];
	const char *arg;
	uint32_t colour;
};

static const struct power_action power_actions[] = {
	{ { "Reboot into the system", "Sisteme yeniden başlat" },         "system",   0x2e7d32 },
	{ { "Reboot into recovery", "Kurtarmaya yeniden başlat" },        "recovery", 0x1565c0 },
	{ { "Reboot into download mode", "İndirme kipine yeniden başlat" }, "download", 0xef6c00 },
	{ { "Power off", "Kapat" },                                       "off",      0xc62828 },
};

static lv_obj_t *power_result;

static void power_confirmed(lv_event_t *e)
{
	const struct power_action *a = lv_event_get_user_data(e);
	lv_obj_t *box = lv_obj_get_parent(lv_obj_get_parent(lv_event_get_target(e)));
	char out[160];

	run_script("power.sh", a->arg, out, sizeof(out));
	if (power_result)
		lv_label_set_text(power_result, out[0] ? out : T("done", "tamam"));
	lv_msgbox_close(box);
}

static void power_cancelled(lv_event_t *e)
{
	lv_msgbox_close(lv_obj_get_parent(lv_obj_get_parent(lv_event_get_target(e))));
}

static void power_clicked(lv_event_t *e)
{
	const struct power_action *a = lv_event_get_user_data(e);
	lv_obj_t *box = lv_msgbox_create(NULL);
	lv_obj_t *yes, *no;

	lv_obj_set_width(box, W - 96);
	lv_msgbox_add_title(box, a->label[lang]);
	lv_msgbox_add_text(box, T("Do this now?", "Şimdi yapılsın mı?"));
	yes = lv_msgbox_add_footer_button(box, T("Yes", "Evet"));
	no = lv_msgbox_add_footer_button(box, T("Cancel", "Vazgeç"));
	lv_obj_set_height(yes, 90);
	lv_obj_set_height(no, 90);
	lv_obj_add_event_cb(yes, power_confirmed, LV_EVENT_CLICKED, (void *)a);
	lv_obj_add_event_cb(no, power_cancelled, LV_EVENT_CLICKED, NULL);
}

static void open_power_page(void)
{
	lv_obj_t *body = open_page(T("Power", "Güç"));
	unsigned int i;

	for (i = 0; i < sizeof(power_actions) / sizeof(power_actions[0]); i++) {
		lv_obj_t *b = lv_button_create(body);
		lv_obj_t *l = lv_label_create(b);

		lv_obj_set_size(b, W - 48, 120);
		lv_obj_set_style_radius(b, 18, 0);
		lv_obj_set_style_bg_color(b, lv_color_hex(power_actions[i].colour), 0);
		lv_obj_set_style_shadow_width(b, 0, 0);
		lv_obj_add_event_cb(b, power_clicked, LV_EVENT_CLICKED, (void *)&power_actions[i]);
		lv_label_set_text(l, power_actions[i].label[lang]);
		lv_obj_align(l, LV_ALIGN_LEFT_MID, 16, 0);
	}
	power_result = lv_label_create(body);
	lv_obj_set_style_text_font(power_result, &font_tr_20, 0);
	lv_obj_set_style_text_color(power_result, lv_color_hex(0x90a4ae), 0);
	lv_label_set_text(power_result, "");
}

/*
 * Terminal page (roadmap R.2): a shell on a pseudo-terminal. Output is shown
 * as plain text (escape sequences are dropped); input is typed on LVGL's
 * on-screen keyboard and sent a line at a time. Enough for commands and
 * logs; full-screen programs are for the USB shell.
 */
#define TERM_KEEP 6000

static int term_fd = -1;
static pid_t term_pid;
static lv_obj_t *term_out, *term_in;
static lv_timer_t *term_timer;
static char term_buf[TERM_KEEP + 1];
static size_t term_len;

static void term_append(const char *data, size_t n)
{
	static int esc;		/* 0 text, 1 after ESC, 2 inside CSI */
	size_t i;

	for (i = 0; i < n; i++) {
		unsigned char c = data[i];

		if (esc == 1) {
			esc = (c == '[') ? 2 : 0;
			continue;
		}
		if (esc == 2) {
			if (c >= 0x40 && c <= 0x7e)
				esc = 0;
			continue;
		}
		if (c == 0x1b) {
			esc = 1;
			continue;
		}
		if (c == '\r' || (c < 0x20 && c != '\n' && c != '\t'))
			continue;
		if (term_len == TERM_KEEP) {	/* drop the oldest half */
			memmove(term_buf, term_buf + TERM_KEEP / 2, TERM_KEEP / 2);
			term_len = TERM_KEEP / 2;
		}
		term_buf[term_len++] = c;
	}
	term_buf[term_len] = 0;
}

static void term_poll(lv_timer_t *t)
{
	char chunk[1024];
	ssize_t n;
	int got = 0;

	(void)t;
	while (term_fd >= 0 && (n = read(term_fd, chunk, sizeof(chunk))) > 0) {
		term_append(chunk, n);
		got = 1;
	}
	if (got && term_out) {
		lv_label_set_text_static(term_out, term_buf);
		lv_obj_scroll_to_y(lv_obj_get_parent(term_out), LV_COORD_MAX, LV_ANIM_OFF);
	}
}

static void term_stop(lv_event_t *e)
{
	(void)e;
	if (term_timer)
		lv_timer_delete(term_timer);
	term_timer = NULL;
	if (term_fd >= 0)
		close(term_fd);
	term_fd = -1;
	if (term_pid > 0) {
		kill(term_pid, SIGHUP);
		waitpid(term_pid, NULL, WNOHANG);
	}
	term_pid = 0;
	term_out = term_in = NULL;
}

static void term_send_line(lv_event_t *e)
{
	const char *line = lv_textarea_get_text(term_in);

	(void)e;
	if (term_fd >= 0) {
		if (write(term_fd, line, strlen(line)) < 0 || write(term_fd, "\n", 1) < 0)
			term_append("\n[write to the shell failed]\n", 31);
	}
	lv_textarea_set_text(term_in, "");
}

static void open_terminal_page(void)
{
	lv_obj_t *body = open_page("Terminal");
	lv_obj_t *page = lv_obj_get_parent(body);
	lv_obj_t *view = lv_obj_create(body);
	lv_obj_t *kb;

	lv_obj_remove_style_all(view);
	lv_obj_set_size(view, W - 48, 520);
	lv_obj_set_style_bg_color(view, lv_color_hex(0x000000), 0);
	lv_obj_set_style_bg_opa(view, LV_OPA_COVER, 0);
	lv_obj_set_style_radius(view, 10, 0);
	lv_obj_set_style_pad_all(view, 12, 0);
	lv_obj_add_flag(view, LV_OBJ_FLAG_SCROLLABLE);

	term_out = lv_label_create(view);
	lv_obj_set_width(term_out, W - 48 - 24);
	lv_label_set_long_mode(term_out, LV_LABEL_LONG_WRAP);
	lv_obj_set_style_text_font(term_out, &font_tr_20, 0);
	lv_obj_set_style_text_color(term_out, lv_color_hex(0xcfd8dc), 0);
	term_len = 0;
	term_buf[0] = 0;
	lv_label_set_text_static(term_out, term_buf);

	term_in = lv_textarea_create(body);
	lv_obj_set_size(term_in, W - 48, 76);
	lv_textarea_set_one_line(term_in, true);
	lv_textarea_set_placeholder_text(term_in, T("command", "komut"));
	lv_obj_set_style_bg_color(term_in, lv_color_hex(0x1c2329), 0);
	lv_obj_set_style_text_color(term_in, lv_color_hex(0xeceff1), 0);
	lv_obj_set_style_border_color(term_in, lv_color_hex(0x546e7a), 0);
	lv_obj_add_event_cb(term_in, term_send_line, LV_EVENT_READY, NULL);

	kb = lv_keyboard_create(page);
	lv_obj_set_size(kb, W, 440);
	lv_keyboard_set_textarea(kb, term_in);
	/* Tight, dark keys: LVGL's default leaves wide gaps at this size. */
	lv_obj_set_style_bg_color(kb, lv_color_hex(0x1c2329), 0);
	lv_obj_set_style_pad_all(kb, 6, 0);
	lv_obj_set_style_pad_gap(kb, 6, 0);
	lv_obj_set_style_bg_color(kb, lv_color_hex(0x37474f), LV_PART_ITEMS);
	lv_obj_set_style_text_color(kb, lv_color_hex(0xeceff1), LV_PART_ITEMS);
	lv_obj_set_style_radius(kb, 8, LV_PART_ITEMS);
	lv_obj_set_style_shadow_width(kb, 0, LV_PART_ITEMS);
	lv_obj_set_style_bg_color(kb, lv_color_hex(0x546e7a), LV_PART_ITEMS | LV_STATE_PRESSED);
	lv_obj_set_style_bg_color(kb, lv_color_hex(0x263238), LV_PART_ITEMS | LV_STATE_CHECKED);
	lv_obj_set_style_text_color(kb, lv_color_hex(0xb0bec5), LV_PART_ITEMS | LV_STATE_CHECKED);
	lv_obj_set_style_text_color(kb, lv_color_hex(0xb0bec5), LV_PART_ITEMS | LV_STATE_DISABLED);
	lv_obj_set_style_text_opa(kb, LV_OPA_COVER, LV_PART_ITEMS | LV_STATE_CHECKED);

	term_pid = forkpty(&term_fd, NULL, NULL, NULL);
	if (term_pid == 0) {
		setenv("TERM", "dumb", 1);
		setenv("PS1", "# ", 1);
		execl("/bin/sh", "sh", (char *)NULL);
		_exit(127);
	}
	if (term_pid < 0) {
		term_fd = -1;
		term_append("could not start a shell\n", 24);
	} else {
		fcntl(term_fd, F_SETFL, fcntl(term_fd, F_GETFL) | O_NONBLOCK);
	}
	term_timer = lv_timer_create(term_poll, 50, NULL);
	lv_obj_add_event_cb(page, term_stop, LV_EVENT_DELETE, NULL);
}

/*
 * Files page (roadmap R.5), first step: browse only. The start directory can
 * be overridden with J701F_RECOVERY_FILES (tests); the selected file's path is
 * shown and kept for the pages that will act on it (view, copy, flash).
 */
static lv_obj_t *files_selected;

static void file_chosen(lv_event_t *e)
{
	lv_obj_t *ex = lv_event_get_target(e);
	const char *dir = lv_file_explorer_get_current_path(ex);
	const char *name = lv_file_explorer_get_selected_file_name(ex);

	/* LVGL paths start with the drive letter and a colon. */
	snprintf(selected_file, sizeof(selected_file), "%s%s", dir + 2, name);
	if (files_selected)
		lv_label_set_text(files_selected, selected_file);
}

/* Show the beginning of the selected file as text. */
static void view_clicked(lv_event_t *e)
{
	static char text[2500];
	size_t n, i;
	FILE *f;

	(void)e;
	if (!selected_file[0])
		return;
	f = fopen(selected_file, "r");
	if (!f) {
		lv_label_set_text_fmt(files_selected, "%s: %s", selected_file, strerror(errno));
		return;
	}
	n = fread(text, 1, sizeof(text) - 1, f);
	fclose(f);
	for (i = 0; i < n; i++)		/* binary files must not break the label */
		if ((unsigned char)text[i] < 0x20 && text[i] != '\n' && text[i] != '\t')
			text[i] = '.';
	text[n] = 0;
	lv_label_set_text_static(files_selected, text);
}

static void copy_clicked(lv_event_t *e)
{
	(void)e;
	if (!selected_file[0] || strchr(selected_file, '\''))
		return;
	pending.script = "storage.sh";
	snprintf(pending.args, sizeof(pending.args), "copy '%s'", selected_file);
	pending.result = files_selected;
	ask(T("Copy to the SD card?", "SD karta kopyalansın mı?"), selected_file);
}

static void open_files_page(void)
{
	lv_obj_t *body = open_page(T("Files", "Dosyalar"));
	const char *start = getenv("J701F_RECOVERY_FILES");
	lv_obj_t *ex = lv_file_explorer_create(body);
	char path[300];

	lv_obj_t *row, *b;
	char out[300];

	/* In the recovery the installed system is not mounted until it is needed
	 * (read-only, at /mnt/root). Not when this runs as a program on that system. */
	if (!getenv("J701F_RECOVERY_DRYRUN"))
		run_script("storage.sh", "mount-root", out, sizeof(out));

	lv_obj_set_size(ex, W - 48, H - 520);
	lv_file_explorer_set_sort(ex, LV_EXPLORER_SORT_KIND);
	snprintf(path, sizeof(path), "A:%s", start && start[0] == '/' ? start : "/");
	lv_file_explorer_open_dir(ex, path);
	lv_obj_add_event_cb(ex, file_chosen, LV_EVENT_VALUE_CHANGED, NULL);

	row = lv_obj_create(body);
	lv_obj_remove_style_all(row);
	lv_obj_set_size(row, W - 48, 96);
	lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
	lv_obj_set_style_pad_column(row, 14, 0);
	b = wide_button(row, T("View", "Görüntüle"), 0x37474f, view_clicked);
	lv_obj_set_size(b, (W - 48 - 14) / 2, 96);
	b = wide_button(row, T("Copy to SD card", "SD karta kopyala"), 0x6a1b9a, copy_clicked);
	lv_obj_set_size(b, (W - 48 - 14) / 2, 96);

	files_selected = lv_label_create(body);
	lv_obj_set_width(files_selected, W - 48);
	lv_label_set_long_mode(files_selected, LV_LABEL_LONG_WRAP);
	lv_obj_set_style_text_font(files_selected, &font_tr_20, 0);
	lv_obj_set_style_text_color(files_selected, lv_color_hex(0x90a4ae), 0);
	lv_label_set_text(files_selected, T("tap a file to select it", "seçmek için bir dosyaya dokunun"));
}

/*
 * Backup (R.6) and Maintenance (R.7): each button runs one action of
 * scripts/storage.sh and shows what it printed. The installed system is only
 * read; the SD card is the only thing written, and only after a confirmation.
 */
struct storage_action {
	const char *script;
	const char *label[2];
	const char *arg;
	const char *question[2];	/* NULL: read-only, runs at once */
	uint32_t colour;
};

static const struct storage_action backup_actions[] = {
	{ "storage.sh", { "Back up to the SD card", "SD karta yedekle" }, "backup",
	  { "Save /etc and the user's settings to the SD card? The archive contains saved passwords.",
	    "/etc ve kullanıcı ayarları SD karta kaydedilsin mi? Arşiv kayıtlı parolaları içerir." }, 0x00838f },
	{ "storage.sh", { "Verify the newest backup", "Son yedeği doğrula" }, "verify", { NULL, NULL }, 0x37474f },
};

static const struct storage_action maintenance_actions[] = {
	{ "storage.sh", { "Check the filesystem (read-only)", "Dosya sistemini denetle (salt okunur)" }, "check", { NULL, NULL }, 0xef6c00 },
	{ "storage.sh", { "Show the kernel log", "Çekirdek günlüğünü göster" }, "log", { NULL, NULL }, 0x37474f },
	{ "wifi.sh", { "Wi-Fi: status", "Wi-Fi: durum" }, "status", { NULL, NULL }, 0x1565c0 },
	{ "wifi.sh", { "Wi-Fi and SSH: on", "Wi-Fi ve SSH: aç" }, "up", { NULL, NULL }, 0x2e7d32 },
	{ "wifi.sh", { "Wi-Fi and SSH: off", "Wi-Fi ve SSH: kapat" }, "down", { NULL, NULL }, 0x37474f },
};

static lv_obj_t *storage_result;

static void storage_clicked(lv_event_t *e)
{
	const struct storage_action *a = lv_event_get_user_data(e);
	char out[300];

	if (a->question[0]) {
		pending.script = a->script;
		snprintf(pending.args, sizeof(pending.args), "%s", a->arg);
		pending.result = storage_result;
		ask(a->label[lang], a->question[lang]);
		return;
	}
	lv_label_set_text(storage_result, T("working...", "çalışıyor..."));
	lv_refr_now(NULL);
	run_script(a->script, a->arg, out, sizeof(out));
	lv_label_set_text(storage_result, script_text[0] ? script_text : T("no output", "çıktı yok"));
}

static void open_storage_page(const char *title, const struct storage_action *actions, unsigned int n)
{
	lv_obj_t *body = open_page(title);
	unsigned int i;

	for (i = 0; i < n; i++) {
		lv_obj_t *b = wide_button(body, actions[i].label[lang], actions[i].colour, NULL);

		lv_obj_add_event_cb(b, storage_clicked, LV_EVENT_CLICKED, (void *)&actions[i]);
	}
	storage_result = lv_label_create(body);
	lv_obj_set_width(storage_result, W - 48);
	lv_label_set_long_mode(storage_result, LV_LABEL_LONG_WRAP);
	lv_obj_set_style_text_font(storage_result, &font_tr_20, 0);
	lv_obj_set_style_text_color(storage_result, lv_color_hex(0x90a4ae), 0);
	lv_label_set_text(storage_result, "");
}

/* Somebody is operating the recovery: tells /init not to boot the system by itself. */
static void used(void)
{
	static int told;

	if (!told && access("/run/recovery-state", F_OK) == 0) {
		FILE *f = fopen("/run/recovery-touched", "w");

		if (f)
			fclose(f);
		told = 1;
	}
}

static void tile_clicked(lv_event_t *e)
{
	const struct tile *t = lv_event_get_user_data(e);

	used();
	if (t->page == P_BOOT) {
		/* /init waits for this file (kernel/diagnostic/recovery-main). */
		const char *flag = getenv("J701F_RECOVERY_BOOT_FLAG");
		const char *dry = getenv("J701F_RECOVERY_DRYRUN");
		FILE *f;

		if (dry && dry[0] == '1') {
			lv_label_set_text(status_line, T("dry run: would boot the system now", "deneme: sistem şimdi başlatılırdı"));
			return;
		}
		f = fopen(flag && flag[0] ? flag : "/run/boot-system", "w");
		if (!f) {
			lv_label_set_text(status_line, T("could not ask /init to boot the system", "/init'e sistemi başlatması söylenemedi"));
			return;
		}
		fclose(f);
		exit(0);
	}
	if (t->page == P_KERNEL) {
		open_kernel_page();
		return;
	}
	if (t->page == P_POWER) {
		open_power_page();
		return;
	}
	if (t->page == P_TERMINAL) {
		open_terminal_page();
		return;
	}
	if (t->page == P_FILES) {
		open_files_page();
		return;
	}
	if (t->page == P_BACKUP)
		open_storage_page(t->title[lang], backup_actions, 2);
	if (t->page == P_MAINTENANCE)
		open_storage_page(t->title[lang], maintenance_actions, 5);
}

static void build_home(void);

static void lang_clicked(lv_event_t *e)
{
	(void)e;
	lang = !lang;
	lang_save();
	lv_obj_clean(home_screen);
	build_home();
}

static void build_home(void)
{
	lv_obj_t *scr = lv_screen_active();
	lv_obj_t *head, *title, *grid, *lb, *ll;
	struct utsname u;
	unsigned int i;

	home_screen = scr;

	lv_obj_set_style_bg_color(scr, lv_color_hex(0x101418), 0);
	lv_obj_set_style_text_color(scr, lv_color_hex(0xeceff1), 0);

	head = lv_obj_create(scr);
	lv_obj_remove_style_all(head);
	lv_obj_set_size(head, W, 150);
	lv_obj_align(head, LV_ALIGN_TOP_MID, 0, 0);

	title = lv_label_create(head);
	lv_obj_set_style_text_font(title, &font_tr_40, 0);
	lv_label_set_text(title, T("J701F Recovery", "J701F Kurtarma"));
	lv_obj_align(title, LV_ALIGN_TOP_LEFT, 32, 28);

	/* The button names the language it switches to. */
	lb = lv_button_create(head);
	ll = lv_label_create(lb);
	lv_obj_set_size(lb, 150, 84);
	lv_obj_align(lb, LV_ALIGN_TOP_RIGHT, -24, 28);
	lv_obj_set_style_bg_color(lb, lv_color_hex(0x263238), 0);
	lv_obj_set_style_shadow_width(lb, 0, 0);
	lv_obj_add_event_cb(lb, lang_clicked, LV_EVENT_CLICKED, NULL);
	lv_label_set_text(ll, T("Türkçe", "English"));
	lv_obj_center(ll);

	status_line = lv_label_create(head);
	lv_obj_set_style_text_font(status_line, &font_tr_20, 0);
	lv_obj_set_style_text_color(status_line, lv_color_hex(0x90a4ae), 0);
	if (uname(&u) == 0)
		lv_label_set_text_fmt(status_line, T("running on Linux %s", "Linux %s üzerinde"), u.release);
	else
		lv_label_set_text(status_line, "");
	lv_obj_align(status_line, LV_ALIGN_TOP_LEFT, 34, 92);

	grid = lv_obj_create(scr);
	lv_obj_remove_style_all(grid);
	lv_obj_set_size(grid, W - 48, H - 190);
	lv_obj_align(grid, LV_ALIGN_TOP_MID, 0, 160);
	lv_obj_set_flex_flow(grid, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(grid, 18, 0);

	for (i = 0; i < sizeof(tiles) / sizeof(tiles[0]); i++) {
		lv_obj_t *b = lv_button_create(grid);
		lv_obj_t *sym = lv_label_create(b);
		lv_obj_t *name = lv_label_create(b);
		lv_obj_t *hint = lv_label_create(b);

		lv_obj_set_size(b, W - 48, 132);
		lv_obj_set_style_radius(b, 18, 0);
		lv_obj_set_style_bg_color(b, lv_color_hex(tiles[i].colour), 0);
		lv_obj_set_style_shadow_width(b, 0, 0);
		lv_obj_add_event_cb(b, tile_clicked, LV_EVENT_CLICKED, (void *)&tiles[i]);

		lv_obj_set_style_text_font(sym, &font_tr_40, 0);
		lv_label_set_text(sym, tiles[i].symbol);
		lv_obj_align(sym, LV_ALIGN_LEFT_MID, 12, 0);

		lv_label_set_text(name, tiles[i].title[lang]);
		lv_obj_align(name, LV_ALIGN_TOP_LEFT, 96, 14);

		lv_obj_set_style_text_font(hint, &font_tr_20, 0);
		lv_obj_set_style_text_opa(hint, LV_OPA_80, 0);
		lv_label_set_text(hint, tiles[i].hint[lang]);
		lv_obj_align(hint, LV_ALIGN_TOP_LEFT, 96, 62);
	}
}

#ifdef J701F_PHONE
/*
 * Touch input. LVGL's own evdev reader reports only the state left after it
 * has drained the queue, so a tap whose press and release arrive between two
 * reads is never seen (the "first tap is lost" defect of the first trial).
 * This reader stops at every change of state and asks to be called again.
 */
static int touch_fd = -1;
static int touch_max_x = W - 1, touch_max_y = H - 1;

static void touch_read(lv_indev_t *indev, lv_indev_data_t *data)
{
	static int x, y, down, shown;
	struct input_event ev;

	(void)indev;
	while (touch_fd >= 0 && read(touch_fd, &ev, sizeof(ev)) == sizeof(ev)) {
		if (ev.type == EV_ABS && (ev.code == ABS_MT_POSITION_X || ev.code == ABS_X))
			x = ev.value;
		else if (ev.type == EV_ABS && (ev.code == ABS_MT_POSITION_Y || ev.code == ABS_Y))
			y = ev.value;
		else if (ev.type == EV_ABS && ev.code == ABS_MT_TRACKING_ID)
			down = ev.value >= 0;
		else if (ev.type == EV_KEY && ev.code == BTN_TOUCH)
			down = ev.value != 0;
		else if (ev.type == EV_SYN && ev.code == SYN_REPORT && down != shown) {
			shown = down;
			used();
			data->continue_reading = true;
			break;
		}
	}
	data->state = shown ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
	data->point.x = (int32_t)x * (W - 1) / touch_max_x;
	data->point.y = (int32_t)y * (H - 1) / touch_max_y;
}

static void touch_open(const char *dev)
{
	struct input_absinfo abs;
	lv_indev_t *indev;

	touch_fd = open(dev, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
	if (touch_fd < 0) {
		fprintf(stderr, "recovery-ui: %s: %s\n", dev, strerror(errno));
		return;
	}
	if (!ioctl(touch_fd, EVIOCGABS(ABS_MT_POSITION_X), &abs) && abs.maximum > 0)
		touch_max_x = abs.maximum;
	if (!ioctl(touch_fd, EVIOCGABS(ABS_MT_POSITION_Y), &abs) && abs.maximum > 0)
		touch_max_y = abs.maximum;
	indev = lv_indev_create();
	lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
	lv_indev_set_read_cb(indev, touch_read);
}

/*
 * Hardware keys, for a recovery whose touchscreen does not answer: volume
 * down / up move the focus, power or home activates. Every input device that
 * has one of these keys is read.
 */
static int key_fds[8];
static int key_count;

static void keys_read(lv_indev_t *indev, lv_indev_data_t *data)
{
	static uint32_t key = LV_KEY_NEXT;
	static int down;
	struct input_event ev;
	int i;

	(void)indev;
	for (i = 0; i < key_count; i++) {
		while (read(key_fds[i], &ev, sizeof(ev)) == sizeof(ev)) {
			uint32_t k = 0;

			if (ev.type != EV_KEY || ev.value > 1)
				continue;
			if (ev.code == KEY_VOLUMEDOWN)
				k = LV_KEY_NEXT;
			else if (ev.code == KEY_VOLUMEUP)
				k = LV_KEY_PREV;
			/* the board's device tree reports the Home key as KEY_LEFTMETA (for Plasma) */
			else if (ev.code == KEY_POWER || ev.code == KEY_HOMEPAGE || ev.code == KEY_HOME ||
				 ev.code == KEY_LEFTMETA || ev.code == KEY_ENTER)
				k = LV_KEY_ENTER;
			if (!k)
				continue;
			key = k;
			down = ev.value;
			used();
			data->continue_reading = true;
			goto out;
		}
	}
out:
	data->key = key;
	data->state = down ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

static void keys_open(const char *touch_dev)
{
	lv_indev_t *indev;
	int n;

	for (n = 0; n < 16 && key_count < 8; n++) {
		unsigned long bits[KEY_MAX / (8 * sizeof(long)) + 1] = { 0 };
		char dev[40];
		int fd;

		snprintf(dev, sizeof(dev), "/dev/input/event%d", n);
		if (!strcmp(dev, touch_dev))
			continue;
		fd = open(dev, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
		if (fd < 0)
			continue;
#define HAS(k) (bits[(k) / (8 * sizeof(long))] >> ((k) % (8 * sizeof(long))) & 1)
		if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(bits)), bits) < 0 ||
		    !(HAS(KEY_VOLUMEDOWN) || HAS(KEY_VOLUMEUP) || HAS(KEY_POWER) || HAS(KEY_HOMEPAGE) || HAS(KEY_LEFTMETA))) {
			close(fd);
			continue;
		}
#undef HAS
		key_fds[key_count++] = fd;
	}
	if (!key_count)
		return;
	indev = lv_indev_create();
	lv_indev_set_type(indev, LV_INDEV_TYPE_KEYPAD);
	lv_indev_set_read_cb(indev, keys_read);
	lv_indev_set_group(indev, lv_group_get_default());
}
#endif

#ifndef J701F_PHONE
/* Computer build: render into memory and write a PPM, for tests and review. */
static uint8_t fb[W * H * 4];

static void flush_to_memory(lv_display_t *d, const lv_area_t *a, uint8_t *px)
{
	int32_t y, w = lv_area_get_width(a);

	for (y = a->y1; y <= a->y2; y++, px += w * 4)
		memcpy(&fb[(y * W + a->x1) * 4], px, w * 4);
	lv_display_flush_ready(d);
}

static int snapshot(const char *path, const char *screen)
{
	static uint8_t draw[W * 64 * 4];
	lv_display_t *d = lv_display_create(W, H);
	FILE *f;
	int i;

	lv_display_set_buffers(d, draw, NULL, sizeof(draw), LV_DISPLAY_RENDER_MODE_PARTIAL);
	lv_display_set_flush_cb(d, flush_to_memory);
	lang_load();
	build_home();
	if (screen && !strcmp(screen, "kernel"))
		open_kernel_page();
	if (screen && !strcmp(screen, "power"))
		open_power_page();
	if (screen && !strcmp(screen, "files"))
		open_files_page();
	if (screen && (!strncmp(screen, "backup", 6) || !strncmp(screen, "maintenance", 11))) {
		/* "backup:verify", "maintenance:log": also run that action as if confirmed */
		const char *act = strchr(screen, ':');
		char out[300];

		if (screen[0] == 'b')
			open_storage_page(T("Backup", "Yedekleme"), backup_actions, 2);
		else
			open_storage_page(T("Maintenance", "Bakım"), maintenance_actions, 5);
		if (act) {
			run_script("storage.sh", act + 1, out, sizeof(out));
			lv_label_set_text(storage_result, script_text);
		}
	}
	if (screen && !strncmp(screen, "flash:", 6)) {
		/* test hook: act as if the file had been chosen and "Yes" tapped */
		char out[300];

		snprintf(selected_file, sizeof(selected_file), "%s", screen + 6);
		open_kernel_page();
		snprintf(pending.args, sizeof(pending.args), "write '%s'", selected_file);
		lv_label_set_text_fmt(kernel_result, "%s%s",
				      run_script("flash-boot.sh", pending.args, out, sizeof(out)) ? "FAILED: " : "", out);
	}
	if (screen && !strcmp(screen, "terminal")) {
		/* test hook: run one command through the page's own input path */
		open_terminal_page();
		lv_textarea_set_text(term_in, "echo recovery-terminal-ok; uname -s");
		term_send_line(NULL);
		for (i = 0; i < 30; i++) {
			usleep(20000);
			lv_tick_inc(50);
			lv_timer_handler();
		}
	}
	for (i = 0; i < 10; i++) {
		lv_tick_inc(16);
		lv_timer_handler();
	}
	f = fopen(path, "wb");
	if (!f)
		return 1;
	fprintf(f, "P6\n%d %d\n255\n", W, H);
	for (i = 0; i < W * H; i++) {
		fputc(fb[i * 4 + 2], f);
		fputc(fb[i * 4 + 1], f);
		fputc(fb[i * 4 + 0], f);
	}
	return fclose(f) != 0;
}
#endif

int main(int argc, char **argv)
{
	lv_init();
#ifndef J701F_PHONE
	if (argc >= 3 && !strcmp(argv[1], "--snapshot"))
		return snapshot(argv[2], argc > 3 ? argv[3] : NULL);
	fprintf(stderr, "usage: %s --snapshot FILE.ppm [kernel]\n", argv[0]);
	return 2;
#else
	{
		lv_display_t *d = lv_linux_fbdev_create();

		lv_linux_fbdev_set_file(d, "/dev/fb0");
		touch_open(argc > 1 ? argv[1] : "/dev/input/event0");
		/* every button made from here on can be reached with the keys */
		lv_group_set_default(lv_group_create());
		keys_open(argc > 1 ? argv[1] : "/dev/input/event0");
		lang_load();
		build_home();
		for (;;) {
			uint32_t wait = lv_timer_handler();

			usleep((wait > 20 ? 20 : wait) * 1000);
		}
	}
#endif
}
