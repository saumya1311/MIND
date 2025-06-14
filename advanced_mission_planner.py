# advanced_mission_planner.py
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import json
import os
from datetime import datetime
from tkinterweb import HtmlFrame

# Import the core logic (unchanged)
from mission_logic import MissionState, DecisionTreeBuilder, drone_objective_function

class DatabaseManager:
    """Handles all SQLite database operations. (Unchanged)"""
    def __init__(self, db_name="mission_plans.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.setup_tables()

    def setup_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                score REAL NOT NULL,
                initial_fuel REAL,
                max_time REAL,
                targets TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS plan_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                step_number INTEGER NOT NULL,
                action TEXT NOT NULL,
                FOREIGN KEY (plan_id) REFERENCES plans (id)
            )
        ''')
        self.conn.commit()

    def save_plan(self, plan_data, plan_steps):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            "INSERT INTO plans (timestamp, score, initial_fuel, max_time, targets) VALUES (?, ?, ?, ?, ?)",
            (timestamp, plan_data['score'], plan_data['fuel'], plan_data['time'], plan_data['targets'])
        )
        plan_id = self.cursor.lastrowid
        for i, step in enumerate(plan_steps, 1):
            self.cursor.execute("INSERT INTO plan_steps (plan_id, step_number, action) VALUES (?, ?, ?)", (plan_id, i, step))
        self.conn.commit()
        return plan_id

class MissionPlannerGUI(tk.Tk):
    """The main Tkinter application window."""
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.planner_instance = None
        self.move_costs = {} # NEW: Dictionary to store user-defined move costs
        
        self.title("Automated Mission Planner")
        self.geometry("1400x900") # Increased size for more controls

        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_pane, width=450, height=900)
        main_pane.add(left_frame, weight=1)

        self.viz_frame = HtmlFrame(main_pane, messages_enabled=False)
        main_pane.add(self.viz_frame, weight=2)

        self._create_controls(left_frame)
        self._populate_default_actions() # NEW: Populate GUI with default data

    def _create_controls(self, parent):
        # Frame for basic mission constraints
        constraints_frame = ttk.LabelFrame(parent, text="Mission Constraints")
        constraints_frame.pack(padx=10, pady=10, fill=tk.X)

        self.fuel_var = tk.StringVar(value="100")
        self.time_var = tk.StringVar(value="50")
        self.targets_var = tk.StringVar(value="A, B")

        ttk.Label(constraints_frame, text="Initial Fuel:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(constraints_frame, textvariable=self.fuel_var).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        ttk.Label(constraints_frame, text="Max Time:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(constraints_frame, textvariable=self.time_var).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(constraints_frame, text="Target Locations (comma-sep):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(constraints_frame, textvariable=self.targets_var).grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        constraints_frame.grid_columnconfigure(1, weight=1)

        # --- NEW: Frame for defining Action Parameters ---
        actions_frame = ttk.LabelFrame(parent, text="Action Parameters")
        actions_frame.pack(padx=10, pady=10, fill=tk.X)

        # Survey cost
        self.survey_cost_var = tk.StringVar(value="5")
        ttk.Label(actions_frame, text="Survey Time Cost:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(actions_frame, textvariable=self.survey_cost_var).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Move cost definition form
        move_form_frame = ttk.Frame(actions_frame)
        move_form_frame.grid(row=1, column=0, columnspan=2, pady=(10,0))
        
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.move_fuel_var = tk.StringVar()
        self.move_time_var = tk.StringVar()
        
        ttk.Label(move_form_frame, text="From:").grid(row=0, column=0, padx=2)
        ttk.Entry(move_form_frame, textvariable=self.from_var, width=8).grid(row=0, column=1, padx=2)
        ttk.Label(move_form_frame, text="To:").grid(row=0, column=2, padx=2)
        ttk.Entry(move_form_frame, textvariable=self.to_var, width=8).grid(row=0, column=3, padx=2)
        ttk.Label(move_form_frame, text="Fuel:").grid(row=1, column=0, padx=2)
        ttk.Entry(move_form_frame, textvariable=self.move_fuel_var, width=8).grid(row=1, column=1, padx=2)
        ttk.Label(move_form_frame, text="Time:").grid(row=1, column=2, padx=2)
        ttk.Entry(move_form_frame, textvariable=self.move_time_var, width=8).grid(row=1, column=3, padx=2)

        move_button_frame = ttk.Frame(actions_frame)
        move_button_frame.grid(row=2, column=0, columnspan=2, pady=5)
        ttk.Button(move_button_frame, text="Add/Update Move", command=self.add_move).pack(side=tk.LEFT, padx=5)
        ttk.Button(move_button_frame, text="Remove Selected", command=self.remove_move).pack(side=tk.LEFT, padx=5)

        # Treeview to display defined moves
        self.moves_tree = ttk.Treeview(actions_frame, columns=("from", "to", "fuel", "time"), show="headings", height=6)
        self.moves_tree.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.moves_tree.heading("from", text="From")
        self.moves_tree.heading("to", text="To")
        self.moves_tree.heading("fuel", text="Fuel Cost")
        self.moves_tree.heading("time", text="Time Cost")
        self.moves_tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # --- End of New Section ---

        # Action Buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(padx=10, pady=10, fill=tk.X)
        ttk.Button(button_frame, text="Generate Optimal Plan", command=self.run_planner).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        ttk.Button(button_frame, text="Visualize Tree", command=self.generate_visualization).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Results Display
        results_frame = ttk.LabelFrame(parent, text="Optimal Plan")
        results_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.results_text = tk.Text(results_frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.results_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

    # --- NEW: Methods to manage the action parameter GUI ---

    def _populate_default_actions(self):
        """Fills the GUI with some example move data for convenience."""
        default_moves = {
            'Base': {'A': {'fuel': 20, 'time': 10}, 'B': {'fuel': 30, 'time': 15}},
            'A': {'Base': {'fuel': 20, 'time': 10}, 'B': {'fuel': 40, 'time': 20}},
            'B': {'Base': {'fuel': 30, 'time': 15}, 'A': {'fuel': 40, 'time': 20}}
        }
        for from_loc, destinations in default_moves.items():
            for to_loc, costs in destinations.items():
                self.from_var.set(from_loc)
                self.to_var.set(to_loc)
                self.move_fuel_var.set(costs['fuel'])
                self.move_time_var.set(costs['time'])
                self.add_move(show_message=False)

    def add_move(self, show_message=True):
        """Adds or updates a move cost from the form to the internal dictionary and the Treeview."""
        from_loc = self.from_var.get().strip()
        to_loc = self.to_var.get().strip()
        try:
            fuel = float(self.move_fuel_var.get())
            time = float(self.move_time_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Fuel and Time must be numbers.")
            return

        if not all([from_loc, to_loc]):
            messagebox.showerror("Invalid Input", "From and To locations cannot be empty.")
            return

        # Update internal dictionary
        if from_loc not in self.move_costs:
            self.move_costs[from_loc] = {}
        self.move_costs[from_loc][to_loc] = {'fuel': fuel, 'time': time}

        # Update Treeview
        item_id = f"{from_loc}->{to_loc}"
        if self.moves_tree.exists(item_id):
            self.moves_tree.item(item_id, values=(from_loc, to_loc, fuel, time))
        else:
            self.moves_tree.insert("", tk.END, iid=item_id, values=(from_loc, to_loc, fuel, time))

        if show_message:
            messagebox.showinfo("Success", f"Move from {from_loc} to {to_loc} added/updated.")

    def remove_move(self):
        """Removes a selected move from the Treeview and internal dictionary."""
        selected_items = self.moves_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select a move to remove.")
            return

        for item_id in selected_items:
            values = self.moves_tree.item(item_id, "values")
            from_loc, to_loc = values[0], values[1]
            
            # Remove from internal dictionary
            if from_loc in self.move_costs and to_loc in self.move_costs[from_loc]:
                del self.move_costs[from_loc][to_loc]
                if not self.move_costs[from_loc]: # clean up empty 'from' keys
                    del self.move_costs[from_loc]

            # Remove from Treeview
            self.moves_tree.delete(item_id)

    def on_tree_select(self, event):
        """When a user clicks a move in the tree, populate the form for easy editing."""
        selected_items = self.moves_tree.selection()
        if not selected_items:
            return
        
        item_id = selected_items[0]
        values = self.moves_tree.item(item_id, "values")
        self.from_var.set(values[0])
        self.to_var.set(values[1])
        self.move_fuel_var.set(values[2])
        self.move_time_var.set(values[3])

    # --- MODIFIED: run_planner now builds 'actions' from GUI state ---
    
    def run_planner(self):
        try:
            # 1. Get constraints from GUI
            initial_fuel = float(self.fuel_var.get())
            max_time = float(self.time_var.get())
            targets = {t.strip() for t in self.targets_var.get().split(',') if t.strip()}

            # 2. **Build the 'actions' dictionary from the user inputs**
            survey_time = float(self.survey_cost_var.get())
            
            if not self.move_costs:
                messagebox.showerror("Configuration Error", "No move actions have been defined. Please add at least one move.")
                return

            actions = {
                'move': {'costs': self.move_costs},
                'survey': {'cost': {'time': survey_time}}
            }
            
            # 3. Define Mission State and Constraints
            initial_state = MissionState(location='Base', fuel=initial_fuel, time_elapsed=0, intel_gathered=set())
            constraints = {'MAX_TIME': max_time, 'INITIAL_FUEL': initial_fuel, 'TARGET_LOCATIONS': targets}
            
            # 4. Build the tree
            self.planner_instance = DecisionTreeBuilder(initial_state, actions, constraints, drone_objective_function)
            self.planner_instance.build_tree(max_depth=7)
            
            # 5. Find and display the best plan
            best_plan, best_score = self.planner_instance.find_best_plan()

            self.results_text.config(state=tk.NORMAL)
            self.results_text.delete(1.0, tk.END)
            if best_plan:
                result_str = f"Plan Found! Score: {best_score:.2f}\n----------------------------\n"
                result_str += "\n".join(f"Step {i+1}: {step}" for i, step in enumerate(best_plan))
                self.results_text.insert(tk.END, result_str)

                # 6. Save to SQLite database
                plan_data = {'score': best_score, 'fuel': initial_fuel, 'time': max_time, 'targets': ', '.join(sorted(list(targets)))}
                plan_id = self.db_manager.save_plan(plan_data, best_plan)
                self.results_text.insert(tk.END, f"\n\nPlan saved to database with ID: {plan_id}")
            else:
                self.results_text.insert(tk.END, "No viable plan found within the given constraints.")
            
            self.results_text.config(state=tk.DISABLED)

        except ValueError:
            messagebox.showerror("Input Error", "Please ensure all constraints and costs are valid numbers.")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    # --- Unchanged Methods Below ---
    def _convert_node_to_dict(self, node):
        return {
            "name": node.action or "Start",
            "children": [self._convert_node_to_dict(child) for child in node.children]
        }
    
    def generate_visualization(self):
        if not self.planner_instance:
            messagebox.showinfo("Info", "Please generate a plan first.")
            return
        try:
            tree_dict = self._convert_node_to_dict(self.planner_instance.root)
            json_data = json.dumps(tree_dict, indent=2)
            with open("template.html", "r") as f:
                template_content = f.read()
            final_html = template_content.replace("__DATA_HERE__", json_data)
            viz_filepath = os.path.abspath("visualization.html")
            with open(viz_filepath, "w") as f:
                f.write(final_html)
            self.viz_frame.load_file(f"file:///{viz_filepath}")
        except Exception as e:
            messagebox.showerror("Visualization Error", f"Could not generate visualization: {e}")

if __name__ == "__main__":
    db = DatabaseManager()
    app = MissionPlannerGUI(db)
    app.mainloop()