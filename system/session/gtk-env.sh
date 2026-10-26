# Written by Claude 2026-10-10. Installed as ~/.config/plasma-workspace/env/j701f-gtk.sh.
# GTK 4 applications (the Software store among them) on this GPU:
#  - GTK's GL renderer with its default optimisations leaves black areas
#    (Panfrost on Mali-T830);
#  - with every optional optimisation switched off it draws correctly;
#  - the Cairo software renderer also draws correctly but is slow (the owner
#    found the store "very laggy" with it).
export GSK_RENDERER=gl
export GSK_GPU_DISABLE=all
