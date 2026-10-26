// Written by Claude 2026-10-10. KWin side of the J701F background-application
// freezer: reports window activity to the j701f-freezer.py daemon over D-Bus.
// Loaded by the daemon through org.kde.KWin /Scripting; see that file.
var S = "org.j701f.Freezer", P = "/Freezer", I = "org.j701f.Freezer";

function tell(method, w) {
    if (!w) {
        callDBus(S, P, I, method, "0", "");
        return;
    }
    callDBus(S, P, I, method, String(w.pid), String(w.resourceClass));
}

function watch(w) {
    if (!w || !w.normalWindow)
        return;
    tell("Seen", w);
    w.unresponsiveChanged.connect(function () {
        if (w.unresponsive)
            tell("Unresponsive", w);
    });
}

workspace.windowAdded.connect(watch);
workspace.windowActivated.connect(function (w) { tell("Activated", w); });

var all = workspace.windowList();
for (var i = 0; i < all.length; i++)
    watch(all[i]);
tell("Activated", workspace.activeWindow);
