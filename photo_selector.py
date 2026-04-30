#!/usr/bin/env python3
"""
Photo File Selector
Match and copy raw photo files based on client selections.
Supports: folder of images, .zip, .txt, .csv, .xls/.xlsx, .doc/.docx
"""

import sys
import re
import json
import shutil
import zipfile
import threading
import queue
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, List, Set
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# ---------------------------------------------------------------------------
# Persistent config  (~/.photo_selector.json)
# ---------------------------------------------------------------------------

CONFIG_FILE = Path.home() / '.photo_selector.json'

def load_config() -> dict:
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data: dict):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

# Optional dependencies — app works without them, warns when needed
try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def extract_number(filename: str, prefix: str, num_digits: int) -> Optional[str]:
    """
    Extract the sequence number from a filename or bare token.

    Handles:
      "C86A0042-HDR.jpg"  prefix="C86A" digits=4  →  "0042"
      "C86A0042.cr2"      prefix="C86A" digits=4  →  "0042"
      "155"               prefix="C86A" digits=4  →  "0155"  (bare number, zero-padded)
      "155, 320, 603"     — each token handled individually by the caller
    """
    stem = Path(filename).stem
    # Strip HDR suffix before extracting the number (case-insensitive)
    stem = re.sub(r'[-_]HDR$', '', stem, flags=re.IGNORECASE)

    # Bare number (e.g. "155" or "0042" typed in a list / pasted message)
    # → zero-pad to the expected digit width so it matches filenames on disk
    if re.match(r'^\d+$', stem):
        return stem.zfill(num_digits)

    if prefix:
        match = re.match(rf'^{re.escape(prefix)}(\d+)', stem, re.IGNORECASE)
        if match:
            return match.group(1)
    else:
        match = re.search(rf'(\d{{{num_digits},}})', stem)
        if match:
            return match.group(1)[:num_digits]
    return None


def parse_text_content(text: str, prefix: str, num_digits: int) -> Set[str]:
    """Extract sequence numbers from arbitrary text (pasted message, file contents)."""
    numbers: Set[str] = set()
    for token in re.split(r'[\s,;|\t\r\n]+', text):
        token = token.strip()
        if token:
            num = extract_number(token, prefix, num_digits)
            if num:
                numbers.add(num)
    return numbers


def group_key(filename: str) -> str:
    """
    Return the display group key for a file.
    HDR files get their own group so they can be controlled separately.
    e.g.  "C86A0001.cr2"      → ".cr2"
          "C86A0001-HDR.dng"  → ".dng (HDR)"
    """
    stem = Path(filename).stem
    ext  = Path(filename).suffix.lower()
    if re.search(r'[-_]HDR$', stem, re.IGNORECASE):
        return f'{ext} (HDR)'
    return ext


def parse_selection(path_str: str, prefix: str, num_digits: int) -> Set[str]:
    """Parse a selection source (folder / zip / txt / xls / doc) and return sequence numbers."""
    path = Path(path_str)
    numbers: Set[str] = set()

    def _scan_name(name: str):
        num = extract_number(name, prefix, num_digits)
        if num:
            numbers.add(num)

    if path.is_dir():
        for f in path.iterdir():
            if f.is_file():
                _scan_name(f.name)

    elif path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as zf:
            for entry in zf.namelist():
                _scan_name(Path(entry).name)

    elif path.suffix.lower() in ('.txt', '.csv'):
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            numbers |= parse_text_content(fh.read(), prefix, num_digits)

    elif path.suffix.lower() in ('.xls', '.xlsx'):
        if not HAS_OPENPYXL:
            raise ImportError(
                "The openpyxl library is required to read Excel files.\n"
                "Install it with:  pip install openpyxl"
            )
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell is not None:
                        numbers |= parse_text_content(str(cell), prefix, num_digits)
        wb.close()

    elif path.suffix.lower() in ('.doc', '.docx'):
        if not HAS_DOCX:
            raise ImportError(
                "The python-docx library is required to read Word files.\n"
                "Install it with:  pip install python-docx"
            )
        doc = DocxDocument(str(path))
        for para in doc.paragraphs:
            numbers |= parse_text_content(para.text, prefix, num_digits)

    return numbers


def scan_source(
    source_dir: str,
    selected_numbers: Set[str],
    prefix: str,
    num_digits: int
) -> tuple:
    """Walk source_dir, return (matched_dict, total_scanned, matched_numbers).
    HDR files get their own key ('.dng (HDR)') separate from '.dng'.
    """
    result: Dict[str, List[Path]] = defaultdict(list)
    matched_numbers: Set[str] = set()
    total_scanned = 0
    for f in Path(source_dir).rglob('*'):
        if f.is_file():
            total_scanned += 1
            num = extract_number(f.name, prefix, num_digits)
            if num and num in selected_numbers:
                result[group_key(f.name)].append(f)
                matched_numbers.add(num)
    return result, total_scanned, matched_numbers


# ---------------------------------------------------------------------------
# Background copy thread
# ---------------------------------------------------------------------------

class CopyWorker(threading.Thread):
    def __init__(self, files: List[Path], dest: str, q: queue.Queue,
                 mode: str = 'copy', on_conflict: str = 'overwrite'):
        super().__init__(daemon=True)
        self.files = files
        self.dest = Path(dest)
        self.q = q
        self.mode = mode                 # 'copy' or 'move'
        self.on_conflict = on_conflict   # 'overwrite' or 'skip'

    def run(self):
        errors = []
        skipped = 0
        total = len(self.files)
        for i, f in enumerate(self.files):
            self.q.put(('progress', i + 1, total, f.name))
            target = self.dest / f.name
            if self.on_conflict == 'skip' and target.exists():
                skipped += 1
                continue
            try:
                if self.mode == 'move':
                    shutil.move(str(f), target)
                else:
                    shutil.copy2(f, target)
            except Exception as e:
                errors.append(f"{f.name}: {e}")
        self.q.put(('done', total - len(errors) - skipped, errors, skipped))


# ---------------------------------------------------------------------------
# Scrollable frame widget
# ---------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind('<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self._win_id = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.bind('<Configure>',
            lambda e: self.canvas.itemconfig(self._win_id, width=e.width))
        self.canvas.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        # Mouse wheel scrolling
        self.canvas.bind('<Enter>', self._bind_wheel)
        self.canvas.bind('<Leave>', self._unbind_wheel)

    def _bind_wheel(self, _):
        self.canvas.bind_all('<MouseWheel>', self._on_wheel)

    def _unbind_wheel(self, _):
        self.canvas.unbind_all('<MouseWheel>')

    def _on_wheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), 'units')


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Photo File Selector')
        self.geometry('820x740')
        self.minsize(720, 620)

        self.file_groups: List[Dict] = []   # [{ext, checkboxes: [(BoolVar, Path)]}]
        self.copy_queue: queue.Queue = queue.Queue()
        self._transfer_mode: str = 'copy'
        self._last_report: str = 'Run Match Files first.'

        self._build_ui()

        # Restore saved prefix / digits
        cfg = load_config()
        self.prefix_var.set(cfg.get('prefix', ''))
        self.digits_var.set(cfg.get('digits', 4))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        PAD = {'padx': 8, 'pady': 4}

        # ── Client Selection ──────────────────────────────────────────
        sel_box = ttk.LabelFrame(self, text='Client Selection')
        sel_box.pack(fill='x', **PAD)

        # Row 1: folder / file picker
        row1 = ttk.Frame(sel_box)
        row1.pack(fill='x', padx=4, pady=(4, 2))
        self.sel_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.sel_var).pack(
            side='left', fill='x', expand=True)
        ttk.Button(row1, text='Folder…',
                   command=self._browse_sel_folder).pack(side='left', padx=2)
        ttk.Button(row1, text='File…',
                   command=self._browse_sel_file).pack(side='left', padx=(2, 0))

        # Row 2: paste area
        ttk.Label(sel_box, text='Or paste a message / number list:',
                  foreground='#555').pack(anchor='w', padx=6, pady=(4, 1))
        paste_row = ttk.Frame(sel_box)
        paste_row.pack(fill='x', padx=4, pady=(0, 4))
        self.paste_text = tk.Text(paste_row, height=3, wrap='word',
                                  font=('Segoe UI', 9))
        paste_vsb = ttk.Scrollbar(paste_row, orient='vertical',
                                  command=self.paste_text.yview)
        self.paste_text.configure(yscrollcommand=paste_vsb.set)
        paste_vsb.pack(side='right', fill='y')
        self.paste_text.pack(side='left', fill='x', expand=True)
        ttk.Button(sel_box, text='Clear paste',
                   command=lambda: self.paste_text.delete('1.0', 'end')
                   ).pack(anchor='e', padx=4, pady=(0, 4))

        # ── Source Folder ─────────────────────────────────────────────
        src_box = ttk.LabelFrame(self, text='Source Folder  (raw / original files)')
        src_box.pack(fill='x', **PAD)

        self.src_var = tk.StringVar()
        ttk.Entry(src_box, textvariable=self.src_var).pack(
            side='left', fill='x', expand=True, padx=4, pady=4)
        ttk.Button(src_box, text='Browse…',
                   command=self._browse_source).pack(side='left', padx=(2, 4), pady=4)

        # ── Filename Settings + Match ─────────────────────────────────
        cfg_box = ttk.LabelFrame(self, text='Filename Settings')
        cfg_box.pack(fill='x', **PAD)

        ttk.Label(cfg_box, text='Prefix:').pack(side='left', padx=(6, 2), pady=6)
        self.prefix_var = tk.StringVar()
        prefix_entry = ttk.Entry(cfg_box, textvariable=self.prefix_var, width=14)
        prefix_entry.pack(side='left', padx=2, pady=6)
        prefix_entry.insert(0, '')
        self._tooltip(prefix_entry,
            "Constant text before the sequence number.\n"
            "e.g. 'C86A' for files like C86A0042-HDR.jpg\n"
            "Leave blank to auto-detect.")

        ttk.Label(cfg_box, text='  Sequence digits:').pack(side='left', padx=(12, 2), pady=6)
        self.digits_var = tk.IntVar(value=4)
        ttk.Spinbox(cfg_box, from_=1, to=8, textvariable=self.digits_var,
                    width=4).pack(side='left', padx=2, pady=6)

        self.match_btn = ttk.Button(cfg_box, text='  Match Files  ',
                                    command=self._match_files)
        self.match_btn.pack(side='right', padx=8, pady=6)

        # ── Results ───────────────────────────────────────────────────
        res_box = ttk.LabelFrame(self, text='Matched Files')
        res_box.pack(fill='both', expand=True, **PAD)

        self.scroll = ScrollableFrame(res_box)
        self.scroll.pack(fill='both', expand=True, padx=2, pady=2)

        self.placeholder = ttk.Label(
            self.scroll.inner,
            text="Run  'Match Files'  to see results here.",
            foreground='gray')
        self.placeholder.pack(pady=30)

        # ── Destination Folder ────────────────────────────────────────
        dest_box = ttk.LabelFrame(self, text='Destination Folder')
        dest_box.pack(fill='x', **PAD)

        self.dest_var = tk.StringVar()
        ttk.Entry(dest_box, textvariable=self.dest_var).pack(
            side='left', fill='x', expand=True, padx=4, pady=4)
        ttk.Button(dest_box, text='Browse…',
                   command=self._browse_dest).pack(side='left', padx=2, pady=4)
        sub_btn = ttk.Button(dest_box, text='+ Subfolder from source',
                             command=self._make_source_subfolder)
        sub_btn.pack(side='left', padx=(2, 4), pady=4)
        self._tooltip(sub_btn,
            "Create a subfolder inside Destination named after\n"
            "the Source folder, and set it as the destination.")

        # ── Progress + Copy / Move buttons ───────────────────────────
        bottom = ttk.Frame(self)
        bottom.pack(fill='x', padx=8, pady=(0, 6))

        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            bottom, variable=self.progress_var, maximum=100)
        # Hidden initially — shown when transfer starts

        self.move_btn = ttk.Button(bottom, text='Move Selected Files',
                                   command=self._move_files)
        self.move_btn.pack(side='right', padx=(4, 0))

        self.copy_btn = ttk.Button(bottom, text='Copy Selected Files',
                                   command=self._copy_files)
        self.copy_btn.pack(side='right')

        # ── Status bar ────────────────────────────────────────────────
        self.status_var = tk.StringVar(value='Ready')
        ttk.Label(self, textvariable=self.status_var,
                  relief='sunken', anchor='w').pack(fill='x', side='bottom')

    # ------------------------------------------------------------------
    # Simple tooltip
    # ------------------------------------------------------------------

    def _tooltip(self, widget, text: str):
        tip_win = [None]

        def show(e):
            if tip_win[0]:
                return
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip_win[0] = tw = tk.Toplevel(self)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f'+{x}+{y}')
            ttk.Label(tw, text=text, background='#ffffe0',
                      relief='solid', borderwidth=1,
                      padding=4).pack()

        def hide(e):
            if tip_win[0]:
                tip_win[0].destroy()
                tip_win[0] = None

        widget.bind('<Enter>', show)
        widget.bind('<Leave>', hide)

    # ------------------------------------------------------------------
    # Browse callbacks
    # ------------------------------------------------------------------

    def _browse_sel_folder(self):
        path = filedialog.askdirectory(title='Select Folder of Client-Selected Images')
        if path:
            self.sel_var.set(path)

    def _browse_sel_file(self):
        path = filedialog.askopenfilename(
            title='Select List File',
            filetypes=[
                ('Supported files', '*.zip *.txt *.csv *.xls *.xlsx *.doc *.docx'),
                ('ZIP Archive', '*.zip'),
                ('Text File', '*.txt'),
                ('CSV File', '*.csv'),
                ('Excel File', '*.xls *.xlsx'),
                ('Word Document', '*.doc *.docx'),
                ('All files', '*.*'),
            ]
        )
        if path:
            self.sel_var.set(path)

    def _browse_source(self):
        path = filedialog.askdirectory(title='Select Source Folder (Raw Files)')
        if path:
            self.src_var.set(path)

    def _browse_dest(self):
        path = filedialog.askdirectory(title='Select Destination Folder')
        if path:
            self.dest_var.set(path)

    def _make_source_subfolder(self):
        src = self.src_var.get().strip()
        dest = self.dest_var.get().strip()
        if not src:
            messagebox.showwarning('No Source', 'Set the Source Folder first.')
            return
        if not dest:
            messagebox.showwarning('No Destination', 'Set the Destination Folder first.')
            return
        src_name = Path(src).name
        if not src_name:
            messagebox.showwarning('Invalid Source',
                'Cannot derive a folder name from the Source path.')
            return
        new_dest = Path(dest) / src_name
        try:
            new_dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror('Error', f'Could not create folder:\n{e}')
            return
        self.dest_var.set(str(new_dest))
        self.status_var.set(f'Destination set to: {new_dest}')

    # ------------------------------------------------------------------
    # Match logic
    # ------------------------------------------------------------------

    def _clear_results(self):
        self.file_groups.clear()
        for w in self.scroll.inner.winfo_children():
            w.destroy()

    def _match_files(self):
        sel        = self.sel_var.get().strip()
        paste      = self.paste_text.get('1.0', 'end').strip()
        src        = self.src_var.get().strip()
        prefix     = self.prefix_var.get().strip()
        num_digits = self.digits_var.get()

        if not sel and not paste:
            messagebox.showwarning('Missing Input',
                'Please provide a client selection:\n'
                '  • a folder / file (top field), or\n'
                '  • paste a number list or message in the text box.')
            return
        if not src:
            messagebox.showwarning('Missing Input', 'Please set the Source Folder.')
            return
        if sel and not Path(sel).exists():
            messagebox.showwarning('Not Found', f'Selection path not found:\n{sel}')
            return
        if not Path(src).is_dir():
            messagebox.showwarning('Not Found', f'Source folder not found:\n{src}')
            return

        # Persist prefix and digits for next session
        save_config({'prefix': prefix, 'digits': num_digits})

        self.status_var.set('Parsing client selection…')
        self.update()

        numbers: Set[str] = set()

        # Numbers from folder / file
        if sel:
            try:
                numbers |= parse_selection(sel, prefix, num_digits)
            except ImportError as e:
                messagebox.showwarning('Missing Library', str(e))
                return
            except Exception as e:
                messagebox.showerror('Parse Error', f'Failed to read selection:\n{e}')
                return

        # Numbers from pasted text
        if paste:
            numbers |= parse_text_content(paste, prefix, num_digits)

        if not numbers:
            messagebox.showwarning('No Numbers Found',
                'Could not extract sequence numbers from the selection.\n\n'
                "Tip: set the Prefix to match your filenames (e.g. 'C86A' for C86A0042-HDR.jpg).\n"
                'Leave blank to auto-detect.')
            return

        self.status_var.set(f'Found {len(numbers)} numbers — scanning source folder…')
        self.update()

        try:
            matched, total_scanned, matched_numbers = scan_source(src, numbers, prefix, num_digits)
        except Exception as e:
            messagebox.showerror('Scan Error', f'Failed to scan source folder:\n{e}')
            return

        unmatched_numbers = numbers - matched_numbers

        # Build the diagnostic report (available via Details button)
        report_lines = [
            f'Selection:    {sel}',
            f'Source:       {src}',
            f'Prefix:       {prefix!r}   Digits: {num_digits}',
            '',
            f'Numbers found in selection ({len(numbers)}):',
        ]
        for n in sorted(numbers):
            hit = '  found' if n in matched_numbers else '  NOT FOUND in source'
            report_lines.append(f'  {prefix}{n}{hit}')
        report_lines += [
            '',
            f'Source folder: {total_scanned} file(s) scanned',
        ]
        for key in sorted(matched.keys()):
            report_lines.append(f'  {key}: {len(matched[key])} file(s)')
            for f in sorted(matched[key], key=lambda p: p.name.lower()):
                report_lines.append(f'    {f}')
        self._last_report = '\n'.join(report_lines)

        self._clear_results()

        # ── Summary bar at top of results ─────────────────────────────
        info_row = ttk.Frame(self.scroll.inner)
        info_row.pack(fill='x', padx=4, pady=(4, 6))
        summary = (f'{len(numbers)} selected  |  {total_scanned} files scanned  |  '
                   f'{sum(len(v) for v in matched.values())} matched')
        if unmatched_numbers:
            summary += f'  |  {len(unmatched_numbers)} number(s) not found in source'
        ttk.Label(info_row, text=summary, foreground='#555').pack(side='left')
        ttk.Button(info_row, text='Details…',
                   command=self._show_details).pack(side='right', padx=2)
        self._all_collapsed = True
        self.collapse_btn = ttk.Button(info_row, text='Expand all',
                                       command=self._toggle_all_groups)
        self.collapse_btn.pack(side='right', padx=2)

        if not matched:
            ttk.Label(self.scroll.inner,
                      text='No matching files found in source folder.',
                      foreground='gray').pack(pady=20)
            self.status_var.set(f'No matches. {total_scanned} files scanned. Click Details for breakdown.')
            return

        first = True
        for ext in sorted(matched.keys()):
            files = matched[ext]

            if not first:
                ttk.Separator(self.scroll.inner, orient='horizontal').pack(
                    fill='x', padx=4, pady=6)
            first = False

            grp_frame = ttk.Frame(self.scroll.inner)
            grp_frame.pack(fill='x', padx=4, pady=2)

            # Header row (clickable to collapse/expand)
            hdr = ttk.Frame(grp_frame)
            hdr.pack(fill='x')
            body = ttk.Frame(grp_frame)   # holds checkboxes; toggled in/out

            ext_display = ext.upper() or '(no ext)'
            hdr_label = ttk.Label(
                hdr, text=f'  ▶  {ext_display}  —  0/{len(files)} files',
                font=('Segoe UI', 9, 'bold'), cursor='hand2')
            hdr_label.pack(side='left', pady=2)

            state = {'collapsed': True}
            checkboxes: List = []   # (BooleanVar, Path)

            def update_label(lbl=hdr_label, cbs=checkboxes,
                             ext_=ext_display, total=len(files), st=state):
                arrow = '▶' if st['collapsed'] else '▼'
                sel = sum(1 for v, _ in cbs if v.get())
                lbl.configure(text=f'  {arrow}  {ext_}  —  {sel}/{total} files')

            def set_collapsed(c, body=body, st=state, ul=update_label):
                st['collapsed'] = c
                if c:
                    body.pack_forget()
                else:
                    body.pack(fill='x')
                ul()

            def toggle(_e=None, st=state, sc=set_collapsed):
                sc(not st['collapsed'])

            hdr_label.bind('<Button-1>', toggle)
            hdr.bind('<Button-1>', toggle)

            btn_u = ttk.Button(hdr, text='Uncheck All', width=11)
            btn_c = ttk.Button(hdr, text='Check All', width=9)
            btn_u.pack(side='right', padx=2)
            btn_c.pack(side='right', padx=2)

            for f in sorted(files, key=lambda p: p.name.lower()):
                var = tk.BooleanVar(value=False)
                var.trace_add('write', lambda *_, ul=update_label: ul())
                ttk.Checkbutton(body, text=f'  {f.name}', variable=var).pack(
                    anchor='w', padx=16)
                checkboxes.append((var, f))

            # Default state: collapsed (body stays unpacked)
            update_label()

            btn_c.configure(command=lambda cbs=checkboxes: [v.set(True) for v, _ in cbs])
            btn_u.configure(command=lambda cbs=checkboxes: [v.set(False) for v, _ in cbs])

            self.file_groups.append({
                'ext': ext,
                'checkboxes': checkboxes,
                'set_collapsed': set_collapsed,
            })

        total_files = sum(len(v) for v in matched.values())
        self.status_var.set(
            f'Matched {total_files} file(s) across {len(matched)} type(s) '
            f'from {len(numbers)} selected number(s).')

    def _toggle_all_groups(self):
        new_state = not getattr(self, '_all_collapsed', False)
        for g in self.file_groups:
            sc = g.get('set_collapsed')
            if sc:
                sc(new_state)
        self._all_collapsed = new_state
        self.collapse_btn.configure(
            text='Expand all' if new_state else 'Collapse all')

    def _show_details(self):
        report = getattr(self, '_last_report', 'No report available yet.')
        win = tk.Toplevel(self)
        win.title('Match Details')
        win.geometry('680x480')
        txt = tk.Text(win, wrap='none', font=('Consolas', 9))
        vsb = ttk.Scrollbar(win, orient='vertical', command=txt.yview)
        hsb = ttk.Scrollbar(win, orient='horizontal', command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side='bottom', fill='x')
        vsb.pack(side='right', fill='y')
        txt.pack(fill='both', expand=True)
        txt.insert('1.0', report)
        txt.configure(state='disabled')

    # ------------------------------------------------------------------
    # Copy / Move logic
    # ------------------------------------------------------------------

    def _copy_files(self):
        self._start_transfer('copy')

    def _move_files(self):
        if not messagebox.askyesno(
                'Confirm Move',
                'Move will remove the selected files from the source folder.\n\n'
                'This cannot be undone. Continue?'):
            return
        self._start_transfer('move')

    def _start_transfer(self, mode: str):
        dest = self.dest_var.get().strip()
        if not dest:
            messagebox.showwarning('No Destination', 'Please select a destination folder.')
            return

        dest_path = Path(dest)
        if not dest_path.exists():
            if messagebox.askyesno('Create Folder?',
                    f'Destination does not exist:\n{dest}\n\nCreate it now?'):
                try:
                    dest_path.mkdir(parents=True)
                except Exception as e:
                    messagebox.showerror('Error', f'Could not create folder:\n{e}')
                    return
            else:
                return

        files: List[Path] = []
        for grp in self.file_groups:
            for var, path in grp['checkboxes']:
                if var.get():
                    files.append(path)

        if not files:
            messagebox.showinfo('Nothing Selected', 'No files are checked.')
            return

        # Check for filename collisions in the destination
        conflicts = sum(1 for f in files if (dest_path / f.name).exists())
        if conflicts:
            action = self._ask_conflict_action(conflicts, len(files), mode)
            if action == 'cancel':
                return
            on_conflict = action   # 'overwrite' or 'skip'
        else:
            on_conflict = 'overwrite'

        self._transfer_mode = mode
        self.copy_btn.state(['disabled'])
        self.move_btn.state(['disabled'])
        self.match_btn.state(['disabled'])
        self.progress_bar['maximum'] = len(files)
        self.progress_bar.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.progress_var.set(0)

        self.copy_queue = queue.Queue()
        CopyWorker(files, str(dest_path), self.copy_queue,
                   mode, on_conflict).start()
        self.after(50, self._poll_copy)

    def _ask_conflict_action(self, conflict_count: int, total: int, mode: str) -> str:
        """Modal dialog. Returns 'overwrite', 'skip', or 'cancel'."""
        win = tk.Toplevel(self)
        win.title('Files Already Exist')
        win.transient(self)
        win.resizable(False, False)

        verb = 'move' if mode == 'move' else 'copy'
        msg = (
            f'{conflict_count} of {total} file(s) already exist in the '
            f'destination folder.\n\n'
            f'  •  Overwrite all  —  replace existing files\n'
            f'  •  Skip existing  —  keep existing, only {verb} the rest\n'
            f'  •  Cancel  —  abort the transfer'
        )
        ttk.Label(win, text=msg, justify='left',
                  padding=14).pack(anchor='w')

        result = {'value': 'cancel'}

        def choose(v):
            result['value'] = v
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(padx=14, pady=(0, 14), anchor='e')
        ttk.Button(btns, text='Overwrite all',
                   command=lambda: choose('overwrite')).pack(side='left', padx=4)
        ttk.Button(btns, text='Skip existing',
                   command=lambda: choose('skip')).pack(side='left', padx=4)
        ttk.Button(btns, text='Cancel',
                   command=lambda: choose('cancel')).pack(side='left', padx=4)

        # Center on parent window
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f'+{max(x, 0)}+{max(y, 0)}')

        win.protocol('WM_DELETE_WINDOW', lambda: choose('cancel'))
        win.grab_set()
        self.wait_window(win)
        return result['value']

    def _poll_copy(self):
        verb = 'Moving' if self._transfer_mode == 'move' else 'Copying'
        try:
            while True:
                msg = self.copy_queue.get_nowait()
                if msg[0] == 'progress':
                    _, current, total, name = msg
                    self.progress_var.set(current)
                    self.status_var.set(f'{verb} {current}/{total}: {name}')
                elif msg[0] == 'done':
                    _, count, errors, skipped = msg
                    self._on_transfer_done(count, errors, skipped)
                    return
        except queue.Empty:
            pass
        self.after(50, self._poll_copy)

    def _on_transfer_done(self, count: int, errors: list, skipped: int = 0):
        self.copy_btn.state(['!disabled'])
        self.move_btn.state(['!disabled'])
        self.match_btn.state(['!disabled'])
        self.progress_bar.pack_forget()

        verb_ed = 'moved' if self._transfer_mode == 'move' else 'copied'

        summary = f'Successfully {verb_ed} {count} file(s).'
        if skipped:
            summary += f'\nSkipped {skipped} file(s) that already existed.'

        if errors:
            details = '\n'.join(errors[:15])
            if len(errors) > 15:
                details += f'\n… (+{len(errors) - 15} more)'
            messagebox.showwarning('Completed with Errors',
                f'{summary}\n\nErrors:\n{details}')
        else:
            messagebox.showinfo('Done!',
                f'{summary}\n\nDestination:\n{self.dest_var.get()}')

        status = f'Done — {count} file(s) {verb_ed}'
        if skipped:
            status += f', {skipped} skipped'
        self.status_var.set(status + '.')


# ---------------------------------------------------------------------------

def main():
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()
