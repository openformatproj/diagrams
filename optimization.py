# -*- coding: utf-8 -*-
"""
This module contains algorithms for optimizing the block diagram layout.
"""

import random
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Callable

from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtWidgets import QApplication

import diagrams.conf as conf
from diagrams.engine import PinType, MoveType, _is_rect_overlapping, OptimizationError

import math # For simulated annealing
if TYPE_CHECKING:
    from diagrams.engine import MainWindow

def _apply_and_evaluate_move(main_window: 'MainWindow', move: Dict[str, Any], move_step: float, cost_params: Optional[Dict[str, Any]] = None) -> Optional[Tuple[float, Callable]]:
    """
    Helper function to apply a move, calculate new cost, and return a revert function.

    Args:
        cost_params (Dict[str, Any], optional): Parameters for the cost function,
            such as weights for different metrics.

    Returns:
        Optional[Tuple[float, Callable]]: A tuple containing the new cost and a
        revert function if the move was valid. Returns None if the move was
        invalid (e.g., caused a collision).
    """
    if move[conf.Key.MOVE_TYPE] == MoveType.MOVE_BLOCK:
        block = move[conf.Key.BLOCK]
        # Defensive check: do not move a locked block.
        if block.is_locked:
            return None
        original_pos = block.pos()
        new_pos = original_pos + QPointF(random.uniform(-move_step, move_step), random.uniform(-move_step, move_step))
        snapped_x = round(new_pos.x() / conf.GRID_SIZE) * conf.GRID_SIZE
        snapped_y = round(new_pos.y() / conf.GRID_SIZE) * conf.GRID_SIZE
        snapped_pos = QPointF(snapped_x, snapped_y)

        proposed_rect = QRectF(snapped_pos, block.rect().size())
        if _is_rect_overlapping(main_window.scene, proposed_rect, block):
            return None

        main_window.move_block(block.name, snapped_pos.x(), snapped_pos.y())
        revert_func = lambda: main_window.move_block(block.name, original_pos.x(), original_pos.y())

    elif move[conf.Key.MOVE_TYPE] == MoveType.REORDER_BLOCK_PINS:
        block, pin_type = move[conf.Key.BLOCK], move[conf.Key.PIN_TYPE]
        pins_dict = block.input_pins if pin_type == PinType.INPUT else block.output_pins
        original_order = sorted(pins_dict.keys(), key=lambda k: pins_dict[k].index)
        new_order = original_order[:]
        random.shuffle(new_order)

        main_window.set_block_pin_order(block.name, pin_type, new_order)
        revert_func = lambda: main_window.set_block_pin_order(block.name, pin_type, original_order)

    elif move[conf.Key.MOVE_TYPE] == MoveType.REORDER_DIAGRAM_PINS:
        pin_type, pins = move[conf.Key.PIN_TYPE], move[conf.Key.PINS]
        original_order = [p.name for p in sorted(pins, key=lambda p: p.scenePos().y())]
        new_order = original_order[:]
        random.shuffle(new_order)

        main_window.set_diagram_pin_order(pin_type, new_order)
        revert_func = lambda: main_window.set_diagram_pin_order(pin_type, original_order)
    else:
        return None

    new_cost = main_window.calculate_diagram_cost(cost_params=cost_params)
    return new_cost, revert_func

def _run_optimization_loop(
    main_window: 'MainWindow',
    possible_moves: List[Dict[str, Any]],
    iterations: int,
    move_step: float,
    reporting_interval: int,
    cost_params: Dict[str, Any],
    strategy_func: Callable[['MainWindow', float, float, Dict[str, Any]], bool],
    strategy_state: Dict[str, Any],
    post_iteration_hook: Optional[Callable[[Dict[str, Any]], None]] = None
) -> float:

    """A generic optimization loop that uses a strategy pattern."""
    # --- Initial State Setup ---
    main_window.show_progress_bar(iterations)
    current_cost = main_window.calculate_diagram_cost(cost_params=cost_params)
    main_window.log_message(conf.UI.Log.OPTIMIZER_INITIAL_COST.format(cost=current_cost))

    # --- Main Loop ---
    for i in range(iterations):
        if main_window.is_shutting_down:
            main_window.log_message(conf.UI.Log.OPTIMIZER_CANCELLED)
            break

        move = random.choice(possible_moves)
        result = _apply_and_evaluate_move(main_window, move, move_step, cost_params=cost_params)

        if result is None:
            continue

        new_cost, revert_func = result

        if strategy_func(main_window, current_cost, new_cost, strategy_state):
            current_cost = new_cost
        else:
            revert_func()

        if post_iteration_hook:
            post_iteration_hook(strategy_state)

        main_window.update_progress_bar(i + 1)
        if (i + 1) % reporting_interval == 0:
            main_window.log_message(conf.UI.Log.OPTIMIZER_ITERATION_STATUS.format(iteration=i+1, total_iterations=iterations, cost=current_cost))
            QApplication.processEvents()

    return current_cost

def _hill_climbing_strategy(main_window: 'MainWindow', current_cost: float, new_cost: float, state: Dict[str, Any]) -> bool:
    """
    Strategy for simple hill-climbing: only accept improvements.

    Args:
        main_window (MainWindow): The main window instance.
        current_cost (float): The current cost of the diagram.
        new_cost (float): The new cost after a proposed move.
        state (Dict[str, Any]): The state dictionary for the strategy.

    Returns:
        bool: True if the move should be accepted, False otherwise.
    """
    return new_cost < current_cost

def run_randomized_hill_climbing(main_window: 'MainWindow', possible_moves: List[Dict[str, Any]], params: Optional[Dict[str, Any]] = None) -> float:
    """
    Runs a randomized hill-climbing optimization algorithm.

    This function iterates for a set number of times, randomly applying a move from
    the provided list. If the move reduces cost, it is kept.

    Args:
        main_window (MainWindow): The main application window instance.
        possible_moves (List[Dict[str, Any]]): A list of possible optimization
            moves (e.g., moving a block, reordering pins).
        params (Dict[str, Any], optional): A dictionary of parameters for the
            algorithm, such as 'iterations' and 'move_step_grid_units'.

    Returns:
        float: The final cost score of the diagram.
    """
    if params is None:
        params = {}

    # Get parameters, using conf.py for defaults
    iterations = params.get('iterations', conf.OPTIMIZER_RHC_DEFAULT_ITERATIONS)
    move_step_grid_units = params.get('move_step_grid_units', conf.OPTIMIZER_RHC_DEFAULT_MOVE_STEP_GRID_UNITS)
    reporting_interval = params.get('reporting_interval', conf.OPTIMIZER_RHC_DEFAULT_REPORTING_INTERVAL)
    move_step = conf.GRID_SIZE * move_step_grid_units

    main_window.log_message(conf.UI.Log.OPTIMIZER_RHC_PARAMS.format(iterations=iterations, move_step_grid_units=move_step_grid_units))

    return _run_optimization_loop(
        main_window,
        possible_moves,
        iterations=iterations,
        move_step=move_step,
        reporting_interval=reporting_interval,
        cost_params=params,
        strategy_func=_hill_climbing_strategy,
        strategy_state={},
        post_iteration_hook=None
    )

def _simulated_annealing_strategy(main_window: 'MainWindow', current_cost: float, new_cost: float, state: Dict[str, Any]) -> bool:
    """
    Strategy for simulated annealing: accept worse moves with decreasing probability.

    Args:
        main_window (MainWindow): The main window instance.
        current_cost (float): The current cost of the diagram.
        new_cost (float): The new cost after a proposed move.
        state (Dict[str, Any]): The state dictionary for the strategy.

    Returns:
        bool: True if the move should be accepted, False otherwise.
    """
    delta = new_cost - current_cost
    if delta < 0:
        return True

    temperature = state.get('temperature', 1.0)
    if temperature < conf.OPTIMIZER_SA_MIN_TEMPERATURE: # Effectively zero, no chance to accept a bad move
        return False

    acceptance_prob = math.exp(-delta / temperature)
    if random.random() < acceptance_prob:
        main_window.log_message(conf.UI.Log.OPTIMIZER_ACCEPTED_BAD_MOVE.format(new_cost=new_cost, delta=delta, temperature=temperature))
        return True

    return False

def run_simulated_annealing(main_window: 'MainWindow', possible_moves: List[Dict[str, Any]], params: Optional[Dict[str, Any]] = None) -> float:
    """
    Runs a simulated annealing optimization algorithm.

    This algorithm can accept moves that temporarily increase cost,
    allowing it to escape local minima. The probability of accepting a
    "bad" move decreases as the "temperature" cools down.

    Args:
        main_window (MainWindow): The main application window instance.
        possible_moves (List[Dict[str, Any]]): A list of possible optimization moves.
        params (Dict[str, Any], optional): A dictionary of parameters for the
            algorithm: 'iterations', 'move_step_grid_units', 'initial_temp', 'cooling_rate'.

    Returns:
        float: The final cost score of the diagram.
    """
    if params is None:
        params = {}

    # Get parameters, using conf.py for defaults
    iterations = params.get('iterations', conf.OPTIMIZER_SA_DEFAULT_ITERATIONS)
    move_step_grid_units = params.get('move_step_grid_units', conf.OPTIMIZER_SA_DEFAULT_MOVE_STEP_GRID_UNITS)
    initial_temp = params.get('initial_temp', conf.OPTIMIZER_SA_DEFAULT_INITIAL_TEMP)
    cooling_rate = params.get('cooling_rate', conf.OPTIMIZER_SA_DEFAULT_COOLING_RATE)
    reporting_interval = params.get('reporting_interval', conf.OPTIMIZER_SA_DEFAULT_REPORTING_INTERVAL)
    move_step = conf.GRID_SIZE * move_step_grid_units

    main_window.log_message(conf.UI.Log.OPTIMIZER_SA_PARAMS.format(initial_temp=initial_temp, cooling_rate=cooling_rate))

    # Prepare state and hooks for the generic loop
    strategy_state = {'temperature': initial_temp}

    def sa_post_hook(state: Dict[str, Any]) -> None:
        """Cools the temperature after each iteration."""
        state['temperature'] *= cooling_rate

    return _run_optimization_loop(
        main_window,
        possible_moves,
        iterations=iterations,
        move_step=move_step,
        reporting_interval=reporting_interval,
        cost_params=params,
        strategy_func=_simulated_annealing_strategy,
        strategy_state=strategy_state,
        post_iteration_hook=sa_post_hook
    )
