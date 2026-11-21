"""Check the installed CLI and web assets from outside the source checkout."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--module", action="store_true", help="Exercise the supported Python module entry point")
    options = parser.parse_args()
    wheel = options.wheel.resolve(strict=True)
    with TemporaryDirectory(prefix="secondbrain-wheel-") as directory:
        root = Path(directory)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        bin_dir = environment / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        brain = [str(bin_dir / ("brain.exe" if os.name == "nt" else "brain"))]
        if options.module:
            brain = [str(python), "-I", "-m", "secondbrain"]
        subprocess.run([str(python), "-m", "pip", "install", str(wheel), "httpx>=0.27,<1"], cwd=root, check=True)
        version = subprocess.check_output([*brain, "--version"], cwd=root, text=True).strip()
        subprocess.run([*brain, "--home", "collection", "init", "--no-vision", "--no-ocr"], cwd=root, check=True)
        repair = subprocess.check_output([*brain, "--home", "collection", "repair", "--dry-run"], cwd=root)
        assert json.loads(repair)["pending"] == 0
        probe = '''
from importlib.metadata import distribution
from fastapi.testclient import TestClient
from secondbrain.api import create_app

package = distribution("adaptive-secondbrain")
assert package.version == CLI_VERSION
assert any(ep.group == "console_scripts" and ep.name == "brain" and ep.value == "secondbrain.cli:main"
           for ep in package.entry_points)
with TestClient(create_app("collection")) as client:
    assert client.get("/openapi.json").json()["info"]["version"] == CLI_VERSION
    assert client.get("/").status_code == 200
    for asset in ("app.js", "styles.css", "fonts/DM-Sans.ttf"):
        assert client.get(f"/static/{asset}").status_code == 200
'''
        subprocess.run([str(python), "-I", "-c", f"CLI_VERSION = {version!r}\n{probe}"], cwd=root, check=True)
        print(f"Installed wheel smoke passed for {version}")


if __name__ == "__main__":
    main()
