"""GTK-free layout and annotation sizing helpers."""


def clamp_workspace_divider(width, requested, viewer_min=280, panel_min=250, panel_max=480):
    """Clamp a split while adapting both panes to narrow windows.

    The separator consumes a little width itself. When the available space
    cannot satisfy both preferred minimums, use a proportional split instead
    of forcing a child to a negative allocation.
    """
    width = max(0, int(width))
    if width == 0:
        return int(requested)
    available = max(0, width - 2)
    if available < viewer_min + panel_min:
        return min(available, max(0, int(round(available * 0.56))))
    low = max(viewer_min, available - panel_max)
    high = min(available - panel_min, available)
    return min(max(int(requested), low), high)


def component_label_font_sizes(scale):
    """Return readable reference/value sizes that grow with board zoom, with caps."""
    scale = max(0.0, float(scale))
    reference_size = max(8.0, min(36.0, scale * 2.7))
    value_size = max(7.0, min(26.0, reference_size * 0.78))
    return reference_size, value_size
