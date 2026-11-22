"""A small toolkit for proper desktop windows in plain Tkinter (standard library only).

One window per app: a colored header with the app's name, a sidebar of pages, a status line at the bottom,
a menu bar with Help, and pages that always open on a start screen that says what to do.
Long jobs run in a background thread and write to a log box, so the window never freezes.
"""
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BG, PANEL, LINE, FG, DIM = "#f6f7f9", "#ffffff", "#dde1e7", "#1d2330", "#5d6675"
FONT = "Sans"


def open_path(path):
    """Open a file or folder in the system's own app."""
    if sys.platform.startswith("win"):
        import os
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class App(tk.Tk):
    """App(name, tagline, accent, about) then add_page(...) for each page, then run()."""

    def __init__(self, name, tagline, accent, about, size="1100x720", class_name=None):
        super().__init__(className=class_name or name.replace(" ", ""))
        self.name, self.accent, self.about = name, accent, about
        self.title(name)
        self.geometry(size)
        self.minsize(900, 600)
        self.configure(bg=BG)
        self.pages, self.buttons, self.current = {}, {}, None
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TCombobox", padding=4)
        style.configure("Horizontal.TProgressbar", background=accent, troughcolor=LINE, bordercolor=LINE)

        head = tk.Frame(self, bg=accent, height=64)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text=name, bg=accent, fg="white", font=(FONT, 18, "bold")).pack(side="left", padx=(20, 12))
        tk.Label(head, text=tagline, bg=accent, fg="white", font=(FONT, 11)).pack(side="left")
        tk.Button(head, text="?  Help", command=self.help_current, bg=accent, fg="white", relief="flat",
                  activebackground=accent, activeforeground="white", font=(FONT, 11, "bold"),
                  cursor="hand2", bd=0).pack(side="right", padx=16)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self.side = tk.Frame(body, bg=PANEL, width=210, highlightthickness=1, highlightbackground=LINE)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        tk.Frame(self.side, bg=PANEL, height=10).pack()
        self.main = tk.Frame(body, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)

        self.status = tk.Label(self, text="", bg=PANEL, fg=DIM, anchor="w", font=(FONT, 10), padx=12, pady=4,
                               highlightthickness=1, highlightbackground=LINE)
        self.status.pack(fill="x", side="bottom")

        bar = tk.Menu(self)
        filem = tk.Menu(bar, tearoff=0)
        filem.add_command(label="Quit", command=self.destroy, accelerator="Ctrl+Q")
        bar.add_cascade(label="File", menu=filem)
        self.go_menu = tk.Menu(bar, tearoff=0)
        bar.add_cascade(label="Go", menu=self.go_menu)
        helpm = tk.Menu(bar, tearoff=0)
        helpm.add_command(label="How to use this page", command=self.help_current, accelerator="F1")
        helpm.add_command(label=f"About {name}", command=lambda: messagebox.showinfo(f"About {name}", about))
        bar.add_cascade(label="Help", menu=helpm)
        self.config(menu=bar)
        self.bind_all("<Control-q>", lambda e: self.destroy())
        self.bind_all("<F1>", lambda e: self.help_current())

    # ---- pages
    def add_page(self, key, label, page_cls, **kw):
        """page_cls(parent_frame, app, **kw) must be a tk.Frame with .HELP text and optional .shown()."""
        b = tk.Button(self.side, text="   " + label, anchor="w", relief="flat", bd=0, bg=PANEL, fg=FG,
                      activebackground=LINE, font=(FONT, 12), padx=10, pady=9, cursor="hand2",
                      command=lambda: self.show(key))
        b.pack(fill="x", padx=8, pady=1)
        self.buttons[key] = b
        self.pages[key] = (page_cls, kw, None)
        self.go_menu.add_command(label=label, command=lambda: self.show(key))

    def show(self, key):
        if self.current == key:
            return
        if self.current:
            prev = self.pages[self.current][2]
            if hasattr(prev, "hidden"):
                prev.hidden()
            prev.pack_forget()
            self.buttons[self.current].config(bg=PANEL, fg=FG, font=(FONT, 12))
        cls, kw, page = self.pages[key]
        if page is None:
            page = cls(self.main, self, **kw)
            self.pages[key] = (cls, kw, page)
        page.pack(fill="both", expand=True)
        self.buttons[key].config(bg=self.accent, fg="white", font=(FONT, 12, "bold"))
        self.current = key
        self.say(getattr(page, "HINT", ""))
        if hasattr(page, "shown"):
            page.shown()

    def page(self, key):
        return self.pages[key][2]

    def help_current(self):
        page = self.pages[self.current][2] if self.current else None
        text = getattr(page, "HELP", None) or self.about
        messagebox.showinfo(f"{self.name}: how to use this page", text)

    def say(self, text):
        self.status.config(text=text)

    def run(self, first):
        self.show(first)
        self.mainloop()


# ---- building blocks for pages
class Page(tk.Frame):
    HELP = ""
    HINT = ""

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=28, pady=20)

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def title(self, text, sub=None, parent=None):
        p = parent or self.body
        tk.Label(p, text=text, bg=BG, fg=FG, font=(FONT, 20, "bold"), anchor="w").pack(fill="x")
        if sub:
            tk.Label(p, text=sub, bg=BG, fg=DIM, font=(FONT, 12), anchor="w", justify="left",
                     wraplength=760).pack(fill="x", pady=(2, 12))

    def text(self, text, size=12, color=FG, bold=False, parent=None, pady=(0, 6)):
        l = tk.Label(parent or self.body, text=text, bg=BG, fg=color, font=(FONT, size, "bold" if bold else "normal"),
                     anchor="w", justify="left", wraplength=760)
        l.pack(fill="x", pady=pady)
        return l

    def steps(self, items, parent=None):
        """A numbered 'how to use' card."""
        card = tk.Frame(parent or self.body, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        card.pack(fill="x", pady=(4, 14))
        tk.Label(card, text="How it works", bg=PANEL, fg=DIM, font=(FONT, 10, "bold"), anchor="w").pack(
            fill="x", padx=16, pady=(10, 4))
        for i, s in enumerate(items, 1):
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(row, text=str(i), bg=self.app.accent, fg="white", font=(FONT, 10, "bold"), width=2).pack(
                side="left", anchor="n", pady=2)
            tk.Label(row, text=s, bg=PANEL, fg=FG, font=(FONT, 11), anchor="w", justify="left",
                     wraplength=700).pack(side="left", padx=10, fill="x")
        tk.Frame(card, bg=PANEL, height=8).pack()
        return card

    def button(self, parent, text, command, primary=True, **kw):
        color = self.app.accent if primary else "#e4e7ec"
        return tk.Button(parent, text=text, command=command, bg=color, fg="white" if primary else FG,
                         activebackground=color, activeforeground="white" if primary else FG, relief="flat",
                         font=(FONT, 11, "bold"), padx=16, pady=7, cursor="hand2", bd=0, **kw)

    def row(self, parent=None, pady=6):
        r = tk.Frame(parent or self.body, bg=BG)
        r.pack(fill="x", pady=pady)
        return r

    def card(self, parent=None, **pack):
        c = tk.Frame(parent or self.body, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        c.pack(**{"fill": "x", "pady": 6, **pack})
        return c

    def path_field(self, label, var, folder=True, parent=None, save=False):
        """A labeled path box with a Browse button."""
        r = self.row(parent)
        tk.Label(r, text=label, bg=BG, fg=FG, font=(FONT, 11), width=16, anchor="w").pack(side="left")
        tk.Entry(r, textvariable=var, font=(FONT, 11), relief="solid", bd=1).pack(side="left", fill="x",
                                                                               expand=True, ipady=4)

        def browse():
            if folder:
                p = filedialog.askdirectory(initialdir=var.get() or None)
            elif save:
                p = filedialog.asksaveasfilename(initialfile=var.get() or None)
            else:
                p = filedialog.askopenfilename(initialdir=None)
            if p:
                var.set(p)
        self.button(r, "Browse…", browse, primary=False).pack(side="left", padx=(8, 0))
        return r

    def log_box(self, height=12, parent=None):
        frame = tk.Frame(parent or self.body, bg=BG)
        frame.pack(fill="both", expand=True, pady=(8, 0))
        box = tk.Text(frame, height=height, font=("Monospace", 10), bg=PANEL, fg=FG, relief="solid", bd=1,
                      wrap="word", state="disabled")
        sb = tk.Scrollbar(frame, command=box.yview)
        box.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        return box


def write(box, text):
    box.config(state="normal")
    box.insert("end", text)
    box.see("end")
    box.config(state="disabled")


class Job:
    """Run fn(log) in a thread; log(text) lines land in the box; done(result_or_exception) runs on the UI thread."""

    def __init__(self, widget, box, fn, done=None):
        self.q, self.widget, self.box, self.done = queue.Queue(), widget, box, done
        self.thread = threading.Thread(target=self._run, args=(fn,), daemon=True)
        self.thread.start()
        self._poll()

    def _run(self, fn):
        try:
            result = fn(lambda s: self.q.put(("log", str(s))))
        except BaseException as e:  # shown to the user, not lost in a thread
            result = e
        self.q.put(("done", result))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    write(self.box, val if val.endswith("\n") else val + "\n")
                else:
                    if self.done:
                        self.done(val)
                    return
        except queue.Empty:
            pass
        self.widget.after(150, self._poll)


class Capture:
    """Sends print() output from a job thread to a log function."""

    def __init__(self, log):
        self.log, self.buf = log, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.log(line)

    def flush(self):
        if self.buf:
            self.log(self.buf)
            self.buf = ""
