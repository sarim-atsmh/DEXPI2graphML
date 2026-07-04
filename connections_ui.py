"""Tkinter UI to inspect a component's upstream / downstream connections.

Layout (see UI.png):
    DEXPI XML: [ path entry ............ ] [ Browse ]
    [ before list ]   [ ID entry ]   [ after list ]
                      [  button   ]

The middle entry takes a component ID (e.g. ``C-044``). Pressing the button
(or Enter) fills the left list with components connected *into* it (before /
upstream) and the right list with components it connects *out to* (after /
downstream), using the logic in ``see_connections``.

The chosen XML file is remembered between sessions in ``.connections_xml_path``
next to this script, so it is pre-filled in the Browse field on next launch.
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import see_connections as sc

CONFIG_PATH = Path(__file__).resolve().parent / ".connections_xml_path"


def load_last_path() -> str:
    """Return the previously used XML path, or the module default."""
    try:
        saved = CONFIG_PATH.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    except OSError:
        pass
    return sc.XML_PATH


def save_last_path(path: str) -> None:
    try:
        CONFIG_PATH.write_text(path, encoding="utf-8")
    except OSError:
        pass


def _format(conn_id: str) -> str:
    """`C-050` -> `C-050: PV` (name omitted when unknown)."""
    name = sc.get_name(conn_id)
    return f"{conn_id}: {name}" if name else conn_id


def ensure_loaded() -> bool:
    """Load the file currently in the path field if it isn't already active.

    Returns True on success; sets the status line and returns False otherwise.
    """
    path = path_var.get().strip()
    if not path:
        status.set("Select a DEXPI XML file first.")
        return False
    if sc.root is not None and path == sc.XML_PATH:
        return True
    if not Path(path).is_file():
        status.set(f"File not found: {path}")
        return False
    try:
        sc.load_xml(path)
    except Exception as exc:  # malformed XML, missing sections, etc.
        status.set(f"Failed to load XML: {exc}")
        return False
    save_last_path(path)
    return True


def browse() -> None:
    initial = path_var.get().strip()
    initial_dir = str(Path(initial).parent) if initial else str(Path.home())
    chosen = filedialog.askopenfilename(
        title="Select DEXPI XML file",
        initialdir=initial_dir,
        filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
    )
    if not chosen:
        return
    path_var.set(chosen)
    if ensure_loaded():
        before_list.delete(0, tk.END)
        after_list.delete(0, tk.END)
        status.set(f"Loaded: {Path(chosen).name}")


def show_connections() -> None:
    before_list.delete(0, tk.END)
    after_list.delete(0, tk.END)
    comp_name_var.set("")

    if not ensure_loaded():
        return

    comp_id = entry.get().strip()
    if not comp_id:
        status.set("Enter a component ID.")
        return

    name = sc.get_name(comp_id)
    comp_name_var.set(name if name else "(no name found)")

    before = [_format(c.attrib["FromID"]) for c in sc.get_from_of(comp_id)]
    after = [_format(c.attrib["ToID"]) for c in sc.get_to_of(comp_id)]

    for row in before:
        before_list.insert(tk.END, row)
    for row in after:
        after_list.insert(tk.END, row)

    if not before and not after:
        status.set(f"No connections found for '{comp_id}'.")
    else:
        status.set(f"{comp_id}: {len(before)} before, {len(after)} after.")


def _build_list(parent, title: str):
    """A titled listbox with a vertical scrollbar; returns (frame, listbox)."""
    frame = ttk.Frame(parent)
    ttk.Label(frame, text=title, anchor="center").pack(fill="x", pady=(0, 4))
    inner = ttk.Frame(frame)
    inner.pack(fill="both", expand=True)
    scrollbar = ttk.Scrollbar(inner, orient="vertical")
    listbox = tk.Listbox(inner, yscrollcommand=scrollbar.set, activestyle="none")
    scrollbar.config(command=listbox.yview)
    scrollbar.pack(side="right", fill="y")
    listbox.pack(side="left", fill="both", expand=True)
    return frame, listbox


root = tk.Tk()
root.title("DEXPI Connections")
root.geometry("900x560")
root.minsize(640, 400)

# --- top: file browse row -------------------------------------------------- #
browse_row = ttk.Frame(root, padding=(12, 12, 12, 0))
browse_row.pack(fill="x")
ttk.Label(browse_row, text="DEXPI XML:").pack(side="left")
path_var = tk.StringVar(value=load_last_path())
ttk.Entry(browse_row, textvariable=path_var).pack(
    side="left", fill="x", expand=True, padx=6
)
ttk.Button(browse_row, text="Browse", command=browse).pack(side="left")

# --- middle: two lists + centered controls --------------------------------- #
container = ttk.Frame(root, padding=12)
container.pack(fill="both", expand=True)
container.columnconfigure(0, weight=1)  # before list
container.columnconfigure(1, weight=0)  # middle controls
container.columnconfigure(2, weight=1)  # after list
container.rowconfigure(0, weight=1)

before_frame, before_list = _build_list(container, "Before (upstream)")
before_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

middle = ttk.Frame(container)
middle.grid(row=0, column=1, sticky="n", pady=40)
ttk.Label(middle, text="Component ID", anchor="center").pack(pady=(0, 4))
entry = ttk.Entry(middle, width=16, justify="center", font=("TkDefaultFont", 14))
entry.pack()
ttk.Button(middle, text="Show Connections", command=show_connections).pack(
    pady=(8, 0), fill="x"
)
comp_name_var = tk.StringVar(value="")
ttk.Label(
    middle,
    textvariable=comp_name_var,
    anchor="center",
    justify="center",
    wraplength=160,
    font=("TkDefaultFont", 11, "italic"),
).pack(pady=(8, 0), fill="x")

after_frame, after_list = _build_list(container, "After (downstream)")
after_frame.grid(row=0, column=2, sticky="nsew", padx=(12, 0))

# --- bottom: status bar ---------------------------------------------------- #
status = tk.StringVar(value="Enter a component ID and press Show Connections.")
ttk.Label(root, textvariable=status, relief="sunken", anchor="w", padding=(8, 3)).pack(
    fill="x", side="bottom"
)

entry.bind("<Return>", lambda _event: show_connections())
entry.focus_set()

if __name__ == "__main__":
    root.mainloop()
