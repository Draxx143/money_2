"""GTK-free layout and annotation sizing helpers."""


def clamp_workspace_divider(width, requested, viewer_min=500, panel_min=340, panel_max=520):
    """Keep the PCB canvas useful while allowing a bounded inspector/chat pane."""
    width = max(0, int(width))
    if width == 0:
        return int(requested)
    low = max(viewer_min, width - panel_max)
    high = max(low, width - panel_min)
    low = min(low, width)
    high = min(max(low, high), width)
    return min(max(int(requested), low), high)


def component_label_font_sizes(scale):
    """Return readable reference/value sizes that grow with board zoom, with caps."""
    scale = max(0.0, float(scale))
    reference_size = max(8.0, min(36.0, scale * 2.7))
    value_size = max(7.0, min(26.0, reference_size * 0.78))
    return reference_size, value_size
