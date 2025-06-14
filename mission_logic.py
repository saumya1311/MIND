# mission_logic.py
import copy

class MissionState:
    """Represents the state of the mission at any given point."""
    def __init__(self, location, fuel, time_elapsed, intel_gathered):
        self.location = location
        self.fuel = fuel
        self.time_elapsed = time_elapsed
        self.intel_gathered = intel_gathered

    def __repr__(self):
        return (f"State(loc={self.location}, fuel={self.fuel:.0f}, "
                f"time={self.time_elapsed}, intel={sorted(list(self.intel_gathered))})")

class Node:
    """Represents a node in our decision tree."""
    def __init__(self, state, parent=None, action=None, score=0):
        self.state = state
        self.parent = parent
        self.action = action
        self.children = []
        self.score = score

    def add_child(self, child_node):
        self.children.append(child_node)

    def __repr__(self):
        return f"Node(action={self.action}, score={self.score}, state={self.state})"

class DecisionTreeBuilder:
    def __init__(self, initial_state, actions, constraints, objective_function):
        self.root = Node(initial_state)
        self.actions = actions
        self.constraints = constraints
        self.objective_function = objective_function

    def build_tree(self, max_depth=5):
        self._expand_node(self.root, 0, max_depth)

    def _expand_node(self, node, depth, max_depth):
        if depth >= max_depth or self._is_terminal(node.state):
            node.score = self.objective_function(node.state, self.constraints)
            return

        valid_actions = self._get_valid_actions(node.state)
        if not valid_actions:
            node.score = self.objective_function(node.state, self.constraints)
            return

        for action_name, params in valid_actions.items():
            next_state = self._apply_action(node.state, action_name, params)
            action_str = f"{action_name}({params.get('target', '')})"
            child_node = Node(state=next_state, parent=node, action=action_str)
            node.add_child(child_node)
            self._expand_node(child_node, depth + 1, max_depth)

    def _is_terminal(self, state):
        if state.fuel <= 0 and state.location != 'Base': return True
        if state.time_elapsed >= self.constraints['MAX_TIME']: return True
        if self.constraints['TARGET_LOCATIONS'].issubset(state.intel_gathered) and state.location == 'Base': return True
        return False

    def _get_valid_actions(self, state):
        valid_actions = {}
        if 'move' in self.actions:
            for loc in self.actions['move']['costs']:
                if state.location != loc:
                    cost = self.actions['move']['costs'][state.location].get(loc, {})
                    if state.fuel >= cost.get('fuel', float('inf')):
                        valid_actions[f"move_to_{loc}"] = {'target': loc}
        if 'survey' in self.actions and state.location in self.constraints['TARGET_LOCATIONS'] and state.location not in state.intel_gathered:
            valid_actions["survey"] = {}
        return valid_actions

    def _apply_action(self, state, action_name, params):
        new_state = copy.deepcopy(state)
        if action_name.startswith("move_to"):
            target = params['target']
            cost = self.actions['move']['costs'][state.location][target]
            new_state.location = target
            new_state.fuel -= cost['fuel']
            new_state.time_elapsed += cost['time']
        elif action_name == "survey":
            cost = self.actions['survey']['cost']
            new_state.time_elapsed += cost['time']
            new_state.intel_gathered.add(state.location)
        return new_state

    def find_best_plan(self):
        best_leaf = self._find_best_leaf(self.root)
        if not best_leaf: return None, -float('inf')
        plan = []
        current_node = best_leaf
        while current_node.parent:
            plan.append(current_node.action)
            current_node = current_node.parent
        plan.reverse()
        return plan, best_leaf.score

    def _find_best_leaf(self, node):
        if not node.children: return node
        best_child_leaf = None
        max_score = -float('inf')
        for child in node.children:
            leaf = self._find_best_leaf(child)
            if leaf and leaf.score > max_score:
                max_score = leaf.score
                best_child_leaf = leaf
        return best_child_leaf

def drone_objective_function(state, constraints):
    score = 0
    score += len(state.intel_gathered) * 150
    score -= state.time_elapsed * 2
    score -= (constraints['INITIAL_FUEL'] - state.fuel) * 1
    if state.fuel <= 0 and state.location != 'Base': score -= 1000
    if state.time_elapsed >= constraints['MAX_TIME']: score -= 1000
    if constraints['TARGET_LOCATIONS'].issubset(state.intel_gathered) and state.location == 'Base': score += 500
    return score