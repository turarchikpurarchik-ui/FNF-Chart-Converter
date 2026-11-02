import json
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

APP_VERSION = "1.0.0-alpha"
PSYCH_TARGET = "Psych Engine Mobile 1.0.4"

def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def detect_format(data):
    if isinstance(data, dict) and isinstance(data.get("song"), dict):
        return "psych"
    if isinstance(data, dict) and "notes" in data and "scrollSpeed" in data:
        return "vslice"
    return "unknown"

def vslice_to_psych(chart, metadata, difficulty):
    warnings = []
    notes_by_diff = chart.get("notes", {})
    if not isinstance(notes_by_diff, dict) or not notes_by_diff:
        raise ValueError("В V-Slice chart нет списка notes по сложностям.")
    if difficulty not in notes_by_diff:
        difficulty = next(iter(notes_by_diff))
        warnings.append(f"Сложность не найдена; использована «{difficulty}».")

    source_notes = notes_by_diff.get(difficulty, [])
    time_changes = (metadata or {}).get("timeChanges", [])
    if not time_changes:
        time_changes = [{"t": 0, "b": 0, "bpm": 100, "bt": [4,4,4,4]}]
        warnings.append("В metadata нет timeChanges: использован временный BPM 100.")

    time_changes = sorted(time_changes, key=lambda x: float(x.get("t", 0)))
    first_bpm = float(time_changes[0].get("bpm", 100) or 100)
    if first_bpm <= 0:
        first_bpm = 100
        warnings.append("Некорректный BPM; использован 100.")

    # Psych sections are 16 steps long. Build section start times across BPM changes.
    max_time = max([float(n.get("t", 0)) + float(n.get("l", 0)) for n in source_notes] + [0])
    max_time = max(max_time, 1)
    boundaries = [0.0]
    bpm_at = []
    current_time = 0.0
    current_bpm = first_bpm
    change_idx = 1
    section_index = 0
    while current_time <= max_time + 60000:
        section_duration = 16 * (60000.0 / current_bpm / 4.0)
        next_time = current_time + section_duration
        while change_idx < len(time_changes) and float(time_changes[change_idx].get("t", 0)) < next_time:
            change_time = float(time_changes[change_idx].get("t", 0))
            if change_time > current_time:
                # Keep a section boundary at the tempo change to avoid applying one BPM across it.
                boundaries.append(change_time)
                current_time = change_time
            current_bpm = float(time_changes[change_idx].get("bpm", current_bpm) or current_bpm)
            change_idx += 1
            section_duration = 16 * (60000.0 / current_bpm / 4.0)
            next_time = current_time + section_duration
        boundaries.append(next_time)
        current_time = next_time
        bpm_at.append(current_bpm)
        section_index += 1
        if section_index > 10000:
            raise ValueError("Слишком длинная или некорректная временная шкала.")
    boundaries = sorted(set(boundaries))
    sections = []
    for i in range(len(boundaries)-1):
        start, end = boundaries[i], boundaries[i+1]
        bpm = first_bpm
        for tc in time_changes:
            if float(tc.get("t", 0)) <= start:
                bpm = float(tc.get("bpm", bpm) or bpm)
            else:
                break
        sections.append({
            "sectionNotes": [],
            "lengthInSteps": max(1, round((end-start) / (60000.0 / bpm / 4.0))),
            "mustHitSection": False,
            "gfSection": False,
            "bpm": bpm,
            "changeBPM": (i == 0 or any(abs(float(tc.get("t",0))-start) < 1 for tc in time_changes)),
            "altAnim": False
        })

    if not sections:
        sections = [{"sectionNotes": [], "lengthInSteps": 16, "mustHitSection": False,
                     "gfSection": False, "bpm": first_bpm, "changeBPM": True, "altAnim": False}]

    for n in source_notes:
        try:
            t = float(n["t"])
            d = int(n["d"])
        except (KeyError, TypeError, ValueError):
            warnings.append("Пропущена нота с некорректными t или d.")
            continue
        if d < 0 or d > 7:
            warnings.append(f"Нота на {t:.1f} ms имеет неизвестную дорожку {d}; она пропущена.")
            continue
        idx = 0
        while idx < len(boundaries)-2 and t >= boundaries[idx+1]:
            idx += 1
        idx = min(idx, len(sections)-1)
        sustain = float(n.get("l", 0) or 0)
        note_type = str(n.get("k", "") or "")
        sections[idx]["sectionNotes"].append([t, d, sustain, note_type])
    for section in sections:
        section["sectionNotes"].sort(key=lambda x: x[0])

    play = (metadata or {}).get("playData", {})
    chars = play.get("characters", {})
    song_name = (metadata or {}).get("songName") or "Converted Song"
    scroll = chart.get("scrollSpeed", {})
    speed = scroll.get(difficulty, 1.0) if isinstance(scroll, dict) else 1.0
    if chart.get("events"):
        warnings.append(f"{len(chart.get('events', []))} V-Slice events не преобразованы: форматы событий различаются.")
    special_types = sorted({str(n.get("k")) for n in source_notes if n.get("k")})
    if special_types:
        warnings.append("Типы нот перенесены как текстовые noteType; поведение нестандартных типов в Psych может отличаться: " + ", ".join(special_types))

    return {
        "song": {
            "song": song_name,
            "notes": sections,
            "bpm": first_bpm,
            "needsVoices": True,
            "speed": speed,
            "player1": chars.get("player", "bf"),
            "player2": chars.get("opponent", "dad"),
            "gfVersion": chars.get("girlfriend") or "gf",
            "stage": play.get("stage", "stage"),
            "arrowSkin": "",
            "splashSkin": "",
            "validScore": True,
            "events": []
        }
    }, warnings

def psych_to_vslice(data, difficulty):
    warnings = []
    song = data.get("song", {})
    sections = song.get("notes", [])
    notes = []
    for section in sections:
        for entry in section.get("sectionNotes", []):
            if not isinstance(entry, list) or len(entry) < 3:
                warnings.append("Пропущена некорректная Psych-нота.")
                continue
            try:
                t, d, sustain = float(entry[0]), int(entry[1]), float(entry[2])
            except (TypeError, ValueError):
                warnings.append("Пропущена нота с некорректными значениями.")
                continue
            note = {"t": t, "d": d}
            if sustain:
                note["l"] = sustain
            note_type = entry[3] if len(entry) > 3 else ""
            if note_type:
                note["k"] = str(note_type)
            notes.append(note)
    notes.sort(key=lambda x: x["t"])
    if song.get("events"):
        warnings.append("Psych events не перенесены: требуется отдельное сопоставление типов событий.")
    if any(s.get("changeBPM") for s in sections):
        warnings.append("Изменения BPM в секциях Psych не могут быть точно восстановлены без исходной временной карты V-Slice.")
    result = {
        "version": "2.0.0",
        "scrollSpeed": {difficulty: song.get("speed", 1.0)},
        "events": [],
        "notes": {difficulty: notes},
        "generatedBy": "FNF Chart Converter " + APP_VERSION
    }
    meta = {
        "version": "2.2.4",
        "songName": song.get("song", "Converted Song"),
        "artist": "Unknown",
        "charter": "Unknown",
        "offsets": {},
        "playData": {
            "difficulties": [difficulty],
            "characters": {
                "player": song.get("player1", "bf"),
                "girlfriend": song.get("gfVersion", "gf"),
                "opponent": song.get("player2", "dad"),
                "opponentVocals": [song.get("player2", "dad")],
                "playerVocals": [song.get("player1", "bf")]
            },
            "stage": song.get("stage", "stage"),
            "noteStyle": "funkin",
            "ratings": {difficulty: 0},
            "album": "volume1"
        },
        "generatedBy": "FNF Chart Converter " + APP_VERSION,
        "timeChanges": [{"t": 0, "b": 0, "bpm": song.get("bpm", 100), "bt": [4,4,4,4]}]
    }
    warnings.append("В Psych-файле не всегда достаточно данных для восстановления оригинальных V-Slice metadata (artist, charter, album, точные BPM changes).")
    return result, meta, warnings

class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FNF Chart Converter")
        self.root.geometry("720x520")
        self.root.minsize(620, 450)
        self.input_path = None
        self.meta_path = None
        self.detected = None

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        outer = ttk.Frame(root, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="FNF Chart Converter", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(outer, text=f"Alpha {APP_VERSION}  •  Target: {PSYCH_TARGET}", foreground="#777").pack(anchor="w", pady=(2,14))

        filebox = ttk.LabelFrame(outer, text="Файлы", padding=12)
        filebox.pack(fill="x")
        self.file_label = ttk.Label(filebox, text="Файл чарта не выбран", wraplength=620)
        self.file_label.pack(anchor="w")
        ttk.Button(filebox, text="Выбрать chart JSON", command=self.pick_chart).pack(anchor="w", pady=(8,4))
        self.meta_label = ttk.Label(filebox, text="Metadata: не выбрана (необязательно)")
        self.meta_label.pack(anchor="w")
        ttk.Button(filebox, text="Выбрать metadata JSON (для V-Slice)", command=self.pick_meta).pack(anchor="w", pady=(6,0))

        opts = ttk.LabelFrame(outer, text="Настройки", padding=12)
        opts.pack(fill="x", pady=12)
        row = ttk.Frame(opts); row.pack(fill="x")
        ttk.Label(row, text="Сложность:").pack(side="left")
        self.diff = tk.StringVar(value="normal")
        ttk.Entry(row, textvariable=self.diff, width=18).pack(side="left", padx=8)
        self.direction = tk.StringVar(value="auto")
        ttk.Label(row, text="Направление:").pack(side="left", padx=(16,4))
        ttk.Combobox(row, textvariable=self.direction, state="readonly", width=24,
                     values=["auto", "V-Slice → Psych 1.0.4", "Psych 1.0.4 → V-Slice"]).pack(side="left")

        buttons = ttk.Frame(outer); buttons.pack(fill="x")
        ttk.Button(buttons, text="Проверить файл", command=self.check).pack(side="left")
        ttk.Button(buttons, text="Конвертировать", command=self.convert).pack(side="left", padx=8)

        logbox = ttk.LabelFrame(outer, text="Результат и предупреждения", padding=8)
        logbox.pack(fill="both", expand=True, pady=(12,0))
        self.log = tk.Text(logbox, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

        self.add_log("Выбери JSON-файл чарта. Для V-Slice также желательно указать metadata.json.")
        self.add_log("Это альфа-версия: события и некоторые специальные механики могут не переноситься.")

    def add_log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def pick_chart(self):
        p = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if p:
            self.input_path = Path(p)
            self.file_label.config(text=str(self.input_path))
            try:
                self.detected = detect_format(read_json(p))
                self.add_log(f"Выбран файл: {self.input_path.name} (формат: {self.detected})")
            except Exception as e:
                self.detected = "unknown"
                self.add_log(f"Ошибка чтения: {e}")

    def pick_meta(self):
        p = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if p:
            self.meta_path = Path(p)
            self.meta_label.config(text=f"Metadata: {self.meta_path.name}")
            self.add_log(f"Metadata выбрана: {self.meta_path.name}")

    def check(self):
        if not self.input_path:
            messagebox.showwarning("Нет файла", "Сначала выбери JSON-файл чарта.")
            return
        try:
            data = read_json(self.input_path)
            fmt = detect_format(data)
            if fmt == "psych":
                song = data["song"]
                count = sum(len(s.get("sectionNotes", [])) for s in song.get("notes", []))
                self.add_log(f"Проверка OK: Psych chart, песня «{song.get('song','?')}», секций {len(song.get('notes',[]))}, нот {count}.")
            elif fmt == "vslice":
                diff = self.diff.get().strip() or next(iter(data.get("notes", {})), "normal")
                arr = data.get("notes", {}).get(diff, [])
                self.add_log(f"Проверка OK: V-Slice chart, версия {data.get('version')}, сложность {diff}, нот {len(arr)}, событий {len(data.get('events',[]))}.")
                if not self.meta_path:
                    self.add_log("Предупреждение: metadata не выбрана; имена персонажей и BPM будут частично заменены значениями по умолчанию.")
            else:
                self.add_log("Неизвестная структура JSON. Нужен Psych chart с объектом song или V-Slice chart с notes и scrollSpeed.")
        except Exception as e:
            messagebox.showerror("Ошибка проверки", str(e))
            self.add_log(f"Ошибка: {e}")

    def convert(self):
        if not self.input_path:
            messagebox.showwarning("Нет файла", "Сначала выбери JSON-файл чарта.")
            return
        try:
            chart = read_json(self.input_path)
            fmt = detect_format(chart)
            direction = self.direction.get()
            difficulty = self.diff.get().strip() or "normal"
            if direction == "auto":
                direction = "V-Slice → Psych 1.0.4" if fmt == "vslice" else "Psych 1.0.4 → V-Slice"
            if direction.startswith("V-Slice"):
                if fmt != "vslice":
                    raise ValueError("Выбранное направление требует V-Slice chart.")
                metadata = read_json(self.meta_path) if self.meta_path else {}
                output, warnings = vslice_to_psych(chart, metadata, difficulty)
                ext = ".json"
                default = self.input_path.stem + "_psych104.json"
                outpath = filedialog.asksaveasfilename(initialfile=default, defaultextension=ext, filetypes=[("JSON", "*.json")])
                if not outpath: return
                write_json(outpath, output)
                self.add_log(f"Готово: {outpath}")
            else:
                if fmt != "psych":
                    raise ValueError("Выбранное направление требует Psych chart.")
                output, meta, warnings = psych_to_vslice(chart, difficulty)
                outdir = filedialog.askdirectory(title="Выбери папку для V-Slice chart и metadata")
                if not outdir: return
                outdir = Path(outdir)
                write_json(outdir / (self.input_path.stem + "-chart.json"), output)
                write_json(outdir / (self.input_path.stem + "-metadata.json"), meta)
                self.add_log(f"Готово: файлы сохранены в {outdir}")
            for w in warnings:
                self.add_log("⚠ " + w)
            if not warnings:
                self.add_log("Предупреждений нет.")
            messagebox.showinfo("Конвертация завершена", "Файлы сохранены. Проверь предупреждения в окне программы.")
        except Exception as e:
            messagebox.showerror("Ошибка конвертации", str(e))
            self.add_log(f"Ошибка конвертации: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()
