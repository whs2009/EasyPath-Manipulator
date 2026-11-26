"""Materialize only public Python modules at the two pinned General engine revisions."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "EasyPath-Viewer": "ad5097c7faa171793cfe995723eaff00d85a10b1",
    "EasyPath-Converter": "26b919a41ffdfc5a07b521ee0697340ec040cca9",
}

def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])

def prepare(local=None):
    files = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, sha in PINS.items():
            repo = (local or Path(tmp)) / name
            if local is None:
                repo.mkdir()
                git(repo, "init", "-q")
                git(repo, "fetch", "-q", "--depth=1", f"https://github.com/whs2009/{name}.git", sha)
            if git(repo, "rev-parse", sha+"^{commit}").decode().strip() != sha:
                raise ValueError("Unexpected engine revision")
            for path in git(repo, "ls-tree", "-r", "--name-only", sha, "easypath").decode().splitlines():
                if not path.endswith(".py") or not path.startswith(("easypath/wsi/", "easypath/core/", "easypath/image/")) and path not in ("easypath/__init__.py","easypath/checkpoint_io.py"):
                    raise ValueError("Unexpected dependency: "+path)
                files[path] = git(repo, "show", sha+":"+path)
            if name == "EasyPath-Viewer":
                files["tools/slide_manipulator/engine.py"] = git(repo, "show", sha+":tools/slide_viewer/engine.py")
    for path, data in files.items():
        dest = ROOT/path
        dest.parent.mkdir(exist_ok=True, parents=True)
        if dest.exists():
            if dest.read_bytes() != data: raise ValueError("Local dependency differs: "+path)
        else:
            with dest.open("xb") as out: out.write(data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", type=Path, help="Parent directory of existing public Git clones")
    prepare(parser.parse_args().local)
