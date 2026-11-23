"""Continuous PDF preview with a viewport-sized page cache. The native renderer is loaded only when opening a PDF."""
from bisect import bisect_right
import math
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import ImageTk


class PdfPreview(tk.Frame):
    def __init__(self, parent, background, foreground):
        super().__init__(parent, bg=background)
        self.path = None
        self.index = 0
        self.pages = {}
        self.render_job = None
        self.percent = 100
        self.wheel_remainder = 0.0
        self.tops = []
        self.redraw_job = None
        self.mode = tk.StringVar(value="Reading size")
        toolbar = tk.Frame(self, bg=background)
        toolbar.pack(fill="x", padx=10, pady=4)

        def button(label, command):
            control = tk.Button(toolbar, text=label, command=command, bg=background,
                                fg=foreground, relief="flat", bd=0, padx=8)
            control.pack(side="left")
            return control

        self.previous = button("Previous", lambda: self.turn(-1))
        self.counter = tk.Label(toolbar, bg=background, fg=foreground)
        self.counter.pack(side="left")
        self.next_page = button("Next", lambda: self.turn(1))
        button("−", lambda: self.zoom(-1))
        self.levels = (50, 75, 90, 100, 110, 125, 150, 175, 200, 250, 300)
        choices = ("Reading size", "Fit page", "Fit width", *(f"{n}%" for n in self.levels))
        menu = tk.OptionMenu(toolbar, self.mode, *choices, command=lambda _: self.redraw())
        menu.configure(bg=background, fg=foreground, relief="flat", highlightthickness=0)
        menu["menu"].configure(bg=background, fg=foreground)
        menu.pack(side="left")
        button("+", lambda: self.zoom(1))

        pane = tk.Frame(self, bg=background)
        pane.pack(fill="both", expand=True)
        pane.columnconfigure(0, weight=1)
        pane.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(pane, bg=background, highlightthickness=0, yscrollincrement=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(pane, orient="vertical", command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal = ttk.Scrollbar(pane, orient="horizontal", command=self.canvas.xview)
        self.horizontal.grid(row=1, column=0, sticky="ew")
        self.horizontal.grid_remove()
        def scrolled(first, last):
            vertical.set(first, last)
            self.schedule_render()
        self.canvas.configure(yscrollcommand=scrolled, xscrollcommand=self.horizontal.set)
        self.canvas.bind("<Configure>", self.resize_page)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Control-MouseWheel>", lambda e: self.zoom(1 if e.delta > 0 else -1))

    def wheel(self, event):
        if not self.path or not event.delta:
            return
        self.wheel_remainder -= event.delta * 48 / 120
        pixels = int(self.wheel_remainder)
        self.wheel_remainder -= pixels
        self.canvas.yview_scroll(pixels, "units")
        return "break"

    def zoom(self, step):
        if self.path:
            candidates = [n for n in self.levels if (n - self.percent) * step > 0.5]
            if candidates:
                self.mode.set(f"{min(candidates) if step > 0 else max(candidates)}%")
                self.redraw()
        return "break"

    def resize_page(self, event):
        if self.path and (event.width, event.height) != self.render_size:
            if self.redraw_job:
                self.after_cancel(self.redraw_job)
            self.redraw_job = self.after(120, self.redraw)

    def redraw(self):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
        self.redraw_job = None
        if self.path:
            self.layout(*self.anchor())

    def turn(self, step):
        index = self.index + step
        if self.path and 0 <= index < len(self.tops):
            self.canvas.yview_moveto((self.tops[index] - 16) / self.total_height)

    def anchor(self):
        y = self.canvas.canvasy(0)
        index = max(0, bisect_right(self.tops, y) - 1)
        return index, (y - self.tops[index]) / self.heights[index]

    def display(self, path, index):
        try:
            import pypdfium2
            document = pypdfium2.PdfDocument(path)
            try:
                sizes = [document.get_page_size(i) for i in range(len(document))]
                if not sizes or any(min(size) <= 0 for size in sizes):
                    raise ValueError("This PDF has no displayable page dimensions.")
            finally:
                document.close()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Open PDF", str(exc), parent=self)
            return False
        same = self.path == path
        index, fraction = self.anchor() if same else (index, 0)
        self.path, self.sizes = path, sizes
        self.layout(min(index, len(sizes) - 1), fraction, same)
        return True

    def layout(self, index, fraction, preserve_x=True):
        area = self.canvas if self.winfo_ismapped() else self.master
        width, height = self.render_size = (area.winfo_width(), area.winfo_height())
        left = self.canvas.xview()[0] if preserve_x else 0
        self.canvas.delete("all")
        self.pages.clear()
        self.tops, self.heights, self.scales = [], [], []
        mode = self.mode.get()
        self.actual_size = self.winfo_fpixels("1i") / 72
        self.extent = width
        top = 16
        for w, h in self.sizes:
            fit_width = max(1, width - 32) / w
            if mode == "Reading size":
                scale = min(self.actual_size, fit_width)
            elif mode == "Fit width":
                scale = fit_width
            elif mode == "Fit page":
                scale = min(fit_width, max(1, height - 32) / h)
            else:
                scale = self.actual_size * int(mode[:-1]) / 100
            scale = min(scale, math.sqrt(8_000_000 / (w * h)))
            page_height = math.ceil(h * scale)
            self.tops.append(top)
            self.heights.append(page_height)
            self.scales.append(scale)
            self.extent = max(self.extent, math.ceil(w * scale) + 32)
            top += page_height + 16
        self.total_height = top
        self.canvas.configure(scrollregion=(0, 0, self.extent, top))
        if self.extent > width:
            self.horizontal.grid()
        else:
            self.horizontal.grid_remove()
        self.canvas.xview_moveto(left)
        offset = self.tops[index] + fraction * self.heights[index]
        self.canvas.yview_moveto(max(0, offset if preserve_x else offset - 16) / top)
        self.schedule_render()

    def schedule_render(self):
        if self.path and self.render_job is None:
            self.render_job = self.after_idle(self.render_visible)

    def render_visible(self):
        self.render_job = None
        if not self.path:
            return
        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()
        first = max(0, bisect_right(self.tops, top) - 1)
        last = max(first, bisect_right(self.tops, bottom) - 1)
        count = len(self.tops)
        self.index = max(0, bisect_right(self.tops, (top + bottom) / 2) - 1)
        self.percent = self.scales[self.index] / self.actual_size * 100
        self.counter.config(text=f"Page {self.index + 1} of {count}")
        self.previous.config(state="normal" if self.index else "disabled")
        self.next_page.config(state="normal" if self.index + 1 < count else "disabled")
        nearby = range(max(0, first - 1), min(count, last + 2))
        for i in list(self.pages):
            if i not in nearby:
                self.canvas.delete(self.pages.pop(i)[0])
        # Visible pages first. Yield to scroll and paint events between renders.
        for i in (*range(first, last + 1), *nearby):
            if i in self.pages:
                continue
            import pypdfium2
            try:
                document = pypdfium2.PdfDocument(self.path)
                try:
                    page = document[i]
                    try:
                        bitmap = page.render(scale=self.scales[i])
                        try:
                            image = ImageTk.PhotoImage(bitmap.to_pil())
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                finally:
                    document.close()
                item = self.canvas.create_image(self.extent // 2, self.tops[i], anchor="n", image=image)
            except (OSError, RuntimeError, ValueError, IndexError) as exc:
                image = None
                item = self.canvas.create_text(self.extent // 2, self.tops[i] + 16,
                                               fill="white", text=f"Page {i + 1}: {exc}")
            self.pages[i] = item, image
            self.render_job = self.after(1, self.render_visible)
            break

    def hide(self):
        for job in (self.redraw_job, self.render_job):
            if job:
                self.after_cancel(job)
        self.redraw_job = self.render_job = None
        self.path = None
        self.pack_forget()
        self.canvas.delete("all")
        self.pages.clear()
