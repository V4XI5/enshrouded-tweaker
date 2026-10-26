import ctypes, os, queue, subprocess, sys, threading, time, traceback
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import autopatch
import gfxmods
import kfc4
import live
import spv_inject
import watermods

APP_NAME = 'Extended Graphics and Physics Tweaker for Enshrouded'
GAME_PATCH, GAME_BUILD = '1.0.0.3', '1273043'
GAME_DIR = os.path.dirname(autopatch.MOD_DIR)
LOGO = os.path.join(HERE, 'logo.png')
LAUNCH_OPTION = f'"{os.path.join(autopatch.MOD_DIR, "autopatch.bat")}" %command%'
HOTKEY_NAME = 'Ctrl+Shift+F10'

SLIDERS = [
    ('smoke_life', 'Smoke Lifetime', 'restart', 0.25),
    ('dust_life', 'Dust puff lifetime', 'restart', 0.25),
    ('fog', 'Fog density', 'live', 0.05),
    ('weather_fog', 'Rain and snow haze', 'live', 0.05),
    ('shroud_fog', 'Shroud fog density', 'restart', 0.05),
    ('night_glow', 'Night fog glow (0 = fog stays dark at night)', 'live', 0.05),
    ('day_glow', 'Day fog glow (0 = no self-lit haze by day)', 'live', 0.05),
    ('vfx_distance', 'Effect draw distance', 'restart', 0.25),
]
PUSH_SLIDERS = [
    ('push_radius', 'Push radius', 0.1, ' m'),
    ('push_strength', 'Push strength', 0.25, ' m/s'),
    ('push_lift', 'Push lift', 0.25, ' m/s'),
]
SMOKE_PUSH_SLIDERS = [
    ('smoke_push_radius', 'Push radius', 0.1, ' m'),
    ('smoke_push_strength', 'Push strength', 0.1, ' m/s'),
    ('smoke_push_lift', 'Push lift', 0.1, ' m/s'),
]
COLLIDE_SLIDERS = [
    ('smoke_collide_radius', 'Collision radius', 0.05, ' m'),
    ('smoke_collide_slide', 'Slide along roofs and walls (0 = sticks)', 0.1, '×'),
]
VOLUME_SLIDERS = [
    ('smoke_volume', 'Volumetric smoke density (0 = off)', 0.1, '', 0.0),
    ('smoke_volume_sprites', 'Smoke billboard opacity with volumetric smoke', 0.05, '×', 1.0),
]
WAVE_SLIDERS = [
    ('wave_strength', 'Wave strength', 0.25),
    ('wave_size', 'Wave size', 0.25),
]
GI_CHOICES = [
    ('ultra', 'Ultra (vanilla)', '', None, "The game's own Ultra preset, with a 512 K global ray budget."),
    ('ultraplus', 'Ultra+ (modded)', 'May Decrease Performance.', 'amber',
     'Ultra probes with the hidden GroundTruth ray settings: a 2.48 M global ray budget (4.8× Ultra), 10× the rays '
     'needed to fill ambient probes and a finer spatial ray cache.'),
    ('ultraplusplus', 'Ultra++ (modded)', 'Will Decrease Performance.', 'red',
     'Ultra+ with a 4 M ray budget (7.8× Ultra), ray caching off and 2 to 4× the minimum rays per probe (128 and '
     '256 near the camera, 32 in the world cache).'),
]
FEATURES = [
    ('Physics debris', 'Rubble from mining, destruction and explosions stays put, and you can kick it around.'),
    ('Reactive particles', 'Smoke, dust, embers and flames part around you; fire and torch smoke hits walls and '
                           'ceilings.'),
    ('Bigger waves', 'Swimming, wading and rolling through water make taller, longer waves that travel further.'),
    ('Longer-lived effects', 'Smoke lasts up to 18× longer, sparks and dust up to 8×; effects draw up to 4× '
                             'farther.'),
    ('Fog and atmosphere', 'Fog, rain and snow haze and night glow tuned live while you play; thicker or '
                           'thinner Shroud.'),
    ('All light cast shadows', '444 more light sources cast shadows: spells, glowing plants, crafting stations.'),
    ('Global illumination beyond Ultra', 'Ultra+ and Ultra++ presets with up to 7.8× the ray budget, set live.'),
    ('In-game overlay', f'{HOTKEY_NAME} shows this window over the game in windowed or borderless mode.'),
    ('Survives game updates', 'Started through autopatch.bat, the mods rebuild themselves for each new game build.'),
]
PAGES = ('About', 'Effects and fog', 'Physics debris', 'Particles', 'Water', 'All light cast shadows',
         'Global illumination')

APPLY_SECONDS = 11.8
APPLY_STAGES = [
    ('installed files are', 1, 2.7, 'Reading the game data'),
    ('backed up the vanilla', 2, 2.7, 'Reading the game data'),
    ('reusing the existing build', 10, 11.3, 'Installing the game files'),
    ('fixed-rate debris linger', 2.6, 2.7, 'Rebuilding the debris shader'),
    ('debris shader', 2.7, 2.8, 'Patching the particle shaders'),
    ('loose-particle pushback', 2.8, 3.2, 'Analysing smoke and dust particles'),
    ('effects:', 3.2, 3.5, 'Re-pointing shader references'),
    ('castShadows', 3.5, 7.7, 'Compressing the game data'),
    ('chunk ', 7.7, 9.1, 'Verifying the game data'),
    ('verify OK: content map', 10, 11.3, 'Installing the game files'),
    ('verify OK', 9.1, 10, 'Verifying the shaders'),
    ('installed kfc pair', 11.3, 11.8, 'Writing the patched shaders'),
    ('mods installed', 11.8, 11.8, 'Installed'),
    ('already patched', 11.8, 11.8, 'Already installed'),
]

POLL_MS, LIVE_DELAY_MS, FRAME_MS = 1500, 500, 16
OVERLAY_ALPHA = 0.92
DRAWER_H = 240
MIN_HEIGHT, TITLE_BAR_H = 560, 40
CONTENT_W = 620
WRAP = CONTENT_W - 36
MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT, VK_F10, WM_HOTKEY = 0x2, 0x4, 0x4000, 0x79, 0x312
DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR = 20, 34, 35
SPI_GETWORKAREA = 0x30

FONT = ('Segoe UI', 10)
FONT_SMALL = ('Segoe UI', 9)
FONT_BOLD = ('Segoe UI Semibold', 10)
FONT_TITLE = ('Segoe UI Semibold', 13)
FONT_H1 = ('Segoe UI Semibold', 16)
FONT_TAG = ('Segoe UI Semibold', 8)
FONT_MONO = ('Consolas', 9)


def mix(a, b, t):
    ca, cb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x + (y - x) * t):02x}' for x, y in zip(ca, cb))


COL = {
    'bg': '#111317', 'panel': '#181b21', 'card': '#1e2229', 'raised': '#282d36', 'field': '#2e343f',
    'line': '#30363f', 'text': '#e8eaee', 'dim': '#a3abb8', 'faint': '#646d7b',
    'accent': '#ffba00', 'accent_hi': '#ffcb3d', 'accent_lo': '#a87b00', 'on_accent': '#16120a',
    'green': '#4ade80', 'green_bg': '#15351f', 'amber': '#fbbf24', 'red': '#f87171', 'tip': '#2a2312',
}
COL.update(hover=mix(COL['panel'], COL['raised'], 0.6), hover_line=mix(COL['line'], COL['accent'], 0.35),
           green_dim=mix(COL['green'], COL['panel'], 0.65))


_jobs = {}


def animate(widget, key, ms, step, done=None, frame_ms=FRAME_MS):
    stop(widget, key)
    frames = max(1, round(ms / frame_ms))

    def tick(i):
        t = i / frames
        step(1 - (1 - t) ** 3)
        if i < frames:
            _jobs[key] = widget.after(frame_ms, tick, i + 1)
        else:
            _jobs.pop(key, None)
            if done:
                done()
    tick(1)


def stop(widget, key):
    job = _jobs.pop(key, None)
    if job:
        widget.after_cancel(job)


def fade(widget, colour, option='background', ms=160):
    start = widget.cget(option)
    animate(widget, (widget, option), ms, lambda t: widget.configure({option: mix(start, colour, t)}))


def hover_area(frame, callback):
    def leave(_):
        w = frame.winfo_containing(*frame.winfo_pointerxy())
        if w is None or not (str(w) == str(frame) or str(w).startswith(str(frame) + '.')):
            callback(False)
    frame.bind('<Enter>', lambda e: callback(True), add='+')
    frame.bind('<Leave>', leave, add='+')


def label(parent, text, fg=None, font=FONT, wrap=WRAP, **kw):
    return tk.Label(parent, text=text, fg=fg or COL['text'], bg=parent.cget('bg'), font=font, justify='left',
                    anchor='w', wraplength=wrap, **kw)


def card(parent):
    c = tk.Frame(parent, bg=COL['card'], padx=16, pady=12, highlightthickness=1, highlightbackground=COL['line'])
    c.pack(fill='x', pady=(14, 0))
    return c


def badge(parent, applies):
    on = applies == 'live'
    return tk.Label(parent, text=applies.upper(), font=FONT_TAG, padx=7, pady=1,
                    fg=COL['green'] if on else COL['dim'], bg=COL['green_bg'] if on else COL['field'])


def gradient(canvas, width, steps=48):
    canvas.delete('all')
    h = int(canvas.cget('height'))
    for i in range(steps):
        canvas.create_rectangle(width * i / steps, 0, width * (i + 1) / steps + 1, h, outline='',
                                fill=mix(COL['accent'], COL['panel'], i / (steps - 1)))


class Button(tk.Label):
    def __init__(self, parent, text, command, kind='normal', tip=None, **kw):
        self.base, self.hover, self.fg = ((COL['accent'], COL['accent_hi'], COL['on_accent']) if kind == 'accent'
                                          else (COL['raised'], COL['field'], COL['text']))
        super().__init__(parent, text=text, bg=self.base, fg=self.fg, font=FONT_BOLD, padx=14, pady=6,
                         cursor='hand2', **kw)
        self.command, self.enabled = command, True
        self.bind('<Enter>', lambda e: self.enabled and fade(self, self.hover))
        self.bind('<Leave>', lambda e: self.enabled and fade(self, self.base))
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<ButtonRelease-1>', self.release)
        if tip:
            Tooltip(self, tip)

    def press(self, _):
        if self.enabled:
            stop(self, (self, 'background'))
            self.configure(bg=mix(self.base, '#000000', 0.2))

    def release(self, e):
        if self.enabled:
            inside = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
            fade(self, self.hover if inside else self.base)
            if inside:
                self.command()

    def set_enabled(self, enabled):
        if enabled != self.enabled:
            self.enabled = enabled
            fade(self, self.base if enabled else mix(self.base, COL['bg'], 0.7))
            fade(self, self.fg if enabled else COL['faint'], 'foreground')
            self.configure(cursor='hand2' if enabled else 'arrow')


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip, self.job = widget, text, None, None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')

    def schedule(self, _):
        self.hide()
        self.job = self.widget.after(450, self.show)

    def show(self):
        self.job = None
        text = self.text()
        if not text:
            return
        self.tip = tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        tip.attributes('-alpha', 0.0)
        tip.attributes('-topmost', True)
        tk.Label(tip, text=text, bg=COL['raised'], fg=COL['text'], font=FONT_SMALL, padx=10, pady=5, justify='left',
                 wraplength=280, highlightthickness=1, highlightbackground=COL['line']).pack()
        tip.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - tip.winfo_reqwidth() - 8)
        tip.geometry(f'+{x}+{self.widget.winfo_rooty() - tip.winfo_reqheight() - 6}')
        animate(tip, (self, 'tip'), 150, lambda t: tip.attributes('-alpha', 0.97 * t))

    def hide(self, _=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip:
            stop(self.tip, (self, 'tip'))
            self.tip.destroy()
            self.tip = None


class Switch(tk.Frame):
    W, H = 36, 20

    def __init__(self, parent, var, text, command=None, wrap=WRAP - 50):
        self.bg = parent.cget('bg')
        super().__init__(parent, bg=self.bg)
        self.var, self.command, self.enabled, self.pos = var, command, True, float(var.get())
        self.track = tk.Canvas(self, width=self.W, height=self.H, bg=self.bg, highlightthickness=0, bd=0,
                               cursor='hand2')
        self.track.pack(side='left', anchor='n')
        self.label = tk.Label(self, text=text, bg=self.bg, fg=COL['text'], font=FONT, justify='left', anchor='w',
                              wraplength=wrap, cursor='hand2')
        self.label.pack(side='left', padx=(10, 0))
        for w in (self, self.track, self.label):
            w.bind('<Button-1>', self.click)
        var.trace_add('write', lambda *_: self.slide())
        self.draw()

    def click(self, _):
        if self.enabled:
            self.var.set(not self.var.get())
            if self.command:
                self.command()

    def slide(self):
        start, to = self.pos, float(self.var.get())

        def step(t):
            self.pos = start + (to - start) * t
            self.draw()
        animate(self, (self, 'knob'), 180, step)

    def set_enabled(self, enabled):
        self.enabled = enabled
        for w in (self.track, self.label):
            w.configure(cursor='hand2' if enabled else 'arrow')
        fade(self.label, COL['text'] if enabled else COL['faint'], 'foreground')
        self.draw()

    def draw(self):
        c, p, w, h = self.track, self.pos, self.W, self.H
        track, knob = mix(COL['field'], COL['accent'], p), mix(COL['dim'], '#ffffff', p)
        if not self.enabled:
            track, knob = mix(track, self.bg, 0.55), mix(knob, self.bg, 0.55)
        c.delete('all')
        c.create_oval(0, 0, h, h, fill=track, outline='')
        c.create_oval(w - h, 0, w, h, fill=track, outline='')
        c.create_rectangle(h / 2, 0, w - h / 2, h, fill=track, outline='')
        x = h / 2 + (w - h) * p
        c.create_oval(x - 6, h / 2 - 6, x + 6, h / 2 + 6, fill=knob, outline='')


class Slider(tk.Canvas):
    H, PAD, VALUE_W = 28, 9, 76

    def __init__(self, parent, var, lo, hi, step, command=None, mark=None, unit=''):
        super().__init__(parent, width=300, height=self.H, bg=parent.cget('bg'), highlightthickness=0, bd=0,
                         cursor='hand2', takefocus=1)
        self.var, self.lo, self.hi, self.step, self.command, self.mark, self.unit = (var, lo, hi, step, command,
                                                                                    mark, unit)
        self.decimals = len(f'{step:g}'.partition('.')[2])
        self.enabled, self.level, self.r = True, 1.0, 6.0
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Button-1>', self.press)
        self.bind('<B1-Motion>', lambda e: self.enabled and self.set_x(e.x))
        self.bind('<Enter>', lambda e: self.grow(8.0))
        self.bind('<Leave>', lambda e: self.grow(6.0))
        for key, d in (('<Left>', -1), ('<Down>', -1), ('<Right>', 1), ('<Up>', 1)):
            self.bind(key, lambda e, d=d: self.enabled and self.set(self.var.get() + d * self.step))
        var.trace_add('write', lambda *_: self.draw())

    def press(self, e):
        if self.enabled:
            self.focus_set()
            self.set_x(e.x)

    def set_x(self, x):
        x0, x1 = self.PAD, self.winfo_width() - self.VALUE_W
        self.set(self.lo + (self.hi - self.lo) * (x - x0) / max(1, x1 - x0))

    def set(self, v):
        v = min(max(round(round(v / self.step) * self.step, 6), self.lo), self.hi)
        if v != self.var.get():
            self.var.set(v)
            if self.command:
                self.command()

    def grow(self, r):
        start = self.r
        if not self.enabled:
            r = 6.0

        def step(t):
            self.r = start + (r - start) * t
            self.draw()
        animate(self, (self, 'knob'), 120, step)

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor='hand2' if enabled else 'arrow')
        start, to = self.level, float(enabled)

        def step(t):
            self.level = start + (to - start) * t
            self.draw()
        animate(self, (self, 'level'), 200, step)

    def draw(self):
        self.delete('all')
        w, y = self.winfo_width(), self.H / 2
        x0, x1 = self.PAD, w - self.VALUE_W
        if x1 - x0 < 10:
            return
        v = min(max(self.var.get(), self.lo), self.hi)
        x = x0 + (x1 - x0) * (v - self.lo) / (self.hi - self.lo)
        fill, knob = mix(COL['faint'], COL['accent'], self.level), mix(COL['faint'], COL['text'], self.level)
        self.create_line(x0, y, x1, y, width=4, capstyle='round', fill=COL['field'])
        if x > x0:
            self.create_line(x0, y, x, y, width=4, capstyle='round', fill=fill)
        if self.mark is not None and self.lo < self.mark < self.hi:
            xm = x0 + (x1 - x0) * (self.mark - self.lo) / (self.hi - self.lo)
            self.create_line(xm, y - 7, xm, y + 7, width=2, fill=COL['dim'])
        r = self.r
        self.create_oval(x - r, y - r, x + r, y + r, fill=knob, outline=fill, width=2)
        self.create_text(w - 2, y, anchor='e', text=f'{v:.{self.decimals}f}{self.unit}', fill=knob, font=FONT_BOLD)


class Segmented(tk.Frame):
    def __init__(self, parent, var, values):
        super().__init__(parent, bg=COL['field'], padx=3, pady=3)
        self.var, self.items = var, {}
        for v in values:
            item = tk.Label(self, text=v, font=FONT_BOLD, padx=11, pady=3, bg=COL['field'], fg=COL['dim'],
                            cursor='hand2')
            item.pack(side='left')
            item.bind('<Button-1>', lambda e, v=v: var.set(v))
            item.bind('<Enter>', lambda e, v=v: self.paint(v, True))
            item.bind('<Leave>', lambda e, v=v: self.paint(v, False))
            self.items[v] = item
        var.trace_add('write', lambda *_: self.repaint())
        self.repaint()

    def repaint(self):
        for v in self.items:
            self.paint(v, False)

    def paint(self, v, hover):
        on, item = v == self.var.get(), self.items[v]
        fade(item, COL['accent'] if on else COL['raised'] if hover else COL['field'])
        fade(item, COL['on_accent'] if on else COL['text'] if hover else COL['dim'], 'foreground')


class Choice(tk.Frame):
    def __init__(self, parent, var, value, title, note, note_colour, details, command=None):
        super().__init__(parent, bg=COL['card'], padx=14, pady=10, highlightthickness=1,
                         highlightbackground=COL['line'], highlightcolor=COL['line'])
        self.var, self.value, self.command, self.inside = var, value, command, False
        self.level = float(var.get() == value)
        self.columnconfigure(1, weight=1)
        self.dot = tk.Canvas(self, width=18, height=18, bg=COL['card'], highlightthickness=0, bd=0)
        self.dot.grid(row=0, column=0, rowspan=2, sticky='n', padx=(0, 12), pady=(2, 0))
        head = tk.Frame(self, bg=COL['card'])
        head.grid(row=0, column=1, sticky='w')
        tk.Label(head, text=title, font=FONT_BOLD, fg=COL['text'], bg=COL['card']).pack(side='left')
        if note:
            tk.Label(head, text=note, font=FONT_BOLD, fg=note_colour, bg=COL['card']).pack(side='left', padx=(10, 0))
        label(self, details, fg=COL['dim'], font=FONT_SMALL, wrap=WRAP - 40).grid(row=1, column=1, sticky='w',
                                                                                 pady=(3, 0))
        for w in (self, self.dot, head, *head.winfo_children(), *self.winfo_children()):
            w.bind('<Button-1>', self.pick, add='+')
            w.configure(cursor='hand2')
        hover_area(self, self.hovering)
        var.trace_add('write', lambda *_: self.refresh())
        self.draw()
        self.border()

    def pick(self, _):
        if self.var.get() != self.value:
            self.var.set(self.value)
            if self.command:
                self.command()

    def hovering(self, inside):
        self.inside = inside
        self.border()

    def border(self):
        colour = (COL['accent'] if self.var.get() == self.value else
                  COL['hover_line'] if self.inside else COL['line'])
        fade(self, colour, 'highlightbackground')

    def refresh(self):
        start, to = self.level, float(self.var.get() == self.value)

        def step(t):
            self.level = start + (to - start) * t
            self.draw()
        animate(self, (self, 'dot'), 200, step)
        self.border()

    def draw(self):
        c, k = self.dot, self.level
        c.delete('all')
        c.create_oval(2, 2, 16, 16, outline=mix(COL['faint'], COL['accent'], k), width=2)
        r = 4 * k
        if r > 0.5:
            c.create_oval(9 - r, 9 - r, 9 + r, 9 + r, fill=COL['accent'], outline='')


class Tile(tk.Frame):
    def __init__(self, parent, title, text):
        super().__init__(parent, bg=COL['card'], padx=12, pady=9, highlightthickness=1,
                         highlightbackground=COL['line'])
        tk.Label(self, text=title, font=FONT_BOLD, fg=COL['accent'], bg=COL['card'], anchor='w').pack(fill='x')
        label(self, text, fg=COL['dim'], font=FONT_SMALL, wrap=(CONTENT_W - 12) // 2 - 28).pack(fill='x',
                                                                                              pady=(2, 0))
        hover_area(self, lambda inside: fade(self, COL['accent_lo'] if inside else COL['line'],
                                             'highlightbackground'))


class Scroll(tk.Frame):
    def __init__(self, parent, bg, **inner):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=bg, **inner)
        self.item = self.canvas.create_window(0, 0, window=self.inner, anchor='nw')
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview, style='Slim.Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.inner.bind('<Configure>', lambda e: self.fit())
        self.canvas.bind('<Configure>', lambda e: self.fit())

    def fit(self):
        c, h = self.canvas, self.inner.winfo_reqheight()
        c.itemconfigure(self.item, width=c.winfo_width())
        c.configure(scrollregion=(0, 0, 0, h))
        if h > c.winfo_height() + 1:
            if not self.bar.winfo_ismapped():
                self.bar.pack(side='right', fill='y', before=c)
        elif self.bar.winfo_ismapped():
            self.bar.pack_forget()
            c.yview_moveto(0)

    def scroll(self, units):
        if self.bar.winfo_ismapped():
            self.canvas.yview_scroll(units, 'units')


class Nav(tk.Frame):
    WIDTH = 210

    def __init__(self, parent, names, on_select):
        super().__init__(parent, bg=COL['panel'], width=self.WIDTH)
        self.pack_propagate(False)
        self.on_select, self.current, self.items, self.bar_y = on_select, None, [], None
        tk.Frame(self, bg=COL['panel'], height=10).pack()
        for i, name in enumerate(names):
            item = tk.Label(self, text=name, anchor='w', font=FONT_BOLD, bg=COL['panel'], fg=COL['dim'], padx=22,
                            pady=9, cursor='hand2')
            item.pack(fill='x')
            item.bind('<Button-1>', lambda e, i=i: self.select(i))
            item.bind('<Enter>', lambda e, i=i: self.hover(i, True))
            item.bind('<Leave>', lambda e, i=i: self.hover(i, False))
            self.items.append(item)
        self.bar = tk.Frame(self, bg=COL['accent'], width=3)

    def hover(self, i, inside):
        if i != self.current:
            fade(self.items[i], COL['hover'] if inside else COL['panel'])
            fade(self.items[i], COL['text'] if inside else COL['dim'], 'foreground')

    def select(self, i):
        if i == self.current:
            return
        previous, self.current = self.current, i
        for j, item in enumerate(self.items):
            fade(item, COL['raised'] if j == i else COL['panel'])
            fade(item, COL['text'] if j == i else COL['dim'], 'foreground')
        y, h = self.items[i].winfo_y(), self.items[i].winfo_height()
        start = y if self.bar_y is None else self.bar_y

        def step(t):
            self.bar_y = start + (y - start) * t
            self.bar.place(x=0, y=round(self.bar_y), width=3, height=h)
        animate(self, (self, 'bar'), 240, step)
        self.bar.lift()
        self.on_select(i, previous)


class ProgressBar(tk.Canvas):
    H = 30

    def __init__(self, parent):
        self.bg = parent.cget('bg')
        super().__init__(parent, height=self.H, width=200, bg=self.bg, highlightthickness=0, bd=0)
        self.job = self.fade_job = None
        self.shown = self.target = self.ceiling = self.span = self.speed = self.phase = self.opacity = 0.0
        self.caption, self.colour, self.active = '', COL['accent'], False
        self.bind('<Configure>', lambda e: self.draw())

    def go(self, value, ceiling=None, caption=None, seconds=0):
        if not self.active:
            self.shown = self.target = 0.0
            self.active, self.colour = True, COL['accent']
        if self.fade_job:
            self.after_cancel(self.fade_job)
            self.fade_job = None
        stop(self, (self, 'fade'))
        self.opacity = 1.0
        self.target = max(self.target, value)
        self.ceiling = max(self.target, value if ceiling is None else ceiling)
        self.span = self.ceiling - self.target
        self.speed = self.span / seconds if seconds > 0 else 0.0
        if caption is not None:
            self.caption = caption
        self.run()

    def finish(self, ok=True, caption=None):
        if not self.active:
            return
        self.active = False
        self.colour = COL['green'] if ok else COL['red']
        self.target = self.ceiling = 1.0 if ok else self.shown
        self.caption = caption or ('Done' if ok else 'Failed: see the log')
        self.run()
        self.fade_job = self.after(2500 if ok else 8000, self.fade_out)

    def fade_out(self):
        self.fade_job = None

        def step(t):
            self.opacity = 1 - t
            self.draw()
        animate(self, (self, 'fade'), 600, step)

    def run(self):
        if self.job is None:
            self.tick()

    def tick(self):
        self.job = None
        gap = self.ceiling - self.target
        if gap > 0 and self.speed:
            step = self.speed * FRAME_MS / 1000
            if gap < 0.25 * self.span:
                step *= gap / (0.25 * self.span)
            self.target += min(step, gap)
        self.shown += (self.target - self.shown) * 0.2
        self.phase = (self.phase + 0.012) % 1.0
        self.draw()
        if self.active or abs(self.target - self.shown) > 0.0005:
            self.job = self.after(FRAME_MS, self.tick)

    def draw(self):
        self.delete('all')
        o = self.opacity
        if o <= 0:
            return
        x0, x1, y = 3, self.winfo_width() - 3, self.H - 6
        self.create_line(x0, y, x1, y, width=4, capstyle='round', fill=mix(self.bg, COL['field'], o))
        xf = x0 + (x1 - x0) * self.shown
        if xf > x0 + 1:
            self.create_line(x0, y, xf, y, width=4, capstyle='round', fill=mix(self.bg, self.colour, o))
            if self.active:
                centre = x0 + (xf - x0 + 120) * self.phase - 60
                for half, k in ((40, 0.18), (24, 0.32), (10, 0.5)):
                    a, b = max(x0, centre - half), min(xf, centre + half)
                    if b > a:
                        self.create_line(a, y, b, y, width=4, fill=mix(self.colour, '#ffffff', k))
        self.create_text(x0, 9, anchor='w', text=self.caption, fill=mix(self.bg, COL['text'], o), font=FONT_SMALL)
        self.create_text(x1, 9, anchor='e', text=f'{self.shown * 100:.0f}%', fill=mix(self.bg, COL['dim'], o),
                         font=FONT_SMALL)


def start_hotkey(callback):
    ready, result = threading.Event(), []

    def run():
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_F10):
            result.append(f'{HOTKEY_NAME} is taken by another program (error {ctypes.get_last_error()})')
            ready.set()
            return
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                callback()

    threading.Thread(target=run, daemon=True).start()
    ready.wait(5)
    return result[0] if result else None


def dark_title_bar(root):
    colorref = lambda c: int(c[5:7] + c[3:5] + c[1:3], 16)
    try:
        hwnd = wintypes.HWND(int(root.wm_frame(), 16))
        for attr, value in ((DWMWA_USE_IMMERSIVE_DARK_MODE, 1), (DWMWA_CAPTION_COLOR, colorref(COL['panel'])),
                            (DWMWA_BORDER_COLOR, colorref(COL['line']))):
            v = wintypes.DWORD(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
    except (AttributeError, OSError, ValueError):
        pass


def make_icon(root):
    img = tk.PhotoImage(master=root, width=32, height=32)
    for y in range(32):
        row = ['#000000' if 6 <= y <= 26 and abs(abs(x + 0.5 - 16) - (26 - y) * 0.4) < 1.8 else COL['accent']
               for x in range(32)]
        img.put('{' + ' '.join(row) + '}', to=(0, y))
    for y in range(32):
        for x in range(32):
            dx, dy = max(5 - x, x - 26, 0), max(5 - y, y - 26, 0)
            if dx * dx + dy * dy > 25:
                img.transparency_set(x, y, True)
    return img


def style_ttk(root):
    s = ttk.Style(root)
    s.theme_use('clam')
    s.layout('Slim.Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
        ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
    s.configure('Slim.Vertical.TScrollbar', troughcolor=COL['panel'], background=COL['raised'],
                bordercolor=COL['panel'], lightcolor=COL['raised'], darkcolor=COL['raised'], gripcount=0,
                arrowsize=10)
    s.map('Slim.Vertical.TScrollbar', background=[('pressed', COL['accent_lo']), ('active', COL['field'])])


def work_area(root):
    r = wintypes.RECT()
    try:
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    except (AttributeError, OSError):
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 48


def python_exe():
    console = os.path.join(os.path.dirname(sys.executable), 'python.exe')
    return console if os.path.exists(console) else sys.executable


def describe_install():
    st = autopatch.load_state()
    saved = autopatch.full_options(st.get('options', {}))
    k = kfc4.KFC(GAME_DIR)
    build = autopatch.svn(k.version)
    rec = st.get('builds', {}).get(k.version)
    if not rec or autopatch.pair_sha1(GAME_DIR) != rec['patched']:
        return build, 'Mods are not installed for this game build; they are applied at next launch.'
    if autopatch.full_options(rec['options']) != saved:
        return build, 'Saved options differ from the installed build; they are applied at next launch.'
    return build, f'Installed build {build} matches the saved options.'


def apply_stage(line, done, seen):
    for start, at, until, what in APPLY_STAGES:
        if line.startswith(start):
            if start in seen:
                return None
            seen.add(start)
            at = max(done, at / APPLY_SECONDS)
            until = max(at, until / APPLY_SECONDS)
            return at, until, what, (until - at) * APPLY_SECONDS
    return None


def log_tag(msg):
    if (msg.startswith(('error', 'Traceback')) or 'failed' in msg or 'INCONSISTENT' in msg
            or ('exit code' in msg and not msg.endswith('(exit code 0)'))):
        return 'error'
    if msg.startswith(('verify OK', 'mods installed', 'already patched', 'options saved', 'fog: ', 'GI: ')) \
            or msg.endswith('(exit code 0)'):
        return 'ok'
    return 'cmd' if msg.startswith('> ') else ''


class App:
    def __init__(self, root):
        self.root, self.q = root, queue.Queue()
        self.busy, self.pending_live, self.pending_gi, self.live_timer = False, False, False, None
        self.fog = self.gi = None
        self.pid = False
        self.vars, self.pages, self.toggles = {}, [], []
        root.withdraw()
        root.title(APP_NAME)
        root.configure(bg=COL['bg'])
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        style_ttk(root)
        self.icon = make_icon(root)
        root.iconphoto(True, self.icon)
        opts = autopatch.full_options(autopatch.load_state().get('options', {}))

        self.header().grid(row=0, column=0, sticky='ew')
        rule = tk.Canvas(root, height=2, bg=COL['panel'], highlightthickness=0, bd=0)
        rule.bind('<Configure>', lambda e: gradient(rule, e.width))
        rule.grid(row=1, column=0, sticky='ew')
        self.body = tk.Frame(root, bg=COL['bg'])
        self.body.grid(row=2, column=0, sticky='nsew')
        self.body.columnconfigure(1, weight=1)
        self.body.rowconfigure(0, weight=1)
        self.box = tk.Frame(self.body, bg=COL['bg'])
        self.box.grid(row=0, column=1, sticky='nsew')
        self.about_page()
        self.effects_page(opts)
        self.debris_page(opts)
        self.particles_page(opts)
        self.water_page(opts)
        self.lights_page(opts)
        self.gi_page()
        self.nav = Nav(self.body, PAGES, self.show_page)
        self.nav.grid(row=0, column=0, sticky='ns')
        self.app_switches()
        self.log_drawer()
        self.activity().grid(row=3, column=0, sticky='ew')
        self.footer().grid(row=4, column=0, sticky='ew')
        root.update_idletasks()
        self.box.configure(width=max(p.inner.winfo_reqwidth() for p in self.pages),
                           height=max(p.inner.winfo_reqheight() for p in self.pages))
        root.bind_all('<MouseWheel>', self.wheel)
        self.toggled()

        self.say('Options marked RESTART go into the game files: "Apply to game files" with the game closed, or '
                 '"Save for next launch". Options marked LIVE also change in the running game.')
        error = start_hotkey(lambda: self.q.put(('hotkey',)))
        self.say(f'Overlay hotkey: {error}' if error else
                 f'{HOTKEY_NAME} shows or hides this window over the game (windowed or borderless fullscreen).')
        self.work(lambda: self.q.put(('install', *describe_install())))
        root.after(100, self.pump)
        root.after(10, self.poll)
        root.after(20, self.reveal)


    def reveal(self):
        root = self.root
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        left, top, right, bottom = work_area(root)
        h = max(min(h, bottom - top - TITLE_BAR_H), MIN_HEIGHT)
        root.minsize(w, MIN_HEIGHT)
        root.geometry(f'{w}x{h}+{max(left, (left + right - w) // 2)}+'
                      f'{max(top, (top + bottom - h - TITLE_BAR_H) // 2)}')
        root.attributes('-alpha', 0.0)
        root.deiconify()
        dark_title_bar(root)
        root.update_idletasks()
        self.nav.select(0)
        animate(root, 'reveal', 350, lambda t: root.attributes('-alpha', t))

    def header(self):
        h = tk.Frame(self.root, bg=COL['panel'], padx=20, pady=14)
        try:
            self.logo = tk.PhotoImage(master=self.root, file=LOGO)
            tk.Label(h, image=self.logo, bg=COL['panel']).grid(row=0, column=0, rowspan=3, sticky='w', padx=(0, 22))
        except tk.TclError:
            pass
        tk.Label(h, text=APP_NAME, font=FONT_TITLE, fg=COL['text'], bg=COL['panel']).grid(row=0, column=1,
                                                                                           sticky='w')
        line = tk.Frame(h, bg=COL['panel'])
        line.grid(row=1, column=1, sticky='w')
        tk.Label(line, text=f'Build for game patch: {GAME_PATCH}', font=FONT_BOLD, fg=COL['green'],
                 bg=COL['panel']).pack(side='left')
        self.dot = tk.Canvas(line, width=10, height=10, bg=COL['panel'], highlightthickness=0, bd=0)
        self.dot.create_oval(1, 1, 9, 9, fill=COL['faint'], outline='', tags='dot')
        self.dot.pack(side='left', padx=(18, 6))
        self.status = tk.Label(line, text='Looking for the game...', font=FONT_SMALL, fg=COL['text'],
                               bg=COL['panel'])
        self.status.pack(side='left')
        self.install = label(h, '', fg=COL['dim'], font=FONT_SMALL, wrap=480)
        self.install.grid(row=2, column=1, sticky='w')
        return h

    def page(self, title, intro=''):
        s = Scroll(self.box, COL['bg'], padx=24, pady=18)
        p = s.inner
        tk.Frame(p, bg=COL['bg'], width=CONTENT_W, height=0).pack()
        tk.Label(p, text=title, font=FONT_H1, fg=COL['text'], bg=COL['bg']).pack(anchor='w')
        if intro:
            label(p, intro, fg=COL['dim'], wrap=CONTENT_W).pack(anchor='w', pady=(2, 0))
        self.pages.append(s)
        return p

    def show_page(self, i, previous):
        if previous is not None:
            self.pages[previous].place_forget()
        page, shift = self.pages[i], 30 if previous is None or i > previous else -30
        animate(self.root, 'page', 240,
                lambda t: page.place(x=round(shift * (1 - t)), y=0, relwidth=1, relheight=1))

    def about_page(self):
        p = self.page('About', 'Pushes Enshrouded past its own Ultra settings and makes its world more physical: '
                               'debris that stays where it falls, particles that react to you, bigger waves, thicker '
                               'fog, more shadowed lights and stronger global illumination. Every change can be '
                               'switched back off.')
        grid = tk.Frame(p, bg=COL['bg'])
        grid.pack(fill='x', pady=(14, 0))
        grid.columnconfigure((0, 1), weight=1, uniform='feature')
        for i, (title, text) in enumerate(FEATURES):
            last = i == len(FEATURES) - 1 and i % 2 == 0
            Tile(grid, title, text).grid(row=i // 2, column=i % 2, columnspan=2 if last else 1, sticky='nsew',
                                         pady=(0, 8), padx=0 if last else (0, 6) if i % 2 == 0 else (6, 0))
        c = card(p)
        c.columnconfigure(0, weight=1)
        label(c, 'Keep the mods through game updates', font=FONT_BOLD).grid(row=0, column=0, columnspan=2,
                                                                          sticky='w')
        label(c, "Set this as Enshrouded's launch option in Steam (Properties > General > Launch options):",
              fg=COL['dim'], font=FONT_SMALL).grid(row=1, column=0, columnspan=2, sticky='w', pady=(2, 0))
        field = tk.Frame(c, bg=COL['field'], padx=8, pady=6)
        field.grid(row=2, column=0, sticky='ew', pady=(6, 0))
        self.launch_var = tk.StringVar(value=LAUNCH_OPTION)
        tk.Entry(field, textvariable=self.launch_var, state='readonly', readonlybackground=COL['field'],
                 fg=COL['text'], font=FONT_MONO, relief='flat', bd=0, highlightthickness=0, width=1).pack(fill='x')
        self.copy_btn = Button(c, 'Copy', self.copy_launch_option, width=7)
        self.copy_btn.grid(row=2, column=1, padx=(8, 0), pady=(6, 0))
        label(c, 'Your saves are never touched. A vanilla backup is kept, and Steam\'s "Verify integrity of game '
                 'files" always brings back the original game.', fg=COL['dim'], font=FONT_SMALL).grid(
            row=3, column=0, columnspan=2, sticky='w', pady=(8, 0))

    def effects_page(self, opts):
        p = self.page('Effects and fog', 'Multipliers, where 1 is vanilla (the tick on a slider). LIVE options also '
                                         'change in the running game as you move them.')
        c = card(p)
        c.columnconfigure(0, minsize=220)
        c.columnconfigure(1, weight=1)
        for r, (name, text, applies, step) in enumerate(SLIDERS):
            lo, hi = gfxmods.LIMITS[name]
            self.vars[name] = v = tk.DoubleVar(value=opts[name])
            label(c, text, wrap=210).grid(row=r, column=0, sticky='w', pady=3)
            Slider(c, v, lo, hi, step, command=lambda n=name: self.changed(n), mark=1.0, unit='×').grid(
                row=r, column=1, sticky='ew')
            badge(c, applies).grid(row=r, column=2, padx=(12, 0))
        self.caps = tk.BooleanVar(value=opts['smoke_caps'] == 'on')
        Switch(c, self.caps, 'Raise particle caps to match longer lifetimes (more GPU memory)').grid(
            row=len(SLIDERS), column=0, columnspan=3, sticky='w', pady=(12, 0))

    def debris_page(self, opts):
        p = self.page('Physics debris', 'The pieces that break off when you mine, destroy or blow things up. '
                                        'Applied to the game files (restart).')
        c = card(p)
        label(c, 'Debris linger in seconds (0 = until the effect ends)').grid(row=0, column=0, sticky='w')
        self.linger = tk.StringVar(value=str(opts['linger']))
        Segmented(c, self.linger, [str(x) for x in sorted(autopatch.LINGER_RATES)]).grid(row=1, column=0,
                                                                                       sticky='w', pady=(6, 12))
        self.linger_all = tk.BooleanVar(value=opts['linger_all'] == 'on')
        Switch(c, self.linger_all, 'Physics Debris from broken things, destruction, mining, explosions etc. stays '
                                   'longer.').grid(row=2, column=0, sticky='w')
        c = card(p)
        c.columnconfigure(1, weight=1)
        self.pushback = tk.BooleanVar(value=opts['pushback'] == 'on')
        self.switched_sliders(c, 0, self.pushback, 'Players push landed debris away (debris tumbles and collides '
                                                   'again)', PUSH_SLIDERS, opts)

    def particles_page(self, opts):
        p = self.page('Particles', 'Sparks, smoke, dust, embers and flames. Applied to the game files (restart).')
        c = card(p)
        c.columnconfigure(0, minsize=220)
        c.columnconfigure(1, weight=1)
        lo, hi = spv_inject.LIMITS['spark_life']
        self.vars['spark_life'] = v = tk.DoubleVar(value=opts['spark_life'])
        label(c, 'Spark lifetime', wrap=210).grid(row=0, column=0, sticky='w')
        Slider(c, v, lo, hi, 0.25, mark=1.0, unit='×').grid(row=0, column=1, sticky='ew')
        c = card(p)
        c.columnconfigure(1, weight=1)
        self.smoke_push = tk.BooleanVar(value=opts['smoke_push'] == 'on')
        widgets = self.switched_sliders(c, 0, self.smoke_push, 'Players push smoke, dust, embers and flames aside',
                                        SMOKE_PUSH_SLIDERS, opts)
        self.smoke_push_own = tk.BooleanVar(value=opts['smoke_push_own'] == 'on')
        own = Switch(c, self.smoke_push_own, 'Also push my own effects: held torch smoke and embers, footstep dust '
                                             '(flames stay on the torch)', wrap=WRAP - 100)
        own.grid(row=1 + len(SMOKE_PUSH_SLIDERS), column=0, columnspan=3, sticky='w', padx=(46, 0), pady=(10, 0))
        widgets.append(own)
        c = card(p)
        c.columnconfigure(1, weight=1)
        self.smoke_collide = tk.BooleanVar(value=opts['smoke_collide'] == 'on')
        self.switched_sliders(c, 0, self.smoke_collide, 'Smoke collides with the world', COLLIDE_SLIDERS, opts)
        label(c, 'Smoke particles, such as the smoke of torches and campfires, collide with ceilings, walls and '
                 'overhangs instead of passing through them. The smoke shaders get the world distance query the game '
                 'otherwise only runs when a particle spawns. Smoke that hits a surface slides along it, up the slope '
                 'of a roof or spreading out under a flat ceiling, instead of resting where it hit. A shader that cannot take it is skipped and named in '
                 'the apply log.', fg=COL['dim']).grid(row=1 + len(COLLIDE_SLIDERS), column=0, columnspan=3,
                                                      sticky='w', pady=(10, 0))
        c = card(p)
        c.columnconfigure(0, minsize=220)
        c.columnconfigure(1, weight=1)
        for r, (name, text, step, unit, mark) in enumerate(VOLUME_SLIDERS):
            lo, hi = spv_inject.LIMITS[name]
            self.vars[name] = v = tk.DoubleVar(value=opts[name])
            label(c, text, wrap=210).grid(row=r, column=0, sticky='w', pady=3)
            Slider(c, v, lo, hi, step, mark=mark, unit=unit).grid(row=r, column=1, sticky='ew')
        label(c, 'Smoke particles also feed the volumetric fog, as soft fog spheres the size of their billboards, so '
                 'the smoke is lit and shadowed the way the fog is. At density 1 a puff is as opaque as its billboard; '
                 'it thins out as the puff ages, and far puffs are spread wider and fainter so they do not flicker. '
                 'Lower the billboard opacity (around 0.5) for smoke that is more fog than sprite (0 = fog only). '
                 'Experimental: it costs GPU time when a lot of smoke is on screen, and the smoke of effect shaders '
                 'that have no room for it stays as it is.',
              fg=COL['dim']).grid(row=len(VOLUME_SLIDERS), column=0, columnspan=2, sticky='w', pady=(10, 0))

    def water_page(self, opts):
        p = self.page('Water', "Waves on the water surface, from the game's own wave simulation. Applied to the game "
                               'files (restart).')
        c = card(p)
        c.columnconfigure(0, minsize=220)
        c.columnconfigure(1, weight=1)
        for r, (name, text, step) in enumerate(WAVE_SLIDERS):
            lo, hi = watermods.LIMITS[name]
            self.vars[name] = v = tk.DoubleVar(value=opts[name])
            label(c, text, wrap=210).grid(row=r, column=0, sticky='w', pady=3)
            Slider(c, v, lo, hi, step, mark=1.0, unit='×').grid(row=r, column=1, sticky='ew')
        label(c, 'How hard you push the water when you swim, wade, jump or glide in, jump out and roll. Strength '
                 'makes the waves taller; size spreads each push wider, which makes longer waves that roll further '
                 'before they break up. Swim strokes are yours alone; the wading wake and the splashes are shared with '
                 'creatures that wade. 2 to 3 is a good start; the game caps how tall a wave can get.',
              fg=COL['dim']).grid(row=len(WAVE_SLIDERS), column=0, columnspan=2, sticky='w', pady=(10, 0))
        c = card(p)
        self.wave_reach = tk.BooleanVar(value=opts['wave_reach'] == 'on')
        Switch(c, self.wave_reach, 'Waves travel further and last longer').grid(row=0, column=0, sticky='w')
        label(c, 'Every wave on the water, from you, creatures, rain, fish and debris, fades half as fast and runs '
                 'freely out to about 24 m from you instead of 16 m before the edge of the simulated area absorbs it. '
                 'The wave speed and the 64 m simulated area are set by game code and stay as they are.',
              fg=COL['dim']).grid(row=1, column=0, sticky='w', pady=(10, 0))

    def lights_page(self, opts):
        p = self.page('All light cast shadows', 'Applied to the game files (restart).')
        c = card(p)
        self.lights = tk.BooleanVar(value=opts['lights'] == 'on')
        Switch(c, self.lights, 'More light sources cast shadows').grid(row=0, column=0, sticky='w')
        label(c, 'In vanilla, torches, campfires, lanterns, braziers, candles and the held torch already cast '
                 'shadows. This turns them on for 444 light sources that have them off, mostly spells and '
                 'projectiles, weapon and orb glows, glowing plants, crafting stations, enemy camp fires and light '
                 'props.', fg=COL['dim']).grid(row=1, column=0, sticky='w', pady=(10, 0))
        label(c, 'On Ultra the game re-traces at most 64 shadowed lights per frame and has 1024 shadow slots, so with '
                 'more shadowed lights each one updates a little less often. Moving lights such as spells go first.',
              fg=COL['dim']).grid(row=2, column=0, sticky='w', pady=(8, 0))
        c = card(p)
        label(c, 'Character shadows', font=FONT_BOLD).grid(row=0, column=0, sticky='w')
        label(c, 'Characters and creatures cast shadows from the sun and moon only. The game traces the shadows of '
                 'other lights against its voxel world, and characters are not part of it, so no setting can add '
                 'them.', fg=COL['dim']).grid(row=1, column=0, sticky='w', pady=(4, 0))

    def gi_page(self):
        p = self.page('Global illumination', 'Live only: pushed into the running game, and reset when the game '
                                             'closes.')
        self.gi_mode = tk.StringVar(value='ultra')
        for mode, title, note, tone, details in GI_CHOICES:
            Choice(p, self.gi_mode, mode, title, note, COL.get(tone), details,
                   command=lambda: self.changed('gi')).pack(fill='x', pady=(12, 0))
        tip = tk.Frame(p, bg=COL['tip'])
        tip.pack(fill='x', pady=(14, 0))
        tk.Frame(tip, bg=COL['accent'], width=3).pack(side='left', fill='y')
        label(tip, 'After you select a change, go into the options menu in-game and change the "Indirect Light" '
                   'setting from Ultra down to High, then set it back to Ultra again to make it apply.',
              wrap=CONTENT_W - 40, padx=14, pady=10).pack(side='left', fill='x')

    def app_switches(self):
        f = tk.Frame(self.nav, bg=COL['panel'], padx=18, pady=16)
        f.pack(side='bottom', fill='x')
        self.auto = tk.BooleanVar(value=True)
        Switch(f, self.auto, 'Push live options as I change them', wrap=124).pack(anchor='w')
        self.overlay = tk.BooleanVar(value=False)
        Switch(f, self.overlay, f'Overlay ({HOTKEY_NAME})', command=self.overlay_toggled, wrap=124).pack(
            anchor='w', pady=(12, 0))

    def log_drawer(self):
        self.drawer = tk.Frame(self.body, bg=COL['panel'], highlightthickness=1, highlightbackground=COL['line'])
        self.log = tk.Text(self.drawer, bg=COL['panel'], fg=COL['dim'], font=FONT_MONO, relief='flat', bd=0,
                           padx=12, pady=8, wrap='word', state='disabled', insertbackground=COL['text'],
                           selectbackground=COL['accent_lo'], selectforeground=COL['text'], width=1, height=1)
        sb = ttk.Scrollbar(self.drawer, orient='vertical', command=self.log.yview, style='Slim.Vertical.TScrollbar')
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        for tag, colour in (('error', COL['red']), ('ok', COL['green']), ('cmd', COL['accent'])):
            self.log.tag_configure(tag, foreground=colour)
        self.log_open, self.log_level = False, 0.0

    def activity(self):
        s = tk.Frame(self.root, bg=COL['panel'], padx=20, pady=6, cursor='hand2')
        s.columnconfigure(1, weight=1)
        tk.Label(s, text='ACTIVITY', font=FONT_TAG, fg=COL['faint'], bg=COL['panel']).grid(row=0, column=0,
                                                                                         padx=(0, 12))
        self.last = tk.Label(s, text='', font=FONT_SMALL, fg=COL['dim'], bg=COL['panel'], anchor='w', width=1)
        self.last.grid(row=0, column=1, sticky='ew')
        self.log_link = tk.Label(s, text='Show log', font=FONT_BOLD, fg=COL['accent'], bg=COL['panel'])
        self.log_link.grid(row=0, column=2, padx=(12, 0))
        for w in (s, *s.winfo_children()):
            w.bind('<Button-1>', lambda e: self.show_log())
        hover_area(s, lambda inside: fade(self.log_link, COL['accent_hi'] if inside else COL['accent'],
                                          'foreground'))
        return s

    def footer(self):
        b = tk.Frame(self.root, bg=COL['bg'], padx=20, pady=12)
        self.btn_files = Button(b, 'Apply to game files', lambda: self.autopatch('apply'), 'accent',
                                tip=lambda: 'Close the game first.' if self.pid else
                                'Build and install the options now (about a minute).')
        self.btn_files.pack(side='right')
        self.btn_save = Button(b, 'Save for next launch', lambda: self.autopatch('set'),
                               tip=lambda: 'Remember the options; autopatch.bat applies them the next time the game '
                                           'starts.')
        self.btn_save.pack(side='right', padx=(0, 8))
        self.btn_live = Button(b, 'Apply live', self.request_live,
                               tip=lambda: 'Push fog and the GI preset into the running game now.' if self.pid else
                               'Needs the game running.')
        self.btn_live.pack(side='right', padx=(0, 8))
        Button(b, 'Vanilla graphics', self.vanilla,
               tip=lambda: 'Set the effect and fog sliders, particle caps, spark lifetime and GI back to vanilla. '
                           'Debris, push and light options stay.').pack(side='right', padx=(0, 8))
        self.bar = ProgressBar(b)
        self.bar.pack(side='left', fill='x', expand=True, padx=(0, 20))
        return b


    def say(self, msg):
        tag = log_tag(msg)
        self.log.configure(state='normal')
        self.log.insert('end', msg + '\n', tag)
        self.log.see('end')
        self.log.configure(state='disabled')
        lines = msg.strip().splitlines()
        self.last.configure(text=lines[-1] if lines else '',
                            fg={'error': COL['red'], 'ok': COL['green']}.get(tag, COL['dim']))
        if tag == 'error':
            self.show_log(True)

    def wheel(self, e):
        if self.nav.current is not None and not str(e.widget).startswith(str(self.drawer)):
            self.pages[self.nav.current].scroll(-round(e.delta / 120) or (-1 if e.delta > 0 else 1))

    def show_log(self, show=None):
        show = not self.log_open if show is None else show
        if show == self.log_open:
            return
        self.log_open = show
        self.log_link.configure(text='Hide log' if show else 'Show log')
        start, to = self.log_level, float(show)

        def step(t):
            self.log_level = start + (to - start) * t
            if self.log_level > 0.001:
                self.drawer.place(x=0, rely=1.0, relwidth=1.0, height=DRAWER_H, y=-round(DRAWER_H * self.log_level))
                self.drawer.lift()
            else:
                self.drawer.place_forget()
        animate(self.drawer, 'drawer', 260, step)
        self.log.see('end')

    def copy_launch_option(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(LAUNCH_OPTION)
        self.copy_btn.configure(text='Copied')
        self.root.after(1500, lambda: self.copy_btn.configure(text='Copy'))

    def switched_sliders(self, frame, row, var, text, sliders, opts):
        Switch(frame, var, text, command=self.toggled).grid(row=row, column=0, columnspan=3, sticky='w')
        widgets = []
        for r, (name, text, step, unit) in enumerate(sliders, start=row + 1):
            lo, hi = spv_inject.LIMITS[name]
            self.vars[name] = v = tk.DoubleVar(value=opts[name])
            text = label(frame, text, wrap=200)
            text.grid(row=r, column=0, sticky='w', padx=(46, 12), pady=2)
            s = Slider(frame, v, lo, hi, step, unit=unit)
            s.grid(row=r, column=1, columnspan=2, sticky='ew')
            widgets += [text, s]
        self.toggles.append((var, widgets))
        return widgets

    def options(self):
        on = lambda var: 'on' if var.get() else 'off'
        o = {name: round(self.vars[name].get(), 3) for name, *_ in SLIDERS}
        o.update(smoke_caps=on(self.caps), lights=on(self.lights), linger=int(self.linger.get()),
                 linger_all=on(self.linger_all), pushback=on(self.pushback), smoke_push=on(self.smoke_push),
                 smoke_push_own=on(self.smoke_push_own), smoke_collide=on(self.smoke_collide),
                 spark_life=round(self.vars['spark_life'].get(), 3), wave_reach=on(self.wave_reach))
        o.update({name: round(self.vars[name].get(), 3)
                  for name, *_ in PUSH_SLIDERS + SMOKE_PUSH_SLIDERS + COLLIDE_SLIDERS + VOLUME_SLIDERS + WAVE_SLIDERS})
        return o

    def toggled(self):
        for var, widgets in self.toggles:
            for w in widgets:
                if isinstance(w, tk.Label):
                    fade(w, COL['text'] if var.get() else COL['faint'], 'foreground')
                else:
                    w.set_enabled(var.get())

    def overlay_toggled(self):
        self.root.attributes('-topmost', self.overlay.get())
        self.root.attributes('-alpha', OVERLAY_ALPHA if self.overlay.get() else 1.0)

    def hotkey(self):
        user32 = ctypes.windll.user32
        shown = self.root.state() not in ('withdrawn', 'iconic')
        if shown and user32.GetForegroundWindow() == int(self.root.wm_frame(), 16):
            self.root.withdraw()
            return
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        if not self.overlay.get():
            self.root.after(200, lambda: self.root.attributes('-topmost', False))
        self.root.lift()
        self.root.focus_force()

    def refresh_buttons(self):
        running = bool(self.pid)
        self.btn_live.set_enabled(running and not self.busy)
        self.btn_files.set_enabled(not running and not self.busy)
        self.btn_save.set_enabled(not self.busy)

    def work(self, fn):
        self.busy = True
        self.refresh_buttons()

        def body():
            try:
                fn()
            except Exception as e:
                self.q.put(('log', f'error: {e}'))
                self.q.put(('log', traceback.format_exc().rstrip()))
            finally:
                self.q.put(('done',))
        threading.Thread(target=body, daemon=True).start()

    def pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == 'log':
                    self.say(msg[1])
                elif msg[0] == 'bar':
                    self.bar.go(*msg[1:])
                elif msg[0] == 'bar_done':
                    self.bar.finish(*msg[1:])
                elif msg[0] == 'install':
                    self.show_install(*msg[1:])
                elif msg[0] == 'gi':
                    self.gi_mode.set(msg[1])
                elif msg[0] == 'hotkey':
                    self.hotkey()
                elif msg[0] == 'done':
                    self.busy = False
                    self.bar.finish()
                    self.refresh_buttons()
                    if self.pending_gi:
                        self.pending_gi = False
                        self.request_gi_state()
                    elif self.pending_live:
                        self.pending_live = False
                        self.request_live()
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def show_install(self, build, text):
        if build != GAME_BUILD:
            text = (f'Game build {build} is not the one these tools were made for ({GAME_BUILD}); anything that no '
                    f'longer matches is skipped. {text}')
        self.install.configure(text=text, fg=COL['amber'] if build != GAME_BUILD else COL['dim'])

    def poll(self):
        pid = live.find_pid()
        if pid != self.pid:
            self.pid = pid
            self.status.configure(text=f'Enshrouded is running (pid {pid})' if pid else 'Enshrouded is not running')
            self.pulse()
            self.refresh_buttons()
            if pid:
                self.request_gi_state()
        self.root.after(POLL_MS, self.poll)

    def pulse(self, up=True):
        if not self.pid:
            stop(self.dot, 'pulse')
            self.dot.itemconfigure('dot', fill=COL['faint'])
            return
        a, b = (COL['green_dim'], COL['green']) if up else (COL['green'], COL['green_dim'])
        animate(self.dot, 'pulse', 900, lambda t: self.dot.itemconfigure('dot', fill=mix(a, b, t)),
                lambda: self.pulse(not up), frame_ms=40)


    def changed(self, name):
        if name != 'gi' and dict((n, a) for n, _, a, _ in SLIDERS)[name] != 'live':
            return
        if not (self.auto.get() and self.pid):
            return
        if self.live_timer:
            self.root.after_cancel(self.live_timer)
        self.live_timer = self.root.after(LIVE_DELAY_MS, self.request_live)

    def vanilla(self):
        for name, *_ in SLIDERS:
            self.vars[name].set(1.0)
        self.vars['spark_life'].set(1.0)
        for name, *_, mark in VOLUME_SLIDERS:
            self.vars[name].set(mark)
        self.caps.set(False)
        self.gi_mode.set('ultra')
        self.changed('fog')

    def request_gi_state(self):
        def task():
            if self.gi is None:
                self.load_gi()
            pid = live.find_pid()
            if self.gi and pid:
                with live.Process(pid) as p:
                    state = self.gi.state(p)
                if state != 'unknown':
                    self.q.put(('gi', state))
        if self.busy:
            self.pending_gi = True
            return
        self.work(task)

    def load_gi(self):
        try:
            self.gi = live.GI(GAME_DIR)
        except (LookupError, OSError, ValueError) as e:
            self.q.put(('log', f'GI preset: {e}'))
            self.gi = False

    def request_live(self):
        self.live_timer = None
        if self.busy:
            self.pending_live = True
            return
        mults = {n: round(self.vars[n].get(), 3) for n in gfxmods.FOG_OPTIONS}
        mode = self.gi_mode.get()
        self.work(lambda: self.live_task(mults, mode))

    def live_task(self, mults, gi_mode):
        log = lambda m: self.q.put(('log', m))
        pid = live.find_pid()
        if not pid:
            log('Enshrouded is not running')
            return
        if self.fog is None:
            self.fog = live.Fog(GAME_DIR)
        if self.gi is None:
            self.load_gi()
        with live.Process(pid) as p:
            for attempt in (0, 1):
                if attempt or not self.fog.located(p):
                    log('searching game memory for the fog data...')
                    n = self.fog.locate(p, progress=lambda x: self.q.put(
                        ('bar', x, x, 'Searching game memory for the fog data')))
                    log(f'found {n} copies of the fog data')
                values, copies = self.fog.apply(p, mults)
                if copies:
                    log(f'fog: {values} values written into {copies} copies; '
                        f'in memory now {self.fog.current(p)}')
                    break
            else:
                log('fog data not found in memory: live fog is unavailable (Save for next launch still works)')
            if self.gi:
                state = self.gi.state(p)
                if state == 'unknown':
                    log('GI preset: the table in memory is not the one in the exe; left alone')
                elif state != gi_mode:
                    self.gi.set(p, gi_mode)
                    log(f'GI: Ultra slot now holds the {gi_mode} preset. In the game, set Indirect Light to High '
                        'and back to Ultra to load it.')

    def autopatch(self, cmd):
        args = [python_exe(), '-I', os.path.join(HERE, 'autopatch.py'), cmd]
        for name, value in self.options().items():
            args += ['--' + name.replace('_', '-'), str(value)]
        apply = cmd == 'apply'

        def task():
            bar = lambda done, until, what, seconds: self.q.put(('bar', done, until, what, seconds))
            self.q.put(('log', '> autopatch ' + ' '.join(args[3:])))
            if apply:
                bar(0.0, 1 / APPLY_SECONDS, 'Checking the installed files', 1)
            else:
                bar(0.0, 0.9, 'Saving the options', 2)
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=autopatch.MOD_DIR,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            done, seen, t0 = 0.0, set(), time.monotonic()
            for raw in proc.stdout:
                line = raw.decode('utf-8', 'replace').rstrip()
                self.q.put(('log', line))
                stage = apply_stage(line, done, seen) if apply else None
                if stage:
                    done, until, what, seconds = stage
                    expected = done * APPLY_SECONDS
                    if expected > 2:
                        seconds *= min(max((time.monotonic() - t0) / expected, 0.4), 4.0)
                    bar(done, until, what, seconds)
            code = proc.wait()
            self.q.put(('log', f'autopatch {cmd} finished (exit code {code})'))
            self.q.put(('bar_done', code == 0, ('Installed in the game files' if apply else 'Saved for the next launch')
                        if code == 0 else f'{"Apply" if apply else "Save"} failed: see the log'))
            self.fog = None
            self.q.put(('install', *describe_install()))
        self.work(task)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
