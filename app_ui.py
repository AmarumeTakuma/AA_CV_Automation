import tkinter as tk


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

        self.start_btn = None
        self.estop_var = None
        self.estop_chk = None
        self.btn_init = None
        self.btn_exit = None
        self.status_label = None

    def build(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left column: electrodes
        left_col = tk.LabelFrame(main_frame, text="Electrodes", padx=5, pady=5)
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

        # Right column
        right_col = tk.Frame(main_frame)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        # Gas control
        gas_frame = tk.LabelFrame(right_col, text="Gas Control", padx=5, pady=5)
        gas_frame.pack(fill=tk.X, pady=5)
        for gname, servo in self.config.servo_map.items():
            if servo.get("pin", -1) < 0:
                continue
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

        # Measurement controls
        measure_frame = tk.LabelFrame(right_col, text="Measurement", padx=5, pady=5)
        measure_frame.pack(fill=tk.X, pady=5)

        self.start_btn = tk.Button(
            measure_frame,
            text="START",
            bg="#ccffcc",
            height=2,
            command=self.callbacks["on_start"],
        )
        self.start_btn.pack(fill=tk.X, pady=5)

        self.estop_var = tk.IntVar()
        self.estop_chk = tk.Checkbutton(
            measure_frame,
            text="E-STOP [Esc]",
            bg="#ffcccc",
            variable=self.estop_var,
            indicatoron=0,
            selectcolor="red",
            height=2,
            font=("Arial", 9, "bold"),
            command=self.callbacks["on_estop"],
        )
        self.estop_chk.pack(fill=tk.X, pady=5)

        # Bottom controls
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

        self.status_label = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
