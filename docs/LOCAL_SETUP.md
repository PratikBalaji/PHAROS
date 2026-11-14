# Run PHAROS on your computer

Install Python 3.11 or newer and Git. Node.js, Vercel and Sites are not required to run the app. An internet connection is required for the first dependency installation.

```bash
git clone https://github.com/PratikBalaji/PHAROS.git
cd PHAROS
python3 run.py
```

On Windows, use `py run.py`. If you already have the repository, run `git pull --ff-only` inside it instead of cloning again.

The launcher creates `.venv`, installs dependencies, creates `.env` without overwriting existing settings, and starts FastAPI on your computer. FastAPI serves both the included frontend and the API at the same address:

- Dashboard: http://127.0.0.1:8000
- Presentation: http://127.0.0.1:8000/presentation/
- API docs: http://127.0.0.1:8000/docs

No frontend build is necessary. Keep the terminal open; press Ctrl+C to stop. `python3 run.py --port 8080` chooses another port. `--reload` reloads backend code during development. `--setup-only` installs dependencies and creates configuration without starting the server.

## Your configuration and data

Edit `.env` in the project root. The launcher loads it before importing the backend. Existing shell environment values take precedence. Restart the server after editing settings. `.env`, `.venv` and `work/` are ignored by Git; they are not included in the downloadable source.

Drafts, approvals, bundles and logs live in `work/pharos.sqlite3` and persist across local restarts. Hosted records and hosting secrets are separate and are not automatically downloaded.

The default local configuration uses `PHAROS_DELIVERY_PROVIDER=inbox`, so the review/send workflow works without messaging credentials. To activate Photon SMS, set `PHAROS_DELIVERY_PROVIDER=photon` and fill in `PHOTON_API_KEY`, `PHOTON_SENDER_ID` and `PHOTON_SPACE_ID`; your project ID is already in the template. See [Photon setup](PHOTON_SETUP.md). Bedrock and other provider keys also belong in `.env`.

Local means the application and database run on your computer. Basemap tiles, live weather/fire data, Bedrock and Photon still use their external services. Replay fixtures, message templates and exercise recording do not need provider credentials. The map has a schematic fallback if tiles are unavailable.

If the dashboard previously used a different backend on this browser origin, open Integrations → Connect backend and enter `http://127.0.0.1:8000` (or your chosen port).

## Troubleshooting

- **Python not found:** install Python 3.11+ and reopen your terminal. On Windows try `py`; on macOS/Linux try `python3`.
- **venv unavailable on Linux:** install your distribution's Python venv package (often `python3-venv`).
- **Port already in use:** stop the old app or choose `--port 8080`.
- **Dependency installation fails:** check your network and the pip error printed above it, then rerun the launcher.
- **SMS setup required:** set all Photon values and ensure the sender/conversation are active SMS resources. Recording a multilingual bundle does not send SMS.

The launcher binds to `127.0.0.1` for use on this computer. It does not require a cloud deployment or change the existing hosted app.
