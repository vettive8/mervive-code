"""Single-page PDF preview. The native renderer is loaded only when opening a PDF."""
import math
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import ImageTk


class PdfPreview(tk.Frame):
    def __init__(self, parent, background, foreground):
        super().__init__(parent, bg=background)
        self.path = None
        self.index = 0
        self.image = None
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
        self.canvas = tk.Canvas(pane, bg=background, highlightthickness=0, yscrollincrement=16)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(pane, orient="vertical", command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal = ttk.Scrollbar(pane, orient="horizontal", command=self.canvas.xview)
        self.horizontal.grid(row=1, column=0, sticky="ew")
        self.horizontal.grid_remove()
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=self.horizontal.set)
        self.canvas.bind("<Configure>", self.resize_page)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Control-MouseWheel>", lambda e: self.zoom(1 if e.delta > 0 else -1))

    def wheel(self, event):
        if not self.path or not event.delta:
            return
        first, last = self.canvas.yview()
        direction = -1 if event.delta > 0 else 1
        if (direction > 0 and last >= 1) or (direction < 0 and first <= 0):
            if self.turn(direction) and direction < 0:
                self.canvas.yview_moveto(1)
        else:
            self.canvas.yview_scroll(direction * max(1, abs(event.delta) // 120) * 3, "units")
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
            self.display(self.path, self.index)

    def turn(self, step):
        index = self.index + step
        if self.path and 0 <= index < self.count:
            return self.display(self.path, index)
        return False

    def display(self, path, index):
        same_page = self.path == path and self.index == index
        top = self.canvas.yview()[0] if same_page else 0
        left = self.canvas.xview()[0] if same_page else 0
        try:
            import pypdfium2
            area = self.canvas if self.winfo_ismapped() else self.master
            width, height = area.winfo_width(), area.winfo_height()
            document = pypdfium2.PdfDocument(path)
            try:
                count = len(document)
                if not count:
                    raise ValueError("This PDF has no pages.")
                index = max(0, min(index, count - 1))
                page = document[index]
                try:
                    w, h = page.get_size()
                    actual_size = self.winfo_fpixels("1i") / 72
                    fit_width = max(1, width - 32) / w
                    mode = self.mode.get()
                    if mode == "Reading size":
                        scale = min(actual_size, fit_width)
                    elif mode == "Fit width":
                        scale = fit_width
                    elif mode == "Fit page":
                        scale = min(fit_width, max(1, height - 32) / h)
                    else:
                        scale = actual_size * int(mode[:-1]) / 100
                    scale = min(scale, math.sqrt(8_000_000 / (w * h)))
                    bitmap = page.render(scale=scale)
                    try:
                        image = ImageTk.PhotoImage(bitmap.to_pil())
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                document.close()
        except (ImportError, OSError, RuntimeError, ValueError, ZeroDivisionError) as exc:
            messagebox.showerror("Open PDF", str(exc), parent=self)
            return False
        self.path, self.index, self.image = path, index, image
        self.count, self.percent, self.render_size = count, scale / actual_size * 100, (width, height)
        self.counter.config(text=f"Page {index + 1} of {count}")
        self.previous.config(state="normal" if index else "disabled")
        self.next_page.config(state="normal" if index + 1 < count else "disabled")
        self.canvas.delete("all")
        extent = max(width, image.width() + 32)
        self.canvas.create_image(extent // 2, 16, anchor="n", image=image)
        self.canvas.configure(scrollregion=(0, 0, extent, image.height() + 32))
        if extent > width:
            self.horizontal.grid()
        else:
            self.horizontal.grid_remove()
        self.canvas.xview_moveto(left)
        self.canvas.yview_moveto(top)
        return True

    def hide(self):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
            self.redraw_job = None
        self.pack_forget()
        self.canvas.delete("all")
        self.path = self.image = None
