from pathlib import Path
import sys
import ctypes
import math
import codecs
import os
import tempfile
from time import perf_counter
from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pygments.lexers import get_lexer_for_filename
from pygments.token import Comment, Keyword, Literal, Name, Operator, String
from pygments.util import ClassNotFound

BG, SIDE, FG, DIM, BLUE = "#1f1f1f", "#181818", "#cccccc", "#858585", "#0078d4"
COLORS = [(Comment, "#6a9955"), (String.Regex, "#d16969"), (String, "#ce9178"),
          (Literal.Number, "#b5cea8"), (Keyword.Declaration, "#569cd6"), (Keyword, "#c586c0"),
          (Name.Function, "#dcdcaa"), (Name.Class, "#4ec9b0"), (Name, "#9cdcfe"), (Operator, "#d4d4d4")]
LIMIT = 1024 * 1024


def activity_icon(name):
    # Rasterize at 4x so diagonal strokes stay smooth at taskbar-scale dimensions.
    im = Image.new("RGBA", (96, 96))
    d = ImageDraw.Draw(im)
    ink = "#cccccc" if name == "Explorer" else "#a1a1a1"
    def stroke(points):
        d.line([(4*x, 4*y) for x,y in points], fill=ink, width=6, joint="curve")
    if name == "Explorer":
        stroke([(8,3),(16,3),(20,7),(20,18),(8,18),(8,3)])
        stroke([(16,3),(16,7),(20,7)])
        stroke([(6,7),(4,7),(4,22),(15,22),(15,20)])
    elif name == "Search":
        d.ellipse((36,8,84,56), outline=ink, width=6)
        stroke([(10,14),(2,22)])
    else:
        stroke([(2,7),(2,5),(9,5),(11,8),(22,8),(22,20),(2,20),(2,7)])
        if name == "Parent folder":
            stroke([(9,14),(12,11),(15,14)])
            stroke([(12,12),(12,17)])
    return im.resize((24, 24), Image.Resampling.LANCZOS)


class Viewer:
    def __init__(self, root):
        self.root = root
        root.title("Mervive Code")
        root.geometry("1060x700")
        root.configure(bg=BG)
        self.path = None
        self.editable = False
        self.render_job = None
        root.protocol("WM_DELETE_WINDOW", self.quit_editor)
        self.folder = Path.home()
        self.start = "1.0"
        self.ui = ("Segoe UI", -15)
        root.option_add("*Font", self.ui)
        root.state("zoomed")
        root.update_idletasks()
        # Keep the Windows sizing frame and taskbar identity, and draw the caption in Tk.
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id())
        flags = user32.GetWindowLongW(hwnd, -16)
        user32.SetWindowLongW(hwnd, -16, flags & ~0x00C00000)  # WS_CAPTION
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x37)  # apply frame change
        def maximize():
            root.state("normal" if root.state() == "zoomed" else "zoomed")
        def move_window(event):
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, 0x00A1, 2, 0)  # native caption drag
        def label(parent, text, command=None, **opts):
            widget = tk.Label(parent, text=text, bg=opts.pop("bg", SIDE), fg=opts.pop("fg", FG),
                              font=opts.pop("font", self.ui), bd=0, **opts)
            if command:
                widget.bind("<Button-1>", lambda _: command())
                widget.config(cursor="hand2")
            return widget
        self.status = label(root, "", anchor="e", padx=14)
        self.status.pack(side="bottom", fill="x", ipady=3)
        bar = tk.Frame(root, bg=SIDE, height=43)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Frame(root, bg="#2b2b2b", height=1).pack(fill="x")
        with Image.open(Path(__file__).with_name("mervive-code-sharp.ico")) as artwork:
            self.brand = ImageTk.PhotoImage(artwork.ico.getimage((20, 20)))
        label(bar, "", self.choose_file, image=self.brand).pack(side="left", fill="y", padx=12)
        for glyph, command in [("×",self.quit_editor), ("□",maximize), ("−",root.iconify)]:
            button = tk.Button(bar, text=glyph, command=command, width=4, bd=0, relief="flat",
                               bg=SIDE, fg=FG, activebackground="#343434", activeforeground="white",
                               font=("Segoe UI", -17), highlightthickness=0)
            button.pack(side="right", fill="y")
        self.caption = label(bar, "", anchor="center")
        self.caption.place(relx=.5, rely=.5, anchor="center")
        for surface in (bar, self.caption):
            surface.bind("<Double-Button-1>", lambda _: maximize())
            surface.bind("<B1-Motion>", move_window)

        for title, actions in [
            ("File", [("Open File…", self.choose_file), ("Open Folder…", self.choose_folder), ("Save", self.save), ("Close File", self.close_file)]),
            ("Edit", [("Undo", lambda: self.history("undo")), ("Redo", lambda: self.history("redo")), ("Cut", lambda: self.code.event_generate("<<Cut>>")), ("Paste", lambda: self.code.event_generate("<<Paste>>")), ("Copy", lambda: self.code.event_generate("<<Copy>>")), ("Find…", self.open_find)]),
            ("Selection", [("Select All", lambda: self.code.tag_add("sel","1.0","end-1c"))]),
            ("View", [("Toggle Explorer", self.toggle_sidebar)]),
            ("Go", [("Parent Folder", lambda: self.browse(self.folder.parent))])]:
            mb = tk.Menubutton(bar,text=title,bg=SIDE,fg=FG,activebackground="#343434",activeforeground="white",
                               relief="flat",bd=0,padx=9)
            menu=tk.Menu(mb,tearoff=False,bg=SIDE,fg=FG)
            for caption,action in actions: menu.add_command(label=caption,command=action)
            mb.config(menu=menu)
            mb.pack(side="left")
        main = tk.Frame(root,bg=SIDE)
        main.pack(fill="both",expand=True)
        rail=tk.Frame(main,bg=SIDE,width=52)
        rail.pack(side="left",fill="y")
        rail.pack_propagate(False)
        self.rail_buttons = {}
        tk.Frame(rail, bg="#2b2b2b", width=1).pack(side="right", fill="y")
        actions = [("Explorer", self.toggle_sidebar), ("Search", self.open_find),
                   ("Open folder", self.choose_folder), ("Parent folder", lambda: self.browse(self.folder.parent))]
        for name, command in actions:
            row = tk.Frame(rail, bg=SIDE, height=52)
            row.pack(fill="x")
            row.pack_propagate(False)
            icon = ImageTk.PhotoImage(activity_icon(name))
            btn = tk.Button(row, image=icon, command=command, bg=SIDE, activebackground="#343434",
                            relief="flat", bd=0, highlightthickness=0, cursor="hand2", takefocus=True)
            btn.image = icon
            btn.place(relx=.5, rely=.5, anchor="center", width=38, height=38)
            self.rail_buttons[name] = btn
            btn.bind("<Enter>", lambda e: e.widget.config(bg="#343434"))
            btn.bind("<Leave>", lambda e: self.refresh_activity())
        self.pane = tk.PanedWindow(main, orient="horizontal", bg="#2b2b2b", sashwidth=1, bd=0)
        self.pane.pack(fill="both",expand=True)
        self.sidebar=tk.Frame(self.pane,bg=SIDE)
        self.pane.add(self.sidebar,width=374,minsize=130)
        self.refresh_activity()
        header = tk.Frame(self.sidebar, bg=SIDE, height=44)
        header.pack(fill="x")
        header.pack_propagate(False)
        label(header,"Explorer",font=("Segoe UI",-15,"bold"),padx=24).pack(side="left",fill="y")
        options = tk.Menubutton(header,text="⋯",bg=SIDE,fg=FG,activebackground="#303030",
                                activeforeground="white", relief="flat", bd=0)
        options.pack(side="right",padx=14)
        actions = tk.Menu(options,tearoff=False,bg=SIDE,fg=FG)
        actions.add_command(label="Open Folder…",command=self.choose_folder)
        actions.add_command(label="Refresh folder and file", accelerator="F5", command=self.refresh_workspace)
        root.bind("<F5>", self.refresh_workspace)
        actions.add_command(label="Expand / Collapse Folder",command=lambda:self.set_folder_expanded(not self.folder_expanded))
        options.config(menu=actions)
        self.folder_expanded = True
        self.chevrons = []
        self.chevron_frame = 8
        self.chevron_timer = None
        for frame in range(9):
            angle = math.pi * frame / 16
            points = [(32 + 4 * (x * math.cos(angle) - y * math.sin(angle)),
                       32 + 4 * (x * math.sin(angle) + y * math.cos(angle)))
                      for x, y in [(-3, -6), (3, 0), (-3, 6)]]
            image = Image.new("RGBA", (64, 64))
            ImageDraw.Draw(image).line(points, fill=FG, width=5, joint="curve")
            self.chevrons.append(ImageTk.PhotoImage(image.resize((16, 16), Image.Resampling.LANCZOS)))
        self.folder_label = tk.Button(self.sidebar, anchor="w", compound="left", image=self.chevrons[8],
                                      command=lambda: self.set_folder_expanded(not self.folder_expanded),
                                      bg=SIDE, fg=FG, activebackground=SIDE, activeforeground=FG,
                                      font=("Segoe UI",-15,"bold"), relief="flat", bd=0, padx=4,
                                      highlightthickness=0, cursor="hand2")
        self.folder_label.pack(fill="x", ipady=1)
        self.folder_label.bind("<Left>", lambda _: self.set_folder_expanded(False))
        self.folder_label.bind("<Right>", lambda _: self.set_folder_expanded(True))
        self.files = ttk.Treeview(self.sidebar, show="tree", selectmode="browse", style="Explorer.Treeview")
        self.files.column("#0", stretch=True, minwidth=60)
        self.file_icons = {}
        self.tab_icons = {}
        with Image.open(Path(__file__).with_name("explorer-icons.png")) as atlas:
            for index, suffix in enumerate((".json", ".md", ".js", ".png", ".py", ".exe", "folder", "file", ".ps1", ".c")):
                icon = atlas.crop((20 * index, 0, 20 * index + 20, 20))
                self.tab_icons[suffix] = ImageTk.PhotoImage(icon)
                self.file_icons[suffix] = self.explorer_image(icon)
                if suffix == "folder":
                    for state, frame in [("folder", 0), ("folder_open", 8)]:
                        arrow = ImageTk.getimage(self.chevrons[frame])
                        self.file_icons[state] = self.explorer_image(icon, arrow)
        self.file_icons[".pyw"] = self.file_icons[".py"]
        self.file_icons[".ico"] = self.file_icons[".png"]
        self.files.pack(fill="both",expand=True)
        self.files.bind("<ButtonRelease-1>",self.open_selected)
        self.files.bind("<Return>",self.open_selected)
        self.files.bind("<Double-Button-1>", lambda _: "break")
        self.files.bind("<Left>", self.tree_arrow)
        self.files.bind("<Right>", self.tree_arrow)
        self.loaded_folders = set()
        self.work=tk.Frame(self.pane,bg=BG)
        self.pane.add(self.work,stretch="always")
        tabs=tk.Frame(self.work,bg=SIDE,height=37)
        tabs.pack(fill="x")
        tabs.pack_propagate(False)
        self.tabframe=tk.Frame(tabs,bg=BG,highlightthickness=0)
        tk.Frame(self.tabframe,bg=BLUE,height=1).pack(fill="x")
        self.tabicon=label(self.tabframe,"",fg="#e8b63c",bg=BG,padx=10)
        self.tabicon.pack(side="left",padx=(12,5))
        self.tabname=label(self.tabframe,"",bg=BG,font=("Segoe UI",-15,"italic"))
        self.tabname.pack(side="left")
        label(self.tabframe,"×",self.close_file,bg=BG,padx=12).pack(side="left")
        self.crumb=label(self.work,"",bg=BG,anchor="w",compound="left",padx=20)
        self.image_panel=tk.Label(self.work,bg=BG,bd=0)
        self.findbar=tk.Frame(self.work,bg=SIDE)
        self.query=tk.Entry(self.findbar,bg="#313131",fg=FG,insertbackground=FG,relief="flat")
        self.query.pack(side="left",padx=7,pady=4)
        label(self.findbar,"Find next",self.find,padx=8).pack(side="left")
        label(self.findbar,"×",self.findbar.pack_forget,padx=8).pack(side="left")
        self.query.bind("<Return>", lambda _: self.find())
        root.bind("<Control-f>", lambda _: self.open_find())
        root.bind("<Control-o>", lambda _: self.choose_file())
        self.body=body=tk.Frame(self.work,bg=BG)
        body.rowconfigure(0,weight=1)
        body.columnconfigure(1,weight=1)
        self.gutter=tk.Canvas(body,width=80,bg=BG,highlightthickness=0)
        self.gutter.grid(row=0,column=0,sticky="ns")
        self.code=tk.Text(body,wrap="none",font=("Consolas",-17),bg=BG,fg="#d4d4d4",bd=0,
                          selectbackground="#264f78",relief="flat",padx=6,pady=1,spacing3=3,
                          state="disabled",highlightthickness=0)
        self.code.configure(undo=True, maxundo=500, insertbackground=FG)
        self.code.bind("<<Modified>>", self.changed)
        self.code.bind("<Control-z>", lambda _: self.history("undo"))
        self.code.bind("<Control-y>", lambda _: self.history("redo"))
        self.code.bind("<Control-Shift-Z>", lambda _: self.history("redo"))
        root.bind("<Control-s>", lambda _: (self.save(), "break")[1])
        self.code.configure(tabs=(self.code.tk.call("font","measure",self.code.cget("font"),"    "),))
        self.code.grid(row=0,column=1,sticky="nsew")
        self.mini=tk.Canvas(body,width=112,bg=BG,highlightthickness=0)
        self.mini.grid(row=0,column=2,sticky="ns")
        self.mini.bind("<Button-1>",self.map_click)
        style=ttk.Style(root)
        style.theme_use("clam")
        style.configure("Explorer.Treeview", background=SIDE, fieldbackground=SIDE, foreground=FG,
                        rowheight=28, borderwidth=0, indent=10, font=("Segoe UI", -16))
        style.layout("Explorer.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.layout("Explorer.Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.image", {"side": "left"}), ("Treeitem.text", {"side": "left"})]})])
        style.map("Explorer.Treeview", background=[("selected", "#04395e")],
                  foreground=[("selected", "#ffffff")])
        # Keep native drag and page-click behavior with flat, arrowless handles.
        # Reserve the tracks so fading never moves or resizes the code.
        self.scroll_shade = 31
        self.scroll_target = 31
        self.scroll_timer = None
        self.scroll_drag = False
        self.scrollbars = {}
        for orient, command, row, column, sticky in [
            ("Horizontal", self.code.xview, 1, 1, "ew"),
            ("Vertical", self.code.yview, 0, 3, "ns"),
        ]:
            base = orient + ".Scrollbar"
            name = "Editor." + orient + ".TScrollbar"
            style.layout(name, [(base + ".trough", {"sticky": "nswe", "children": [
                (base + ".thumb", {"sticky": "nswe"})]})])
            style.configure(name, troughcolor=BG, bordercolor=BG, borderwidth=0,
                            arrowsize=12, gripcount=0)
            bar = ttk.Scrollbar(body, orient=orient.lower(), command=command,
                                style=name, takefocus=False)
            bar.grid(row=row, column=column, sticky=sticky)
            bar.bind("<ButtonPress-1>", lambda _: self.scroll_pressed(True))
            bar.bind("<ButtonRelease-1>", lambda _: self.scroll_pressed(False))
            self.scrollbars[orient] = bar
        # Preserve dimensions even if either axis fits its contents.
        self.body.rowconfigure(1, minsize=self.scrollbars["Horizontal"].winfo_reqheight())
        self.body.columnconfigure(3, minsize=self.scrollbars["Vertical"].winfo_reqwidth())
        self.paint_scrollbars()
        for surface in (self.code, self.gutter, *self.scrollbars.values()):
            surface.bind("<Enter>", lambda _: self.fade_scrollbars(True), add="+")
            surface.bind("<Leave>", lambda _: self.fade_scrollbars(False), add="+")
        self.welcome=tk.Frame(self.work,bg=BG)
        center=tk.Frame(self.welcome,bg=BG)
        center.place(relx=.5,rely=.5,anchor="center")
        label(center,"⌁",bg=BG,fg="white",font=("Segoe UI Symbol",-54)).pack()
        label(center,"Mervive Code",bg=BG,font=("Segoe UI",-22)).pack(pady=12)
        label(center,"Open file     Ctrl + O",self.choose_file,bg=BG,fg=DIM).pack(pady=20)
        def scrolled(first, last):
            self.set_scroll_range("Vertical", first, last)
            self.draw_lines()
        self.code.configure(yscrollcommand=scrolled, xscrollcommand=lambda a, b: self.set_scroll_range("Horizontal", a, b))
        self.code.bind("<Configure>", lambda _: self.draw_lines())
        for token, color in COLORS:
            self.code.tag_configure(str(token), foreground=color)
        self.code.tag_configure("match", background="#594628", foreground="#fff3c4")
        self.code.tag_configure("call",foreground="#dcdcaa")
        self.code.tag_configure("declaration",foreground="#569cd6")
        self.close_file()
        self.start = "1.0"

    def set_scroll_range(self, orient, first, last):
        bar = self.scrollbars[orient]
        bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            bar.grid_remove()
        elif not bar.winfo_manager():
            bar.grid()


    def paint_scrollbars(self):
        color = "#" + f"{self.scroll_shade:02x}" * 3
        style = ttk.Style(self.root)
        for bar in self.scrollbars.values():
            style.map(bar.cget("style"), **{option: [("", color)] for option in
                      ("background", "lightcolor", "darkcolor", "bordercolor")})

    def scroll_pressed(self, pressed):
        self.scroll_drag = pressed
        x, y = self.root.winfo_pointerxy()
        surface = self.root.winfo_containing(x, y)
        self.fade_scrollbars(pressed or surface in (self.code, self.gutter, *self.scrollbars.values()))

    def fade_scrollbars(self, visible):
        self.scroll_target = 79 if visible or self.scroll_drag else 31
        if self.scroll_timer is None:
            self.advance_scroll_fade()

    def advance_scroll_fade(self):
        self.scroll_timer = None
        delta = self.scroll_target - self.scroll_shade
        if delta:
            self.scroll_shade += max(-5, min(5, delta))
            self.paint_scrollbars()
            self.scroll_timer = self.root.after(14, self.advance_scroll_fade)

    def refresh_activity(self):
        visible = str(self.sidebar) in self.pane.panes()
        for name, button in self.rail_buttons.items():
            button.config(bg="#303030" if name == "Explorer" and visible else SIDE)

    def toggle_sidebar(self):
        if str(self.sidebar) in self.pane.panes():
            self.pane.forget(self.sidebar)
        else:
            self.pane.add(self.sidebar,before=self.work,width=374)

        self.refresh_activity()

    def open_find(self):
        if self.path and self.body.winfo_manager():
            self.findbar.pack(before=self.body,anchor="e")
            self.query.focus_set()
            self.query.selection_range(0,"end")

    def history(self, action):
        if self.editable:
            try:
                getattr(self.code, "edit_" + action)()
            except tk.TclError:
                self.root.bell()
        return "break"

    def changed(self, event=None):
        if not self.code.edit_modified():
            return
        self.code.edit_modified(False)
        if self.editable:
            self.tabname.config(text=self.path.name + " •")
            if self.render_job:
                self.root.after_cancel(self.render_job)
            self.render_job = self.root.after(350, self.refresh_text)

    def refresh_text(self):
        self.render_job = None
        if self.editable:
            source = self.code.get("1.0", "end-1c")
            self.highlight(self.path, source)
            self.draw_map(source)
            self.tabname.config(text=self.path.name + (" •" if source != self.original else ""))

    def can_leave(self):
        if not self.editable or self.code.get("1.0", "end-1c") == self.original:
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", f"Save changes to {self.path.name}?")
        return answer is False or (answer is True and self.save())

    def quit_editor(self):
        if self.can_leave():
            self.root.destroy()

    def deactivate(self):
        self.editable = False
        if self.render_job:
            self.root.after_cancel(self.render_job)
            self.render_job = None

    def save(self):
        if not self.editable:
            return False
        source = self.code.get("1.0", "end-1c")
        if source == self.original:
            return True
        temp = None
        try:
            payload = self.bom + source.replace("\n", self.newline).encode(self.codec)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                temp = Path(stream.name)
                stream.write(payload)
            if self.path.read_bytes() != self.saved_bytes:
                messagebox.showerror("Save", "The file changed on disk. Your edits are still open. Copy them before reopening the file.")
                return False
            if not ctypes.windll.kernel32.ReplaceFileW(str(self.path), str(temp), None, 0, None, None):
                raise ctypes.WinError()
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("Save", str(exc))
            return False
        finally:
            if temp:
                temp.unlink(missing_ok=True)
        self.saved_bytes = payload
        self.original = source
        self.code.edit_separator()
        self.tabname.config(text=self.path.name)
        return True

    def close_file(self):
        if not self.can_leave():
            return
        self.deactivate()
        self.path=None
        self.image_panel.pack_forget()
        self.tabframe.pack_forget()
        self.crumb.pack_forget()
        self.body.pack_forget()
        self.findbar.pack_forget()
        self.welcome.pack(fill="both",expand=True)
        self.status.config(text="")
        self.root.title(f"{self.folder.name} — Mervive Code")
        self.caption.config(text=self.root.title())

    def map_click(self,event):
        if self.map_lines:
            line=int(event.y / self.map_height * self.map_lines)+1
            self.code.yview(f"{min(self.map_lines,line)}.0")

    def draw_map(self,source):
        lines=source.split("\n")
        self.map_lines=len(lines)
        self.map_height=min(780,max(2,len(lines)*2))
        im=Image.new("RGB",(112,self.map_height),BG)
        pixels = im.load()
        for y in range(0,self.map_height,2):
            line=lines[y*len(lines)//self.map_height][:104]
            for x,ch in enumerate(line):
                if not ch.isspace():
                    pixels[4+x, y] = (155, 130, 117) if ch.isalpha() else (116, 146, 156)
        self.preview=ImageTk.PhotoImage(im)
        self.mini.delete("all")
        self.mini.create_image(0,0,image=self.preview,anchor="nw")

    def draw_lines(self):
        self.gutter.delete("all")
        index = self.code.index("@0,0")
        while info := self.code.dlineinfo(index):
            self.gutter.create_text(53, info[1], anchor="ne", text=index.split(".")[0],
                                    fill=DIM, font=("Consolas", -17))
            index = self.code.index(index + " +1line")
            if self.code.compare(index, ">=", "end"):
                break

    def set_folder_expanded(self, expanded):
        self.folder_expanded = expanded
        target = 8 if expanded else 0
        if self.chevron_timer is not None:
            self.root.after_cancel(self.chevron_timer)
        start = self.chevron_frame
        began = perf_counter()
        def advance():
            progress = min(1, (perf_counter() - began) / 0.12)
            self.chevron_frame = round(start + (target - start) * (1 - (1 - progress) ** 2))
            self.folder_label.configure(image=self.chevrons[self.chevron_frame])
            self.chevron_timer = self.root.after(12, advance) if progress < 1 and start != target else None
        advance()
        if expanded:
            self.files.pack(fill="both", expand=True)
        else:
            self.files.pack_forget()

    def folder_items(self, path):
        try:
            return sorted((item for item in path.iterdir() if item.name != ".git"),
                          key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError as exc:
            messagebox.showerror("Open folder", str(exc))
            return None

    def insert_items(self, parent, items):
        for item in items:
            directory = item.is_dir()
            key = "folder" if directory else item.suffix.lower()
            self.files.insert(parent, "end", iid=str(item), text=item.name,
                              tags=("directory",) if directory else (),
                              image=self.file_icons.get(key, self.file_icons["file"]))

    def browse(self, path):
        items = self.folder_items(path)
        if items is None:
            return
        expanded = sorted((node for node in self.loaded_folders if self.files.item(node, "open")),
                          key=lambda node: len(Path(node).parts)) if path == self.folder else []
        self.folder = path
        self.folder_label.config(text=path.name or str(path))
        self.set_folder_expanded(True)
        self.files.delete(*self.files.get_children())
        self.loaded_folders.clear()
        self.insert_items("", items)
        for node in expanded:
            if self.files.exists(node) and self.files.tag_has("directory", node):
                self.set_branch(node, True)

    def refresh_workspace(self, event=None):
        selected = self.files.focus()
        tree_top = self.files.yview()[0]
        expanded = self.folder_expanded
        focus = self.root.focus_get()
        self.browse(self.folder)
        if not expanded:
            self.set_folder_expanded(False)

        if self.path:
            dirty = self.editable and self.code.get("1.0", "end-1c") != self.original
            if dirty:
                self.status.config(text="Folder refreshed · Unsaved edits kept")
            elif not self.path.is_file():
                self.close_file()
            else:
                cursor = self.code.index("insert")
                top = self.code.index("@0,0").split(".")[0] + ".0"
                left = self.code.xview()[0]
                self.show(self.path, reload=True)
                self.code.mark_set("insert", cursor)
                self.code.yview(top)
                self.code.xview_moveto(left)

        if selected and self.files.exists(selected):
            self.files.focus(selected)
            self.files.selection_set(selected)
        self.files.yview_moveto(tree_top)
        if focus and focus.winfo_ismapped():
            focus.focus_set()
        return "break"

    def set_branch(self, node, expanded):
        if expanded and node not in self.loaded_folders:
            items = self.folder_items(Path(node))
            if items is None:
                return
            self.insert_items(node, items)
            self.loaded_folders.add(node)
        self.files.item(node, open=expanded,
                        image=self.file_icons["folder_open" if expanded else "folder"])

    def tree_arrow(self, event):
        node = self.files.focus()
        if not node:
            return "break"
        folder = self.files.tag_has("directory", node)
        expanded = bool(self.files.item(node, "open"))
        if event.keysym == "Right":
            if folder and not expanded:
                self.set_branch(node, True)
                return "break"
            children = self.files.get_children(node)
            target = children[0] if children else None
        else:
            if folder and expanded:
                self.set_branch(node, False)
                return "break"
            target = self.files.parent(node)
        if target:
            self.files.focus(target)
            self.files.selection_set(target)
            self.files.see(target)
        return "break"

    @staticmethod
    def explorer_image(icon, arrow=None):
        # Treeview paints this image from the top of the row. Include the
        # row height so the glyph sits alongside the filename's baseline.
        row = Image.new("RGBA", (63, 28))
        if arrow is not None:
            row.paste(arrow, (15, 6))
        bounds = icon.getbbox()
        if bounds:
            glyph = icon.crop(bounds)
            row.paste(glyph, (46 - glyph.width // 2, 14 - glyph.height // 2))
        return ImageTk.PhotoImage(row)

    def open_selected(self, event):
        node = self.files.identify_row(event.y) if event.type == tk.EventType.ButtonRelease else self.files.focus()
        if node and not Path(node).exists():
            return self.refresh_workspace()
        if node:
            self.files.focus(node)
            self.files.selection_set(node)
            if self.files.tag_has("directory", node):
                self.set_branch(node, not self.files.item(node, "open"))
            else:
                self.show(Path(node))
        return "break"

    def choose_file(self):
        if name := filedialog.askopenfilename(initialdir=self.folder):
            path = Path(name)
            if path.is_relative_to(self.folder):
                branch = self.folder
                for part in path.parent.relative_to(self.folder).parts:
                    branch /= part
                    if self.files.exists(str(branch)):
                        self.set_branch(str(branch), True)
            else:
                self.browse(path.parent)
            self.show(path)

    def choose_folder(self):
        if name := filedialog.askdirectory(initialdir=self.folder):
            self.browse(Path(name))

    def display_header(self,path):
        self.path=path
        self.welcome.pack_forget()
        self.tabframe.pack(side="left",fill="y")
        self.tabname.config(text=path.name)
        suffix = path.suffix.lower()
        key = {".ico":".png",".pyw":".py"}.get(suffix,suffix)
        icon = self.tab_icons.get(key,self.tab_icons["file"])
        self.tabicon.config(image=icon)
        self.crumb.config(image=icon,text=f"  {path.name}")
        if not self.crumb.winfo_manager():
            self.crumb.pack(fill="x", ipady=4)
        if self.files.exists(str(path)):
            self.files.selection_set(str(path))
            self.files.focus(str(path))
        self.root.title(f"{self.folder.name} — Mervive Code — {path.name}")
        self.caption.config(text=self.root.title())

    def show_image(self,path):
        try:
            with Image.open(path) as im:
                im.thumbnail((640,640),Image.Resampling.LANCZOS)
                preview = ImageTk.PhotoImage(im.convert("RGBA"))
        except (OSError,ValueError,Image.DecompressionBombError) as exc:
            messagebox.showerror("Open image",str(exc))
            return
        self.deactivate()
        self.display_header(path)
        self.body.pack_forget()
        self.findbar.pack_forget()
        self.image_panel.config(image=preview)
        self.image_panel.image=preview
        self.image_panel.pack(fill="both",expand=True)
        self.status.config(text=path.name)

    def show(self, path, *, reload=False):
        if self.path == path and self.editable and not reload:
            self.code.focus_set()
            return
        if not self.can_leave():
            if self.path and self.files.exists(str(self.path)):
                self.files.selection_set(str(self.path))
                self.files.focus(str(self.path))
            return
        if path.suffix.lower() in (".ico", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"):
            self.show_image(path)
            return
        try:
            with path.open("rb") as stream:
                data = stream.read(LIMIT + 1)
            sample = data[:LIMIT]
            bom, codec = b"", "utf-8"
            for prefix, name in [(codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"), (codecs.BOM_UTF8, "utf-8")]:
                if sample.startswith(prefix):
                    bom, codec = prefix, name
                    break
            if codec == "utf-8" and b"\0" in sample:
                raise ValueError("This file contains binary data.")
            editable = len(data) <= LIMIT
            try:
                source = sample[len(bom):].decode(codec)
            except UnicodeDecodeError:
                source = sample[len(bom):].decode(codec, errors="replace")
                editable = False
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open file", str(exc))
            return
        if (getattr(self, "buffer_path", None) == path and self.saved_bytes == data
                and self.code.get("1.0", "end-1c") == self.original):
            self.deactivate()
            self.editable = self.code.cget("state") == "normal"
            self.display_header(path)
            self.image_panel.pack_forget()
            self.body.pack(fill="both", expand=True)
            self.status.config(text=self.document_status)
            self.code.focus_set()
            return
        self.deactivate()
        crlf = source.count("\r\n")
        newline_types = [ending for ending, count in [("\r\n", crlf), ("\n", source.count("\n") - crlf),
                                                      ("\r", source.count("\r") - crlf)] if count]
        self.newline = next(iter(newline_types), os.linesep)
        self.codec, self.bom = codec, bom
        source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.buffer_path = path
        self.original, self.saved_bytes = source, data
        self.editable = editable and len(newline_types) <= 1 and "\0" not in source
        self.code.config(state="normal", undo=False)
        self.code.delete("1.0", "end")
        self.code.insert("1.0", source)
        self.code.mark_set("insert", "1.0")
        self.code.config(undo=True, state="normal" if self.editable else "disabled")
        self.code.edit_reset()
        self.code.edit_modified(False)
        self.start = "1.0"
        detail = self.highlight(path, source)
        self.display_header(path)
        self.image_panel.pack_forget()
        self.body.pack(fill="both", expand=True)
        self.draw_map(source)
        endings = {"\n": "LF", "\r": "CR", "\r\n": "CRLF"}[self.newline] if len(newline_types) <= 1 else "Mixed endings"
        state = "" if self.editable else "    Read-only preview"
        if len(data) > LIMIT:
            state += " (first 1 MiB)"
        self.document_status = f"{codec.upper()}     {endings}      {{ }}  {detail}{state}"
        self.status.config(text=self.document_status)
        self.code.yview_moveto(0)
        self.code.xview_moveto(0)
        self.code.focus_set()

    def highlight(self, path, source):
        for tag in [str(token) for token, _ in COLORS] + ["declaration", "call"]:
            self.code.tag_remove(tag, "1.0", "end")
        detail = "Plain text"
        if len(source) <= 128 * 1024:
            try:
                lexer = get_lexer_for_filename(path.name)
                detail = lexer.name
                ranges = {str(token): [] for token, _ in COLORS}
                line, column = 1, 0
                for pos, kind, value in lexer.get_tokens_unprocessed(source):
                    start_index = f"{line}.{column}"
                    breaks = value.count("\n")
                    if breaks:
                        line += breaks
                        column = len(value.rsplit("\n", 1)[1])
                    else:
                        column += len(value)
                    end_index=f"{line}.{column}"
                    if kind in Name and source[pos+len(value):pos+len(value)+1]=="(":
                        self.code.tag_add("call", start_index,end_index)
                    if kind in Keyword and value in ("const","let","var","function"):
                        self.code.tag_add("declaration",start_index,end_index)
                    for token, _ in COLORS:
                        if kind in token and value:
                            ranges[str(token)].extend((start_index, f"{line}.{column}"))
                            break
                for tag, indices in ranges.items():
                    for offset in range(0, len(indices), 512):
                        self.code.tag_add(tag, *indices[offset:offset + 512])
            except ClassNotFound:
                pass
        return detail

    def find(self):
        term = self.query.get()
        self.code.tag_remove("match", "1.0", "end")
        if not term:
            return
        hit = self.code.search(term, self.start, stopindex="end", nocase=True)
        if not hit:
            hit = self.code.search(term, "1.0", stopindex="end", nocase=True)
        if hit:
            self.start = self.code.index(f"{hit}+{len(term)}c")
            self.code.tag_add("match", hit, self.start)
            self.code.see(hit)
        else:
            self.root.bell()


if __name__ == "__main__":
    ctypes.windll.user32.SetProcessDPIAware()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mervive.Code.Viewer")
    root = tk.Tk()
    root.iconbitmap(default=str(Path(__file__).with_name("mervive-code-sharp.ico")))
    app = Viewer(root)
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.home()
    app.browse(path if path.is_dir() else path.parent)
    if path.is_file():
        app.show(path)
    root.mainloop()
