"""Gtk.DrawingArea-based PCB viewer with zoom, pan and component selection."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GObject, Gtk

from .model import Board, pad_board_position, Component


# Layer colours (KiCad-like, dark theme friendly)
LAYER_COLORS = {
    "F.Cu": (0.90, 0.12, 0.12),   # red top copper
    "B.Cu": (0.00, 0.00, 1.00),   # vivid blue bottom copper (EasyEDA style)
    "Edge.Cuts": (0.90, 0.00, 0.82),  # magenta board edge
    "F.SilkS": (0.76, 0.68, 0.08),
    "B.SilkS": (0.40, 0.90, 0.18),
    "MECHANICAL15": (0.76, 0.68, 0.08),
}

SELECT_COLOR = (1.00, 0.18, 0.82)   # vivid magenta selection, distinct on copper blue
HOVER_COLOR = (0.20, 0.92, 1.00)    # bright cyan hover


class PcbViewer(Gtk.DrawingArea):
    __gsignals__ = {
        "component-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self):
        super().__init__()
        self.board: Board = None
        self.scale = 4.0          # pixels per mm
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.flip_vertical = False
        self.view_side = "Top"
        self.layer_names = []
        self.visible_layers = set()
        self.side_layer_visibility = {}
        self.active_layer = None
        self.selected_ref = None
        self.hover_ref = None
        self.marker = None          # (x_mm, y_mm) or None
        self._dragging = False
        self._drag_last = (0.0, 0.0)
        self.tool_mode = "select"
        self.grid_visible = True
        self.zones_visible = True
        self.measure_points = []
        self.measurements = []
        self.measure_cursor = None
        self.snap_points = []

        self.set_can_focus(True)
        self.add_events(
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.connect("draw", self._on_draw)
        self.connect("scroll-event", self._on_scroll)
        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("key-press-event", self._on_key_press)

    # ---- Public API ----
    def set_tool_mode(self, mode):
        if mode not in ("select", "pan", "measure"):
            return
        self.tool_mode = mode
        self.measure_points.clear()
        self.measure_cursor = None
        self.queue_draw()

    def _build_snap_points(self):
        """Cache snap targets for precise ruler endpoints (pads, tracks, edges)."""
        points = []
        board = self.board
        if not board:
            self.snap_points = points
            return
        bounds = board.bounds()
        if bounds:
            x1, y1, x2, y2 = bounds
            points.extend(((x1, y1, "Edge.Cuts"), (x1, y2, "Edge.Cuts"),
                       (x2, y1, "Edge.Cuts"), (x2, y2, "Edge.Cuts")))
        for x1, y1, x2, y2 in board.outline.segments:
            points.extend(((x1, y1, "Edge.Cuts"), (x2, y2, "Edge.Cuts")))
        for track in board.tracks:
            if self._layer_is_visible(track.layer):
                points.extend(((track.start_x, track.start_y, track.layer),
                               (track.end_x, track.end_y, track.layer)))
        for component in board.components:
            if self._component_is_visible(component):
                points.append((component.x, component.y, component.layer))
            for pad in component.pads:
                for layer in (pad.layers or [component.layer]):
                    if self._layer_is_visible(layer):
                        points.append((component.x + pad.x, component.y + pad.y, layer))
        self.snap_points = list(dict.fromkeys(points))

    def _snap_measure_point(self, px, py):
        """Snap within 12 screen pixels to a known PCB feature."""
        nearest = None
        nearest_d2 = 12.0 ** 2
        for x, y, layer in self.snap_points:
            sx, sy = self._layer_to_px(x, y, layer)
            d2 = (sx - px) ** 2 + (sy - py) ** 2
            if d2 <= nearest_d2:
                nearest_d2 = d2
                display_y = self._vertical_axis_sum() - y if self.view_side == "Bottom" else y
                nearest = (x, display_y)
        return nearest if nearest is not None else self.px_to_mm(px, py)

    def zoom_by(self, factor):
        alloc = self.get_allocation()
        cx, cy = alloc.width / 2, alloc.height / 2
        wx, wy = self.px_to_mm(cx, cy)
        self.scale = max(min(self.scale * factor, 200.0), 0.1)
        view_y = self._vertical_axis_sum() - wy if self.flip_vertical else wy
        self.offset_x = cx - wx * self.scale
        self.offset_y = cy - view_y * self.scale
        self.queue_draw()

    def toggle_grid(self, visible):
        self.grid_visible = bool(visible)
        self.queue_draw()

    def toggle_zones(self, visible):
        self.zones_visible = bool(visible)
        self.queue_draw()

    def set_board(self, board: Board):
        self.board = board
        discovered = {self._canonical_layer(layer) for layer in getattr(board, "layers", [])}
        discovered.update(self._canonical_layer(track.layer) for track in board.tracks)
        discovered.update(self._canonical_layer(component.layer) for component in board.components)
        discovered.update(self._canonical_layer(pad_layer)
                          for component in board.components for pad in component.pads
                          for pad_layer in (pad.layers or [component.layer]))
        discovered.update(self._canonical_layer(zone.layer) for zone in getattr(board, "zones", []))
        if board.outline.segments:
            discovered.add("Edge.Cuts")
        standard_order = ("F.Cu", "B.Cu", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask",
                          "F.Paste", "B.Paste", "Ratlines", "Edge.Cuts", "Multi-Layer", "Document")
        self.layer_names = [layer for layer in standard_order if layer in discovered]
        self.layer_names.extend(sorted(discovered - set(self.layer_names)))
        self.view_side = "Top"
        self.visible_layers = {
            layer for layer in self.layer_names
            if layer.startswith("F.") or layer in ("Multi-Layer", "Edge.Cuts")
        }
        self.side_layer_visibility = {"Top": set(self.visible_layers)}
        self.active_layer = "F.Cu" if "F.Cu" in self.layer_names else (
            self.layer_names[0] if self.layer_names else None
        )
        self.measure_points.clear()
        self.measurements.clear()
        self.measure_cursor = None
        self._build_snap_points()
        self.selected_ref = None
        self.hover_ref = None
        self.fit_to_view()
        self.queue_draw()

    def fit_to_view(self):
        if not self.board:
            return
        b = self.board.bounds()
        if not b:
            return
        alloc = self.get_allocation()
        min_x, min_y, max_x, max_y = b
        bw = max(max_x - min_x, 1e-3)
        bh = max(max_y - min_y, 1e-3)
        margin = 40
        sx = (alloc.width - 2 * margin) / bw
        sy = (alloc.height - 2 * margin) / bh
        self.scale = max(min(sx, sy), 0.5)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self.offset_x = alloc.width / 2 - cx * self.scale
        self.offset_y = alloc.height / 2 - cy * self.scale

    def select_component(self, reference):
        self.selected_ref = reference
        self.queue_draw()

    def set_hover(self, reference):
        if reference != self.hover_ref:
            self.hover_ref = reference
            self.queue_draw()

    def set_marker(self, x_mm, y_mm):
        self.marker = None if x_mm is None else (x_mm, y_mm)
        self.queue_draw()

    def pan_to(self, x_mm, y_mm):
        alloc = self.get_allocation()
        view_y = self._vertical_axis_sum() - y_mm if self.flip_vertical else y_mm
        self.offset_x = alloc.width / 2 - x_mm * self.scale
        self.offset_y = alloc.height / 2 - view_y * self.scale
        self.queue_draw()

    # ---- Coordinate transform ----
    def _vertical_axis_sum(self):
        bounds = self.board.bounds() if self.board else None
        return (bounds[1] + bounds[3]) if bounds else 0.0

    def set_vertical_flip(self, enabled):
        # Legacy API: side switching must filter layers, never mirror coordinates.
        self.flip_vertical = False
        self.queue_draw()

    def set_view_side(self, side):
        target_side = "Bottom" if side == "Bottom" else "Top"
        if target_side != self.view_side:
            if self.view_side:
                self.side_layer_visibility[self.view_side] = set(self.visible_layers)
            self.view_side = target_side
            saved = self.side_layer_visibility.get(target_side)
            if saved is not None:
                self.visible_layers = set(saved)
            else:
                prefix = "B." if target_side == "Bottom" else "F."
                self.visible_layers = {
                    layer for layer in self.layer_names
                    if layer.startswith(prefix) or layer in ("Multi-Layer", "Edge.Cuts")
                }
            self.active_layer = "B.Cu" if target_side == "Bottom" else "F.Cu"
        # EasyEDA's BottomLayer canvas is viewed from the underside, so the
        # complete board artwork uses the bottom-view Y reflection. Top stays
        # in the source board coordinate orientation.
        self.flip_vertical = False
        if self.selected_ref and not self._component_is_visible(
                next((c for c in self.board.components if c.reference == self.selected_ref), None)):
            self.selected_ref = None
        self._build_snap_points()
        self.queue_draw()

    @staticmethod
    def _canonical_layer(layer):
        value = str(layer or "").strip()
        aliases = {"MULTILAYER": "Multi-Layer", "MULTI-LAYER": "Multi-Layer",
                   "TOP": "F.Cu", "BOTTOM": "B.Cu"}
        return aliases.get(value.upper(), value)

    def set_layer_visible(self, layer, visible):
        layer = self._canonical_layer(layer)
        if visible:
            self.visible_layers.add(layer)
        else:
            self.visible_layers.discard(layer)
        self.active_layer = layer
        self.side_layer_visibility[self.view_side] = set(self.visible_layers)
        self._build_snap_points()
        self.queue_draw()

    def set_active_layer(self, layer):
        self.active_layer = self._canonical_layer(layer)
        self.queue_draw()

    def _layer_is_visible(self, layer):
        return self._canonical_layer(layer) in self.visible_layers

    def _component_has_visible_pad(self, component):
        return any(any(self._layer_is_visible(layer)
                       for layer in (pad.layers or [component.layer]))
                   for pad in component.pads)

    def _component_is_visible(self, component):
        if component is None:
            return False
        return self._layer_is_visible(component.layer)

    def mm_to_px(self, x, y):
        if self.flip_vertical:
            y = self._vertical_axis_sum() - y
        return (x * self.scale + self.offset_x,
                y * self.scale + self.offset_y)

    def _layer_to_px(self, x, y, layer):
        """Render bottom-side geometry in its bottom-view orientation only."""
        if self.view_side == "Bottom":
            y = self._vertical_axis_sum() - y
        return self.mm_to_px(x, y)

    def px_to_mm(self, x, y):
        board_y = (y - self.offset_y) / self.scale
        if self.flip_vertical:
            board_y = self._vertical_axis_sum() - board_y
        return ((x - self.offset_x) / self.scale, board_y)

    # ---- Drawing ----
    def _on_draw(self, widget, cr):
        alloc = self.get_allocation()
        cr.set_source_rgb(0.0, 0.0, 0.0)  # black PCB canvas, as in the source layout
        cr.paint()

        if not self.board:
            cr.set_source_rgb(0.58, 0.64, 0.71)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(14)
            cr.move_to(20, 30)
            cr.show_text("Open a KiCad .kicad_pcb file to view a board.")
            return

        if self.grid_visible:
            self._draw_grid(cr, alloc.width, alloc.height)

        # Copper pours/zones sit beneath tracks and pads. The Altium ASCII
        # exporter supplies their filled polygon contours as Region records.
        for zone in getattr(self.board, "zones", []) if self.zones_visible else []:
            if not self._layer_is_visible(zone.layer) or len(zone.points) < 3:
                continue
            zone_color = LAYER_COLORS.get(zone.layer, (0.0, 0.0, 1.0))
            cr.set_source_rgb(*zone_color)
            x, y = self._layer_to_px(*zone.points[0], zone.layer)
            cr.move_to(x, y)
            for point in zone.points[1:]:
                cr.line_to(*self._layer_to_px(*point, zone.layer))
            cr.close_path()
            cr.fill()

        # Outline is an independently toggleable Edge.Cuts layer.
        if self._layer_is_visible("Edge.Cuts"):
            cr.set_source_rgb(*LAYER_COLORS["Edge.Cuts"])
            cr.set_line_width(1.5)
            for x1, y1, x2, y2 in self.board.outline.segments:
                px1, py1 = self.mm_to_px(x1, y1)
                px2, py2 = self.mm_to_px(x2, y2)
                cr.move_to(px1, py1)
                cr.line_to(px2, py2)
            cr.stroke()

        # Tracks: round caps and joins keep adjoining Altium segments visually
        # continuous at acute corners and very small endpoint-rounding errors.
        # Cairo enum value 1 is LINE_CAP_ROUND / LINE_JOIN_ROUND.
        cr.set_line_cap(1)
        cr.set_line_join(1)
        for t in self.board.tracks:
            if not self._layer_is_visible(t.layer):
                continue
            color = LAYER_COLORS.get(t.layer, (0.6, 0.6, 0.6))
            cr.set_source_rgb(*color)
            cr.set_line_width(max(t.width * self.scale, 1.0))
            px1, py1 = self._layer_to_px(t.start_x, t.start_y, t.layer)
            px2, py2 = self._layer_to_px(t.end_x, t.end_y, t.layer)
            cr.move_to(px1, py1)
            cr.line_to(px2, py2)
            cr.stroke()

        # Highlight the complete selected footprint, not just its pads: Altium
        # ASCII tracks retain their owning component designator.
        if self.selected_ref:
            for track in self.board.tracks:
                if track.component_ref != self.selected_ref or not self._layer_is_visible(track.layer):
                    continue
                px1, py1 = self._layer_to_px(track.start_x, track.start_y, track.layer)
                px2, py2 = self._layer_to_px(track.end_x, track.end_y, track.layer)
                base_width = max(track.width * self.scale, 1.0)
                cr.set_source_rgba(*SELECT_COLOR, 0.28)
                cr.set_line_width(base_width + 7.0)
                cr.move_to(px1, py1); cr.line_to(px2, py2); cr.stroke()
                cr.set_source_rgb(*SELECT_COLOR)
                cr.set_line_width(max(base_width + 1.5, 3.0))
                cr.move_to(px1, py1); cr.line_to(px2, py2); cr.stroke()

        # Components (pads + reference)
        for c in self.board.components:
            component_visible = self._component_is_visible(c)
            if not component_visible and not self._component_has_visible_pad(c):
                continue
            is_sel = c.reference == self.selected_ref
            is_hover = c.reference == self.hover_ref

            for pad in c.pads:
                pad_layers = pad.layers or [c.layer]
                if not any(self._layer_is_visible(layer) for layer in pad_layers):
                    continue
                pad_layer = next(iter(pad.layers), c.layer)
                pad_x, pad_y = pad_board_position(c, pad)
                px, py = self._layer_to_px(pad_x, pad_y, pad_layer)
                w = pad.width * self.scale
                h = pad.height * self.scale
                if is_sel:
                    cr.set_source_rgb(*SELECT_COLOR)
                elif is_hover:
                    cr.set_source_rgb(*HOVER_COLOR)
                elif getattr(pad, "hole_diameter", 0.0) > 0:
                    # Neutral metal annulus for plated through-hole pads.
                    cr.set_source_rgb(0.72, 0.74, 0.79)
                else:
                    cr.set_source_rgb(*LAYER_COLORS.get(pad_layer, (0.0, 0.0, 1.0)))
                if pad.shape.lower() in ("circle", "round"):
                    cr.arc(px, py, max(w, h) / 2, 0, 2 * math.pi)
                else:
                    cr.rectangle(px - w / 2, py - h / 2, w, h)
                cr.fill()
                if getattr(pad, "hole_diameter", 0.0) > 0:
                    cr.set_source_rgb(0.0, 0.0, 0.0)
                    cr.arc(px, py, pad.hole_diameter * self.scale / 2, 0, 2 * math.pi)
                    cr.fill()

            if not component_visible:
                continue

            # Altium stores designator/value text at independent board
            # coordinates; use those positions rather than centering labels on
            # component origins (which causes collisions in dense boards).
            ref_x = c.reference_x if c.reference_x is not None else c.x
            ref_y = c.reference_y if c.reference_y is not None else c.y
            silk_layer = "B.SilkS" if self._canonical_layer(c.layer) == "B.Cu" else "F.SilkS"
            px, py = self._layer_to_px(ref_x, ref_y, silk_layer)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(11)
            if is_sel:
                cr.set_source_rgb(*SELECT_COLOR)
            elif is_hover:
                cr.set_source_rgb(*HOVER_COLOR)
            else:
                cr.set_source_rgb(*LAYER_COLORS[silk_layer])
            cr.move_to(px + 2, py - 2)
            cr.show_text(c.reference)

            if c.value:
                value_x = c.value_x if c.value_x is not None else c.x
                value_y = c.value_y if c.value_y is not None else c.y + 1.5
                vx, vy = self._layer_to_px(value_x, value_y, silk_layer)
                cr.set_font_size(9)
                cr.move_to(vx + 2, vy - 2)
                cr.show_text(c.value)

        # Test-point marker
        if self.marker is not None:
            mx, my = self.mm_to_px(self.marker[0], self.marker[1])
            cr.set_source_rgba(1.0, 0.30, 0.30, 0.9)
            cr.set_line_width(2.0)
            cr.arc(mx, my, 10, 0, 2 * 3.141592653589793)
            cr.stroke()
            cr.move_to(mx - 14, my); cr.line_to(mx + 14, my)
            cr.move_to(mx, my - 14); cr.line_to(mx, my + 14)
            cr.stroke()

        # CAD-style dimensions: extension lines, inward arrowheads, rotated
        # value text, persistent completed measurements, and live preview.
        dimensions = list(self.measurements)
        if self.measure_points and self.measure_cursor:
            dimensions.append((self.measure_points[0], self.measure_cursor, True))
        for item in dimensions:
            (x1, y1), (x2, y2), *preview_flag = item
            preview = bool(preview_flag and preview_flag[0])
            self._draw_dimension(cr, (x1, y1), (x2, y2), preview)

        # Coordinate readout
        cr.set_source_rgb(0.58, 0.64, 0.71)
        cr.set_font_size(11)
        cr.move_to(10, alloc.height - 10)
        cr.show_text(f"Scale: {self.scale:.2f} px/mm")

    def _draw_dimension(self, cr, start, end, preview=False):
        """Draw an engineering dimension annotation in screen space."""
        x1, y1 = self.mm_to_px(*start)
        x2, y2 = self.mm_to_px(*end)
        dx, dy = x2 - x1, y2 - y1
        screen_length = math.hypot(dx, dy)
        if screen_length < 2:
            return
        ux, uy = dx / screen_length, dy / screen_length
        nx, ny = -uy, ux
        color = (0.98, 0.75, 0.20) if preview else (0.98, 0.88, 0.52)
        cr.save()
        cr.set_source_rgba(*color, 0.95 if not preview else 0.72)
        cr.set_line_width(1.35)
        cr.set_line_cap(1)
        # Short extension lines beyond both measured points.
        ext = 7.0
        cr.move_to(x1 - nx * ext, y1 - ny * ext)
        cr.line_to(x1 + nx * ext, y1 + ny * ext)
        cr.move_to(x2 - nx * ext, y2 - ny * ext)
        cr.line_to(x2 + nx * ext, y2 + ny * ext)
        cr.stroke()
        # Dimension line and two inward-facing arrowheads.
        cr.move_to(x1, y1); cr.line_to(x2, y2); cr.stroke()
        arrow = min(7.0, screen_length * 0.22)
        for x, y, direction in ((x1, y1, 1), (x2, y2, -1)):
            bx, by = x + ux * arrow * direction, y + uy * arrow * direction
            wing = 2.8
            cr.move_to(x, y)
            cr.line_to(bx + nx * wing, by + ny * wing)
            cr.move_to(x, y)
            cr.line_to(bx - nx * wing, by - ny * wing)
        cr.stroke()
        # Rotated label follows the dimension line, kept upright for readability.
        angle = math.atan2(dy, dx)
        if angle > math.pi / 2 or angle < -math.pi / 2:
            angle += math.pi
        length_mm = math.hypot(end[0] - start[0], end[1] - start[1])
        label = f"{length_mm:.3f} mm"
        mx, my = (x1 + x2) / 2 + nx * 10, (y1 + y2) / 2 + ny * 10
        cr.translate(mx, my)
        cr.rotate(angle)
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(12)
        extents = cr.text_extents(label)
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.rectangle(-extents.width / 2 - 3, -extents.height / 2 - 2,
                     extents.width + 6, extents.height + 4)
        cr.fill()
        cr.set_source_rgba(*color, 1.0)
        cr.move_to(-extents.width / 2, extents.height / 2)
        cr.show_text(label)
        cr.restore()

    def _draw_grid(self, cr, width, height):
        """Draw a subtle scale-aware drafting grid behind the board artwork."""
        scale = max(self.scale, 1e-6)
        raw_step = 36.0 / scale
        decade = 10 ** math.floor(math.log10(max(raw_step, 1e-9)))
        step = next((m * decade for m in (1, 2, 5, 10)
                     if m * decade >= raw_step), 10 * decade)
        world_a = self.px_to_mm(0, 0)
        world_b = self.px_to_mm(width, height)
        min_x, max_x = sorted((world_a[0], world_b[0]))
        min_y, max_y = sorted((world_a[1], world_b[1]))
        x0 = math.floor(min_x / step)
        x1 = math.ceil(max_x / step)
        y0 = math.floor(min_y / step)
        y1 = math.ceil(max_y / step)

        cr.save()
        cr.set_line_width(1.0)
        cr.set_source_rgba(0.55, 0.66, 0.78, 0.10)
        cr.new_path()
        for index in range(x0, x1 + 1):
            if index % 5:
                x, _ = self.mm_to_px(index * step, 0)
                cr.move_to(x, 0); cr.line_to(x, height)
        for index in range(y0, y1 + 1):
            if index % 5:
                _, y = self.mm_to_px(0, index * step)
                cr.move_to(0, y); cr.line_to(width, y)
        cr.stroke()

        cr.set_source_rgba(0.60, 0.72, 0.86, 0.17)
        cr.new_path()
        for index in range(x0, x1 + 1):
            if index % 5 == 0:
                x, _ = self.mm_to_px(index * step, 0)
                cr.move_to(x, 0); cr.line_to(x, height)
        for index in range(y0, y1 + 1):
            if index % 5 == 0:
                _, y = self.mm_to_px(0, index * step)
                cr.move_to(0, y); cr.line_to(width, y)
        cr.stroke()
        cr.restore()

    # ---- Events ----
    def _on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            _, dx, dy = event.get_scroll_deltas()
        elif event.direction == Gdk.ScrollDirection.UP:
            dy = -1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            dy = 1
        else:
            return False

        # zoom centred on cursor
        mx, my = event.x, event.y
        wx, wy = self.px_to_mm(mx, my)
        factor = math.exp(-dy * 0.2)
        new_scale = max(min(self.scale * factor, 200.0), 0.1)
        if new_scale == self.scale:
            return True
        self.scale = new_scale
        # keep cursor-anchored point fixed
        self.offset_x = mx - wx * self.scale
        view_y = self._vertical_axis_sum() - wy if self.flip_vertical else wy
        self.offset_y = my - view_y * self.scale
        self.queue_draw()
        return True

    def _on_button_press(self, widget, event):
        self.grab_focus()
        if event.button == 1 and self.tool_mode == "select":
            ref = self._hit_test(event.x, event.y)
            self.selected_ref = ref
            self.emit("component-selected", ref)
            self.queue_draw()
        elif event.button == 1 and self.tool_mode == "pan":
            self._dragging = True
            self._drag_last = (event.x, event.y)
        elif event.button == 1 and self.tool_mode == "measure":
            point = self._snap_measure_point(event.x, event.y)
            if not self.measure_points:
                self.measure_points = [point]
            else:
                self.measurements.append((self.measure_points[0], point))
                self.measure_points.clear()
            self.measure_cursor = point
            self.queue_draw()
        elif event.button == 3 and self.tool_mode == "measure":
            self.measurements.clear()
            self.measure_points.clear()
            self.measure_cursor = None
            self.queue_draw()
        elif event.button == 2:
            self._dragging = True
            self._drag_last = (event.x, event.y)
        return True

    def _on_key_press(self, _widget, event):
        if event.keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            if self.measurements:
                self.measurements.pop()
                self.queue_draw()
                return True
        if event.keyval == Gdk.KEY_Escape and self.measure_points:
            self.measure_points.clear()
            self.measure_cursor = None
            self.queue_draw()
            return True
        return False

    def _on_button_release(self, widget, event):
        self._dragging = False
        return True

    def _on_motion(self, widget, event):
        if self.tool_mode == "measure" and self.measure_points:
            self.measure_cursor = self._snap_measure_point(event.x, event.y)
            self.queue_draw()
        if self._dragging:
            dx = event.x - self._drag_last[0]
            dy = event.y - self._drag_last[1]
            self.offset_x += dx
            self.offset_y += dy
            self._drag_last = (event.x, event.y)
            self.queue_draw()
        else:
            ref = self._hit_test(event.x, event.y)
            if ref != self.hover_ref:
                self.hover_ref = ref
                self.queue_draw()
        return True

    def _hit_test(self, px, py):
        if not self.board:
            return None
        best = None
        best_d2 = 20.0 ** 2
        for c in self.board.components:
            if not self._component_is_visible(c) and not self._component_has_visible_pad(c):
                continue
            cx, cy = self._layer_to_px(c.x, c.y, c.layer)
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best = c.reference
        return best
