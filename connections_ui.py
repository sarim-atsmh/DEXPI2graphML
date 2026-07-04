"""Tkinter UI to inspect a component's upstream / downstream connections.

Layout (see UI.png):
    [ before list ]   [ ID entry ]   [ after list ]
                      [  button   ]

The middle entry takes a component ID (e.g. ``C-044``). Pressing the button
(or Enter) fills the left list with components connected *into* it (before /
upstream) and the right list with components it connects *out to* (after /
downstream), using the logic in ``see_connections``.
"""

import tkinter as tk
from tkinter import ttk

import see_connections as sc


def _format(conn_id: str) -> str:
    """`C-050` -> `C-050: PV` (name omitted when unknown)."""
    name = sc.get_name(conn_id)
    return f"{conn_id}: {name}" if name else conn_id


def show_connections() -> None:
    comp_id = entry.get().strip()
    before_list.delete(0, tk.END)
    after_list.delete(0, tk.END)

    if not comp_id:
        status.set("Enter a component ID.")
        return

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
    """A titled listbox with a vertical scrollbar; returns the listbox."""
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
root.geometry("900x520")
root.minsize(640, 360)

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

after_frame, after_list = _build_list(container, "After (downstream)")
after_frame.grid(row=0, column=2, sticky="nsew", padx=(12, 0))

status = tk.StringVar(value="Enter a component ID and press Show Connections.")
ttk.Label(root, textvariable=status, relief="sunken", anchor="w", padding=(8, 3)).pack(
    fill="x", side="bottom"
)

entry.bind("<Return>", lambda _event: show_connections())
entry.focus_set()

if __name__ == "__main__":
    root.mainloop()
