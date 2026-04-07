import tkinter as tk
from tkinter import ttk


class MainUI:
    """Builds the application UI and exposes widget/variable references."""

    def __init__(self, root, config, callbacks):
        self.root = root
        self.config = config
        self.callbacks = callbacks

        self.elec_chk_vars = {}
        self.master_chk_vars = {}
        self.gas_chk_vars = {}
        self.lockable_widgets = []
        
        self.is_expanded = False

        self.start_btn = None
        self.toggle_button = None
        self.detail_panel = None
        self.estop_var = None
        self.estop_chk = None
        self.exclusive_var = None
        self.exclusive_chk = None
        self.btn_init = None
        self.btn_exit = None
        self.log_combo = None
        self.status_label = None

    def infer_cell_for_gas(self, gas_name):
        """Infer related cell from gas line name using direct/suffix matching."""
        upper_name = gas_name.upper().replace("-", " ")

        # 1) Direct match: if full cell name appears in gas label.
        for cell_name in self.config.cells_and_electrodes.keys():
            if cell_name.upper() in upper_name:
                return cell_name

        # 2) Suffix match: Gas Line A -> Cell A, Gas Line B -> Cell B.
        tokens = upper_name.split()
        suffix = None
        for token in reversed(tokens):
            if len(token) == 1 and token.isalpha():
                suffix = token
                break

        if suffix:
            for cell_name in self.config.cells_and_electrodes.keys():
                cell_tokens = cell_name.upper().replace("-", " ").split()
                if cell_tokens and cell_tokens[-1] == suffix:
                    return cell_name

        return None

    def build(self):
        # 1. START button at top
        control_frame = tk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        self.start_btn = tk.Button(
            control_frame,
            text="START",
            bg="#ccffcc",
            fg="black",
            height=2,
            font=("Arial", 11, "bold"),
            command=self.callbacks["on_start"],
            width=40,
        )
        self.start_btn.pack(pady=(0, 10))
        self.lockable_widgets.append(self.start_btn)

        # 2. E-STOP (never locked)
        estop_frame = tk.Frame(self.root)
        estop_frame.pack(padx=10, pady=10)

        self.estop_var = tk.IntVar()
        self.estop_chk = tk.Checkbutton(
            estop_frame,
            text="E-STOP [Esc]",
            bg="#ffcccc",
            fg="black",
            activebackground="red",
            activeforeground="white",
            variable=self.estop_var,
            indicatoron=0,
            selectcolor="red",
            height=2,
            font=("Arial", 11, "bold"),
            command=self.callbacks["on_estop"],
            width=40,
        )
        self.estop_chk.pack()

        # 3. Toggle button for accordion
        toggle_frame = tk.Frame(self.root)
        toggle_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.toggle_button = tk.Button(
            toggle_frame,
            text="> Individual Controls",
            command=self.toggle_panel,
            relief=tk.GROOVE,
            font=("Arial", 10),
            height=1,
        )
        self.toggle_button.pack(anchor=tk.W)
        self.lockable_widgets.append(self.toggle_button)

        # 4. Detail panel (initially hidden, placed right after toggle button)
        self.detail_panel = tk.Frame(self.root, padx=15, pady=15)
        self.build_accordion_panel()

        # 5. Bottom controls (Init, Exit)
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        self.btn_init = tk.Button(
            bottom_frame,
            text="Initialize All",
            width=15,
            font=("Arial", 10),
            height=1,
            command=self.callbacks["on_init_btn"],
        )
        self.btn_init.pack(side=tk.LEFT)
        self.lockable_widgets.append(self.btn_init)

        self.btn_exit = tk.Button(
            bottom_frame,
            text="Exit",
            width=15,
            font=("Arial", 10),
            height=1,
            command=self.callbacks["on_close"],
        )
        self.btn_exit.pack(side=tk.RIGHT)
        self.lockable_widgets.append(self.btn_exit)

        # Log history (above bottom controls)
        log_frame = tk.Frame(self.root)
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))
        tk.Label(log_frame, text="Log History:", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.log_combo = ttk.Combobox(log_frame, state="readonly", font=("Arial", 10))
        self.log_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # Status label
        self.status_label = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W,
                                     font=("Arial", 11, "bold"), bg="#f0f0f0", pady=5)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def build_accordion_panel(self):
        """Build the accordion detail panel with cell-first grouping."""
        top_row = tk.Frame(self.detail_panel)
        top_row.pack(fill=tk.X, anchor=tk.W, pady=(0, 8))

        self.exclusive_var = tk.IntVar(value=1)
        self.exclusive_chk = tk.Checkbutton(
            top_row,
            text="Exclusive Interlock",
            variable=self.exclusive_var,
            command=self.callbacks.get("on_toggle_exclusive"),
            font=("Arial", 10),
        )
        self.exclusive_chk.pack(anchor=tk.W)
        self.lockable_widgets.append(self.exclusive_chk)

        cells_row = tk.Frame(self.detail_panel)
        cells_row.pack(fill=tk.X, anchor=tk.W)

        cell_to_gases = {cell: [] for cell in self.config.cells_and_electrodes.keys()}
        unassigned_gases = []

        for gname, servo in self.config.servo_map.items():
            if servo.get("pin", -1) < 0:
                continue

            related_cell = self.infer_cell_for_gas(gname)
            if related_cell in cell_to_gases:
                cell_to_gases[related_cell].append(gname)
            else:
                unassigned_gases.append(gname)

        for cell_name, elecs in self.config.cells_and_electrodes.items():
            cell_frame = tk.LabelFrame(cells_row, text=cell_name, font=("bold", 10), padx=6, pady=6)
            cell_frame.pack(side=tk.LEFT, fill=tk.Y, anchor=tk.N, padx=(0, 8), pady=5)

            elec_frame = tk.LabelFrame(cell_frame, text="Electrodes", padx=4, pady=4)
            elec_frame.pack(fill=tk.X, anchor=tk.N)

            master_var = tk.IntVar()
            master_cb = tk.Checkbutton(
                elec_frame,
                text="All",
                variable=master_var,
                command=lambda c=cell_name: self.callbacks["on_master_click"](c),
            )
            master_cb.pack(anchor=tk.W)
            self.master_chk_vars[cell_name] = master_var
            self.lockable_widgets.append(master_cb)

            for ename in elecs:
                elec_var = tk.IntVar()
                etype = ename.split("-")[1]
                elec_cb = tk.Checkbutton(
                    elec_frame,
                    text=etype,
                    variable=elec_var,
                    padx=10,
                    command=lambda n=ename: self.callbacks["on_elec_click"](n),
                )
                elec_cb.pack(anchor=tk.W)
                self.elec_chk_vars[ename] = elec_var
                self.lockable_widgets.append(elec_cb)

            gas_frame = tk.LabelFrame(cell_frame, text="Gas", padx=4, pady=4)
            gas_frame.pack(fill=tk.X, anchor=tk.N, pady=(6, 0))

            for gname in cell_to_gases.get(cell_name, []):
                gas_var = tk.IntVar()
                gas_cb = tk.Checkbutton(
                    gas_frame,
                    text=gname,
                    variable=gas_var,
                    command=lambda n=gname: self.callbacks["on_gas_click"](n),
                )
                gas_cb.pack(anchor=tk.W)
                self.gas_chk_vars[gname] = gas_var
                self.lockable_widgets.append(gas_cb)

            if not cell_to_gases.get(cell_name):
                tk.Label(gas_frame, text="(none)", fg="#666666").pack(anchor=tk.W)

        if unassigned_gases:
            other_frame = tk.LabelFrame(cells_row, text="Other", font=("bold", 10), padx=6, pady=6)
            other_frame.pack(side=tk.LEFT, fill=tk.Y, anchor=tk.N, padx=(0, 8), pady=5)

            other_gas_frame = tk.LabelFrame(other_frame, text="Gas", padx=4, pady=4)
            other_gas_frame.pack(fill=tk.X, anchor=tk.N)

            for gname in unassigned_gases:
                gas_var = tk.IntVar()
                gas_cb = tk.Checkbutton(
                    other_gas_frame,
                    text=gname,
                    variable=gas_var,
                    command=lambda n=gname: self.callbacks["on_gas_click"](n),
                )
                gas_cb.pack(anchor=tk.W)
                self.gas_chk_vars[gname] = gas_var
                self.lockable_widgets.append(gas_cb)

    def toggle_panel(self):
        """Toggle the accordion detail panel visibility."""
        if self.is_expanded:
            self.detail_panel.pack_forget()
            self.toggle_button.config(text="> Individual Controls")
        else:
            self.detail_panel.pack(fill=tk.BOTH, expand=False, padx=10, pady=10)
            self.toggle_button.config(text="v Individual Controls")
        self.is_expanded = not self.is_expanded
