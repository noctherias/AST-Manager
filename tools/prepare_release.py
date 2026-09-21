"""Version every successful main build monotonically; never overwrite a release."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ast_app import __version__
from ast_app.updates import version_tuple, repository_name


def main():
    # Git tags are fetched by checkout (fetch-depth: 0), including previous releases.
    tags = subprocess.check_output(["git", "tag", "--list", "v*"], text=True).splitlines()
    previous = []
    for tag in tags:
        try: previous.append(version_tuple(tag))
        except ValueError: pass
    base = version_tuple(__version__)
    latest = max(previous, default=(0, 0, 0))
    version = base if base > latest else (latest[0], latest[1], latest[2] + 1)
    value = ".".join(map(str, version))
    (ROOT / "ast_app/__init__.py").write_text(f'__version__ = "{value}"\n', encoding="utf-8")
    repo = repository_name(os.environ["GITHUB_REPOSITORY"])
    (ROOT / "release_config.json").write_text(json.dumps({"repository": repo}) + "\n", encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"version={value}\ntag=v{value}\n")
    print(f"Release v{value}")


if __name__ == "__main__": main()
