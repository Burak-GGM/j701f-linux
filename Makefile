.DEFAULT_GOAL := all
.PHONY: all check-tools unpack busybox helpers initramfs repack verify test flash-plan restore-plan framebuffer-probe terminal-probe

# Phony prerequisites form an ordered chain even with make -j. Never flashes.
all: verify
check-tools:
	@./scripts/check-tools.sh
unpack: check-tools
	@./scripts/unpack.sh
busybox: unpack
	@./scripts/prepare-busybox.sh
helpers: busybox
	@./scripts/build-helpers.sh
	@./scripts/build-terminal.sh
initramfs: helpers
	@./scripts/build-initramfs.sh
repack: initramfs
	@./scripts/repack.sh
verify: repack
	@python3 tools/recovery.py verify
test: verify
	@python3 -m unittest discover -s tests -v
	@./scripts/test-busybox.sh
	@./scripts/test-display.sh
	@./scripts/test-terminal.sh
flash-plan: verify
	@./scripts/flash.sh
restore-plan: unpack
	@./scripts/flash.sh --restore
framebuffer-probe:
	@mkdir -p build
	@FB_HELPER_OUTPUT=build/fb-heartbeat-probe ./scripts/build-helpers.sh
terminal-probe:
	@mkdir -p build
	@TERMINAL_HELPER_OUTPUT=build/ondevice-terminal-probe ./scripts/build-terminal.sh
