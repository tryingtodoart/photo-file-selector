# Photo File Selector

A small desktop tool for photographers to match and copy (or move) raw files based on client selections.

## The problem it solves

After delivering a watermarked gallery to a client, they send back their selection — as a folder of chosen images, a ZIP, a text/Excel/Word list, or even a WhatsApp message with numbers. You then have to manually hunt through your source folder to find and copy the matching raw files (`.CR2`, `.DNG`, `-HDR.DNG`, etc.).

This tool automates that. Point it at the client selection and your source folder, and it finds every matching file — including HDR variants — grouped by file type, with one-click copy or move to a destination folder.

## Features

- **Multiple selection input formats**: folder of images, `.zip`, `.txt`, `.xls`/`.xlsx`, `.doc`/`.docx`, or paste a message/number list directly
- **Smart number matching**: bare numbers like `155` are automatically zero-padded to match filenames (`C86A0155`)
- **HDR-aware grouping**: `C86A0001-HDR.dng` appears as its own group (`.DNG (HDR)`) separate from `.DNG`, so you can include/exclude all HDR files independently
- **Bulk select controls**: Check All / Uncheck All per file type
- **Copy or Move**: move files out of the source folder when you're done
- **Match Details**: shows exactly which numbers were found and which had no match in source — useful for spotting missing files
- **Saved prefix**: your file prefix (e.g. `C86A`) is remembered between sessions
- **Customisable**: works with any camera brand and naming convention

## Download

Go to the [Releases](../../releases) page and download `PhotoFileSelector.exe`. No installation or Python required — just run it.

## Verify the code yourself

Everything the app does is in a single file: [`photo_selector.py`](photo_selector.py).

It only uses:
- Python standard library (`re`, `shutil`, `zipfile`, `tkinter`, `threading`, `json`, `pathlib`)
- [`openpyxl`](https://pypi.org/project/openpyxl/) — read `.xlsx` files
- [`python-docx`](https://pypi.org/project/python-docx/) — read `.docx` files

**It does not connect to the internet, send any data anywhere, or access anything outside the folders you point it to.**

## Run from source

```
pip install openpyxl python-docx
python photo_selector.py
```

## Build the exe yourself

```
pip install pyinstaller openpyxl python-docx
pyinstaller --onefile --windowed --name "PhotoFileSelector" photo_selector.py
```

The exe will be in the `dist/` folder.

## File naming convention

The tool expects filenames in the format:

```
[PREFIX][NUMBER][-HDR].[EXT]

Examples:
  C86A0042.CR2
  C86A0042-HDR.DNG
  IMG_0042.CR2
```

Set the **Prefix** field to the constant part before the number (e.g. `C86A`). Leave it blank for auto-detection.

## License

MIT — free to use, share, and modify.
