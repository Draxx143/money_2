"""Gtk.DrawingArea-based PCB viewer with zoom, pan and component selection."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GObject, Gtk

from .model import Board, Component


# Layer colours (KiCad-like, dark theme friendly)
LAYER_COLORS = {
    "F.Cu": (0.85, 0.20, 0.20),   # red
    "B.Cu": (0.20, 0.45, 0.85),   # blue
    "Edge.Cuts": (0.88, 0.05, 0.80),  # magenta, like Altium/KiCad board edges
    "F.SilkS": (0.90, 0.90, 0.90),
    "B.SilkS": (0.35, 0.82, 0.25),
}

SELECT_COLOR = (0.00, 0.82, 0.70)   # accent primary
HOVER_COLOR = (0.30, 0.64, 1.00)    # accent secondary


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
        self.offset_x = alloc.width / 2 - x_mm * self.scale
        self.offset_y = alloc.height / 2 - y_mm * self.scale
        self.queue_draw()

    # ---- Coordinate transform ----
    def mm_to_px(self, x, y):
        return (x * self.scale + self.offset_x,
                y * self.scale + self.offset_y)

    def px_to_mm(self, x, y):
        return ((x - self.offset_x) / self.scale,
                (y - self.offset_y) / self.scale)

    # ---- Drawing ----
    def _on_draw(self, widget, cr):
        alloc = self.get_allocation()
        cr.set_source_rgb(0.043, 0.059, 0.078)  # #0B0F14
        cr.paint()

        if not self.board:
            cr.set_source_rgb(0.58, 0.64, 0.71)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(14)
            cr.move_to(20, 30)
            cr.show_text("Open a KiCad .kicad_pcb file to view a board.")
            return

        # Copper pours/zones sit beneath tracks and pads. The Altium ASCII
        # exporter supplies their filled polygon contours as Region records.
        for zone in getattr(self.board, "zones", []):
            if len(zone.points) < 3:
                continue
            if zone.layer == "F.Cu":
                cr.set_source_rgba(0.05, 0.18, 0.96, 0.88)
            else:
                cr.set_source_rgba(0.08, 0.24, 0.92, 0.88)
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

        # Tracks
        for t in self.board.tracks:
            color = LAYER_COLORS.get(t.layer, (0.6, 0.6, 0.6))
            cr.set_source_rgb(*color)
            cr.set_line_width(max(t.width * self.scale, 1.0))
            px1, py1 = self.mm_to_px(t.start_x, t.start_y)
            px2, py2 = self.mm_to_px(t.end_x, t.end_y)
            cr.move_to(px1, py1)
            cr.line_to(px2, py2)
            cr.stroke()

        # Components (pads + reference)
        for c in self.board.components:
            is_sel = c.reference == self.selected_ref
            is_hover = c.reference == self.hover_ref

            for pad in c.pads:
                px, py = self.mm_to_px(c.x + pad.x, c.y + pad.y)
                w = pad.width * self.scale
                h = pad.height * self.scale
                if is_sel:
                    cr.set_source_rgb(*SELECT_COLOR)
                elif is_hover:
                    cr.set_source_rgb(*HOVER_COLOR)
                else:
                    cr.set_source_rgb(0.80, 0.80, 0.55)
                if pad.shape.lower() in ("circle", "round"):
                    cr.arc(px, py, max(w, h) / 2, 0, 2 * math.pi)
                else:
                    cr.rectangle(px - w / 2, py - h / 2, w, h)
                cr.fill()
                if getattr(pad, "hole_diameter", 0.0) > 0:
                    cr.set_source_rgb(0.043, 0.059, 0.078)
                    cr.arc(px, py, pad.hole_diameter * self.scale / 2, 0, 2 * math.pi)
                    cr.fill()

            # Reference label
            px, py = self.mm_to_px(c.x, c.y)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(11)
            if is_sel:
                cr.set_source_rgb(*SELECT_COLOR)
            elif is_hover:
                cr.set_source_rgb(*HOVER_COLOR)
            else:
                cr.set_source_rgb(0.95, 0.95, 0.95)
            cr.move_to(px + 4, py - 4)
            cr.show_text(c.reference)

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
        self.offset_y = my - wy * self.scale
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
