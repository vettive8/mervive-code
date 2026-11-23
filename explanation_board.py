"""A project-authored, live explanation board for Mervive Code."""
import json
from pathlib import Path
import tkinter as tk

BG = "#191c1a"
PANEL = "#232824"
INK = "#f3eee4"
DIM = "#b1b5a9"
ACCENT = "#ffab79"
BOARD_NAME = ".mervive-board.json"


def read_board(path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Board exceeds 1 MiB.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise ValueError("The board needs a steps array.")
    steps = data["steps"]
    if not 1 <= len(steps) <= 200:
        raise ValueError("Use between 1 and 200 steps.")
    for step in steps:
        if not isinstance(step, dict) or any(not isinstance(step.get(k), str) or not step[k].strip()
                      for k in ("id", "title", "story", "why", "file", "anchor")):
            raise ValueError("Each step needs id, title, story, why, file and anchor.")
    ids = [s["id"] for s in steps]
    if len(set(ids)) != len(ids):
        raise ValueError("Step IDs must be unique.")
    if "focus" in data and data["focus"] not in ids:
        raise ValueError("The focused step is missing.")
    if not isinstance(data.get("title", ""), str):
        raise ValueError("The title must be text.")
    return data


class ExplanationBoard:
    def __init__(self, viewer):
        self.viewer = viewer
        self.folder = viewer.folder.resolve()
        self.path = self.folder / BOARD_NAME
        self.window = w = tk.Toplevel(viewer.root)
        w.title("Explanation board — Mervive Code")
        w.geometry("1120x690")
        w.minsize(720, 520)
        w.configure(bg=BG)
        self.data = {}
        self.steps = []
        self.index = 0
        self.stamp = object()
        self.frame = self.timer = None
        self.playing = False

        top = tk.Frame(w, bg=BG, padx=20, pady=12)
        top.pack(fill="x")
        self.title = tk.Label(top, text="Explanation board", bg=BG, fg=INK, font=("Georgia", 21))
        self.title.pack(side="left")
        self.next = self.button(top, "Next", lambda: self.select(self.index+1))
        self.next.pack(side="right")
        self.play = self.button(top, "Play walkthrough", self.toggle)
        self.play.pack(side="right", padx=6)
        self.back = self.button(top, "Back", lambda: self.select(self.index-1))
        self.back.pack(side="right")
        self.board = c = tk.Canvas(w, bg="#1d211e", height=185, highlightthickness=0)
        c.pack(fill="x")
        scroll = tk.Scrollbar(w, orient="horizontal", command=c.xview)
        scroll.pack(fill="x")
        c.configure(xscrollcommand=scroll.set)
        c.bind("<ButtonPress-1>", lambda e: c.scan_mark(e.x, e.y))
        c.bind("<B1-Motion>", lambda e: c.scan_dragto(e.x, e.y, gain=1))
        c.bind("<MouseWheel>", lambda e: c.xview_scroll(-int(e.delta/120)*3, "units"))
        details = tk.PanedWindow(w, orient="horizontal", bg=BG, bd=0, sashwidth=6)
        details.pack(fill="both", expand=True, padx=16, pady=12)
        left = tk.Frame(details, bg=PANEL, padx=16, pady=14)
        right = tk.Frame(details, bg=PANEL, padx=12, pady=14)
        details.add(left, width=390, minsize=220)
        details.add(right, minsize=300)
        self.labels = []
        for heading in ("User story", "How it works"):
            tk.Label(left, text=heading, fg=ACCENT, bg=PANEL, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            label = tk.Label(left, text="", bg=PANEL, fg=INK, justify="left", anchor="nw", wraplength=340,
                             font=("Segoe UI", 12))
            label.pack(fill="x", pady=(3, 14))
            self.labels.append(label)
        left.bind("<Configure>", lambda e: [label.configure(wraplength=max(100,e.width-36)) for label in self.labels])
        self.file_label = tk.Label(right, text="", anchor="w", bg=PANEL, fg=ACCENT)
        self.file_label.pack(fill="x")
        self.code = tk.Text(right, bg="#181b19", fg=INK, font=("Consolas", 11), height=7, width=20,
                            wrap="char", relief="flat", padx=10, pady=8, state="disabled")
        self.code.pack(fill="both", expand=True, pady=8)
        self.code.tag_configure("point", background="#664735", foreground="#fff2dc")
        self.open = self.button(right, "Select in editor", self.open_code)
        self.open.pack(anchor="w")
        self.status = tk.Label(w, text="", anchor="w", bg=BG, fg=DIM, padx=20)
        self.status.pack(fill="x", pady=(0, 7))
        w.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    @staticmethod
    def button(parent, text, command):
        return tk.Button(parent, text=text, command=command, bg="#38413a", fg=INK, activebackground="#4c564c",
                         activeforeground="white", bd=0, padx=10, pady=5, cursor="hand2")

    def poll(self):
        try:
            stamp = self.path.stat().st_mtime_ns
            if stamp != self.stamp:
                data = read_board(self.path)
                old_id = self.steps[self.index]["id"] if self.steps else None
                target = data.get("focus") if data.get("focus") != self.data.get("focus") else old_id
                self.data, self.steps, self.stamp = data, data["steps"], stamp
                self.title.configure(text=data.get("title") or "Explanation board")
                self.status.configure(text="Live board   ·   Click a box to explore. Drag to pan.")
                self.select(next((i for i,s in enumerate(self.steps) if s["id"]==target), 0))
        except (OSError, ValueError) as error:
            self.status.configure(text=f"Waiting for {BOARD_NAME} in {self.folder.name}." if isinstance(error, FileNotFoundError) else str(error))
        self.watch = self.window.after(420, self.poll)

    def stop(self):
        self.playing = False
        self.play.configure(text="Play walkthrough")
        if self.timer:
            self.window.after_cancel(self.timer)
            self.timer = None

    def toggle(self):
        if self.playing:
            self.stop()
        elif self.steps:
            self.playing = True
            self.play.configure(text="Pause")
            self.select(0 if self.index == len(self.steps)-1 else self.index, auto=True)

    def snippet(self, step):
        path = (self.folder / step["file"]).resolve()
        if not path.is_relative_to(self.folder) or path.stat().st_size > 1024*1024:
            raise ValueError("Choose a project text file under 1 MiB.")
        # Reflect unsaved text when the linked file is already open.
        if self.viewer.path == path and self.viewer.editable:
            text = self.viewer.code.get("1.0", "end-1c")
        else:
            text = path.read_text(encoding="utf-8-sig")
        anchor = step["anchor"]
        offset = text.find(anchor)
        if offset < 0 or text.find(anchor,offset+1) >= 0:
            raise ValueError("Update the source anchor: it must match exactly once.")
        row = text.count("\n",0,offset)+1
        first = max(1,row-3)
        excerpt = "\n".join(text.split("\n")[first-1:row+anchor.count("\n")+3])
        column = offset-(text.rfind("\n",0,offset)+1)
        return path,row,column,first,excerpt

    def select(self, index, auto=False):
        if not 0 <= index < len(self.steps):
            return
        if not auto:
            self.stop()
        if self.frame:
            self.window.after_cancel(self.frame)
            self.frame = None
        previous = self.index
        self.index = index
        step = self.steps[index]
        self.back.configure(state="normal" if index else "disabled")
        self.next.configure(state="normal" if index+1 < len(self.steps) else "disabled")
        for label,key in zip(self.labels, ("story","why")):
            label.configure(text=step[key])
        self.code.configure(state="normal")
        self.code.delete("1.0","end")
        self.start = None
        try:
            path,row,col,first,excerpt = self.snippet(step)
            self.start = f"{row-first+1}.{col}"
            self.file_label.configure(text=f"{step['file']}   ·   line {row}")
            self.code.insert("1.0",excerpt)
            self.code.see(self.start)
        except (OSError,ValueError) as error:
            self.file_label.configure(text=step["file"])
            self.code.insert("1.0",str(error))
        self.open.configure(state="normal" if self.start else "disabled")
        self.code.configure(state="disabled")
        self.draw(previous)
        if auto and index+1 < len(self.steps):
            self.timer=self.window.after(7000,lambda:self.select(index+1,auto=True))
        elif auto:
            self.stop()

    def draw(self, previous):
        c=self.board
        c.delete("all")
        stride=210
        extent=max(1,len(self.steps)*stride+24)
        c.configure(scrollregion=(0,0,extent,183))
        for i,step in enumerate(self.steps):
            x=16+i*stride
            if i:
                c.create_line(x-29,112,x,112,fill="#8a9283",width=2,arrow="last")
            tag=f"step{i}"
            c.create_rectangle(x,79,x+180,145, fill="#453b30" if i==self.index else PANEL,
                               outline=ACCENT if i==self.index else "#626b60", width=2,tags=tag)
            c.create_text(x+90,111,text=step["title"],width=164,justify="center",fill=INK,
                          font=("Segoe UI",11,"bold"),tags=tag)
            c.tag_bind(tag,"<Button-1>",lambda e,n=i:self.select(n))
        c.update_idletasks()
        c.xview_moveto(max(0,(16+self.index*stride+90-c.winfo_width()/2)/extent))
        end=106+self.index*stride
        begin=end+max(-1,min(1,previous-self.index))*stride
        def animate(n):
            t=n/22
            x=begin+(end-begin)*t*t*(3-2*t)
            y=47-12*4*t*(1-t)
            c.delete("guide")
            c.create_oval(x-18,y-17,x+18,y+17,fill="#c9c7bc",outline="",tags="guide")
            for dx in (-8,8):
                c.create_oval(x+dx-6,y-5,x+dx+6,y+7,fill="#f6ecce",outline="#575546",width=2,tags="guide")
                c.create_oval(x+dx-2,y-2,x+dx+2,y+3,fill="#22261f",tags="guide")
            if self.start:
                count=round(t*len(self.steps[self.index]["anchor"]))
                self.code.tag_add("point",self.start,f"{self.start}+{count}c")
            self.frame=self.window.after(22,lambda:animate(n+1)) if n<22 else None
        animate(0)

    def open_code(self):
        step=self.steps[self.index]
        try:
            path,row,col,_,_=self.snippet(step)
        except (OSError,ValueError) as error:
            self.status.configure(text=str(error)); return
        self.viewer.show(path)
        if self.viewer.path == path:
            self.stop()
            start=f"{row}.{col}"
            editor=self.viewer.code
            editor.tag_remove("sel","1.0","end")
            editor.tag_add("sel",start,f"{start}+{len(step['anchor'])}c")
            editor.see(start)
            self.viewer.root.lift()
            editor.focus_set()

    def close(self):
        self.stop()
        for job in (self.watch,self.frame):
            if job:
                self.window.after_cancel(job)
        self.window.destroy()
