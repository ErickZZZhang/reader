"""
Chinese Novel Chapter Renumberer (GUI)

Converts Chinese number chapter titles (e.g. 第一百二十三章) to Arabic numerals
(e.g. 第123章) so Kindle and other e-readers can correctly detect chapters.
"""

import re
import uuid
import webbrowser
from pathlib import Path
from html import escape as html_escape
from urllib.parse import quote

from ebooklib import epub
from tkinterdnd2 import TkinterDnD, DND_FILES
import tkinter as tk
from tkinter import filedialog

# Dracula color palette
DRACULA = {
    'bg': '#282a36',
    'current': '#44475a',
    'fg': '#f8f8f2',
    'comment': '#6272a4',
    'cyan': '#8be9fd',
    'green': '#50fa7b',
    'orange': '#ffb86c',
    'pink': '#ff79c6',
    'purple': '#bd93f9',
    'red': '#ff5555',
    'yellow': '#f1fa8c',
}

KINDLE_EMAIL = '769290061erick_zrYPtf@kindle.com'

# ── Chinese number conversion ──────────────────────────────────────────

CN_DIGITS = {
    '零': 0, '〇': 0,
    '一': 1, '壹': 1,
    '二': 2, '贰': 2, '两': 2,
    '三': 3, '叁': 3,
    '四': 4, '肆': 4,
    '五': 5, '伍': 5,
    '六': 6, '陆': 6,
    '七': 7, '柒': 7,
    '八': 8, '捌': 8,
    '九': 9, '玖': 9,
}

CN_UNITS = {
    '十': 10, '拾': 10,
    '百': 100, '佰': 100,
    '千': 1000, '仟': 1000,
    '万': 10000,
}


def chinese_to_int(cn_str: str) -> int:
    if not cn_str:
        return 0
    result = 0
    current = 0
    i = 0
    if cn_str[0] in ('十', '拾'):
        result = 10
        i = 1
    while i < len(cn_str):
        char = cn_str[i]
        if char in CN_DIGITS:
            current = CN_DIGITS[char]
        elif char in CN_UNITS:
            unit = CN_UNITS[char]
            if unit == 10000:
                result = (result + current) * unit
                current = 0
            else:
                if current == 0 and unit == 10:
                    current = 1
                result += current * unit
                current = 0
        i += 1
    result += current
    return result


CN_NUM_CHARS = ''.join(list(CN_DIGITS.keys()) + list(CN_UNITS.keys()))
CHAPTER_PATTERN = re.compile(
    rf'(第)([{re.escape(CN_NUM_CHARS)}]+)(章|节|回|卷|篇|集)'
)


def convert_line(line: str) -> str:
    def replacer(match):
        prefix = match.group(1)
        cn_num = match.group(2)
        suffix = match.group(3)
        num = chinese_to_int(cn_num)
        return f'{prefix}{num}{suffix}'
    return CHAPTER_PATTERN.sub(replacer, line)


# ── File I/O ───────────────────────────────────────────────────────────

def read_file(path: Path) -> str:
    for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5']:
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("Could not detect file encoding.")


def process_file(input_path: Path) -> tuple[Path, int]:
    text = read_file(input_path)
    lines = text.splitlines(keepends=True)
    converted_lines = [convert_line(line) for line in lines]
    changes = sum(1 for old, new in zip(lines, converted_lines) if old != new)
    output_path = input_path.with_name(f"{input_path.stem}_numbered{input_path.suffix}")
    output_path.write_text(''.join(converted_lines), encoding='utf-8')
    return output_path, changes


# ── EPUB generation ────────────────────────────────────────────────────

CHAPTER_LINE_PATTERN = re.compile(r'^第\d+(?:章|节|回|卷|篇|集)')


def split_into_chapters(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    chapters = []
    current_title = None
    current_lines = []
    for line in lines:
        if CHAPTER_LINE_PATTERN.match(line.strip()):
            if current_title is not None or current_lines:
                title = current_title or "前言"
                chapters.append((title, '\n'.join(current_lines)))
            current_title = line.strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title is not None or current_lines:
        title = current_title or "前言"
        chapters.append((title, '\n'.join(current_lines)))
    return chapters


def make_chapter_html(title: str, body: str) -> str:
    paragraphs = []
    for line in body.split('\n'):
        stripped = line.strip()
        if stripped:
            paragraphs.append(f'<p>{html_escape(stripped)}</p>')
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        '<head><title>' + html_escape(title) + '</title></head>\n'
        '<body>\n'
        '<h2>' + html_escape(title) + '</h2>\n'
        + '\n'.join(paragraphs) + '\n'
        '</body>\n</html>'
    )


def process_file_epub(input_path: Path, renumber: bool = True) -> tuple[Path, int, int]:
    text = read_file(input_path)
    if renumber:
        lines = text.splitlines(keepends=True)
        converted_lines = [convert_line(line) for line in lines]
        changes = sum(1 for old, new in zip(lines, converted_lines) if old != new)
        converted_text = ''.join(converted_lines)
    else:
        changes = 0
        converted_text = text
    chapters = split_into_chapters(converted_text)

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(input_path.stem)
    book.set_language('zh')

    style = epub.EpubItem(
        uid='style',
        file_name='style/default.css',
        media_type='text/css',
        content='body { font-family: serif; line-height: 1.8; } '
                'h2 { text-align: center; margin: 1em 0; } '
                'p { text-indent: 2em; margin: 0.5em 0; }'.encode('utf-8'),
    )
    book.add_item(style)

    epub_chapters = []
    for i, (title, body) in enumerate(chapters):
        ch = epub.EpubHtml(
            title=title,
            file_name=f'chapter_{i:04d}.xhtml',
            lang='zh',
        )
        ch.content = make_chapter_html(title, body).encode('utf-8')
        ch.add_item(style)
        book.add_item(ch)
        epub_chapters.append(ch)

    book.toc = epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + epub_chapters

    suffix = "_numbered" if renumber else ""
    output_path = input_path.with_name(f"{input_path.stem}{suffix}.epub")
    epub.write_epub(str(output_path), book)
    return output_path, changes, len(chapters)


# ── GUI ────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("Chapter Renumberer")
        self.root.configure(bg=DRACULA['bg'])
        self.root.resizable(False, False)

        self.file_path = None
        self._build_ui()
        self._center_window()

    def _make_btn(self, parent, text, sublabel, color, command):
        frame = tk.Frame(parent, bg=DRACULA['current'], cursor='hand2')

        label = tk.Label(frame, text=text, font=("Segoe UI", 12, "bold"),
                         fg=color, bg=DRACULA['current'])
        label.pack(pady=(10, 0))

        sub = tk.Label(frame, text=sublabel, font=("Segoe UI", 9),
                       fg=DRACULA['comment'], bg=DRACULA['current'])
        sub.pack(pady=(0, 10))

        for widget in (frame, label, sub):
            widget.bind('<Enter>', lambda e, f=frame, l=label, s=sub: (
                f.configure(bg=DRACULA['comment']),
                l.configure(bg=DRACULA['comment'], fg=DRACULA['fg']),
                s.configure(bg=DRACULA['comment']),
            ))
            widget.bind('<Leave>', lambda e, f=frame, l=label, s=sub, c=color: (
                f.configure(bg=DRACULA['current']),
                l.configure(bg=DRACULA['current'], fg=c),
                s.configure(bg=DRACULA['current']),
            ))
            widget.bind('<Button-1>', lambda e, cmd=command: cmd())

        return frame

    def _build_ui(self):
        root = self.root
        D = DRACULA

        # ── Title bar ──
        titlebar = tk.Frame(root, bg=D['bg'])
        titlebar.pack(fill='x', padx=24, pady=(18, 0))

        tk.Label(titlebar, text="Chapter Renumberer",
                 font=("Segoe UI", 16, "bold"), fg=D['purple'],
                 bg=D['bg']).pack()
        tk.Label(titlebar, text="Convert Chinese chapter titles to Arabic numerals",
                 font=("Segoe UI", 10), fg=D['comment'],
                 bg=D['bg']).pack(pady=(2, 0))

        # Separator
        tk.Frame(root, bg=D['current'], height=1).pack(fill='x', padx=24, pady=(14, 0))

        # ── Content area ──
        content = tk.Frame(root, bg=D['bg'])
        content.pack(fill='both', padx=24, pady=(16, 24))

        # ── Drop zone ──
        self.drop_frame = tk.Frame(content, bg=D['bg'],
                                   highlightbackground=D['current'],
                                   highlightcolor=D['purple'],
                                   highlightthickness=2)
        self.drop_frame.pack(fill='x')

        self.drop_inner = tk.Frame(self.drop_frame, bg=D['bg'])
        self.drop_inner.pack(fill='x', padx=20, pady=20)

        self.drop_icon = tk.Label(self.drop_inner, text="\U0001F4C4",
                                  font=("Segoe UI", 24), bg=D['bg'])
        self.drop_icon.pack()

        self.drop_text = tk.Label(self.drop_inner,
                                  text="Drag & drop a .txt file here, or click to browse",
                                  font=("Segoe UI", 11), fg=D['comment'], bg=D['bg'])
        self.drop_text.pack(pady=(4, 0))

        self.file_name_label = tk.Label(self.drop_inner, text="",
                                        font=("Segoe UI", 12, "bold"),
                                        fg=D['fg'], bg=D['bg'])

        self.file_path_label = tk.Label(self.drop_inner, text="",
                                        font=("Segoe UI", 9), fg=D['comment'],
                                        bg=D['bg'])

        self.file_change_label = tk.Label(self.drop_inner, text="change",
                                          font=("Segoe UI", 9, "underline"),
                                          fg=D['purple'], bg=D['bg'], cursor='hand2')
        self.file_change_label.bind('<Button-1>', lambda e: self._select_file())

        # Click to browse
        for widget in (self.drop_frame, self.drop_inner, self.drop_icon, self.drop_text):
            widget.bind('<Button-1>', lambda e: self._select_file())

        # Drag and drop
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<DropEnter>>', self._on_drag_enter)
        self.drop_frame.dnd_bind('<<DropLeave>>', self._on_drag_leave)
        self.drop_frame.dnd_bind('<<Drop>>', self._on_drop)

        # ── Preview ──
        tk.Label(content, text="PREVIEW", font=("Segoe UI", 10, "bold"),
                 fg=D['comment'], bg=D['bg'], anchor='w').pack(fill='x', pady=(16, 6))

        preview_frame = tk.Frame(content, bg=D['current'],
                                 highlightbackground=D['current'],
                                 highlightthickness=1)
        preview_frame.pack(fill='x')

        self.preview = tk.Text(preview_frame, height=9, width=55,
                               font=("Consolas", 10), bg=D['bg'], fg=D['fg'],
                               state="disabled", wrap="none", bd=0,
                               padx=12, pady=10, insertbackground=D['fg'],
                               selectbackground=D['current'])
        scrollbar = tk.Scrollbar(preview_frame, command=self.preview.yview,
                                 bg=D['current'], troughcolor=D['bg'],
                                 highlightbackground=D['bg'])
        self.preview.configure(yscrollcommand=scrollbar.set)
        self.preview.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.preview.tag_configure("before", foreground=D['red'],
                                   overstrike=True)
        self.preview.tag_configure("after", foreground=D['green'])
        self.preview.tag_configure("arrow", foreground=D['comment'])
        self.preview.tag_configure("placeholder", foreground=D['comment'])

        self.preview.configure(state="normal")
        self.preview.insert("end", "  Select a file to preview changes...", "placeholder")
        self.preview.configure(state="disabled")

        # ── Renumber toggle ──
        self.renumber_var = tk.BooleanVar(value=True)
        toggle_frame = tk.Frame(content, bg=D['bg'])
        toggle_frame.pack(fill='x', pady=(16, 0))

        self.renumber_cb = tk.Checkbutton(
            toggle_frame, text="Renumber chapter titles (Chinese → Arabic)",
            variable=self.renumber_var, font=("Segoe UI", 10),
            fg=D['fg'], bg=D['bg'], selectcolor=D['current'],
            activebackground=D['bg'], activeforeground=D['fg'],
            command=self._on_renumber_toggle,
        )
        self.renumber_cb.pack(anchor='w')

        # ── Action buttons ──
        btn_frame = tk.Frame(content, bg=D['bg'])
        btn_frame.pack(fill='x', pady=(12, 0))

        btn_txt = self._make_btn(btn_frame, "Export TXT", "Renumber only",
                                 D['cyan'], self._export_txt)
        btn_txt.pack(side='left', fill='both', expand=True, padx=(0, 6))

        btn_epub = self._make_btn(btn_frame, "Export EPUB", "Kindle-ready chapters",
                                  D['purple'], self._export_epub)
        btn_epub.pack(side='left', fill='both', expand=True, padx=3)

        btn_kindle = self._make_btn(btn_frame, "Send to Kindle",
                                    "Export EPUB & open Gmail",
                                    D['orange'], self._send_to_kindle)
        btn_kindle.pack(side='left', fill='both', expand=True, padx=(6, 0))

        # ── Status bar ──
        self.status = tk.Label(content, text="", font=("Segoe UI", 10),
                               fg=D['comment'], bg=D['bg'], anchor='center')
        self.status.pack(fill='x', pady=(14, 0))

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

    # ── Drag and drop handlers ──

    def _on_drag_enter(self, event):
        self.drop_frame.configure(highlightbackground=DRACULA['purple'])

    def _on_drag_leave(self, event):
        color = DRACULA['green'] if self.file_path else DRACULA['current']
        self.drop_frame.configure(highlightbackground=color)

    def _on_drop(self, event):
        path = event.data.strip()
        # tkdnd wraps paths with spaces in braces
        if path.startswith('{') and path.endswith('}'):
            path = path[1:-1]
        if path.lower().endswith('.txt'):
            self._load_file(Path(path))
        else:
            self._set_status("Only .txt files are supported", DRACULA['red'])

    # ── File loading ──

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="Select a .txt novel file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path):
        self.file_path = path
        self.drop_frame.configure(highlightbackground=DRACULA['green'])

        # Switch to file-selected state
        self.drop_icon.pack_forget()
        self.drop_text.pack_forget()

        self.file_name_label.configure(text=path.name)
        self.file_name_label.pack()
        self.file_path_label.configure(text=str(path))
        self.file_path_label.pack(pady=(2, 0))
        self.file_change_label.pack(pady=(4, 0))

        self._show_preview()
        self._set_status("File loaded — ready to export", DRACULA['green'])

    def _show_preview(self):
        D = DRACULA
        try:
            text = read_file(self.file_path)
        except ValueError:
            self.preview.configure(state="normal")
            self.preview.delete("1.0", "end")
            self.preview.insert("end", "Error: could not read file encoding.", "placeholder")
            self.preview.configure(state="disabled")
            return

        lines = text.splitlines()
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")

        if self.renumber_var.get():
            found = 0
            for line in lines:
                converted = convert_line(line)
                if converted != line:
                    found += 1
                    self.preview.insert("end", f"  {line.strip()}", "before")
                    self.preview.insert("end", "  \u2192  ", "arrow")
                    self.preview.insert("end", f"{converted.strip()}\n", "after")

            if found == 0:
                self.preview.insert("end", "  No Chinese chapter headings found.", "placeholder")
            else:
                self.preview.insert("1.0",
                                    f"  Found {found} chapter heading(s) to convert:\n\n")
        else:
            # Show chapter detection preview only
            chapters = split_into_chapters(text)
            self.preview.insert("end",
                                f"  {len(chapters)} chapter(s) detected — no renumbering\n\n")
            for title, _ in chapters[:20]:
                self.preview.insert("end", f"  {title}\n", "after")
            if len(chapters) > 20:
                self.preview.insert("end",
                                    f"\n  ... and {len(chapters) - 20} more", "placeholder")

        self.preview.configure(state="disabled")

    # ── Toggle handler ──

    def _on_renumber_toggle(self):
        if self.file_path:
            self._show_preview()

    # ── Export actions ──

    def _set_status(self, text, color=None):
        self.status.configure(text=text, fg=color or DRACULA['comment'])

    def _export_txt(self):
        if not self.file_path:
            self._set_status("No file selected", DRACULA['red'])
            return
        if not self.renumber_var.get():
            self._set_status("TXT export requires renumbering enabled", DRACULA['orange'])
            return
        try:
            output_path, changes = process_file(self.file_path)
            self._set_status(
                f"Exported TXT — {changes} heading(s) converted \u2192 {output_path.name}",
                DRACULA['green'])
        except Exception as e:
            self._set_status(f"Error: {e}", DRACULA['red'])

    def _export_epub(self):
        if not self.file_path:
            self._set_status("No file selected", DRACULA['red'])
            return
        try:
            renumber = self.renumber_var.get()
            output_path, changes, num_chapters = process_file_epub(self.file_path, renumber)
            if renumber:
                self._set_status(
                    f"Exported EPUB — {num_chapters} chapter(s), {changes} renamed \u2192 {output_path.name}",
                    DRACULA['green'])
            else:
                self._set_status(
                    f"Exported EPUB — {num_chapters} chapter(s) \u2192 {output_path.name}",
                    DRACULA['green'])
        except Exception as e:
            self._set_status(f"Error: {e}", DRACULA['red'])

    def _send_to_kindle(self):
        if not self.file_path:
            self._set_status("No file selected", DRACULA['red'])
            return
        try:
            renumber = self.renumber_var.get()
            output_path, _, num_chapters = process_file_epub(self.file_path, renumber)

            # Copy file path to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(str(output_path))

            # Open Gmail compose with Kindle email pre-filled
            gmail_url = (
                f"https://mail.google.com/mail/?view=cm"
                f"&to={quote(KINDLE_EMAIL)}"
                f"&su={quote(output_path.stem)}"
            )
            webbrowser.open(gmail_url)

            self._set_status(
                f"Gmail opened — file path copied to clipboard ({num_chapters} chapters)",
                DRACULA['green'])
        except Exception as e:
            self._set_status(f"Error: {e}", DRACULA['red'])

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()
