"""Single-page PDF preview. The native renderer is loaded only when opening a PDF."""
import math
import tkinter as tk
from tkinter import messagebox
from PIL import ImageTk


class PdfPreview(tk.Frame):
    def __init__(self, parent, background, foreground):
        super().__init__(parent, bg=background)
        self.path = None
        self.index = 0
        self.image = None
        self.redraw_job = None
        toolbar = tk.Frame(self, bg=background)
        toolbar.pack(fill="x")
        def button(label, step):
            control = tk.Button(toolbar, text=label, command=lambda: self.turn(step),
                                bg=background, fg=foreground, relief="flat", bd=0, padx=8)
            control.pack(side="left")
            return control
        self.previous = button("Previous", -1)
        self.counter = tk.Label(toolbar, bg=background, fg=foreground)
        self.counter.pack(side="left")
        self.next_page = button("Next", 1)
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.resize_page)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-int(e.delta / 120)*3, "units"))

    def resize_page(self, event):
        if self.path and event.width != self.render_width:
            if self.redraw_job:
                self.after_cancel(self.redraw_job)
            self.redraw_job = self.after(120, self.redraw)

    def redraw(self):
        self.redraw_job = None
        if self.path:
            self.display(self.path, self.index)

    def turn(self, step):
        self.display(self.path, self.index + step)

    def display(self, path, index):
        try:
            import pypdfium2
            width = self.canvas.winfo_width() if self.winfo_ismapped() else self.master.winfo_width()
            document = pypdfium2.PdfDocument(path)
            try:
                count = len(document)
                if not count:
                    raise ValueError("This PDF has no pages.")
                index = max(0, min(index, count - 1))
                page = document[index]
                try:
                    w, h = page.get_size()
                    scale = min(max(1, width - 24) / w, 2.5, math.sqrt(5_000_000 / (w * h)))
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
        self.path, self.index, self.image, self.render_width = path, index, image, width
        self.counter.config(text=f"Page {index + 1} of {count}")
        self.previous.config(state="normal" if index else "disabled")
        self.next_page.config(state="normal" if index + 1 < count else "disabled")
        self.canvas.delete("all")
        self.canvas.create_image(max(width, image.width()) // 2, 0, anchor="n", image=image)
        self.canvas.configure(scrollregion=(0, 0, width, image.height()))
        self.canvas.yview_moveto(0)
        return True

    def hide(self):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
            self.redraw_job = None
        self.pack_forget()
        self.canvas.delete("all")
        self.path = self.image = None
