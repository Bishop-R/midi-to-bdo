#!/usr/bin/env python3
"""GUI wrapper for midi2bdo — MIDI to BDO music converter."""

import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

from midi2bdo import (parse_midi, midi_to_bdo, extract_owner_id,
                      gm_program_name, gm_to_bdo_instrument,
                      BDO_INSTRUMENT_NAMES, make_track_settings, Note)

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPT_DIR = BUNDLE_DIR
DEFAULT_OUTDIR = os.path.join(SCRIPT_DIR, 'converted')
DEFAULT_MIDI_DIR = os.path.join(SCRIPT_DIR, 'midi')
os.makedirs(DEFAULT_MIDI_DIR, exist_ok=True)

# Theme setup
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme(os.path.join(BUNDLE_DIR, 'bdo_theme.json'))

# MIDI note number → name
_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_name(midi_note):
    return f"{_NOTE_NAMES[midi_note % 12]}{midi_note // 12 - 1}"

# Native file dialog
_HAS_KDIALOG = shutil.which('kdialog') is not None

def _native_open(title='Open', initialdir=None, filetypes=None):
    """Open a file dialog using kdialog (KDE-native, dark-themed) with
    tkinter fallback."""
    if _HAS_KDIALOG:
        cmd = ['kdialog', '--getopenfilename']
        cmd.append(initialdir or os.getcwd())
        if filetypes:
            # Build kdialog filter: "*.mid *.midi|MIDI files"
            parts = []
            for label, patterns in filetypes:
                if patterns == '*.*' or patterns == '*':
                    continue
                parts.append(f"{patterns}|{label}")
            if parts:
                cmd.append('\n'.join(parts))
        cmd.extend(['--title', title])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
            return ''
        except Exception:
            pass
    return filedialog.askopenfilename(title=title, initialdir=initialdir,
                                      filetypes=filetypes or [])


# BDO Color Palette
BDO = {
    'bg_dark':     '#161618',
    'bg':          '#1d1d1f',
    'bg_light':    '#242427',
    'surface':     '#313239',
    'surface_alt': '#343436',
    'border':      '#444348',
    'border_light':'#595a62',
    'gold':        '#d8ad70',
    'gold_light':  '#ddc39e',
    'gold_bright': '#ffedd4',
    'gold_dark':   '#b09046',
    'gold_scroll': '#cca471',
    'text':        '#e0e0e0',
    'text_dim':    '#9a9a9e',
    'text_gold':   '#d4bc98',
    'error':       '#e05555',
}


class ScrollableComboBox(ctk.CTkFrame):
    """Combobox with a scrollable dropdown for long value lists.

    Uses a raw Canvas+Scrollbar dropdown instead of CTkScrollableFrame to
    avoid conflicting bind_all('<MouseWheel>') handlers that cause dual-
    scrolling with the main window.
    """

    _MAX_VISIBLE = 10
    _ROW_HEIGHT = 28
    _open_instance = None  # class-level: the instance whose dropdown is open

    def __init__(self, master, values=None, width=230, state='readonly', **kw):
        super().__init__(master, fg_color=BDO['surface'], corner_radius=6,
                         border_width=2, border_color=BDO['border'], width=width)
        self._values = values or []
        self._current = ''
        self._dropdown = None
        self._dd_canvas = None
        self._click_bind_id = None
        self._configure_bind_id = None

        self._label = ctk.CTkLabel(self, text='', text_color=BDO['text'],
                                   anchor='w', padx=8)
        self._label.pack(side='left', fill='x', expand=True)

        self._arrow = ctk.CTkLabel(self, text='\u25bc', width=24,
                                   text_color=BDO['gold_light'])
        self._arrow.pack(side='right', padx=(0, 4))

        for w in (self, self._label, self._arrow):
            w.bind('<Button-1>', self._toggle)

    def get(self):
        return self._current

    def set(self, value):
        self._current = value
        self._label.configure(text=value)

    def _toggle(self, event=None):
        if self._dropdown and self._dropdown.winfo_exists():
            self._close()
        else:
            self._open()

    def _open(self):
        # Close any other open dropdown first
        if ScrollableComboBox._open_instance is not None:
            ScrollableComboBox._open_instance._close()
        self._close()

        dd = tk.Toplevel(self)
        dd.withdraw()
        dd.overrideredirect(True)
        if sys.platform.startswith('win'):
            dd.wm_attributes('-topmost', True)
        dd.configure(bg=BDO['surface'])
        self._dropdown = dd
        ScrollableComboBox._open_instance = self

        # DPI scaling factor (customtkinter tracks this)
        try:
            scale = ctk.ScalingTracker.get_widget_scaling(self)
        except Exception:
            scale = 1.0

        n = len(self._values)
        visible = min(n, self._MAX_VISIBLE)
        row_h = int(self._ROW_HEIGHT * scale)
        h = visible * row_h + 4
        w = self.winfo_width()
        font_size = max(9, int(9 * scale))

        # Raw canvas + scrollbar
        canvas = tk.Canvas(dd, bg=BDO['surface'], highlightthickness=0,
                           width=w - 14, height=h)
        scrollbar = tk.Scrollbar(dd, orient='vertical', command=canvas.yview,
                                 bg=BDO['surface'], troughcolor=BDO['bg'],
                                 activebackground=BDO['gold_scroll'],
                                 highlightthickness=0, bd=0)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        self._dd_canvas = canvas

        inner = tk.Frame(canvas, bg=BDO['surface'])
        canvas.create_window((0, 0), window=inner, anchor='nw')

        for val in self._values:
            btn = tk.Label(inner, text=val, bg=BDO['surface'], fg=BDO['text'],
                           anchor='w', padx=8, pady=3, cursor='hand2',
                           font=('TkDefaultFont', font_size))
            btn.pack(fill='x')
            btn.bind('<Enter>', lambda e, b=btn: b.configure(bg=BDO['gold_dark']))
            btn.bind('<Leave>', lambda e, b=btn: b.configure(bg=BDO['surface']))
            btn.bind('<Button-1>', lambda e, v=val: self._select(v))

        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox('all'))

        # Position below the widget
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        dd.geometry(f'{w}x{h}+{x}+{y}')
        dd.deiconify()

        # Close on click-outside (after a short delay so the opening click doesn't trigger it)
        self.after(100, self._bind_click_outside)
        dd.bind('<Escape>', lambda e: self._close())
        # Close when main window moves or resizes
        self._configure_bind_id = self.winfo_toplevel().bind(
            '<Configure>', lambda e: self._close(), add='+')

    def _bind_click_outside(self):
        self._click_bind_id = self.winfo_toplevel().bind_all(
            '<Button-1>', self._on_click_outside, add='+')

    def _on_click_outside(self, event):
        """Close dropdown if click is outside it."""
        if self._dropdown is None or not self._dropdown.winfo_exists():
            self._unbind_click()
            return
        # Check if click is inside the dropdown window
        try:
            w = event.widget
            if str(w).startswith(str(self._dropdown)):
                return
        except Exception:
            pass
        # Check if click is on the combo itself (toggle handles that)
        try:
            if w is self or w is self._label or w is self._arrow:
                return
        except Exception:
            pass
        self._close()

    def _unbind_click(self):
        if self._click_bind_id is not None:
            try:
                self.winfo_toplevel().unbind_all('<Button-1>')
            except Exception:
                pass
            self._click_bind_id = None

    def _close(self):
        self._unbind_click()
        if self._configure_bind_id is not None:
            try:
                self.winfo_toplevel().unbind('<Configure>', self._configure_bind_id)
            except Exception:
                pass
            self._configure_bind_id = None
        self._dd_canvas = None
        if ScrollableComboBox._open_instance is self:
            ScrollableComboBox._open_instance = None
        if self._dropdown and self._dropdown.winfo_exists():
            self._dropdown.destroy()
        self._dropdown = None

    def _select(self, value):
        self.set(value)
        self._close()


def _make_section(parent, title, collapsed=False):
    """Create a labeled section: gold header label + bordered frame.
    If collapsed=True, the frame starts hidden and the header toggles it."""
    container = ctk.CTkFrame(parent, fg_color='transparent')
    frame = ctk.CTkFrame(container, border_width=1, border_color=BDO['border'])

    arrow = '\u25b6' if collapsed else '\u25bc'
    header = ctk.CTkLabel(container, text=f'{arrow} {title}',
                          text_color=BDO['gold_light'],
                          font=ctk.CTkFont(weight='bold'), cursor='hand2')
    header.pack(anchor='w', padx=4)

    if not collapsed:
        frame.pack(fill='x', expand=True, padx=2, pady=(0, 2))

    def _toggle(event=None):
        if frame.winfo_manager():
            frame.pack_forget()
            header.configure(text=f'\u25b6 {title}')
        else:
            frame.pack(fill='x', expand=True, padx=2, pady=(0, 2))
            header.configure(text=f'\u25bc {title}')

    header.bind('<Button-1>', _toggle)
    return container, frame


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MIDI to BDO Converter")
        self.resizable(True, True)

        # State
        self.midi_path = tk.StringVar()
        self.output_name = tk.StringVar()
        self.char_name = tk.StringVar(value='')
        self.bpm_override = tk.StringVar()
        self.transpose = tk.StringVar(value='0')
        self.vel_mode = tk.StringVar(value='layered')
        self.step_base = tk.StringVar(value='100')
        self.step_step = tk.StringVar(value='5')
        self.rescale_min = tk.StringVar(value='80')
        self.rescale_max = tk.StringVar(value='127')
        self.floor_val = tk.StringVar(value='100')
        self.apply_sustain = tk.BooleanVar(value=True)
        self.flatten_tempo = tk.BooleanVar(value=False)
        self.reverb = tk.IntVar(value=0)
        self.delay = tk.IntVar(value=0)
        self.chorus_fb = tk.IntVar(value=0)
        self.chorus_depth = tk.IntVar(value=0)
        self.chorus_freq = tk.IntVar(value=0)
        self.status_text = tk.StringVar(value='Ready')
        self._owner_id = 0
        self._tempo_changes = 0
        self._channel_groups = []
        self._inst_combos = []

        self._build_ui()

        # Size window to fit content
        self.update_idletasks()
        content_w = self._scroll_frame.winfo_reqwidth() + 40  # padding + scrollbar
        content_h = self._scroll_frame.winfo_reqheight() + 80  # bottom bar + padding
        max_h = int(self.winfo_screenheight() * 0.85)
        self.geometry(f'{max(content_w, 520)}x{min(content_h, max_h)}')
        self.minsize(520, 400)

    # UI construction

    def _build_ui(self):
        pad = dict(padx=6, pady=3)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Outer container: scrollable top + fixed bottom
        outer = ctk.CTkFrame(self, fg_color='transparent')
        outer.grid(sticky='nsew', padx=10, pady=(10, 0))
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        # Scrollable area
        scroll = ctk.CTkScrollableFrame(outer, fg_color=BDO['bg_light'])
        scroll.grid(row=0, column=0, sticky='nsew')
        self._scroll_frame = scroll

        # Unified scroll handler
        def _scroll_target():
            inst = ScrollableComboBox._open_instance
            if inst is not None and inst._dd_canvas is not None:
                return inst._dd_canvas
            return scroll._parent_canvas

        def _on_mousewheel(event):
            target = _scroll_target()
            if not event.delta:
                return
            # Windows delta is ±120 (or multiples), Linux is ±1
            if sys.platform.startswith('win'):
                units = -int(event.delta / 40)  # ±3 per tick
            elif sys.platform == 'darwin':
                units = -event.delta
            else:
                units = -3 if event.delta > 0 else 3
            target.yview_scroll(units, 'units')

        # Replace CTkScrollableFrame's own MouseWheel handler
        scroll.bind_all('<MouseWheel>', _on_mousewheel)

        # Linux X11 scroll events (Button-4/5 don't exist on Windows)
        if not sys.platform.startswith('win') and sys.platform != 'darwin':
            def _on_button4(event):
                _scroll_target().yview_scroll(-3, 'units')
            def _on_button5(event):
                _scroll_target().yview_scroll(3, 'units')
            scroll.bind_all('<Button-4>', _on_button4)
            scroll.bind_all('<Button-5>', _on_button5)

        frame = scroll
        row = 0

        # File selection
        ctk.CTkLabel(frame, text="Input MIDI:", text_color=BDO['gold_light']).grid(
            row=row, column=0, sticky='e', **pad)
        ctk.CTkEntry(frame, textvariable=self.midi_path, width=350).grid(
            row=row, column=1, columnspan=2, sticky='we', **pad)
        ctk.CTkButton(frame, text="Browse\u2026", command=self._browse, width=80).grid(
            row=row, column=3, **pad)
        frame.columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(frame, text="Output name:", text_color=BDO['gold_light']).grid(
            row=row, column=0, sticky='e', **pad)
        ctk.CTkEntry(frame, textvariable=self.output_name, width=350).grid(
            row=row, column=1, columnspan=2, sticky='we', **pad)
        row += 1

        # Settings
        settings_container, sep = _make_section(frame, "Settings")
        settings_container.grid(row=row, column=0, columnspan=4, sticky='we', pady=(8, 4), padx=4)
        row += 1

        r = 0
        ctk.CTkLabel(sep, text="Character name:").grid(row=r, column=0, sticky='e', **pad)
        ctk.CTkEntry(sep, textvariable=self.char_name, width=160).grid(row=r, column=1, sticky='w', **pad)
        ctk.CTkButton(sep, text="Load ID from BDO file\u2026",
                      command=self._load_owner_id, width=180).grid(row=r, column=2, sticky='w', **pad)
        r += 1
        ctk.CTkLabel(sep, text="BPM override:").grid(row=r, column=0, sticky='e', **pad)
        ctk.CTkEntry(sep, textvariable=self.bpm_override, width=64).grid(row=r, column=1, sticky='w', **pad)
        ctk.CTkLabel(sep, text="(blank = use MIDI tempo)",
                     text_color=BDO['text_dim']).grid(row=r, column=2, sticky='w', **pad)
        r += 1
        ctk.CTkLabel(sep, text="Transpose:").grid(row=r, column=0, sticky='e', **pad)
        ctk.CTkEntry(sep, textvariable=self.transpose, width=64).grid(row=r, column=1, sticky='w', **pad)
        ctk.CTkLabel(sep, text="semitones",
                     text_color=BDO['text_dim']).grid(row=r, column=2, sticky='w', **pad)

        # Velocity
        vel_container, vel = _make_section(frame, "Velocity")
        vel_container.grid(row=row, column=0, columnspan=4, sticky='we', pady=(4, 4), padx=4)
        row += 1

        modes = [('Layered', 'layered'), ('Stepped', 'stepped'), ('Rescale', 'rescale'), ('Floor', 'floor'), ('Off', 'off')]
        mode_frame = ctk.CTkFrame(vel, fg_color='transparent')
        mode_frame.grid(row=0, column=0, columnspan=4, sticky='w', **pad)
        ctk.CTkLabel(mode_frame, text="Mode:").pack(side='left', padx=(0, 6))
        for text, val in modes:
            ctk.CTkRadioButton(mode_frame, text=text, variable=self.vel_mode, value=val,
                               command=self._update_vel_fields).pack(side='left', padx=4)

        # Velocity param grid — all rows share columns so entries align
        self._step_base_label = ctk.CTkLabel(vel, text="Base:")
        self._step_base_label.grid(row=1, column=0, sticky='e', padx=(16, 2), pady=2)
        self._step_base_entry = ctk.CTkEntry(vel, textvariable=self.step_base, width=48)
        self._step_base_entry.grid(row=1, column=1, sticky='w', padx=2, pady=2)
        self._step_step_label = ctk.CTkLabel(vel, text="Step:")
        self._step_step_label.grid(row=1, column=2, sticky='e', padx=(4, 2), pady=2)
        self._step_step_entry = ctk.CTkEntry(vel, textvariable=self.step_step, width=48)
        self._step_step_entry.grid(row=1, column=3, sticky='w', padx=2, pady=2)

        self._rescale_min_label = ctk.CTkLabel(vel, text="Min:")
        self._rescale_min_label.grid(row=2, column=0, sticky='e', padx=(16, 2), pady=2)
        self._rescale_min_entry = ctk.CTkEntry(vel, textvariable=self.rescale_min, width=48)
        self._rescale_min_entry.grid(row=2, column=1, sticky='w', padx=2, pady=2)
        self._rescale_max_label = ctk.CTkLabel(vel, text="Max:")
        self._rescale_max_label.grid(row=2, column=2, sticky='e', padx=(4, 2), pady=2)
        self._rescale_max_entry = ctk.CTkEntry(vel, textvariable=self.rescale_max, width=48)
        self._rescale_max_entry.grid(row=2, column=3, sticky='w', padx=2, pady=2)

        self._floor_label = ctk.CTkLabel(vel, text="Min vel:")
        self._floor_label.grid(row=3, column=0, sticky='e', padx=(16, 2), pady=2)
        self._floor_entry = ctk.CTkEntry(vel, textvariable=self.floor_val, width=48)
        self._floor_entry.grid(row=3, column=1, sticky='w', padx=2, pady=2)

        self._update_vel_fields()

        # Options
        opt_container, opt = _make_section(frame, "Options")
        opt_container.grid(row=row, column=0, columnspan=4, sticky='we', pady=(4, 4), padx=4)
        row += 1
        ctk.CTkCheckBox(opt, text="Apply sustain pedal", variable=self.apply_sustain,
                        onvalue=True, offvalue=False,
                        command=self._on_option_toggle).grid(sticky='w', padx=6, pady=3)
        ctk.CTkCheckBox(opt, text="Flatten tempo (use highest BPM throughout)",
                        variable=self.flatten_tempo, onvalue=True, offvalue=False,
                        command=self._on_option_toggle).grid(sticky='w', padx=6, pady=3)

        # Effector
        eff_container, eff = _make_section(frame, "Effector", collapsed=True)
        eff_container.grid(row=row, column=0, columnspan=4, sticky='we', pady=(4, 4), padx=4)
        row += 1

        def _make_slider(parent, r, label, var):
            ctk.CTkLabel(parent, text=label).grid(row=r, column=0, sticky='e', **pad)
            slider = ctk.CTkSlider(parent, from_=0, to=127, variable=var,
                                   orientation='horizontal', number_of_steps=127)
            slider.grid(row=r, column=1, sticky='we', **pad)
            val_label = ctk.CTkLabel(parent, text='0', width=32,
                                     text_color=BDO['gold_light'])
            val_label.grid(row=r, column=2, sticky='w', **pad)
            var.trace_add('write', lambda *_: val_label.configure(text=str(var.get())))
            return slider

        eff.columnconfigure(1, weight=1)
        _make_slider(eff, 0, "Reverb:", self.reverb)
        _make_slider(eff, 1, "Delay:", self.delay)
        _make_slider(eff, 2, "Chorus FB:", self.chorus_fb)
        _make_slider(eff, 3, "Chorus Depth:", self.chorus_depth)
        _make_slider(eff, 4, "Chorus Freq:", self.chorus_freq)

        # MIDI info
        info_container, info = _make_section(frame, "MIDI Info")
        info_container.grid(row=row, column=0, columnspan=4, sticky='we', pady=(4, 4), padx=4)
        row += 1
        self._info_label = ctk.CTkLabel(info, text="(no file loaded)",
                                        text_color=BDO['text_dim'])
        self._info_label.grid(sticky='w', padx=6, pady=3)

        # Instruments
        inst_container, self._instrument_frame = _make_section(frame, "Instruments")
        inst_container.grid(row=row, column=0, columnspan=4, sticky='we', pady=(4, 4), padx=4)
        self._inst_container = inst_container
        row += 1
        self._no_inst_label = ctk.CTkLabel(self._instrument_frame,
                                           text="(load a MIDI file)",
                                           text_color=BDO['text_dim'])
        self._no_inst_label.grid(sticky='w', padx=6, pady=3)

        # Fixed bottom bar (outside scrollable area)
        bottom = ctk.CTkFrame(outer, fg_color='transparent')
        bottom.grid(row=1, column=0, sticky='we', pady=(6, 10))

        # Convert button — gold accent 
        ctk.CTkButton(bottom, text="Convert", command=self._convert,
                      fg_color=BDO['gold_dark'], hover_color=BDO['gold'],
                      text_color=BDO['bg_dark'],
                      font=ctk.CTkFont(size=14, weight='bold'),
                      height=36).pack(fill='x', padx=40, pady=(0, 4))

        # Status bar
        status_frame = ctk.CTkFrame(bottom, fg_color=BDO['bg'], corner_radius=4)
        status_frame.pack(fill='x', padx=4)
        ctk.CTkLabel(status_frame, textvariable=self.status_text,
                     text_color=BDO['text_gold']).pack(anchor='w', padx=6, pady=2)

    # Helpers

    def _update_vel_fields(self):
        mode = self.vel_mode.get()
        active_color = BDO['text']
        dim_color = BDO['text_dim']

        # Stepped
        is_stepped = mode == 'stepped'
        self._step_base_label.configure(text_color=active_color if is_stepped else dim_color)
        self._step_step_label.configure(text_color=active_color if is_stepped else dim_color)
        self._step_base_entry.configure(state='normal' if is_stepped else 'disabled')
        self._step_step_entry.configure(state='normal' if is_stepped else 'disabled')

        # Rescale
        is_rescale = mode == 'rescale'
        self._rescale_min_label.configure(text_color=active_color if is_rescale else dim_color)
        self._rescale_max_label.configure(text_color=active_color if is_rescale else dim_color)
        self._rescale_min_entry.configure(state='normal' if is_rescale else 'disabled')
        self._rescale_max_entry.configure(state='normal' if is_rescale else 'disabled')

        # Floor
        is_floor = mode == 'floor'
        self._floor_label.configure(text_color=active_color if is_floor else dim_color)
        self._floor_entry.configure(state='normal' if is_floor else 'disabled')

    def _load_owner_id(self):
        path = _native_open(
            title="Select a BDO file you saved in-game",
            filetypes=[("BDO music files", "*"), ("All files", "*.*")])
        if not path:
            return
        try:
            owner_id, char_name = extract_owner_id(path)
            if owner_id == 0:
                self.status_text.set("Warning: that file has no owner ID")
                return
            self._owner_id = owner_id
            if char_name:
                self.char_name.set(char_name)
            self.status_text.set(f"Owner ID loaded: 0x{owner_id:08x} ({char_name})")
        except Exception as exc:
            self.status_text.set(f"Error reading BDO file: {exc}")

    def _on_option_toggle(self):
        path = self.midi_path.get()
        if path and os.path.isfile(path):
            self._load_midi_info(path)

    def _browse(self):
        path = _native_open(
            title="Select MIDI file",
            initialdir=DEFAULT_MIDI_DIR,
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")])
        if not path:
            return
        self.midi_path.set(path)
        basename = os.path.splitext(os.path.basename(path))[0]
        self.output_name.set(basename)
        self._load_midi_info(path)

        # Auto-enable flatten for multi-tempo MIDIs on file load only
        if self._tempo_changes > 1:
            self.flatten_tempo.set(True)

    def _load_midi_info(self, path):
        try:
            bpm, tsig, channel_groups, tempo_changes = parse_midi(
                path, apply_sustain=self.apply_sustain.get(),
                flatten_tempo=self.flatten_tempo.get())

            self._tempo_changes = tempo_changes

            self._channel_groups = channel_groups
            all_notes = [n for notes, _, _ in channel_groups for n in notes]
            total_notes = len(all_notes)

            if all_notes:
                pitches = [n.pitch for n in all_notes]
                lo, hi = note_name(min(pitches)), note_name(max(pitches))
                last_end = max(n.start + n.dur for n in all_notes)
                mins, secs = divmod(int(last_end / 1000), 60)
                dur_str = f"{mins}m {secs:02d}s"
                pitch_str = f"{lo}\u2013{hi}"
            else:
                dur_str = "0m 00s"
                pitch_str = "\u2013"

            bpm_str = str(bpm)
            if tempo_changes > 1:
                bpm_str += f" ({tempo_changes} changes)"

            self._info_label.configure(
                text=(f"Channels: {len(channel_groups)}  |  Notes: {total_notes}  |  "
                      f"BPM: {bpm_str}  |  {tsig}/4\n"
                      f"Duration: {dur_str}  |  Pitch range: {pitch_str}"),
                text_color=BDO['text'])

            # Populate instrument assignment panel
            self._populate_instruments()
            self.update_idletasks()

            # Grow window to fit content if needed, but never shrink
            needed_h = self.winfo_reqheight()
            max_h = int(self.winfo_screenheight() * 0.85)
            cur_h = self.winfo_height()
            new_h = min(max(needed_h, cur_h), max_h)
            if new_h != cur_h:
                self.geometry(f"{self.winfo_width()}x{new_h}")

            self.status_text.set("File loaded")
        except Exception as exc:
            self._channel_groups = []
            self._inst_combos = []
            self._info_label.configure(text=f"Error: {exc}",
                                       text_color=BDO['error'])
            self.status_text.set("Failed to load MIDI")

    def _populate_instruments(self):
        """Rebuild the instrument assignment panel from self._channel_groups."""
        for w in self._instrument_frame.winfo_children():
            w.destroy()
        self._inst_combos = []

        if not self._channel_groups:
            ctk.CTkLabel(self._instrument_frame,
                         text="(no instruments detected)",
                         text_color=BDO['text_dim']).grid(sticky='w', padx=6, pady=3)
            return

        bdo_names = list(BDO_INSTRUMENT_NAMES.values())
        bdo_id_by_name = {v: k for k, v in BDO_INSTRUMENT_NAMES.items()}

        for i, (notes, gm_prog, is_perc) in enumerate(self._channel_groups):
            if is_perc:
                label_text = f"Drums (ch 10) ({len(notes)} notes)"
            else:
                label_text = f"{gm_program_name(gm_prog)} ({len(notes)} notes)"

            ctk.CTkLabel(self._instrument_frame, text=label_text).grid(
                row=i, column=0, sticky='w', padx=(6, 8), pady=2)
            ctk.CTkLabel(self._instrument_frame, text="\u2192",
                         text_color=BDO['gold_light']).grid(
                row=i, column=1, padx=4, pady=2)

            combo = ScrollableComboBox(self._instrument_frame, values=bdo_names,
                                       width=230)
            combo.grid(row=i, column=2, sticky='w', padx=(4, 6), pady=2)

            # Set default to auto-mapped instrument
            default_id = gm_to_bdo_instrument(gm_prog, is_perc)
            default_name = BDO_INSTRUMENT_NAMES.get(default_id, bdo_names[0])
            combo.set(default_name)

            self._inst_combos.append(combo)

    def _convert(self):
        path = self.midi_path.get()
        if not path or not os.path.isfile(path):
            self.status_text.set("Error: select a valid MIDI file")
            return

        out_name = self.output_name.get().strip()
        if not out_name:
            self.status_text.set("Error: output name is empty")
            return

        # Parse settings
        try:
            semitones = int(self.transpose.get()) if self.transpose.get().strip() else 0
        except ValueError:
            self.status_text.set("Error: transpose must be an integer")
            return

        bpm_str = self.bpm_override.get().strip()
        bpm_override = None
        if bpm_str:
            try:
                bpm_override = int(bpm_str)
            except ValueError:
                self.status_text.set("Error: BPM must be an integer")
                return

        vel_range = None
        vel_floor_val = None
        vel_step_val = None
        mode = self.vel_mode.get()
        try:
            if mode == 'rescale':
                vel_range = (int(self.rescale_min.get()), int(self.rescale_max.get()))
            elif mode == 'floor':
                vel_floor_val = int(self.floor_val.get())
            elif mode == 'stepped':
                vel_step_val = (int(self.step_base.get()), int(self.step_step.get()))
        except ValueError:
            self.status_text.set("Error: velocity parameters must be integers")
            return

        char_name = self.char_name.get().strip() or 'MIDI'

        # Build instrument_map from combos
        instrument_map = None
        if self._channel_groups and self._inst_combos:
            name_to_id = {v: k for k, v in BDO_INSTRUMENT_NAMES.items()}
            instrument_map = {}
            for i, (notes, gm_prog, is_perc) in enumerate(self._channel_groups):
                selected_name = self._inst_combos[i].get()
                if selected_name in name_to_id:
                    instrument_map[(gm_prog, is_perc)] = name_to_id[selected_name]

        # Convert
        self.status_text.set("Converting\u2026")
        self.update_idletasks()

        try:
            chorus = None
            fb = self.chorus_fb.get()
            depth = self.chorus_depth.get()
            freq = self.chorus_freq.get()
            if fb or depth or freq:
                chorus = (fb, depth, freq)

            bdo_data, summary = midi_to_bdo(
                path, bpm_override=bpm_override, char_name=char_name,
                vel_range=vel_range, vel_floor=vel_floor_val, vel_step=vel_step_val,
                vel_layered=(mode == 'layered'),
                transpose=semitones, apply_sustain=self.apply_sustain.get(),
                flatten_tempo=self.flatten_tempo.get(),
                owner_id=self._owner_id,
                instrument_map=instrument_map,
                reverb=self.reverb.get(), delay=self.delay.get(),
                chorus=chorus)

            os.makedirs(DEFAULT_OUTDIR, exist_ok=True)
            out_path = os.path.join(DEFAULT_OUTDIR, out_name)
            with open(out_path, 'wb') as f:
                f.write(bdo_data)

            self.status_text.set(
                f"Saved: {out_path}  ({len(bdo_data)} bytes, "
                f"{summary['tracks']} tracks, {summary['total_notes']} notes)")
        except Exception as exc:
            self.status_text.set(f"Error: {exc}")


if __name__ == '__main__':
    App().mainloop()
