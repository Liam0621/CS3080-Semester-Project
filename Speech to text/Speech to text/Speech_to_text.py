# Speech to text application
# UI made with Claude help
# everything else is me

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import os
import io
import wave

# Optional heavy deps — missing ones give clear UI feedback 
try:
    import numpy as np
    import sounddevice as sd
    SD_AVAILABLE = True
    SD_ERROR = None
except Exception as e:
    SD_AVAILABLE = False
    SD_ERROR = str(e)

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False


# BaseApp — Tk root + palette + ttk theme

class BaseApp(tk.Tk):
    BG       = "#0D1117"
    SURFACE  = "#161B22"
    SURFACE2 = "#21262D"
    ACCENT   = "#ff8c00"
    GREEN    = "#3FB950"
    DANGER   = "#F85149"
    TEXT     = "#ff8c00"
    TEXT_DIM = "#ff8c00"
    BORDER   = "#30363D"

    FONT_TITLE = ("Courier New", 17, "bold")
    FONT_BODY  = ("Courier New", 11)
    FONT_SMALL = ("Courier New", 9)
    FONT_MONO  = ("Courier New", 10)

    def __init__(self):
        super().__init__()
        self.configure(bg=self.BG)
        self._apply_theme()

    def _apply_theme(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("TFrame",      background=self.BG)
        s.configure("Card.TFrame", background=self.SURFACE)
        s.configure("TLabel",      background=self.BG,      foreground=self.TEXT,     font=self.FONT_BODY)
        s.configure("Dim.TLabel",  background=self.BG,      foreground=self.TEXT_DIM, font=self.FONT_SMALL)
        s.configure("Card.TLabel", background=self.SURFACE, foreground=self.TEXT,     font=self.FONT_BODY)

        def btn(name, bg, fg, hover):
            s.configure(name, background=bg, foreground=fg,
                        font=("Courier New", 10, "bold"),
                        padding=(14, 8), relief="flat", borderwidth=0)
            s.map(name, background=[("active", hover), ("disabled", self.SURFACE2)],
                        foreground=[("disabled", self.TEXT_DIM)])

        btn("Accent.TButton", self.ACCENT,   "#000000", "#ff8c00")
        btn("Danger.TButton", self.DANGER,   "#ffffff", "#FF6B6B")
        btn("Ghost.TButton",  self.SURFACE2, self.TEXT, self.BORDER)

        s.configure("TCombobox",
                    fieldbackground=self.SURFACE2, background=self.SURFACE2,
                    foreground=self.TEXT, selectbackground=self.ACCENT,
                    arrowcolor=self.ACCENT, font=self.FONT_BODY)
        s.map("TCombobox", fieldbackground=[("readonly", self.SURFACE2)])

        s.configure("Accent.Horizontal.TProgressbar",
                    troughcolor=self.SURFACE2, background=self.ACCENT, thickness=5)



# SpeechApp — inherits BaseApp
class SpeechApp(BaseApp):
    """
    Speech-to-Text GUI app.

    Inherits: BaseApp  (Tk root + theme)

    Mic recording: sounddevice.rec() → numpy array → in-memory WAV → SpeechRecognition
    File import:   sr.AudioFile → SpeechRecognition
    """

    APP_TITLE       = "◈  SPEECH → TEXT"
    VERSION         = "v2.1"
    MIN_W, MIN_H    = 780, 620
    SAMPLE_RATE     = 16_000
    CHANNELS        = 1
    MAX_SECS        = 60

    def __init__(self):
        super().__init__()
        self._recording     = False
        self._stop_event    = threading.Event()
        self._recognizer    = sr.Recognizer() if SR_AVAILABLE else None
        self._q: queue.Queue[dict] = queue.Queue()
        self._pulse_id      = None
        self._selected_file: str | None = None

        self.title(self.APP_TITLE)
        self.minsize(self.MIN_W, self.MIN_H)
        self.resizable(True, True)
        self.geometry(f"{self.MIN_W}x{self.MIN_H}")

        self._build_ui()
        self._refresh_dep_banner()
        self._poll()

    # Builds UI framework
    def _build_ui(self):
        # Header 
        hdr = tk.Frame(self, bg=self.BG)
        hdr.pack(fill="x", padx=20, pady=(18, 0))

        tk.Label(hdr, text=self.APP_TITLE,
                 font=self.FONT_TITLE, bg=self.BG, fg=self.ACCENT).pack(side="left")
        tk.Label(hdr, text=self.VERSION,
                 font=self.FONT_SMALL, bg=self.BG, fg=self.TEXT_DIM).pack(side="left", padx=(8,0), pady=(5,0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=20, pady=(10, 0))

        # Dependency banner to let user know what dependencies are needed
        self._dep_banner = tk.Label(self, text="", font=self.FONT_SMALL,
                                    bg=self.SURFACE2, fg=self.TEXT_DIM,
                                    anchor="w", padx=14, pady=5)
        self._dep_banner.pack(fill="x", padx=20, pady=(8, 0))

        # Settings row
        cfg = tk.Frame(self, bg=self.BG)
        cfg.pack(fill="x", padx=20, pady=(12, 0))

        def lbl(text):
            tk.Label(cfg, text=text, bg=self.BG, fg=self.TEXT_DIM,
                     font=self.FONT_SMALL).pack(side="left")

        lbl("Engine:")
        self._engine_var = tk.StringVar(value="google")
        ttk.Combobox(cfg, textvariable=self._engine_var,
                     values=["google", "sphinx"], state="readonly",
                     width=12).pack(side="left", padx=(5, 20))

        lbl("Language:")
        self._lang_var = tk.StringVar(value="en-US")
        ttk.Combobox(cfg, textvariable=self._lang_var,
                     values=["en-US","en-GB","es-ES","fr-FR","de-DE","zh-CN","ja-JP"],
                     state="readonly", width=9).pack(side="left", padx=(5, 20))

        lbl("Max duration (s):")
        self._dur_var = tk.IntVar(value=10)
        tk.Spinbox(cfg, from_=2, to=self.MAX_SECS,
                   textvariable=self._dur_var, width=5,
                   bg=self.SURFACE2, fg=self.TEXT,
                   buttonbackground=self.SURFACE2,
                   highlightthickness=0, relief="flat",
                   font=self.FONT_SMALL).pack(side="left", padx=(5, 0))

        # Source cards
        cards = tk.Frame(self, bg=self.BG)
        cards.pack(fill="x", padx=20, pady=14)
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)

        self._build_mic_card(self._card(cards, 0))
        self._build_file_card(self._card(cards, 1))

        # Status bar 
        bar = tk.Frame(self, bg=self.SURFACE2)
        bar.pack(fill="x", padx=20)
        self._dot = tk.Label(bar, text="●", font=("Courier New", 10),
                             bg=self.SURFACE2, fg=self.TEXT_DIM)
        self._dot.pack(side="left", padx=(10, 4), pady=5)
        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(bar, textvariable=self._status_var, font=self.FONT_SMALL,
                 bg=self.SURFACE2, fg=self.TEXT_DIM).pack(side="left")

        # Transcript 
        out = tk.Frame(self, bg=self.BG)
        out.pack(fill="both", expand=True, padx=20, pady=(12, 0))

        th = tk.Frame(out, bg=self.BG)
        th.pack(fill="x")
        tk.Label(th, text="TRANSCRIPT", font=("Courier New", 9, "bold"),
                 bg=self.BG, fg=self.TEXT_DIM).pack(side="left")
        ttk.Button(th, text="Copy",  style="Ghost.TButton", command=self._copy).pack(side="right", padx=(4,0))
        ttk.Button(th, text="Clear", style="Ghost.TButton", command=self._clear).pack(side="right")

        self._transcript = scrolledtext.ScrolledText(
            out, font=self.FONT_MONO, bg=self.SURFACE, fg=self.TEXT,
            insertbackground=self.ACCENT, selectbackground=self.ACCENT,
            relief="flat", bd=0, wrap="word", padx=14, pady=12)
        self._transcript.pack(fill="both", expand=True, pady=(8, 0))

        tk.Frame(self, bg=self.BG, height=14).pack()

    def _card(self, parent, col):
        c = tk.Frame(parent, bg=self.SURFACE,
                     highlightthickness=1, highlightbackground=self.BORDER)
        c.grid(row=0, column=col, sticky="nsew", padx=(0,8) if col==0 else (8,0))
        return c

    def _build_mic_card(self, card):
        tk.Label(card, text="🎙  MICROPHONE",
                 font=("Courier New", 10, "bold"),
                 bg=self.SURFACE, fg=self.TEXT).pack(anchor="w", padx=14, pady=(14,3))
        tk.Label(card,
                 text="Press Record, speak, then press Stop.\nTranscription runs automatically.",
                 font=self.FONT_SMALL, bg=self.SURFACE, fg=self.TEXT_DIM,
                 justify="left").pack(anchor="w", padx=14)

        row = tk.Frame(card, bg=self.SURFACE)
        row.pack(anchor="w", padx=14, pady=14)

        self._rec_btn = ttk.Button(row, text="⏺  Record",
                                   style="Accent.TButton",
                                   command=self._toggle_rec)
        self._rec_btn.pack(side="left", padx=(0, 10))

        self._pulse_lbl = tk.Label(row, text="", font=("Courier New", 16),
                                   bg=self.SURFACE, fg=self.GREEN)
        self._pulse_lbl.pack(side="left")

    def _build_file_card(self, card):
        tk.Label(card, text="📂  AUDIO FILE",
                 font=("Courier New", 10, "bold"),
                 bg=self.SURFACE, fg=self.TEXT).pack(anchor="w", padx=14, pady=(14,3))
        tk.Label(card, text="Load a .wav, .aiff, or .flac file to transcribe.",
                 font=self.FONT_SMALL, bg=self.SURFACE, fg=self.TEXT_DIM,
                 justify="left").pack(anchor="w", padx=14)

        self._file_lbl = tk.Label(card, text="No file selected.",
                                  font=self.FONT_SMALL, bg=self.SURFACE,
                                  fg=self.TEXT_DIM, wraplength=260, justify="left")
        self._file_lbl.pack(anchor="w", padx=14, pady=(5,0))

        row = tk.Frame(card, bg=self.SURFACE)
        row.pack(anchor="w", padx=14, pady=14)

        ttk.Button(row, text="Browse…", style="Ghost.TButton",
                   command=self._browse).pack(side="left", padx=(0, 8))
        self._conv_btn = ttk.Button(row, text="Convert ▶",
                                    style="Accent.TButton",
                                    command=self._convert_file)
        self._conv_btn.pack(side="left")

    # Dependency banner (always visible strip under the title) 
    def _refresh_dep_banner(self):
        parts = []
        if SR_AVAILABLE:
            parts.append(("speech_recognition ✓", self.GREEN))
        else:
            parts.append(("speech_recognition ✗  →  pip install SpeechRecognition", self.DANGER))

        if SD_AVAILABLE:
            parts.append(("sounddevice ✓", self.GREEN))
        else:
            msg = f"sounddevice ✗  →  pip install sounddevice numpy  ({SD_ERROR})"
            parts.append((msg, self.DANGER))

        all_ok = SR_AVAILABLE and SD_AVAILABLE

        # Join into one string with separators
        text = "   |   ".join(t for t, _ in parts)
        color = self.GREEN if all_ok else self.DANGER
        prefix = "  ✓ All dependencies loaded" if all_ok else "  ⚠ "
        self._dep_banner.config(text=prefix + ("" if all_ok else text), fg=color,
                                bg=self.SURFACE2 if all_ok else "#1a0a0a")

        # Disable mic if sounddevice not available
        if not SD_AVAILABLE:
            self._rec_btn.state(["disabled"])

    #  Mic recording
    def _toggle_rec(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not SD_AVAILABLE:
            messagebox.showerror("Missing", "pip install sounddevice numpy")
            return
        if not SR_AVAILABLE:
            messagebox.showerror("Missing", "pip install SpeechRecognition")
            return

        self._recording = True
        self._stop_event.clear()
        self._rec_btn.config(text="⏹  Stop", style="Danger.TButton")
        dur = self._dur_var.get()
        self._set_status(f"Recording… up to {dur}s — press Stop when done")
        self._animate_pulse()
        threading.Thread(target=self._mic_worker, args=(dur,), daemon=True).start()

    def _stop_recording(self):
        self._stop_event.set()   # signals the worker thread to stop early

    def _mic_worker(self, duration: int):
        """
        Record audio using sounddevice.rec() which is simple and reliable.
        We poll _stop_event every 100 ms to support early stopping.
        """
        try:
            import sounddevice as sd
            import numpy as np

            total_frames = duration * self.SAMPLE_RATE
            recording = sd.rec(total_frames,
                               samplerate=self.SAMPLE_RATE,
                               channels=self.CHANNELS,
                               dtype="int16",
                               blocking=False)

            # Poll until done or user pressed Stop
            elapsed_frames = 0
            chunk = int(self.SAMPLE_RATE * 0.1)   # check every 100 ms
            while elapsed_frames < total_frames:
                if self._stop_event.wait(timeout=0.1):
                    sd.stop()
                    break
                elapsed_frames += chunk

            sd.wait()   # make sure stream is flushed

            # Trim silence
            captured = recording[:elapsed_frames] if elapsed_frames < total_frames else recording

            if captured is None or len(captured) == 0:
                self._q.put({"t": "error", "msg": "No audio captured."})
                return

            self._q.put({"t": "status", "msg": "Transcribing…"})
            audio_data = self._numpy_to_sr(captured)
            text = self._recognise(audio_data)
            if text:
                self._q.put({"t": "result", "msg": text})

        except Exception as e:
            self._q.put({"t": "error", "msg": f"Recording error: {e}"})
        finally:
            self._q.put({"t": "done_rec"})

    def _numpy_to_sr(self, arr) -> "sr.AudioData":
        """Convert a numpy int16 array to sr.AudioData via in-memory WAV."""
        import numpy as np
        if arr.ndim > 1:
            arr = arr[:, 0]           # take first channel if stereo
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)        # int16 = 2 bytes
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(arr.tobytes())
        buf.seek(0)
        with sr.AudioFile(buf) as src:
            return self._recognizer.record(src)

    # File transcription 
    def _browse(self):
        p = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[("Audio files", "*.wav *.aiff *.flac"), ("All", "*.*")])
        if p:
            self._selected_file = p
            self._file_lbl.config(text=os.path.basename(p), fg=self.TEXT)

    def _convert_file(self):
        if not self._selected_file:
            messagebox.showwarning("No file", "Please select an audio file first.")
            return
        if not SR_AVAILABLE:
            messagebox.showerror("Missing", "pip install SpeechRecognition")
            return
        self._conv_btn.state(["disabled"])
        self._set_status(f"Loading: {os.path.basename(self._selected_file)}…")
        threading.Thread(target=self._file_worker,
                         args=(self._selected_file,), daemon=True).start()

    def _file_worker(self, path: str):
        try:
            with sr.AudioFile(path) as src:
                audio = self._recognizer.record(src)
            self._q.put({"t": "status", "msg": "Transcribing file…"})
            text = self._recognise(audio)
            if text:
                self._q.put({"t": "result", "msg": text})
        except Exception as e:
            self._q.put({"t": "error", "msg": str(e)})
        finally:
            self._q.put({"t": "done_file"})

    # Recognition 
    def _recognise(self, audio: "sr.AudioData") -> "str | None":
        try:
            if self._engine_var.get() == "sphinx":
                return self._recognizer.recognize_sphinx(audio)
            return self._recognizer.recognize_google(audio, language=self._lang_var.get())
        except sr.UnknownValueError:
            self._q.put({"t": "error", "msg": "Speech not recognised. Try speaking more clearly."})
        except sr.RequestError as e:
            self._q.put({"t": "error", "msg": f"API request failed: {e}"})
        except Exception as e:
            self._q.put({"t": "error", "msg": str(e)})
        return None

    # Queue polling
    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                t = msg["t"]
                if t == "status":
                    self._set_status(msg["msg"])
                elif t == "result":
                    self._append(msg["msg"])
                    self._set_status("Done ✓")
                elif t == "error":
                    self._set_status(msg["msg"], error=True)
                    messagebox.showerror("Error", msg["msg"])
                elif t == "done_rec":
                    self._recording = False
                    self._rec_btn.config(text="⏺  Record", style="Accent.TButton")
                    self._rec_btn.state(["!disabled"])
                    if self._pulse_id:
                        self.after_cancel(self._pulse_id)
                        self._pulse_id = None
                    self._pulse_lbl.config(text="")
                elif t == "done_file":
                    self._conv_btn.state(["!disabled"])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # Pulse animation 
    def _animate_pulse(self, on: bool = True):
        if not self._recording:
            self._pulse_lbl.config(text="")
            return
        self._pulse_lbl.config(text="●" if on else " ")
        self._pulse_id = self.after(500, self._animate_pulse, not on)

    # Transcript helpers
    def _append(self, text: str):
        if self._transcript.get("1.0", "end-1c"):
            self._transcript.insert("end", "\n\n")
        self._transcript.insert("end", text)
        self._transcript.see("end")

    def _copy(self):
        t = self._transcript.get("1.0", "end-1c").strip()
        if t:
            self.clipboard_clear(); self.clipboard_append(t)
            self._set_status("Copied to clipboard.")
        else:
            self._set_status("Nothing to copy.")

    def _clear(self):
        self._transcript.delete("1.0", "end")
        self._set_status("Transcript cleared.")

    # Status 
    def _set_status(self, text: str, error: bool = False):
        self._status_var.set(text)
        self._dot.config(fg=self.DANGER if error else self.TEXT_DIM)


# main
def main():
    app = SpeechApp()
    app.mainloop()

if __name__ == "__main__":
    main()
