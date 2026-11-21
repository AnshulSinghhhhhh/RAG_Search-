# Installation and first run

Adaptive Second Brain 0.2.0 runs on your computer. It indexes files you select, then makes them searchable in a terminal or a browser. Start with the bundled synthetic playground so you can verify the installation before adding personal files.

## Requirements

- **Python 3.11** is the recommended version. The package declares support for Python 3.10 through 3.13. The standard CI runs on Windows and Ubuntu with Python 3.11. macOS uses the manual Python setup.
- Use Git to clone the repository, or choose **Code → Download ZIP** on GitHub and extract it.
- Allow network access for Python packages and the first model downloads. The full model cache measured in one development run was about 823 MB, including audio. The exact size depends on the enabled models and their versions.
- The app runs on CPU. Python serves the web interface and SQLite stores the index. Standard search requires only the Python application and its models. Ollama is an optional integration for generated answers.

Run these commands from a terminal to clone the repository. If you downloaded a ZIP, open the extracted project folder instead.

```sh
git clone https://github.com/AnshulSinghhhhhh/RAG_Search-.git
cd RAG_Search-
```

## Install

### Windows Command Prompt

Install 64-bit Python 3.11 with the Python launcher or add Python to PATH. Open **Command Prompt** in the project directory. The setup script installs voice transcription as well as image and text search.

```bat
setup.cmd
brain.cmd --version
brain.cmd doctor
```

For a smaller base installation without voice transcription, or to install manually, create a virtual environment and use its Python directly:

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m secondbrain --version
```

Install the audio extra later with `.venv\Scripts\python.exe -m pip install -e ".[audio]"`. If `py` is unavailable, use `python -m venv .venv` after confirming `python --version` reports Python 3.11. If Windows blocks the generated `brain.exe` launcher, use `brain.cmd` or invoke the module through the virtual environment's Python.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[audio]"
.\.venv\Scripts\python.exe -m secondbrain --version
.\.venv\Scripts\python.exe -m secondbrain doctor
```

The explicit Python path works without activating the environment. To use the wrapper from PowerShell, type `.\brain.cmd`.

### macOS and Linux

Use an installed Python 3.11 interpreter. On Linux distributions that package virtual environment support separately, install the corresponding venv package if Python reports that `ensurepip` is unavailable.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[audio]"
brain --version
brain doctor
```

Use `python -m pip install -e .` to skip voice transcription. If you prefer to work without activating the environment, run `.venv/bin/python -m secondbrain` in place of `brain`.

## Verify with the synthetic playground

Use a dedicated collection for the sample files. Run the commands from the repository root. On Windows, use `brain.cmd` in CMD or `.\brain.cmd` in PowerShell. The `--home` option goes before the subcommand.

```sh
brain --home .secondbrain-demo init
brain --home .secondbrain-demo models --audio
brain --home .secondbrain-demo index playground/inbox
brain --home .secondbrain-demo search "Juniper Cafe"
brain --home .secondbrain-demo ask "What is the receipt total for Juniper Cafe?" --kind image
brain --home .secondbrain-demo serve
```

The first model download can take several minutes. With the audio extra installed, all supported sample files can be indexed. For a base installation, run `models` without `--audio` and index `playground/inbox/receipts` (or `notes` and `screenshots`, one at a time). The café receipt is expected to show a total of INR 690 with an image citation, subject to the OCR reading. Check the source line if the result needs verification.

The browser opens at **http://127.0.0.1:8765**. Search for a receipt, click **Show evidence**, and open the citation to see its highlighted line. Use **Refine OCR** to request another reading. Stop the server with **Ctrl+C**. To specify a different port, use `brain --home .secondbrain-demo serve --port 8766`.

The demo collection is generated data. Keep it outside any Git checkout where you plan to commit files, or retain the ignored `.secondbrain-demo` name.

## Use your own collection

Omit `--home` to use the default collection. It lives under `%LOCALAPPDATA%\SecondBrain` on Windows and `~/.local/share/secondbrain` on macOS and Linux. Use the same explicit `--home` (or `SECONDBRAIN_HOME` environment variable) for the CLI and browser when you want a custom collection. Run `brain status` to see which collection is in use.

```sh
brain init
brain index "path/to/a/selected/folder"
brain status
brain search "meeting notes last week"
brain search "7718" --lexical-only
brain ask "What is the invoice number for Harbor Books?" --refine
brain serve
```

Replace the sample folder path and queries with your own. You can also add a file or folder through the browser's **Add files or folder** control. The app supports common images (PNG, JPEG, WebP, BMP and TIFF), audio formats (WAV, MP3, M4A, OGG, FLAC, AAC and Opus), and plain-text formats (TXT, Markdown, CSV, JSON, LOG and RST). Use `--kind image`, `--kind audio` or `--kind text` when the query should search a specific file type. PDFs and video are outside the supported formats.

Folder indexing registers the folder for later `brain sync`. Use `brain watch` to keep registered folders updated while the process is running. Use `brain forget "path"` to remove index entries while preserving the originals, or `brain prune` to remove missing locations. Extracted text and previews are stored locally. Treat the collection and any backups as private data because the SQLite database is unencrypted. Keep the browser server on localhost.

### Optional local answer model

Standard Ask can quote source evidence and extract supported receipt or price fields without an answer model. If you already run Ollama locally with a model downloaded, other question types can use it via:

```sh
brain ask "What are the main points in my project notes?" --model "your-installed-model"
```

The integration connects to the loopback Ollama instance. Inspect cited originals when exact facts matter.

## Upgrade an existing collection

From the existing checkout, update the source and reinstall it into the same virtual environment. If you installed from ZIP, extract the new version separately and point it at the same collection. The commands below assume an activated environment. Use the explicit virtual environment Python path on Windows if needed.

```sh
git pull --ff-only
python -m pip install -e ".[audio]"
brain --version
brain repair --dry-run
brain repair
```

For an image and text collection, install the base package without `[audio]`. Keep any existing `--home` argument before both repair commands. Repair commits assets individually and can resume on a second run. It reports originals that have moved, changed, or become unavailable. Index the file at its current path to refresh changed or moved sources. Existing source folders also refresh as `brain sync` encounters their files.

## Common issues

| Symptom | What to try |
| --- | --- |
| Python or the `brain` command is missing | Check the Python version and call the virtual environment's interpreter explicitly with `-m secondbrain`. On Windows, also try `brain.cmd` from the checkout. |
| Installation cannot resolve a runtime wheel | Use Python 3.11 on a supported operating system and architecture. Read the first package error from pip. A 32-bit Python distribution may lack compatible model-runtime wheels. |
| Search fails during a model download | Check connectivity and available disk space, then run `brain models` or `brain models --audio` before opening the UI. Previously indexed text can be queried with `--lexical-only` while semantic models are unavailable. |
| Audio indexing reports missing support | Install `".[audio]"` into the same virtual environment, then index or sync again. |
| Browser opened with an empty collection | Check the `--home` path on both the index and serve commands. Run `brain status` with that same path. |
| A date-relative demo query misses results | The app uses file modification time. Use a query without a date or regenerate the synthetic fixtures with `python scripts/generate_playground.py` if you want a fresh date-based playground. |
| Port 8765 is in use | Start the app with `brain serve --port 8766` and open the corresponding loopback address. |
| A field answer reports insufficient evidence | Name the merchant or product, check the returned files, and request an OCR retry if the image is readable. Open the original when readings conflict. |

## Development and a wheel install

From the repository root, install developer tools, run the test suite, and build the wheel:

```sh
python -m pip install -e ".[audio,dev]"
python -m pytest -q
python -m build
```

To install the built wheel in an activated environment use `python -m pip install dist/adaptive_secondbrain-0.2.0-py3-none-any.whl`. For optional audio use `python -m pip install "dist/adaptive_secondbrain-0.2.0-py3-none-any.whl[audio]"`. The package includes the browser assets. For benchmark and paper reproduction, see the [research instructions](../research/README.txt).
