"""Reproducible, fail-on-drift source-only Konfid tour patch installer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent.parent
MANIFEST = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
STORE = ROOT.parent / "Tandem_Local" / "konfid_tour_p1" / "backups"


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def valid_path(rel: str) -> Path:
    # Fixed paths from the package, not user input. Defend against traversal and local symlinks.
    pure = Path(rel)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Unsafe patch path: {rel}")
    path = ROOT / pure
    for parent in [path, *list(path.parents)[:len(pure.parts)-1]]:
        if parent.is_symlink():
            raise ValueError(f"Symlink in patch target: {rel}")
    return path


def check_root() -> None:
    if not (ROOT / "src" / "konfid" / "auth.py").is_file() or not (ROOT / "pyproject.toml").is_file():
        raise ValueError(
            f"Repo cible incorrect: {ROOT}. Attendu: ...\\Konfid\\konfid contenant src/konfid/auth.py"
        )


def status() -> tuple[dict[str, str], bool]:
    check_root()
    results = {}
    ok = True
    for relative, meta in MANIFEST.items():
        dest = valid_path(relative)
        data = dest.read_bytes() if dest.exists() else None
        actual = hash_bytes(data) if data is not None else None
        expected = (PACKAGE / "payload" / relative).read_bytes()
        if hash_bytes(expected) != meta["updated"]:
            raise ValueError(f"Invalid package integrity: {relative}")
        if actual == meta["updated"]:
            state = "ALREADY_UPDATED"
        elif actual == meta["baseline"]:
            state = "READY"
        else:
            state = "DRIFT"
            ok = False
        results[relative] = state
        print(f"[{state}] {relative}")
    return results, ok


def staged_tests() -> str:
    # All work remains in system temp; never run tests against the user's Konfid DB.
    with tempfile.TemporaryDirectory(prefix="konfid_tour_p1_") as dir_name:
        temp = Path(dir_name)
        for dirname in ("src", "tests"):
            shutil.copytree(
                ROOT / dirname, temp / dirname,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.sqlite", "*.db", "*.db-wal", "*.db-shm"),
            )
        shutil.copy2(ROOT / "pyproject.toml", temp / "pyproject.toml")
        for relative in MANIFEST:
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PACKAGE / "payload" / relative, dst)
        import compileall
        if not compileall.compile_dir(str(temp / "src"), quiet=1, force=True):
            raise ValueError("Python source compile failed")
        if not compileall.compile_dir(str(temp / "tests"), quiet=1, force=True):
            raise ValueError("Python tests compile failed")
        print("[PASS] Compilation Python sur copie isolee")
        if importlib.util.find_spec("pytest") is None or any(
            importlib.util.find_spec(name) is None for name in ("sqlalchemy", "fastapi", "jwt", "pydantic")
        ):
            print("[ATTENTE] Suite pytest Konfid non disponible dans cet interpreteur; pas de qualification runtime locale")
            return "NOT_RUN"
        env = os.environ.copy()
        # Override any ambient deployment credentials/configuration: tests target a brand new disposable SQLite file.
        env.update({
            "KONFID_DEV_MODE": "true", "KONFID_ENV": "test", "KONFID_POLICY_MODE": "local",
            "KONFID_DATABASE_URL": "sqlite:///" + (temp / "konfid-test.sqlite").as_posix(),
            "KONFID_REQUIRE_ACTOR_ASSERTION": "false", "KONFID_REQUIRE_ACTOR_AUTHORIZED_PARTY": "false",
        })
        env.pop("PYTHONPATH", None)
        print("[TEST] Suite Konfid native sur copie isolee, SQLite ephemere (aucun service distant)")
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--disable-warnings"],
            cwd=temp, env=env, check=False, timeout=120,
        )
        if completed.returncode:
            raise ValueError(f"Suite native Konfid en echec (exit={completed.returncode}). Aucune source modifiee.")
        return "PASS"


def install() -> None:
    result, ok = status()
    if not ok:
        raise ValueError("DRIFT constate. Aucun fichier modifie.")
    if all(v == "ALREADY_UPDATED" for v in result.values()):
        print("[OK] Patch deja installe; aucun changement")
        return
    staged_tests()
    # Recheck after tests: no race with another editor or process.
    result, ok = status()
    if not ok:
        raise ValueError("DRIFT apres tests. Aucune source modifiee.")
    if all(v == "ALREADY_UPDATED" for v in result.values()):
        print("[OK] Deja installe; aucun changement")
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = STORE / timestamp
    backup.mkdir(parents=True, exist_ok=False)
    backup_manifest = {}
    for relative, state in result.items():
        if state != "READY":
            continue
        original = valid_path(relative)
        original_content = original.read_bytes() if original.exists() else None
        backup_manifest[relative] = {
            "was_present": original_content is not None,
            "original_sha256": hash_bytes(original_content) if original_content is not None else None,
            "updated_sha256": MANIFEST[relative]["updated"],
        }
        if original_content is not None:
            snapshot_file = backup / relative
            snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            snapshot_file.write_bytes(original_content)
    (backup / "backup_manifest.json").write_text(json.dumps(backup_manifest, sort_keys=True, indent=2), encoding="utf-8")
    written = []
    try:
        for relative in backup_manifest:
            path = valid_path(relative)
            actual = hash_bytes(path.read_bytes()) if path.exists() else None
            if actual != MANIFEST[relative]["baseline"]:
                raise ValueError(f"Changement concurrent : {relative}")
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=".konfid-tour-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write((PACKAGE / "payload" / relative).read_bytes())
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            written.append(relative)
    except Exception:
        for relative in reversed(written):
            path = valid_path(relative)
            original = backup_manifest[relative]
            if original["was_present"]:
                shutil.copy2(backup / relative, path)
            else:
                path.unlink(missing_ok=True)
        raise
    _, final_ok = status()
    if not final_ok:
        raise ValueError("Verification d'empreinte apres installation echouee")
    print(f"[OK] Konfid tour P1 installe; sauvegarde: {backup}")
    print("[INFO] Aucun Docker, kOA, Konfid runtime, DB ou configuration de production modifie")


def rollback() -> None:
    check_root()
    if not STORE.exists():
        raise ValueError("Aucune sauvegarde pour ce lot")
    candidates = sorted(STORE.glob("*/backup_manifest.json"), reverse=True)
    if not candidates:
        raise ValueError("Aucune sauvegarde pour ce lot")
    meta_path = candidates[0]
    entries = json.loads(meta_path.read_text(encoding="utf-8"))
    # Validate ALL files before reverting ANY file.
    for relative, meta in entries.items():
        target = valid_path(relative)
        if not target.is_file() or hash_bytes(target.read_bytes()) != meta["updated_sha256"]:
            raise ValueError(f"ROLLBACK_BLOQUE: contenu modifie depuis l'installation: {relative}")
    for relative, meta in entries.items():
        target = valid_path(relative)
        if meta["was_present"]:
            shutil.copy2(meta_path.parent / relative, target)
        else:
            target.unlink()
    meta_path.rename(meta_path.with_name("backup_manifest.RESTORED.json"))
    print(f"[OK] Retour arriere termine; sauvegarde: {meta_path.parent}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    print(f"=== KONFID / TANDEM / TOUR 3 SUR 8 / P1 / {mode.upper()} ===")
    print(f"[REPO] {ROOT}")
    print("[PORTEE] Sources locales uniquement; aucune DB, API, SSO, Docker ni VPS touche")
    try:
        if mode == "preview":
            _, ok = status()
            if not ok:
                raise ValueError("DRIFT: le contenu local ne correspond pas au snapshot")
            print("[OK] Apercu favorable; aucune source modifiee")
        elif mode == "install":
            install()
        elif mode == "verify":
            statuses, ok = status()
            if not ok or any(v != "ALREADY_UPDATED" for v in statuses.values()):
                raise ValueError("Patch absent, incomplet ou modifie")
            staged_tests()
            print("[OK] Sources conformes et controles disponibles passes")
        elif mode == "rollback":
            rollback()
        else:
            raise ValueError(f"Mode inconnu: {mode}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[BLOQUE] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
