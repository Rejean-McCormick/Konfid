# -*- coding: utf-8 -*-
from pathlib import Path
import hashlib, shutil, tkinter as tk
from tkinter import messagebox

ROOT = Path(r"C:\mycode\Konfid\konfid")
TARGET = ROOT / r"src/konfid/cli.py"
BACKUP = Path(r"C:\mycode\Konfid\konfid\.koali-update-backups\worker-db-init-20261005-194655\src\konfid\cli.py")
EXPECTED = "1295a9664031dc0a3329bda3e53791d83f393727c11ddaf7504d8188e96bc74e"

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()

app = tk.Tk()
app.withdraw()

if not TARGET.exists() or digest(TARGET) != EXPECTED:
    messagebox.showerror(
        "Rollback Konfid",
        "Rollback refusé : cli.py a été modifié après le hotfix."
    )
    raise SystemExit(2)

shutil.copy2(BACKUP, TARGET)
messagebox.showinfo("Rollback Konfid", "Rollback terminé.")
