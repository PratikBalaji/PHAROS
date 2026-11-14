"""One-command local PHAROS: python3 run.py (Windows: py run.py)."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'


def port_number(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('Port must be between 1 and 65535')
    return port


def prepare():
    python = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Creating the local Python environment…', flush=True)
        venv.EnvBuilder(with_pip=True).create(VENV)
    requirements = ROOT / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = VENV / '.pharos-requirements'
    if not stamp.exists() or stamp.read_text().strip() != fingerprint:
        print('Installing local dependencies (first run or requirements changed)…', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        stamp.write_text(fingerprint)
    if Path(sys.prefix).resolve() != VENV.resolve():
        os.execv(str(python), [str(python), str(ROOT / 'run.py'), *sys.argv[1:]])


def main():
    parser = argparse.ArgumentParser(description='Run the PHAROS dashboard and API locally.')
    parser.add_argument('--port', type=port_number, default=8000)
    parser.add_argument('--reload', action='store_true', help='Reload when backend Python files change')
    parser.add_argument('--setup-only', action='store_true', help='Install dependencies and create .env without starting the server')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Install Python 3.11 or newer, then run this command again.')
    os.chdir(ROOT)
    prepare()
    env_file = ROOT / '.env'
    try:
        # Exclusive creation preserves existing keys and settings on subsequent runs.
        descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as f:
            f.write((ROOT / '.env.example').read_text(encoding='utf-8'))
        print('Created .env. Add optional API keys there; it is excluded from Git.', flush=True)
    from dotenv import load_dotenv
    load_dotenv(env_file, override=False)
    if args.setup_only:
        print('Local setup is ready. Run python3 run.py (Windows: py run.py).')
        return
    print(f'PHAROS:      http://127.0.0.1:{args.port}', flush=True)
    print(f'Presentation: http://127.0.0.1:{args.port}/presentation/', flush=True)
    print(f'API docs:     http://127.0.0.1:{args.port}/docs', flush=True)
    print('Press Ctrl+C to stop.', flush=True)
    import uvicorn
    uvicorn.run('backend.app:app', host='127.0.0.1', port=args.port,
                reload=args.reload, reload_dirs=[str(ROOT / 'backend')] if args.reload else None)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'Local setup failed: {exc}', file=sys.stderr)
        sys.exit(1)
