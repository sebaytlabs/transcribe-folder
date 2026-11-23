"""A small toolkit for proper desktop windows in plain Tkinter (standard library only).

One window per app: a colored header with the app's name, a sidebar of pages, a status line at the bottom,
a menu bar with Help, and pages that always open on a start screen that says what to do.
Long jobs run in a background thread and write to a log box, so the window never freezes.
"""
import json
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
                  cursor="hand2", bd=0).pack(side="right", padx=(4, 16))
        self.tour_button = tk.Button(head, text="▶  Tutorial", command=lambda: self.start_tour(), bg=accent,
                                     fg="white", relief="flat", activebackground=accent, activeforeground="white",
                                     font=(FONT, 11, "bold"), cursor="hand2", bd=0)
        self.tour_button.pack(side="right", padx=4)
        self.tour, self.tour_steps, self.tour_file, self.tour_version = None, None, None, 1

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
        helpm.add_command(label="Tutorial (every part, one step at a time)", command=lambda: self.start_tour())
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

    # ---- the tutorial
    def set_tutorial(self, steps, store, version=1):
        """steps() -> list of step dicts (see Tour). store: a JSON file that remembers the tutorial was finished.
        The first time the app opens (and after a new version of the tutorial) it runs by itself and can't be
        skipped; from the Tutorial button it's a replay you can skip."""
        self.tour_steps, self.tour_file, self.tour_version = steps, store, version

    def tutorial_seen(self):
        try:
            return json.loads(open(self.tour_file, encoding="utf-8").read()).get("tutorial") == self.tour_version
        except (OSError, ValueError, TypeError):
            return False

    def start_tour(self, required=False):
        if self.tour or not self.tour_steps:
            return
        self.tour = Tour(self, self.tour_steps(), required)

    def tour_finished(self):
        self.tour = None
        if self.tour_file:
            import os
            os.makedirs(os.path.dirname(str(self.tour_file)), exist_ok=True)
            try:
                data = json.loads(open(self.tour_file, encoding="utf-8").read())
            except (OSError, ValueError):
                data = {}
            data["tutorial"] = self.tour_version
            with open(self.tour_file, "w", encoding="utf-8") as f:
                json.dump(data, f)

    def run(self, first):
        self.show(first)
        if self.tour_steps and not self.tutorial_seen():
            self.after(500, lambda: self.start_tour(required=True))
        self.mainloop()


class Tour:
    """The tutorial: rings one part of the window at a time, says what it is for and has you do one real thing.

    Each step is a dict:
      title, text   what this part is and why it's there
      do            the one thing to do now ("Your turn: ...")
      page          the page to show first (optional)
      target        fn() -> the widget to ring (optional; none = the card sits in the middle)
      start         fn() -> a value remembered when the step opens (optional)
      check         fn(start_value) -> True once the thing is done; Next waits for it in the first-run tutorial
    `required` (first run): no Skip, Next waits for each check. From the Tutorial button: Skip, Esc and Next work.
    """
    RING = "#f59f00"

    def __init__(self, app, steps, required=False):
        self.app, self.steps, self.required, self.i = app, steps, required, 0
        self.passed, self.base, self.poll_job = set(), None, None
        self.ring = [tk.Frame(app, bg=self.RING) for _ in range(4)]
        # The card is a small window of its own beside the app, so it never covers the part you're working in.
        self.win = tk.Toplevel(app, bg="#fffdf5")
        self.win.title(f"{app.name}: tutorial")
        self.win.transient(app)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", (lambda: None) if required else self.finish)
        self.where = None
        self.card = tk.Frame(self.win, bg="#fffdf5", highlightthickness=2, highlightbackground=self.RING)
        self.card.pack(fill="both", expand=True)
        self.title = tk.Label(self.card, bg="#fffdf5", fg=FG, font=(FONT, 14, "bold"), anchor="w", justify="left",
                              wraplength=380)
        self.title.pack(fill="x", padx=14, pady=(12, 4))
        self.body = tk.Label(self.card, bg="#fffdf5", fg=FG, font=(FONT, 11), anchor="w", justify="left",
                             wraplength=380)
        self.body.pack(fill="x", padx=14)
        self.todo = tk.Label(self.card, bg="#fffdf5", fg="#a35c00", font=(FONT, 11, "bold"), anchor="w",
                             justify="left", wraplength=380)
        self.todo.pack(fill="x", padx=14, pady=(8, 0))
        bar = tk.Frame(self.card, bg="#fffdf5")
        bar.pack(fill="x", padx=14, pady=12)
        self.count = tk.Label(bar, bg="#fffdf5", fg=DIM, font=(FONT, 10))
        self.count.pack(side="left")
        mk = lambda t, c: tk.Button(bar, text=t, command=c, relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                                    font=(FONT, 10, "bold"), bg="#e4e7ec", fg=FG, activebackground=LINE)
        self.next_b = mk("Next", self.next)
        self.next_b.config(bg=app.accent, fg="white", activebackground=app.accent, activeforeground="white")
        self.next_b.pack(side="right")
        self.back_b = mk("Back", self.back)
        self.back_b.pack(side="right", padx=6)
        self.skip_b = mk("Skip", self.finish)
        if not required:
            self.skip_b.pack(side="right")
            self.win.bind("<Escape>", lambda e: self.finish())
        self.show_step()

    def step(self):
        return self.steps[self.i]

    def waiting(self):
        return "check" in self.step() and self.i not in self.passed

    def show_step(self):
        st = self.step()
        if st.get("page"):
            self.app.show(st["page"])
        self.app.update_idletasks()
        if "start" in st and self.i not in self.passed:
            self.base = st["start"]()
        self.title.config(text=st["title"])
        self.body.config(text=st["text"])
        self.count.config(text=f"{self.i + 1} of {len(self.steps)}")
        self.back_b.config(state="normal" if self.i else "disabled")
        self.next_b.config(text="Done" if self.i == len(self.steps) - 1 else "Next")
        self.refresh()
        self.place()
        self.app.after(150, self.focus_target)
        if self.poll_job:
            self.app.after_cancel(self.poll_job)
        self.poll_job = self.app.after(300, self.poll)

    def refresh(self):
        st = self.step()
        do = st.get("do", "")
        if self.waiting():
            self.todo.config(text="Your turn: " + do + ("\nNext opens when you've done it." if self.required else ""),
                             fg="#a35c00")
        elif "check" in st:
            self.todo.config(text="✓ Done. Click Next.", fg="#2b8a3e")
        else:
            self.todo.config(text=("Try it: " + do) if do else "", fg="#a35c00")
        self.next_b.config(state="disabled" if self.required and self.waiting() else "normal")

    def target(self):
        t = self.step().get("target")
        try:
            w = t() if t else None
            return w if w is not None and w.winfo_ismapped() else None
        except (tk.TclError, AttributeError):
            return None

    def focus_target(self):
        """Keys go to the app (the ringed box if you type into it), not to the card."""
        w = self.target()
        try:
            (w if isinstance(w, (tk.Entry, tk.Text)) else self.app).focus_force()
        except tk.TclError:
            pass

    def place(self):
        app, w = self.app, self.target()
        app.update_idletasks()
        W, H = app.winfo_width(), app.winfo_height()
        cw, ch = self.card.winfo_reqwidth(), self.card.winfo_reqheight()
        ax, ay, sw = app.winfo_rootx(), app.winfo_rooty(), app.winfo_screenwidth()
        if w is None:
            for r in self.ring:
                r.place_forget()
            x, y = (W - cw) // 2, (H - ch) // 2
            if ax + W + 16 + cw <= sw:          # nothing ringed: still beside the app when there's room
                x, y = W + 16, 70
            elif ax - 16 - cw >= 0:
                x, y = -16 - cw, 70
        else:
            x0, y0 = w.winfo_rootx() - app.winfo_rootx() - 5, w.winfo_rooty() - app.winfo_rooty() - 5
            x1, y1 = x0 + w.winfo_width() + 10, y0 + w.winfo_height() + 10
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
            t = 4
            for r, geo in zip(self.ring, ((x0, y0, x1 - x0, t), (x0, y1 - t, x1 - x0, t),
                                          (x0, y0, t, y1 - y0), (x1 - t, y0, t, y1 - y0))):
                r.place(x=geo[0], y=geo[1], width=geo[2], height=geo[3])
                r.lift()
            # the card goes beside the ringed part: right, left, below or above, wherever it fits
            if x1 + 12 + cw <= W:
                x, y = x1 + 12, y0
            elif x0 - 12 - cw >= 0:
                x, y = x0 - 12 - cw, y0
            elif y1 + 12 + ch <= H:
                x, y = x0, y1 + 12
            elif y0 - 12 - ch >= 0:
                x, y = x0, y0 - 12 - ch
            else:
                x, y = W - cw - 16, H - ch - 40
            x, y = min(max(x, 8), W - cw - 8), min(max(y, 70), H - ch - 30)
            ty = y0
            if ax + W + 16 + cw <= sw:          # room on the right of the app: dock the card there
                x, y = W + 16, min(max(ty, 0), H - ch - 48)
            elif ax - 16 - cw >= 0:             # or on the left
                x, y = -16 - cw, min(max(ty, 0), H - ch - 48)
        where = f"+{ax + x}+{ay + y}"
        if where != self.where:
            self.where = where
            self.win.geometry(where)
        self.win.lift()

    def poll(self):
        self.poll_job = None
        if self.app.tour is not self:
            return
        st = self.step()
        if self.waiting():
            try:
                ok = bool(st["check"](self.base))
            except Exception:  # a half-done step is not done yet, never a crash
                ok = False
            if ok:
                self.passed.add(self.i)
                self.refresh()
        self.place()   # follow the part if the page changed under it
        self.poll_job = self.app.after(300, self.poll)

    def next(self):
        if self.required and self.waiting():
            return
        if self.i == len(self.steps) - 1:
            self.finish()
        else:
            self.i += 1
            self.show_step()

    def back(self):
        if self.i:
            self.i -= 1
            self.show_step()

    def finish(self):
        if self.poll_job:
            self.app.after_cancel(self.poll_job)
        for w in self.ring:
            w.destroy()
        self.win.destroy()
        self.app.tour_finished()


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
