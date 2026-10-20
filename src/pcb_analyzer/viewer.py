"""Gtk.DrawingArea-based PCB viewer with zoom, pan and component selection."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GObject, Gtk

from .model import Board, Component


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
        self.selected_ref = None
        self.hover_ref = None
        self.marker = None          # (x_mm, y_mm) or None
        self._dragging = False
        self._drag_last = (0.0, 0.0)

        self.set_can_focus(True)
        self.add_events(
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        self.connect("draw", self._on_draw)
        self.connect("scroll-event", self._on_scroll)
        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion)

    # ---- Public API ----
    def set_board(self, board: Board):
        self.board = board
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
        self.flip_vertical = bool(enabled)
        self.queue_draw()

    def mm_to_px(self, x, y):
        if self.flip_vertical:
            y = self._vertical_axis_sum() - y
        return (x * self.scale + self.offset_x,
                y * self.scale + self.offset_y)

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

        self._draw_grid(cr, alloc.width, alloc.height)

        # Copper pours/zones sit beneath tracks and pads. The Altium ASCII
        # exporter supplies their filled polygon contours as Region records.
        for zone in getattr(self.board, "zones", []):
            if len(zone.points) < 3:
                continue
            zone_color = LAYER_COLORS.get(zone.layer, (0.0, 0.0, 1.0))
            cr.set_source_rgb(*zone_color)
            x, y = self.mm_to_px(*zone.points[0])
            cr.move_to(x, y)
            for point in zone.points[1:]:
                cr.line_to(*self.mm_to_px(*point))
            cr.close_path()
            cr.fill()

        # Outline
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
            color = LAYER_COLORS.get(t.layer, (0.6, 0.6, 0.6))
            cr.set_source_rgb(*color)
            cr.set_line_width(max(t.width * self.scale, 1.0))
            px1, py1 = self.mm_to_px(t.start_x, t.start_y)
            px2, py2 = self.mm_to_px(t.end_x, t.end_y)
            cr.move_to(px1, py1)
            cr.line_to(px2, py2)
            cr.stroke()

        # Highlight the complete selected footprint, not just its pads: Altium
        # ASCII tracks retain their owning component designator.
        if self.selected_ref:
            for track in self.board.tracks:
                if track.component_ref != self.selected_ref:
                    continue
                px1, py1 = self.mm_to_px(track.start_x, track.start_y)
                px2, py2 = self.mm_to_px(track.end_x, track.end_y)
                base_width = max(track.width * self.scale, 1.0)
                cr.set_source_rgba(*SELECT_COLOR, 0.28)
                cr.set_line_width(base_width + 7.0)
                cr.move_to(px1, py1); cr.line_to(px2, py2); cr.stroke()
                cr.set_source_rgb(*SELECT_COLOR)
                cr.set_line_width(max(base_width + 1.5, 3.0))
                cr.move_to(px1, py1); cr.line_to(px2, py2); cr.stroke()

        # Components (pads + reference)
        for c in self.board.components:
            is_sel = c.reference == self.selected_ref
            is_hover = c.reference == self.hover_ref

            for pad in c.pads:
                px, py = self.mm_to_px(c.x + pad.x, c.y + pad.y)
                w = pad.width * self.scale
                h = pad.height * self.scale
                pad_layer = next(iter(pad.layers), c.layer)
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

            # Altium stores designator/value text at independent board
            # coordinates; use those positions rather than centering labels on
            # component origins (which causes collisions in dense boards).
            ref_x = c.reference_x if c.reference_x is not None else c.x
            ref_y = c.reference_y if c.reference_y is not None else c.y
            px, py = self.mm_to_px(ref_x, ref_y)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(11)
            if is_sel:
                cr.set_source_rgb(*SELECT_COLOR)
            elif is_hover:
                cr.set_source_rgb(*HOVER_COLOR)
            else:
                silk_layer = "B.SilkS" if c.layer == "B.Cu" else "F.SilkS"
                cr.set_source_rgb(*LAYER_COLORS[silk_layer])
            cr.move_to(px + 2, py - 2)
            cr.show_text(c.reference)

            if c.value:
                value_x = c.value_x if c.value_x is not None else c.x
                value_y = c.value_y if c.value_y is not None else c.y + 1.5
                vx, vy = self.mm_to_px(value_x, value_y)
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

        # Coordinate readout
        cr.set_source_rgb(0.58, 0.64, 0.71)
        cr.set_font_size(11)
        cr.move_to(10, alloc.height - 10)
        cr.show_text(f"Scale: {self.scale:.2f} px/mm")

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
        if event.button == 1:
            # selection
            ref = self._hit_test(event.x, event.y)
            if ref:
                self.selected_ref = ref
                self.emit("component-selected", ref)
                self.queue_draw()
            else:
                self.selected_ref = None
                self.emit("component-selected", None)
                self.queue_draw()
            # begin pan drag
            self._dragging = True
            self._drag_last = (event.x, event.y)
        elif event.button == 2:
            self._dragging = True
            self._drag_last = (event.x, event.y)
        return True

    def _on_button_release(self, widget, event):
        self._dragging = False
        return True

    def _on_motion(self, widget, event):
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
        wx, wy = self.px_to_mm(px, py)
        # radius in mm scaled by zoom (≈ 20px)
        r = 20.0 / self.scale
        best = None
        best_d2 = r * r
        for c in self.board.components:
            d2 = (c.x - wx) ** 2 + (c.y - wy) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best = c.reference
        return best
