# Written by Claude 2026-10-10. Builds the recovery UI.
#   make                 computer build (renders snapshots, no display needed)
#   make TARGET=phone    native build on the phone (framebuffer + touchscreen)
LVGL ?= ../../build/third-party/lvgl-src
OUT  ?= ../../build/recovery-ui/$(if $(TARGET),$(TARGET),host)
CC   ?= cc
CFLAGS += -O2 -Wall -I. -I$(LVGL) -DLV_CONF_INCLUDE_SIMPLE $(if $(filter phone,$(TARGET)),-DJ701F_PHONE)
SRCS := $(shell find $(LVGL)/src -name '*.c')
OBJS := $(patsubst $(LVGL)/%.c,$(OUT)/lvgl/%.o,$(SRCS)) $(OUT)/main.o $(OUT)/font_tr.o

$(OUT)/recovery-ui: $(OBJS)
	@$(CC) -o $@ $(OBJS) -lm -lutil $(if $(filter phone,$(TARGET)),-static)

$(OUT)/lvgl/%.o: $(LVGL)/%.c lv_conf.h
	@mkdir -p $(dir $@)
	@$(CC) $(CFLAGS) -c -o $@ $<

# font_tr.c is generated on the computer (needs Python with Pillow) and kept in
# the repository, so the build on the phone does not need the generator.
font_tr.c: $(wildcard gen-tr-font.py)
	python3 gen-tr-font.py $(LVGL) $@

$(OUT)/%.o: %.c lv_conf.h
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<
