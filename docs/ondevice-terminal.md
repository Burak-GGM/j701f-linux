# On-device C terminal and touchscreen keyboard

The updated C terminal is now installed in normal Alpine and flashed into RECOVERY. It adds a status bar, three independent PTY shells, scrollback and a mobile keyboard based on the user's reference image. Both boot paths were verified. The user confirmed keyboard, session switching and scroll work, then reported missed rapid taps. A refinement drains queued touch events before painting and uses hardware-supported monotonic event timestamps; it is installed and boot-verified, with its physical typing result still pending.

Current normal Alpine/SSH address: **192.168.1.144**. Normal Wi-Fi status code reports `wlan0 192.168.1.144`; RECOVERY remains RAM-only and does not start Wi-Fi, so `OFFLINE` there is expected. BOOT/kernel/DTBH were preserved. The complete newly boot-tested UI rescue backup and RECOVERY-only restore tar are in `build/ui-v2-fast-input/`. Previous rescue backups remain intact.

## Status and terminal sessions

- The top bar shows the clock in **UTC**, or `CLOCK UNSET` when the kernel has no valid time.
- The network line shows an active interface and its IPv4 address, `NO IP`, or `OFFLINE`. It prefers `wlan0`. These are local interface checks, not a test of Internet reachability; no network packets are sent.
- `T1`, `T2` and `T3` identify independent interactive shell sessions. The bar also displays the actual `/dev/pts/N` path. These are PTYs, not Linux virtual consoles `/dev/tty1`–`/dev/tty3`.
- Swipe **right across the terminal text** to cycle T1 → T2 → T3 → T1. Swipe left reverses the direction. Each session has its own shell, cursor, parser and output history. A shell starts when its session is first opened; background sessions continue receiving output.
- Drag **down** across the terminal text to read older output; drag up to return toward newer output. Each session keeps up to 512 previous lines. The bar displays `SCROLL N / LIVE` while browsing history. New output preserves the viewed position until the oldest retained lines are evicted.
- Tap the top bar or type a key to return to live output. Typing `exit` restarts that session's shell.

## Keyboard

The dark rounded keys use staggered QWERTY rows, wider Shift and Backspace keys, a wide Space key and a green Enter key. There are no emoji, settings or language controls. The strip above the letters contains **ESC, CTRL, ALT, TAB, LEFT, DOWN, UP, RIGHT**.

- Tap a letter, then release to type it. Hold it for about **450 ms** to type its small number or punctuation legend. A hold sends one character, without repeating it on release.
- **SHIFT** changes the next letter to uppercase. **?123** opens the symbol keyboard; Shift switches between its two pages. Together these layouts provide every printable ASCII character, including shell punctuation.
- **CTRL** and **ALT** modify the next printable key. CTRL then `c` sends Ctrl+C. ALT sends an Escape prefix.
- **TAB** requests shell completion. The arrow keys send the standard terminal arrow sequences. **BS** sends Backspace; **ENTER** submits a line.
- Sliding off a keyboard key cancels that tap. Swiping on the keyboard does not switch terminals. Only one finger is supported; additional contacts cancel the gesture.
- Hold physical **Power** for 1.2 seconds to open the existing power menu. An action requires pressing and releasing the same button. Cancel returns to the terminal.

The emulator supports printable ASCII and basic ANSI cursor movement/clearing. ANSI colors are ignored. Unicode, complete full-screen terminal emulation and automatic key repeat remain future work.

## Temporary trial after recovery

Close other USB serial clients and any manually launched Qt GUI. From the project directory, build the separate probe if needed, then run:

```sh
make terminal-probe
python3 tools/usb-console.py --test-terminal
```

The host uploads a SHA-256-checked static AArch64 binary into the phone's RAM-backed `/tmp`. The trial lasts three minutes and pauses the existing C terminal or heartbeat. It takes exclusive touchscreen input during the trial so the paused old terminal does not receive taps intended for the new layout. It also saves the existing framebuffer pixels in RAM. On normal completion it closes the trial shells, restores those pixels, releases the touchscreen and resumes the old display process. If exclusive input or the RAM snapshot cannot be obtained, the trial refuses to start. An external kill or interruption does not guarantee framebuffer restoration.

The trial itself does not mount or write phone partitions. Commands typed into its root shells are real commands and have their usual effects. Its power menu shows **TEST MODE: NO REBOOT**: action buttons highlight and log their selection without executing a reboot. Startup diagnostics and input/output counts are captured in `build/phone-terminal-test.txt`.

Check typing a short command, switching between sessions, scrolling long output, long-pressing a number hint and cancelling the power menu. Confirm the old terminal returns after the timeout. The current revision is already installed persistently; this command is for later temporary trials. Keep the verified rescue artifacts intact when testing changes.

## Offline verification and previews

```sh
make terminal-probe
TERMINAL_HELPER_OUTPUT=build/ondevice-terminal-probe ./scripts/test-terminal.sh
```

Host AddressSanitizer/UndefinedBehaviorSanitizer checks cover independent session state, bounded history, ANSI parsing, all printable ASCII keys, tap and long-press framing, swipe and scroll gestures, multi-contact cancellation, power-menu selection and framebuffer bounds. Pixel tracing verifies that cursor blinking only repaints its own cell and that switching sessions preserves the keyboard. QEMU runs the exact static AArch64 probe and starts three real interactive PTY shells, checking distinct PTY identifiers and separate shell variables.

The renderer still paints only changed cells, status text and keys. It reuses the bounds checks and red/blue correction previously confirmed on this handset. The previous revision's second physical trial eliminated the whole-screen black flashes. The user confirmed the new UI's core features work on the handset; the rapid-input refinement still needs physical confirmation.

`build/terminal-preview.png`, `build/terminal-scroll-preview.png` and `build/power-menu-preview.png` are host-rendered examples using fixed sample time, IP and shell text. They are not screenshots or evidence of current phone connectivity. `build/terminal-ui-v2-report.json` records the probe/source hashes, checks and preserved rescue hashes.

The phone previously identified `sec_touchscreen` as `/dev/input/event2`, with X 0–720 and Y 0–1280. Runtime discovery still queries device capabilities, axis ranges and multitouch slots rather than hardcoding that path or range. Samsung's early boot chain and the running kernel are outside this terminal change.
