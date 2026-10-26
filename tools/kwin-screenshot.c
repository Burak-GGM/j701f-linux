/* Written by Claude 2026-10-09. Remote screenshot helper for the phone's
 * Plasma session: calls org.kde.KWin.ScreenShot2.CaptureWorkspace and writes
 * the raw pixels to a file. KWin only serves callers whose executable is named
 * in a .desktop file with X-KDE-DBUS-Restricted-Interfaces listing the
 * interface. Build on the phone: cc kwin-screenshot.c $(pkg-config --cflags
 * --libs dbus-1) -o kwin-screenshot ; usage: kwin-screenshot OUT.raw
 * Prints "width height stride format" (QImage::Format) on success.
 */
#include <dbus/dbus.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc != 2) { fprintf(stderr, "usage: %s OUT.raw\n", argv[0]); return 2; }
    int fd = open(argv[1], O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) { perror("open"); return 1; }
    DBusError error; dbus_error_init(&error);
    DBusConnection *bus = dbus_bus_get(DBUS_BUS_SESSION, &error);
    if (!bus) { fprintf(stderr, "bus: %s\n", error.message); return 1; }
    DBusMessage *call = dbus_message_new_method_call("org.kde.KWin", "/org/kde/KWin/ScreenShot2",
                                                     "org.kde.KWin.ScreenShot2", "CaptureWorkspace");
    DBusMessageIter args, options;
    dbus_message_iter_init_append(call, &args);
    dbus_message_iter_open_container(&args, DBUS_TYPE_ARRAY, "{sv}", &options);
    dbus_message_iter_close_container(&args, &options);
    dbus_message_iter_append_basic(&args, DBUS_TYPE_UNIX_FD, &fd);
    DBusMessage *reply = dbus_connection_send_with_reply_and_block(bus, call, 15000, &error);
    if (!reply) { fprintf(stderr, "call: %s\n", error.message); return 1; }
    unsigned width = 0, height = 0, stride = 0, format = 0;
    DBusMessageIter top, dict;
    dbus_message_iter_init(reply, &top);
    dbus_message_iter_recurse(&top, &dict);
    while (dbus_message_iter_get_arg_type(&dict) == DBUS_TYPE_DICT_ENTRY) {
        DBusMessageIter entry, value; const char *key; dbus_uint32_t number = 0;
        dbus_message_iter_recurse(&dict, &entry);
        dbus_message_iter_get_basic(&entry, &key);
        dbus_message_iter_next(&entry);
        dbus_message_iter_recurse(&entry, &value);
        if (dbus_message_iter_get_arg_type(&value) == DBUS_TYPE_UINT32) {
            dbus_message_iter_get_basic(&value, &number);
            if (!strcmp(key, "width")) width = number;
            else if (!strcmp(key, "height")) height = number;
            else if (!strcmp(key, "stride")) stride = number;
            else if (!strcmp(key, "format")) format = number;
        }
        dbus_message_iter_next(&dict);
    }
    printf("%u %u %u %u\n", width, height, stride, format);
    return 0;
}
