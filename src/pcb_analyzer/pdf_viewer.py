"""PDF viewer widget using Poppler-GLib + cairo, with text search."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Poppler", "0.18")
from gi.repository import Gdk, GObject, Gtk, Poppler


HIGHLIGHT_COLOR = (1.0, 0.85, 0.20, 0.55)  # amber translucent


class PdfViewer(Gtk.Box):
    """A self-contained PDF viewer: canvas, page navigation, text search."""

    __gsignals__ = {
        "page-changed": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.document = None
        self.current_page = 0
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._dragging = False
        self._drag_last = (0.0, 0.0)
        self._search_text = ""
        self._search_matches = []  # list of (page_index, [rects in page coords])

        self.build_ui()

    def build_ui(self):
        # Toolbar
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.get_style_context().add_class("toolbar")

        self.btn_prev = Gtk.Button(label="◀")
        self.btn_prev.connect("clicked", self.on_prev_page)
        bar.pack_start(self.btn_prev, False, False, 0)

        self.page_label = Gtk.Label(label="— / —")
        bar.pack_start(self.page_label, False, False, 0)

        self.btn_next = Gtk.Button(label="▶")
        self.btn_next.connect("clicked", self.on_next_page)
        bar.pack_start(self.btn_next, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 6)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Find in PDF…")
        self.search_entry.connect("search-changed", self.on_search_changed)
        bar.pack_start(self.search_entry, True, True, 0)

        self.match_label = Gtk.Label(label="")
        self.match_label.get_style_context().add_class("dim")
        bar.pack_start(self.match_label, False, False, 0)

        self.pack_start(bar, False, False, 0)

        # Canvas
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_can_focus(True)
        self.canvas.add_events(
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.canvas.connect("draw", self.on_draw)
        self.canvas.connect("scroll-event", self.on_scroll)
        self.canvas.connect("button-press-event", self.on_button_press)
        self.canvas.connect("button-release-event", self.on_button_release)
        self.canvas.connect("motion-notify-event", self.on_motion)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.canvas)
        self.pack_start(scroll, True, True, 0)

        self._update_nav_state()

    # ---- Public API ----
    def load(self, path):
        try:
            uri = "file://" + path if not path.startswith("file://") else path
            doc = Poppler.Document.new_from_file(uri, None)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Could not open PDF: {exc}") from exc
        self.document = doc
        self.current_page = 0
        self._search_matches = []
        self._search_text = ""
        self.search_entry.set_text("")
        self.fit_page()
        self.emit("page-changed", 0, doc.get_n_pages())
        self._update_nav_state()
        self.canvas.queue_draw()

    def fit_page(self):
        if not self.document:
            return
        page = self.document.get_page(self.current_page)
        alloc = self.canvas.get_allocation()
        if alloc.width <= 1 or alloc.height <= 1:
            return
        pw, ph = page.get_size()
        margin = 20
        sx = (alloc.width - 2 * margin) / max(pw, 1)
        sy = (alloc.height - 2 * margin) / max(ph, 1)
        self.scale = min(sx, sy)
        self.offset_x = (alloc.width - pw * self.scale) / 2
        self.offset_y = margin

    # ---- Navigation ----
    def on_prev_page(self, _w):
        if self.current_page > 0:
            self.current_page -= 1
            self.fit_page()
            self.emit("page-changed", self.current_page, self.document.get_n_pages())
            self._update_nav_state()
            self.canvas.queue_draw()

    def on_next_page(self, _w):
        if self.document and self.current_page < self.document.get_n_pages() - 1:
            self.current_page += 1
            self.fit_page()
            self.emit("page-changed", self.current_page, self.document.get_n_pages())
            self._update_nav_state()
            self.canvas.queue_draw()

    def _update_nav_state(self):
        if not self.document:
            self.page_label.set_text("— / —")
            self.btn_prev.set_sensitive(False)
            self.btn_next.set_sensitive(False)
            return
        n = self.document.get_n_pages()
        self.page_label.set_text(f"{self.current_page + 1} / {n}")
        self.btn_prev.set_sensitive(self.current_page > 0)
        self.btn_next.set_sensitive(self.current_page < n - 1)

    # ---- Search ----
    def on_search_changed(self, entry):
        self._search_text = entry.get_text()
        self._search_matches = []
        if not self.document or not self._search_text.strip():
            self.match_label.set_text("")
            self.canvas.queue_draw()
            return
        needle = self._search_text.lower()
        total = 0
        for i in range(self.document.get_n_pages()):
            page = self.document.get_page(i)
            try:
                res = page.find_text_with_options(
                    self._search_text,
                    Poppler.FindFlags.CASE_INSENSITIVE,
                )
            except Exception:
                res = []
            if res:
                self._search_matches.append((i, res))
                total += len(res)
        self.match_label.set_text(f"{total} match(es)")
        self.canvas.queue_draw()

    # ---- Drawing ----
    def on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        cr.set_source_rgb(0.043, 0.059, 0.078)  # #0B0F14
        cr.paint()

        if not self.document:
            cr.set_source_rgb(0.58, 0.64, 0.71)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(14)
            cr.move_to(20, 30)
            cr.show_text("Open a PDF file to view a schematic.")
            return

        page = self.document.get_page(self.current_page)
        pw, ph = page.get_size()
        cr.save()
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(self.scale, self.scale)
        page.render(cr)
        cr.restore()

        # Highlights for search matches on current page
        for page_idx, rects in self._search_matches:
            if page_idx != self.current_page:
                continue
            for rect in rects:
                x1, y1, x2, y2 = rect.x1, rect.y1, rect.x2, rect.y2
                px1 = self.offset_x + x1 * self.scale
                py1 = self.offset_y + y1 * self.scale
                px2 = self.offset_x + x2 * self.scale
                py2 = self.offset_y + y2 * self.scale
                cr.set_source_rgba(*HIGHLIGHT_COLOR)
                cr.rectangle(px1, py1, px2 - px1, py2 - py1)
                cr.fill()

    # ---- Pan / zoom ----
    def on_scroll(self, widget, event):
        if not self.document:
            return False
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            _, _dx, dy = event.get_scroll_deltas()
        elif event.direction == Gdk.ScrollDirection.UP:
            dy = -1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            dy = 1
        else:
            return False

        mx, my = event.x, event.y
        wx = (mx - self.offset_x) / self.scale
        wy = (my - self.offset_y) / self.scale
        factor = math.exp(-dy * 0.15)
        self.scale = max(min(self.scale * factor, 20.0), 0.1)
        self.offset_x = mx - wx * self.scale
        self.offset_y = my - wy * self.scale
        widget.queue_draw()
        return True

    def on_button_press(self, _w, event):
        if event.button in (1, 2):
            self._dragging = True
            self._drag_last = (event.x, event.y)
        return True

    def on_button_release(self, _w, _event):
        self._dragging = False
        return True

    def on_motion(self, widget, event):
        if self._dragging:
            dx = event.x - self._drag_last[0]
            dy = event.y - self._drag_last[1]
            self.offset_x += dx
            self.offset_y += dy
            self._drag_last = (event.x, event.y)
            widget.queue_draw()
        return True
