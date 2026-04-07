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
        self.btn_init = None
        self.btn_exit = None
        self.log_combo = None
        self.status_label = None

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
            font=("Arial", 12, "bold"),
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
            font=("Arial", 9, "bold"),
            command=self.callbacks["on_estop"],
            width=40,
        )
        self.estop_chk.pack()

        # 3. Toggle button for accordion
        toggle_frame = tk.Frame(self.root)
        toggle_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.toggle_button = tk.Button(
            toggle_frame,
            text="> Open Individual Controls",
            command=self.toggle_panel,
            relief=tk.GROOVE,
        )
        self.toggle_button.pack(fill=tk.X)
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
            command=self.callbacks["on_init_btn"],
        )
        self.btn_init.pack(side=tk.LEFT)
        self.lockable_widgets.append(self.btn_init)

        self.btn_exit = tk.Button(
            bottom_frame,
            text="Exit",
            width=15,
            command=self.callbacks["on_close"],
        )
        self.btn_exit.pack(side=tk.RIGHT)
        self.lockable_widgets.append(self.btn_exit)

        # Log history (above bottom controls)
        log_frame = tk.Frame(self.root)
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))
        tk.Label(log_frame, text="Log History:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.log_combo = ttk.Combobox(log_frame, state="readonly", font=("Arial", 9))
        self.log_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # Status label
        self.status_label = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def build_accordion_panel(self):
        """Build the accordion detail panel (electrodes and gas control)."""
        # Left column: electrodes
        left_col = tk.LabelFrame(self.detail_panel, text="Electrodes", padx=5, pady=5)
        left_col.pack(side=tk.LEFT, fill=tk.Y, anchor=tk.N)

        for cell, elecs in self.config.cells_and_electrodes.items():
            cell_frame = tk.LabelFrame(left_col, text=cell, font=("bold", 10))
            cell_frame.pack(fill=tk.X, pady=5)

            master_var = tk.IntVar()
            master_cb = tk.Checkbutton(
                cell_frame,
                text="All",
                variable=master_var,
                command=lambda c=cell: self.callbacks["on_master_click"](c),
            )
            master_cb.pack(anchor=tk.W)
            self.master_chk_vars[cell] = master_var
            self.lockable_widgets.append(master_cb)

            for ename in elecs:
                elec_var = tk.IntVar()
                etype = ename.split("-")[1]
                elec_cb = tk.Checkbutton(
                    cell_frame,
                    text=etype,
                    variable=elec_var,
                    padx=10,
                    command=lambda n=ename: self.callbacks["on_elec_click"](n),
                )
                elec_cb.pack(anchor=tk.W)
                self.elec_chk_vars[ename] = elec_var
                self.lockable_widgets.append(elec_cb)

        # Right column: gas control
        right_col = tk.LabelFrame(self.detail_panel, text="Gas Control", padx=5, pady=5)
        right_col.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))

        for gname, servo in self.config.servo_map.items():
            if servo.get("pin", -1) < 0:
                continue
            gas_var = tk.IntVar()
            gas_cb = tk.Checkbutton(
                right_col,
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
            self.toggle_button.config(text="> Open Individual Controls")
        else:
            self.detail_panel.pack(fill=tk.BOTH, expand=False, padx=10, pady=10)
            self.toggle_button.config(text="v Close Individual Controls")
        self.is_expanded = not self.is_expanded
