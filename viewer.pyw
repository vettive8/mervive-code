from pathlib import Path
from pdf_preview import PdfPreview
from explorer_drop import transfer_dropped_items
from concurrent.futures import ThreadPoolExecutor
from tkinterdnd2 import TkinterDnD, DND_FILES, COPY, MOVE, REFUSE_DROP
import explorer_order
import sys
import ctypes
from ctypes import wintypes
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


def folder_setting():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Mervive Code" / "last-folder.txt"


def startup_folder():
    try:
        path = Path(folder_setting().read_text(encoding="utf-8"))
        if path.is_absolute() and path.is_dir():
            return path
    except (OSError, ValueError):
        pass
    return Path.home()


def remember_folder(folder):
    target = folder_setting()
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False, mode="w", encoding="utf-8") as stream:
            temporary = Path(stream.name)
            stream.write(str(folder))
        temporary.replace(target)
    except OSError:
        if temporary:
            temporary.unlink(missing_ok=True)


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


def configure_window_frame(root):
    """Keep the native frame, but move this window without starting Aero Shake."""
    user = ctypes.windll.user32
    hwnd = user.GetParent(root.winfo_id())
    enabled = wintypes.BOOL(1)
    for attribute in (20, 3):  # Immersive dark caption, disable DWM transition bitmaps
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(enabled), 4)

    repaint_job = None

    def repaint():
        nonlocal repaint_job
        repaint_job = None
        user.RedrawWindow(hwnd, None, None, 0x0181)  # invalidate and paint all children

    def request_repaint(event):
        nonlocal repaint_job
        if event.widget is root and repaint_job is None:
            repaint_job = root.after_idle(repaint)

    root.bind("<Map>", request_repaint, add="+")
    root.bind("<Configure>", request_repaint, add="+")

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("bounds", wintypes.RECT),
                    ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

    user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user.MonitorFromPoint.restype = wintypes.HANDLE
    user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user.MonitorFromWindow.restype = wintypes.HANDLE

    def snap_at_top(window, start_x, start_y):
        point = wintypes.POINT()
        if not user.GetCursorPos(ctypes.byref(point)):
            return
        if abs(point.x - start_x) + abs(point.y - start_y) < 5:
            return
        monitor = user.MonitorFromPoint(point, 0)
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if monitor and user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            if 0 <= point.y - info.bounds.top <= 4:
                if user.MonitorFromWindow(window, 2) != monitor:
                    user.SetWindowPos(window, 0, info.work.left, info.work.top, 0, 0, 0x15)
                user.ShowWindow(window, 3)  # SW_MAXIMIZE uses the monitor work area.

    controls = ctypes.windll.comctl32
    word, signed = ctypes.c_size_t, ctypes.c_ssize_t
    callback = ctypes.WINFUNCTYPE(signed, wintypes.HWND, wintypes.UINT, word, signed, word, word)
    controls.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, word, signed]
    controls.DefSubclassProc.restype = signed
    controls.SetWindowSubclass.argtypes = [wintypes.HWND, callback, word, word]
    controls.RemoveWindowSubclass.argtypes = [wintypes.HWND, callback, word]
    drag = None
    user.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
    ctypes.windll.gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    ctypes.windll.gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    brush = ctypes.windll.gdi32.CreateSolidBrush(0x1f1f1f)

    @callback
    def caption_proc(window, message, key, data, ident, reference):
        nonlocal drag
        if message == 0x00A1 and key == 2:  # WM_NCLBUTTONDOWN on HTCAPTION
            rect = wintypes.RECT()
            user.GetWindowRect(window, ctypes.byref(rect))
            point = wintypes.POINT()
            user.GetCursorPos(ctypes.byref(point))
            drag = (point.x - rect.left, point.y - rect.top, rect.right - rect.left,
                    point.x, point.y)
            user.SetCapture(window)
            return 0
        if drag is not None and message == 0x0200:  # WM_MOUSEMOVE
            dx, dy, width, start_x, start_y = drag
            point = wintypes.POINT()
            user.GetCursorPos(ctypes.byref(point))
            if user.IsZoomed(window):
                if abs(point.x - start_x) + abs(point.y - start_y) < 5:
                    return 0
                user.ShowWindow(window, 9)  # SW_RESTORE
                rect = wintypes.RECT()
                user.GetWindowRect(window, ctypes.byref(rect))
                dx = int(dx * (rect.right - rect.left) / max(1, width))
                drag = (dx, dy, width, start_x, start_y)
            user.SetWindowPos(window, 0, point.x - dx, point.y - dy, 0, 0, 0x15)
            return 0
        if drag is not None and message in (0x0202, 0x001F, 0x0215):
            start_x, start_y = drag[-2:]
            drag = None  # button released, cancel mode, or capture lost
            if user.GetCapture() == window:
                user.ReleaseCapture()
            if message == 0x0202:
                snap_at_top(window, start_x, start_y)
                return 0
        if message == 0x0014 and brush:  # WM_ERASEBKGND: exposed frame behind Tk widgets
            rect = wintypes.RECT()
            user.GetClientRect(window, ctypes.byref(rect))
            user.FillRect(key, ctypes.byref(rect), brush)
            return 1
        if message == 0x0005 and key != 1:  # WM_SIZE, restored or maximized
            result = controls.DefSubclassProc(window, message, key, data)
            user.RedrawWindow(window, None, None, 0x0185)
            return result
        if message == 0x0082:  # WM_NCDESTROY
            ctypes.windll.gdi32.DeleteObject(brush)
            controls.RemoveWindowSubclass(window, caption_proc, ident)
        return controls.DefSubclassProc(window, message, key, data)

    if not controls.SetWindowSubclass(hwnd, caption_proc, 1, 0):
        raise ctypes.WinError()
    return caption_proc  # keep the native callback alive for the window lifetime


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
        self.window_frame = configure_window_frame(root)

        def label(parent, text, command=None, **opts):
            widget = tk.Label(parent, text=text, bg=opts.pop("bg", SIDE), fg=opts.pop("fg", FG),
                              font=opts.pop("font", self.ui), bd=0, **opts)
            if command:
                widget.bind("<Button-1>", lambda _: command())
                widget.config(cursor="hand2")
            return widget
        status_bar = tk.Frame(root, bg=SIDE)
        status_bar.pack(side="bottom", fill="x")
        self.notice = label(status_bar, "", anchor="w", padx=12)
        self.notice.pack(side="left")
        self.notice_timer = None
        self.status = label(status_bar, "", anchor="e", padx=14)
        self.status.pack(side="right", ipady=3)
        bar = tk.Frame(root, bg=SIDE, height=32)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Frame(root, bg="#2b2b2b", height=1).pack(fill="x")
        with Image.open(Path(__file__).with_name("mervive-code-sharp.ico")) as artwork:
            self.brand = ImageTk.PhotoImage(artwork.ico.getimage((20, 20)))
        label(bar, "", self.choose_file, image=self.brand).pack(side="left", fill="y", padx=12)
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
        self.order = {"view": "Alphabetical", "folders": {}}
        self.order_view = tk.StringVar(value="Alphabetical")
        for view in ("Order", "Alphabetical"):
            actions.add_radiobutton(label=view, variable=self.order_view, value=view,
                                    command=self.switch_order_view)
        actions.add_separator()
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
        self.files = ttk.Treeview(self.sidebar, show="tree", selectmode="extended", style="Explorer.Treeview")
        self.files.column("#0", stretch=True, minwidth=60)
        self.file_icons = {}
        self.tab_icons = {}
        with Image.open(Path(__file__).with_name("explorer-icons.png")) as atlas:
            for index, suffix in enumerate((".json", ".md", ".js", ".png", ".py", ".exe", "folder", "file", ".ps1", ".c", ".pdf", ".txt")):
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
        self.drag_start = None
        self.drag_active = False
        self.drag_rows = ()
        self.ctrl_click = False
        self.drop_highlight = None
        # Windows composites this popup independently as it crosses the tree and editor.
        self.drag_popup = tk.Toplevel(root, takefocus=False)
        self.drag_popup.withdraw()
        self.drag_popup.overrideredirect(True)
        self.drag_popup.transient(root)
        self.drag_popup.attributes("-disabled", True)
        self.drag_badge = tk.Label(self.drag_popup, bg="#17394e", fg="#e5f3ff", padx=8, pady=2,
                                   highlightthickness=1, highlightbackground=BLUE, bd=0)
        self.drag_badge.pack()
        self.files.tag_configure("drop-destination", background="#18455d", foreground="white")
        self.drop_line = tk.Frame(self.files, height=2, bg=BLUE)
        self.files.bind("<ButtonPress-1>", self.start_reorder)
        self.files.bind("<B1-Motion>", self.drag_reorder)
        self.files.bind("<ButtonRelease-1>", self.finish_reorder)
        self.files.bind("<Delete>", self.delete_selected)
        self.files.bind("<Button-3>", self.explorer_menu)
        self.files.bind("<Return>",self.open_selected)
        self.files.bind("<Double-Button-1>", self.start_reorder)
        self.files.bind("<Escape>", self.cancel_drag)
        self.files.bind("<Left>", self.tree_arrow)
        self.files.bind("<Right>", self.tree_arrow)
        self.transfer_job = None
        self.drop_hover = None
        if isinstance(root, TkinterDnD.Tk):
            for surface in (self.folder_label, self.files):
                surface.drop_target_register(DND_FILES)
                surface.dnd_bind("<<DropEnter>>", self.external_drag)
                surface.dnd_bind("<<DropPosition>>", self.external_drag)
                surface.dnd_bind("<<DropLeave>>", self.leave_external_drag)
                surface.dnd_bind("<<Drop>>", self.external_drop)
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
        self.pdf = PdfPreview(self.work, BG, FG)
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
        if self.transfer_job:
            self.refresh_feedback("Transfer in progress. Close after it finishes.")
            return
        if self.can_leave():
            remember_folder(self.folder)
            self.root.destroy()

    def deactivate(self, keep_pdf=False):
        if not keep_pdf:
            self.pdf.hide()
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
        if self.can_leave():
            self.clear_document()

    def clear_document(self):
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

    def save_order(self, **changes):
        updated = {**self.order, **changes}
        try:
            explorer_order.write_order(self.folder, self.order, updated)
        except (OSError, ValueError) as exc:
            self.refresh_feedback(str(exc))
            return False
        self.order = updated
        return True

    def switch_order_view(self):
        view = self.order_view.get()
        if self.save_order(view=view):
            self.refresh_workspace()
        else:
            self.order_view.set(self.order["view"])

    def start_reorder(self, event):
        self.drag_active = False
        row = self.files.identify_row(event.y)
        self.drag_start = None
        self.ctrl_click = bool(event.state & 0x4)
        if not row:
            self.files.selection_set(())
            return "break"
        self.files.focus_set()
        self.files.focus(row)
        selected = self.files.selection()
        self.toggle_off = self.ctrl_click and row in selected
        if row not in selected:
            if self.ctrl_click:
                self.files.selection_add(row)
            else:
                self.files.selection_set(row)
        if not self.transfer_job:
            self.drag_start = (row, event.x, event.y)
        return "break"

    def mark_destination(self, destination):
        if destination == self.drop_highlight:
            return
        for path, active in ((self.drop_highlight, False), (destination, True)):
            if path == self.folder:
                self.folder_label.config(bg="#18455d" if active else SIDE)
            elif path and self.files.exists(str(path)):
                tags = list(self.files.item(str(path), "tags"))
                tags = [tag for tag in tags if tag != "drop-destination"]
                if active:
                    tags.append("drop-destination")
                self.files.item(str(path), tags=tags)
        self.drop_highlight = destination

    def cancel_drag(self, event=None):
        self.drag_start = None
        self.drag_rows = ()
        self.drag_active = False
        self.drop_line.place_forget()
        self.drag_popup.withdraw()
        self.mark_destination(None)
        if event:
            self.notice.config(text="")
        return "break"

    def internal_destination(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if widget == self.folder_label:
            destination = self.folder
        elif (0 <= event.x < self.files.winfo_width()
              and 0 <= event.y < self.files.winfo_height()):
            row = self.files.identify_row(event.y)
            if not row:
                destination = self.folder
            elif self.files.tag_has("directory", row):
                _, y, _, height = self.files.bbox(row)
                if (self.order_view.get() == "Order"
                        and all(Path(item).parent == Path(row).parent for item in self.drag_rows)
                        and not y + height / 4 <= event.y < y + 3 * height / 4):
                    return None  # Upper and lower edges reorder siblings.
                destination = Path(row)
            else:
                destination = Path(row).parent
        else:
            return None
        if all(Path(row).parent == destination for row in self.drag_rows) or any(
                destination.is_relative_to(Path(row)) for row in self.drag_rows):
            return None
        return destination

    def drop_target(self, event):
        if self.order_view.get() != "Order":
            return None
        source = self.drag_rows[0]
        target = self.files.identify_row(event.y)
        if (not target or target in self.drag_rows or not self.files.exists(source)
                or not 0 <= event.x < self.files.winfo_width()
                or any(self.files.parent(row) != self.files.parent(target) for row in self.drag_rows)):
            return None
        x, y, width, height = self.files.bbox(target)
        after = event.y >= y + height / 2
        return target, after, y + height if after else y

    def drag_reorder(self, event):
        if not self.drag_start:
            return
        _, x, y = self.drag_start
        if not self.drag_active and max(abs(event.x - x), abs(event.y - y)) < 5:
            return
        if not self.drag_active:
            selected = set(self.files.selection())
            self.drag_rows = tuple(row for row in self.files.selection()
                                   if not any(str(parent) in selected for parent in Path(row).parents))
            if not self.drag_rows:
                return "break"
        self.drag_active = True
        if event.y < 15 or event.y > self.files.winfo_height() - 15:
            self.files.yview_scroll(-1 if event.y < 15 else 1, "units")
        destination = self.internal_destination(event)
        action = COPY if event.state & 0x4 else MOVE
        self.notice.config(text=f"{action.capitalize()} to {destination.name}" if destination else "", fg=FG)
        target = None if destination else self.drop_target(event)
        count = len(self.drag_rows)
        name = Path(self.drag_rows[0]).name
        caption = (name if len(name) <= 32 else name[:29] + "…") if count == 1 else f"{count} items"
        prefix = "Copy" if destination and action == COPY else "Move" if destination else "Reorder" if target else "Dragging"
        badge_text = f"{prefix} · {caption}"
        if self.drag_badge.cget("text") != badge_text:
            self.drag_badge.configure(text=badge_text)
        self.drag_popup.geometry(f"+{event.x_root + 14}+{event.y_root + 18}")
        if not self.drag_popup.winfo_ismapped():
            self.drag_popup.deiconify()
        self.mark_destination(destination)
        if target:
            self.drop_line.place(x=0, y=target[2]-1, relwidth=1)
        else:
            self.drop_line.place_forget()
        return "break"

    def finish_reorder(self, event):
        try:
            if not self.drag_start:
                return "break"
            if not self.drag_active:
                if self.ctrl_click:
                    if self.toggle_off:
                        self.files.selection_remove(self.drag_start[0])
                    return "break"
                return self.open_selected(event)
            destination = self.internal_destination(event)
            if destination:
                sources = [Path(row) for row in self.drag_rows]
                self.start_transfer(destination, sources, COPY if event.state & 0x4 else MOVE, internal=True)
                return "break"
            self.notice.config(text="")
            target = self.drop_target(event)
            if target:
                source = self.drag_rows[0]
                parent = self.files.parent(source)
                siblings = list(self.files.get_children(parent))
                siblings = [row for row in siblings if row not in self.drag_rows]
                index = siblings.index(target[0]) + int(target[1])
                siblings[index:index] = self.drag_rows
                key = Path(source).parent.relative_to(self.folder).as_posix()
                folders = {**self.order["folders"], key: [Path(node).name for node in siblings]}
                if self.save_order(folders=folders):
                    self.files.set_children(parent, *siblings)
            return "break"
        finally:
            self.cancel_drag()

    def folder_items(self, path, root=None):
        root = root or self.folder
        try:
            items = sorted((item for item in path.iterdir() if item.name != ".git"
                            and item != root / explorer_order.FILENAME),
                           key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError as exc:
            messagebox.showerror("Open folder", str(exc))
            return None
        if self.order["view"] == "Order":
            key = path.relative_to(root).as_posix()
            saved = self.order["folders"].get(key, [])
            ranks = {name: index for index, name in enumerate(saved)}
            items.sort(key=lambda item: ranks.get(item.name, len(saved)))
            additions = [item.name for item in items if item.name not in ranks]
            if additions:
                updated = {**self.order, "folders": {**self.order["folders"], key: saved + additions}}
                try:
                    explorer_order.write_order(root, self.order, updated)
                    self.order = updated
                except (OSError, ValueError) as exc:
                    self.refresh_feedback(str(exc))
        return items

    def insert_items(self, parent, items):
        for item in items:
            directory = item.is_dir()
            key = "folder" if directory else item.suffix.lower()
            self.files.insert(parent, "end", iid=str(item), text=item.name,
                              tags=("directory",) if directory else (),
                              image=self.file_icons.get(key, self.file_icons["file"]))

    def browse(self, path):
        previous = self.order
        try:
            self.order = explorer_order.read_order(path)
        except (ValueError, OSError) as exc:
            self.refresh_feedback(str(exc))
            self.order = {"view": "Alphabetical", "folders": {}}
        items = self.folder_items(path, path)
        if items is None:
            self.order = previous
            return
        self.order_view.set(self.order["view"])
        expanded = sorted((node for node in self.loaded_folders if self.files.item(node, "open")),
                          key=lambda node: len(Path(node).parts)) if path == self.folder else []
        self.folder = path
        title = f"{path.name or path} — Mervive Code"
        if self.path:
            title += f" — {self.path.name}"
        self.root.title(title)
        self.folder_label.config(text=path.name or str(path))
        self.set_folder_expanded(True)
        self.files.delete(*self.files.get_children())
        self.loaded_folders.clear()
        self.insert_items("", items)
        for node in expanded:
            if self.files.exists(node) and self.files.tag_has("directory", node):
                self.set_branch(node, True)
        return True

    def refresh_feedback(self, message):
        if self.notice_timer:
            self.root.after_cancel(self.notice_timer)
        shades = iter(("#9cdcfe", "#acc7d5", "#a0a8ad", "#858585"))
        def fade():
            color = next(shades, None)
            self.notice.config(text=message if color else "", fg=color or DIM)
            self.notice_timer = self.root.after(450, fade) if color else None
        fade()

    def refresh_workspace(self, event=None):
        selected = self.files.selection()
        focused = self.files.focus()
        tree_top = self.files.yview()[0]
        expanded = self.folder_expanded
        focus = self.root.focus_get()
        if not self.browse(self.folder):
            self.refresh_feedback("Folder refresh failed")
            return "break"
        message = "Folder refreshed"
        if not expanded:
            self.set_folder_expanded(False)

        if self.path:
            dirty = self.editable and self.code.get("1.0", "end-1c") != self.original
            if dirty:
                message = "Folder refreshed · Unsaved edits kept"
            elif not self.path.is_file():
                self.close_file()
                message = "Folder refreshed · File removed from disk"
            else:
                cursor = self.code.index("insert")
                top = self.code.index("@0,0").split(".")[0] + ".0"
                left = self.code.xview()[0]
                previous = getattr(self, "saved_bytes", None)
                if not self.show(self.path, reload=True):
                    message = "Folder refreshed · File reload failed"
                elif getattr(self, "saved_bytes", None) != previous:
                    message = "Refreshed · File updated from disk"
                else:
                    message = "Folder and file refreshed"
                self.code.mark_set("insert", cursor)
                self.code.yview(top)
                self.code.xview_moveto(left)

        self.refresh_feedback(message)
        self.files.selection_set([row for row in selected if self.files.exists(row)])
        if focused and self.files.exists(focused):
            self.files.focus(focused)
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

    def external_destination(self, event):
        if event.widget == self.files:
            row = self.files.identify_row(event.y_root - self.files.winfo_rooty())
            if row:
                return Path(row) if self.files.tag_has("directory", row) else Path(row).parent
        return self.folder

    def external_action(self, event):
        if self.transfer_job:
            return REFUSE_DROP
        control = any(key.lower() in ("ctrl", "control") for key in event.modifiers)
        if not control and MOVE in event.actions:
            return MOVE
        return COPY if COPY in event.actions else REFUSE_DROP

    def external_drag(self, event):
        action = self.external_action(event)
        if action == REFUSE_DROP:
            return REFUSE_DROP
        folder = self.external_destination(event)
        if (folder, action) != self.drop_hover:
            self.drop_hover = (folder, action)
            if self.notice_timer:
                self.root.after_cancel(self.notice_timer)
                self.notice_timer = None
            self.notice.config(text=f"{action.capitalize()} to {folder.name}", fg=FG)
        return action

    def leave_external_drag(self, event):
        if self.drop_hover is not None:
            self.drop_hover = None
            self.notice.config(text="")
        return COPY

    def external_drop(self, event):
        self.leave_external_drag(event)
        action = self.external_action(event)
        if action == REFUSE_DROP:
            return REFUSE_DROP
        folder = self.external_destination(event)
        sources = [Path(name) for name in self.root.tk.splitlist(event.data)]
        if not sources:
            return REFUSE_DROP
        self.start_transfer(folder, sources, action)
        # The worker owns source removal. Never signal a source-side delete,
        # especially when a multi-item drop might partially fail.
        return COPY if action == COPY else REFUSE_DROP

    def start_transfer(self, folder, sources, action, internal=False):
        project = self.folder
        worker = ThreadPoolExecutor(max_workers=1)
        job = worker.submit(transfer_dropped_items, project, folder, sources, action)
        worker.shutdown(wait=False)
        self.transfer_job = job
        progress, done = ("Moving", "Moved") if action == MOVE else ("Copying", "Copied")
        self.notice.config(text=f"{progress} to {folder.name}…", fg=FG)

        def finish():
            if not job.done():
                self.root.after(100, finish)
                return
            self.transfer_job = None
            transferred, skipped = job.result()
            if transferred and self.folder == project:
                if internal:
                    for source, target in transferred:
                        self.follow_internal_transfer(source, target, action)
                self.refresh_workspace()
                if folder != project and self.files.exists(str(folder)):
                    self.set_branch(str(folder), True)
                rows = [str(target) for _, target in transferred if self.files.exists(str(target))]
                if rows:
                    row = rows[0]
                    self.files.selection_set(*rows)
                    self.files.focus(row)
                    self.files.see(row)
            self.refresh_feedback(f"{done} {len(transferred)} to {folder.name}")
            if skipped:
                messagebox.showwarning("Skipped items", "\n".join(skipped), parent=self.root)
        self.root.after(50, finish)

    def follow_internal_transfer(self, source, target, action):
        if action == MOVE and self.path and self.path.is_relative_to(source):
            previous = self.path
            self.path = target / previous.relative_to(source)
            if getattr(self, "buffer_path", None) == previous:
                self.buffer_path = self.path
            if self.pdf.path == previous:
                self.pdf.path = self.path
            self.display_header(self.path)
            if self.editable and self.code.get("1.0", "end-1c") != self.original:
                self.tabname.config(text=self.path.name + " •")

        # Keep each nested folder's custom sequence at its new relative path.
        try:
            self.order = explorer_order.read_order(self.folder)
        except (OSError, ValueError) as exc:
            self.refresh_feedback(str(exc))
            return
        old = source.relative_to(self.folder)
        new = target.relative_to(self.folder)
        folders = dict(self.order["folders"])
        for key, names in self.order["folders"].items():
            directory = Path(key)
            if directory.is_relative_to(old):
                folders[(new / directory.relative_to(old)).as_posix()] = names
                if action == MOVE:
                    folders.pop(key, None)
        parent = old.parent.as_posix()
        if action == MOVE and old.name in folders.get(parent, []):
            folders[parent] = [n for n in folders[parent] if n != old.name]
        if folders != self.order["folders"]:
            self.save_order(folders=folders)

    def explorer_menu(self, event):
        node = self.files.identify_row(event.y)
        if not node:
            return "break"
        self.files.focus_set()
        self.files.focus(node)
        self.files.selection_set(node)
        path = Path(node)
        menu = tk.Menu(self.files, tearoff=False, bg=SIDE, fg=FG)
        if self.files.tag_has("directory", node):
            expanded = bool(self.files.item(node, "open"))
            menu.add_command(label="Collapse" if expanded else "Expand",
                             command=lambda: self.set_branch(node, not expanded))
        else:
            menu.add_command(label="Open", command=lambda: self.show(path))
        def copy_path():
            self.root.clipboard_clear()
            self.root.clipboard_append(str(path))
        menu.add_command(label="Copy path", command=copy_path)
        menu.add_separator()
        menu.add_command(label="Delete", accelerator="Del", command=self.delete_selected)
        # Post asynchronously so the menu survives until a command is chosen.
        menu.bind("<Unmap>", lambda _: self.root.after_idle(menu.destroy))
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def delete_selected(self, event=None):
        selected = self.files.selection()
        if len(selected) != 1:
            return "break"
        path = Path(selected[0])
        affects_document = self.path is not None and self.path.is_relative_to(path)
        try:
            if path == self.folder or not path.parent.resolve().is_relative_to(self.folder.resolve()):
                raise ValueError("Select an item inside the project folder.")
            if not os.path.lexists(path):
                return self.refresh_workspace()
            detail = " and its contents" if path.is_dir() and not path.is_symlink() else ""
            if not messagebox.askyesno("Delete", f"Move {path.name}{detail} to the Recycle Bin?",
                                       parent=self.root, default="no"):
                return "break"
            if affects_document and not self.can_leave():
                return "break"
            from send2trash import send2trash
            send2trash(str(path))
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror("Delete", str(exc), parent=self.root)
            return "break"
        if affects_document:
            self.clear_document()
        self.refresh_workspace()
        self.files.focus_set()
        return "break"

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
                self.show(Path(node), focus_editor=event.type != tk.EventType.ButtonRelease)
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
        return True

    def show(self, path, *, reload=False, focus_editor=True):
        if path.suffix.lower() in (".mp3", ".mp4", ".wav"):
            try:
                os.startfile(path, "open")
            except OSError as exc:
                detail = ("Choose a default player for this file type in Windows Settings."
                          if exc.winerror == 1155 else str(exc))
                messagebox.showerror("Open media", detail, parent=self.root)
                return False
            self.refresh_feedback(f"Opened {path.name} in the default app")
            return True
        if self.path == path and self.editable and not reload:
            if focus_editor:
                self.code.focus_set()
            return
        if not self.can_leave():
            if self.path and self.files.exists(str(self.path)):
                self.files.selection_set(str(self.path))
                self.files.focus(str(self.path))
            return
        if path.suffix.lower() == ".pdf":
            index = self.pdf.index if self.pdf.path == path else 0
            if not self.pdf.display(path, index):
                return False
            self.deactivate(keep_pdf=True)
            self.display_header(path)
            self.body.pack_forget()
            self.findbar.pack_forget()
            self.image_panel.pack_forget()
            self.pdf.pack(fill="both", expand=True)
            self.status.config(text="PDF")
            return True
        if path.suffix.lower() in (".ico", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"):
            return self.show_image(path)
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
            if focus_editor:
                self.code.focus_set()
            return True
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
        if focus_editor:
            self.code.focus_set()
        return True

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
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        ctypes.windll.user32.SetProcessDPIAware()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mervive.Code.Viewer")
    root = TkinterDnD.Tk()
    root.iconbitmap(default=str(Path(__file__).with_name("mervive-code-sharp.ico")))
    app = Viewer(root)
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else startup_folder()
    app.browse(path if path.is_dir() else path.parent)
    if path.is_file():
        app.show(path)
    root.mainloop()
