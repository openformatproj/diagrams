# -*- coding: utf-8 -*-
"""
A demonstration script for the block diagram editor.

This script creates an instance of the MainWindow, populates it with
a few example blocks and wires, and runs the Qt application.
"""

import sys
from functools import partial
# Import the necessary components from the engine library
from PyQt5.QtWidgets import QApplication
from diagrams.engine import MainWindow
from diagrams.optimization import run_simulated_annealing

def setup_demo_scene(main_window: MainWindow) -> None:
    """
    Populates the main window with a demo scene.

    This function uses the programmatic API to create a sample diagram.
    """
    # Use the programmatic API on the MainWindow to create items.
    block1 = main_window.create_block("Source Block", input_pins=["Control"], output_pins=["Out1", "Another Output"])
    block2 = main_window.create_block("Processor", input_pins=["InA", "InB"], output_pins=["Result", "Status"])
    block3 = main_window.create_block("Sink", input_pins=["Data"], output_pins=["Status"])

    # Create multiple diagram inputs and outputs to demonstrate the new auto-alignment.
    # The position argument is no longer needed.
    diagram_input1 = main_window.create_diagram_input("System Input 1")
    diagram_input2 = main_window.create_diagram_input("System Input 2")
    diagram_output1 = main_window.create_diagram_output("Final Result")
    diagram_output2 = main_window.create_diagram_output("Final Status")

    # Connect wires if all items were created successfully
    if all([block1, block2, block3, diagram_input1, diagram_input2, diagram_output1, diagram_output2]):
        main_window.scene.create_wire(block1.output_pins["Out1"], block2.input_pins["InA"])
        main_window.scene.create_wire(block1.output_pins["Another Output"], block3.input_pins["Data"])
        main_window.scene.create_wire(diagram_input1, block1.input_pins["Control"])
        main_window.scene.create_wire(diagram_input2, block2.input_pins["InB"])
        main_window.scene.create_wire(block2.output_pins["Result"], diagram_output1)
        main_window.scene.create_wire(block3.output_pins["Status"], diagram_output2)

if __name__ == "__main__":
    # A QApplication instance must be created before any QWidget.
    app = QApplication(sys.argv)

    # --- Configure and Create the Main Window ---

    # # --- Option 1: Randomized Hill Climbing ---
    # from diagrams.optimization import run_randomized_hill_climbing
    # optimizer_params = {
    #     'iterations': 500,
    #     'move_step_grid_units': 10
    # }
    # configured_optimizer = partial(run_randomized_hill_climbing, params=optimizer_params)

    # --- Option 2: Simulated Annealing (Currently Active) ---
    sa_params = {
        'iterations': 1500,
        'initial_temp': 15.0,
        'cooling_rate': 0.996,
        'move_step_grid_units': 15,
        'intersection_weight': 100.0,
        'wirelength_weight': 0.1
    }
    configured_optimizer = partial(run_simulated_annealing, params=sa_params)
    main_window = MainWindow(enable_logging=True, optimizer_func=configured_optimizer)

    # Populate the scene with a demo setup.
    setup_demo_scene(main_window)

    # Demonstrate the new bounding box feature
    # blocks_bbox = main_window.scene.get_blocks_bounding_box()
    # if not blocks_bbox.isEmpty():
    #     main_window.log_message(
    #         f"Bounding box of all blocks: "
    #         f"TopLeft({blocks_bbox.x():.2f}, {blocks_bbox.y():.2f}), "
    #         f"Size({blocks_bbox.width():.2f}x{blocks_bbox.height():.2f})"
    #     )
    #     # Draw the bounding box on the scene for visual confirmation.
    #     main_window.scene.draw_bounding_box(blocks_bbox)

    # Start the application event loop and exit with its return code.
    sys.exit(main_window.start())