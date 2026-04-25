# Photo File Selector — Integration Reference

Reference document for wiring the Photo File Selector tools to an external system
(e.g. a website that delivers galleries via Dropbox and exports the client's selection
as a CSV).

Both tools — the **desktop app** (`photo_selector.py` / `PhotoFileSelector.exe`) and the
**Lightroom Classic plugin** (`photo-selector-lr.lrplugin/`) — share the same input formats
and number-extraction logic, so a CSV produced by the website works identically with both.

---

## 1. Tool overview

| Tool | What it does | Input | Output |
|------|--------------|-------|--------|
| **Desktop app** | Copies / moves matched RAW files into a destination folder | Source folder + selection | Files on disk |
| **LR plugin** | Sets star rating and/or color label on matched photos in the catalog | LR catalog scope + selection | Metadata in catalog |

Both tools accept the same selection inputs:

1. A **folder of images** (typically the client-returned watermarked JPEGs)
2. A **`.txt` or `.csv` file** containing numbers or filenames
3. **Free-text paste** (WhatsApp message, email body, etc.)

For website integration, format **#2 (CSV)** is the relevant one.

---

## 2. CSV format — what the tools accept

### 2.1 Tokenization rules

Both tools read the CSV as plain text and tokenize on any of these characters:

```
whitespace , ; | \t \r \n
```

So all of the following are equivalent and parse correctly:

```csv
155,175,245,275,320
```
```csv
155
175
245
275
320
```
```csv
155;175;245;275;320
```
```csv
155 | 175 | 245 | 275 | 320
```

There is **no header row, no schema, no escaping** — every token is independently passed
to the number-extraction logic. Tokens that don't yield a number are silently ignored.

### 2.2 What each token can be

A single token can be any of:

| Token type | Example | Result |
|------------|---------|--------|
| Bare number | `155` | `0155` (zero-padded to `numDigits`) |
| Zero-padded number | `0155` | `0155` |
| Full filename with extension | `C86A0155.CR2` | `0155` |
| HDR filename | `C86A0042-HDR.dng` | `0042` (HDR suffix stripped) |
| Filename without extension | `C86A0155` | `0155` |

The matching is **case-insensitive** on the prefix.

### 2.3 What the website should output

**Recommended CSV format** (simplest, most robust):

```csv
0155
0175
0245
0275
0320
```

One bare or zero-padded number per line, no header, no quotes, no commas.
This works with any prefix and any digit count the photographer configures in the tool.

If the website knows the original filenames, this also works:

```csv
C86A0155.jpg
C86A0175.jpg
C86A0245.jpg
```

The tool strips extensions and prefixes automatically, so either format is fine.

---

## 3. Number extraction logic (shared by both tools)

The photographer configures two settings in the tool:

- **Prefix** — the fixed part of their RAW filenames before the sequence number (e.g. `C86A`)
- **Sequence digits** — how many digits the sequence number has (default `4`)

Extraction algorithm, applied to every token:

1. Strip the file extension if present (`.jpg`, `.cr2`, etc.)
2. Strip an HDR suffix if present (`-HDR`, `_HDR`, case-insensitive)
3. If the remaining string is **only digits**, zero-pad it to `numDigits` and return it
4. If a **prefix is configured**, look for `^{prefix}(\d+)` (case-insensitive) and return the digits
5. Otherwise (no prefix), return the first run of `≥ numDigits` digits, truncated to `numDigits`
6. If nothing matches, the token is dropped

This means:
- `155` with `numDigits=4` → `0155`
- `C86A0042-HDR.dng` with `prefix=C86A` → `0042`
- `IMG_0042.JPG` with `prefix=IMG_` → `0042`
- `random text` → dropped

Reference implementations:

- Python: [photo_selector.py](photo_selector.py) — `extract_number()`
- Lua: [photo-selector-lr.lrplugin/PluginMenu.lua](photo-selector-lr.lrplugin/PluginMenu.lua) — `extractNumber()`

---

## 4. End-to-end workflow with website integration

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Photographer's Website                                                  │
│  ─────────────────────                                                   │
│  1. Photographer uploads gallery → Dropbox shares with client            │
│  2. Client picks images on the website                                   │
│  3. Website exports selection as CSV  ◄── numbers or filenames, one per │
│                                            line, no header               │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ CSV download
                                   ▼
                ┌──────────────────────────────────┐
                │  Photographer's local machine    │
                └────┬───────────────────────┬─────┘
                     │                       │
                     ▼                       ▼
        ┌────────────────────────┐   ┌──────────────────────────┐
        │  Desktop App           │   │  Lightroom Classic       │
        │  ──────────────        │   │  ──────────────────      │
        │  • Pick CSV via "File" │   │  • Library → Plugin      │
        │  • Pick source folder  │   │    Extras → Photo File   │
        │  • Pick destination    │   │    Selector              │
        │  • Set prefix/digits   │   │  • Pick CSV via "File    │
        │  • Copy or Move        │   │    selection"            │
        │                        │   │  • Set prefix/digits     │
        │  → RAW files copied    │   │  • Pick scope + types    │
        │    to destination      │   │  • Apply rating/label    │
        └────────────────────────┘   └──────────────────────────┘
```

The two tools serve different purposes:

- **Desktop app** — when the photographer wants the matched RAWs as a separate folder
  (e.g. for backup, for handing off to a retoucher, for sharing with a co-shooter)
- **LR plugin** — when the photographer is editing in Lightroom and just wants to
  filter / mark the selection in their existing catalog

Both can consume the **same CSV** from the website — the photographer chooses the tool
based on what they want to do next.

---

## 5. Optional enhancements for the website side

The current tools accept very loose CSV formats. If the website wants to be helpful,
it can:

1. **Use the photographer's filename convention** — exporting `C86A0155.CR2` instead
   of bare numbers means the photographer doesn't need to set a prefix in the tool.
   But bare numbers work too and are more robust if the photographer changes cameras.

2. **Include a UTF-8 BOM** if the CSV may contain non-ASCII filenames — both tools
   handle UTF-8 input.

3. **One number per line** — easier to read, easier to debug, and works as both
   `.csv` and `.txt`.

4. **Avoid Excel auto-formatting** — if the export goes through Excel, `0155` becomes
   `155` (Excel strips leading zeros). Either export directly without round-tripping
   through Excel, or trust that the tools auto-pad bare numbers.

---

## 6. Direct API integration (future possibility, not implemented)

The current tools are GUI-only. If the website wants to skip the manual step entirely,
two paths exist:

- **Headless desktop app** — `photo_selector.py` could expose a CLI that takes a CSV
  path + source folder + destination folder + prefix and runs without the UI. The
  matching logic is already separable.
- **LR plugin "auto" mode** — the plugin could read the CSV path from a known location
  (e.g. a watch folder) and apply rating/label without showing a dialog. Would require
  changes to `PluginMenu.lua`.

Neither is built today — only mentioning so the website-side integration can decide
whether to plan for that direction or stick with the current download-and-open flow.

---

## 7. File reference

| File | Purpose |
|------|---------|
| [photo_selector.py](photo_selector.py) | Desktop app — single-file Python, all logic |
| [photo-selector-lr.lrplugin/Info.lua](photo-selector-lr.lrplugin/Info.lua) | Plugin manifest for LR Classic |
| [photo-selector-lr.lrplugin/PluginMenu.lua](photo-selector-lr.lrplugin/PluginMenu.lua) | Plugin — single-file Lua, all logic |
| [README.md](README.md) | End-user overview and install instructions |
| [MANUAL_RO.txt](MANUAL_RO.txt) | Romanian user manual (plain text) |
| [INTEGRATION.md](INTEGRATION.md) | This document |
