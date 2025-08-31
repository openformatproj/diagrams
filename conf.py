# -*- coding: utf-8 -*-
"""
Configuration file for the block diagram editor.

This file contains all the constants used throughout the application,
including colors, dimensions, and UI strings.
"""

from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt

# --- Version ---
__version__ = '0.1.0'

# --- General Visuals ---
# Z-Values (Layering) - Higher values are drawn on top.
Z_VALUE_WIRE = 1
Z_VALUE_PIN = 2
Z_VALUE_BLOCK = 2 # Pins and Blocks are on the same level
Z_VALUE_TEXT = 3

# Pen Styles & Widths
PEN_WIDTH_GRID = 1
PEN_WIDTH_NORMAL = 2
PEN_WIDTH_HIGHLIGHT = 3
PEN_STYLE_NO_PEN = Qt.NoPen

# --- Scene & View ---
GRID_SIZE = 20
GRID_COLOR_LIGHT = QColor(230, 230, 230)
SCENE_RECT_X = -5000
SCENE_RECT_Y = -5000
SCENE_RECT_WIDTH = 10000
SCENE_RECT_HEIGHT = 10000

# View Panning and Zooming
MIN_ZOOM_FACTOR = 0.1
MAX_ZOOM_FACTOR = 5.0
ZOOM_STEP_FACTOR = 1.15 # Factor for each zoom step (e.g., wheel scroll)
FIT_VIEW_MARGIN = 50 # Margin in pixels around items when fitting to view
SUPER_BLOCK_MARGIN_X = 120 # Horizontal margin in pixels for the super block bounding box
SUPER_BLOCK_MARGIN_Y = 40 # Vertical margin in pixels for the super block bounding box
INITIAL_ZOOM_FACTOR = 1.0
FLOAT_COMPARISON_EPSILON = 1e-9 # For comparing float values like zoom levels

# --- Item Colors ---
# Block Colors
BLOCK_COLOR = QColor(100, 100, 100, 180)
BLOCK_BORDER_COLOR = QColor(50, 50, 50)
BLOCK_HIGHLIGHT_COLOR = QColor(255, 170, 0)
BLOCK_LOCKED_BORDER_COLOR = QColor(200, 0, 0) # A strong red for locked blocks
BLOCK_TEXT_COLOR = QColor(255, 255, 255)

# Block Pin Colors
BLOCK_PIN_RADIUS = 6
BLOCK_PIN_COLOR = QColor(0, 150, 200)
BLOCK_PIN_LOCKED_COLOR = QColor(0, 100, 130) # Darker version of BLOCK_PIN_COLOR
BLOCK_PIN_HIGHLIGHT_COLOR = QColor(255, 100, 0)

# Diagram Pin Colors
DIAGRAM_PIN_RADIUS = 6
DIAGRAM_PIN_COLOR = QColor(0, 180, 100)
DIAGRAM_PIN_LOCKED_COLOR = QColor(0, 120, 70) # Darker version of DIAGRAM_PIN_COLOR
DIAGRAM_PIN_HIGHLIGHT_COLOR = QColor(100, 255, 150)
DIAGRAM_OUTPUT_PIN_COLOR = QColor(200, 0, 150)
DIAGRAM_OUTPUT_PIN_LOCKED_COLOR = QColor(130, 0, 100) # Darker version of DIAGRAM_OUTPUT_PIN_COLOR
DIAGRAM_OUTPUT_PIN_HIGHLIGHT_COLOR = QColor(255, 100, 200)
DIAGRAM_PIN_TEXT_COLOR = QColor(0, 0, 0)

# Wire Colors
WIRE_COLOR = QColor(0, 0, 0)
WIRE_HIGHLIGHT_COLOR = QColor(255, 0, 0)
WIRE_LOCKED_COLOR = QColor(0, 0, 200) # A strong blue for locked wires

# --- Fonts ---
FONT_SIZE_BLOCK_PIN = 8
FONT_SIZE_DIAGRAM_PIN = 9
FONT_SIZE_BLOCK_TITLE = 10
FONT_WEIGHT_BLOCK_TITLE = QFont.Bold

# --- Item Dimensions & Spacing ---
# General
INITIAL_ITEM_X = 0
INITIAL_ITEM_Y = 0
MIN_ITEM_DIMENSION = GRID_SIZE # Min snapped size for blocks

# Block Dimensions & Padding
STANDARD_BLOCK_WIDTH = GRID_SIZE * 8 # Default width for blocks (e.g., 160px)
MIN_BLOCK_INTERNAL_PADDING = 5 # Min padding around title and after pin labels
BLOCK_TITLE_TOP_MARGIN = 4 # Vertical space between title and block's top edge

# Block Pin Spacing & Visuals
BLOCK_PIN_TEXT_PADDING = 4 # Padding between pin and its text label
BLOCK_PIN_DIAMETER_SCALE = 2.0 # Multiplier for pin radius to get diameter
BLOCK_PIN_TOP_PADDING = GRID_SIZE # From block top to center of first pin
BLOCK_PIN_BOTTOM_PADDING = GRID_SIZE # From center of last pin to block bottom
BLOCK_PIN_VERTICAL_SPACING = GRID_SIZE # Vertical distance between pin centers

# Diagram Pin Spacing & Visuals
DIAGRAM_PIN_TEXT_PADDING = 4 # Padding between pin and its text label
DIAGRAM_PIN_DIAMOND_SCALE = 1.5 # Scale factor for the diamond shape of diagram pins
DIAGRAM_PIN_VERTICAL_SPACING = GRID_SIZE * 2 # Vertical spacing between diagram pins on super block edge

# --- Wire & Routing ---
WIRE_STUB_LENGTH = GRID_SIZE # The minimum horizontal length of the "stub" coming out of a pin
BEZIER_DX_FACTOR = 0.5  # Multiplier for horizontal distance in Bezier calculation. Affects curve "roundness".
BEZIER_STUB_FACTOR = 3.0  # Multiplier for stub length in Bezier calculation.
WIRE_CLICKABLE_WIDTH = 10 # Width of the clickable area around a wire

# --- Auto-Placement ---
BLOCK_PLACEMENT_SEARCH_MAX_RADIUS = 500 * GRID_SIZE # Max search radius for spiral search in grid units

# --- Optimization Cost Function ---
# Weights for combining different metrics into a single cost score.
COST_FUNCTION_INTERSECTION_WEIGHT = 100.0 # Each intersection adds a high penalty.
COST_FUNCTION_WIRELENGTH_WEIGHT = 0.1   # Each grid unit of wire length adds a small penalty.

# --- Optimization Algorithm Defaults ---
# Default parameters for Randomized Hill Climbing
OPTIMIZER_RHC_DEFAULT_ITERATIONS = 200
OPTIMIZER_RHC_DEFAULT_MOVE_STEP_GRID_UNITS = 8
OPTIMIZER_RHC_DEFAULT_REPORTING_INTERVAL = 20

# Default parameters for Simulated Annealing
OPTIMIZER_SA_DEFAULT_ITERATIONS = 1500
OPTIMIZER_SA_DEFAULT_INITIAL_TEMP = 10.0
OPTIMIZER_SA_DEFAULT_COOLING_RATE = 0.995
OPTIMIZER_SA_DEFAULT_MOVE_STEP_GRID_UNITS = 8
OPTIMIZER_SA_DEFAULT_REPORTING_INTERVAL = 50
OPTIMIZER_SA_MIN_TEMPERATURE = 1e-9 # Temperature at which it's considered "frozen"

# Whether to use detailed area calculation for wire intersections or a simple boolean check.
USE_DETAILED_INTERSECTION_CHECK = False

# --- Main Window ---
MAIN_WINDOW_DEFAULT_X = 100
MAIN_WINDOW_DEFAULT_Y = 100
MAIN_WINDOW_DEFAULT_WIDTH = 1200
MAIN_WINDOW_DEFAULT_HEIGHT = 800
STATUS_BAR_TIMEOUT_MS = 5000

# --- Debug ---
DEBUG_BBOX_COLOR = QColor(0, 0, 0)
DEBUG_BBOX_PEN_STYLE = Qt.DashLine
DEBUG_BBOX_PEN_WIDTH = 1

class Key:
    """Symbolic constants for dictionary keys used in data structures."""
    # For optimization moves dictionary
    MOVE_TYPE = 'type'
    BLOCK = 'block'
    PIN_TYPE = 'pin_type'
    PINS = 'pins'
    # For JSON serialization
    FORMAT_VERSION_KEY = "format_version"
    PART_KEY = "part"
    IDENTIFIER_KEY = "identifier"
    CLASS_KEY = "class"
    PORTS_KEY = "ports"
    INNER_PARTS_KEY = "inner_parts"
    CONNECTIONS_KEY = "connections"
    NAME_KEY = "name"
    DIRECTION_KEY = "direction"
    SOURCE_KEY = "source"
    DESTINATION_KEY = "destination"
    PART_ID_KEY = "part_id"
    PORT_ID_KEY = "port_id"

class UI:
    """A container for all UI-related strings, organized by context."""
    MAIN_WINDOW_TITLE = "Qt5 Block Diagram Editor"

    class Menu:
        """Strings used in context menus and toolbars."""
        ADD_BLOCK_PIN = "Add Block Pin" # Also in README.md
        RENAME_BLOCK = "Rename Block" # Also in README.md
        RENAME_DIAGRAM_INPUT = "Rename Diagram Input" # Also in README.md
        RENAME_DIAGRAM_OUTPUT = "Rename Diagram Output" # Also in README.md
        LOCK_BLOCK_POSITION = "Lock Position" # Also in README.md
        UNLOCK_BLOCK_POSITION = "Unlock Position" # Also in README.md
        LOCK_WIRE = "Lock Wire" # Also in README.md
        UNLOCK_WIRE = "Unlock Wire" # Also in README.md
        DELETE_BLOCK = "Delete Block" # Also in README.md
        DELETE_WIRE = "Delete Wire" # Also in README.md
        DELETE_DIAGRAM_INPUT = "Delete Diagram Input" # Also in README.md
        DELETE_DIAGRAM_OUTPUT = "Delete Diagram Output" # Also in README.md
        ADD_BLOCK = "Add Block" # Also in README.md
        ADD_DIAGRAM_INPUT = "Add Diagram Input" # Also in README.md
        ADD_DIAGRAM_OUTPUT = "Add Diagram Output" # Also in README.md
        FIT_TO_VIEW = "Fit to View" # Also in README.md
        OPTIMIZE_PLACEMENT = "Optimize Placement" # Also in README.md
        UNLOCK_EVERYTHING = "Unlock Everything" # Also in README.md
        EXPORT_TO_SVG = "Export to SVG" # Also in README.md
        TOOLBAR_ACTIONS = "Actions"

    PIN_TYPE_INPUT_LOWER = "input"
    PIN_TYPE_OUTPUT_LOWER = "output"

    class Dialog:
        """Strings used in QInputDialog and QMessageBox dialogs."""
        NEW_BLOCK_PIN_TITLE = "New Block Pin"
        NEW_BLOCK_PIN_LABEL = "Enter block pin name:"
        BLOCK_PIN_TYPE_TITLE = "Block Pin Type"
        BLOCK_PIN_TYPE_LABEL = "Select block pin type:"
        BLOCK_PIN_TYPE_INPUT_STR = "Input"
        BLOCK_PIN_TYPE_OUTPUT_STR = "Output"
        NEW_SYS_INPUT_TITLE = "New Diagram Input"
        NEW_SYS_INPUT_LABEL = "Enter input name:"
        NEW_SYS_OUTPUT_TITLE = "New Diagram Output"
        NEW_SYS_OUTPUT_LABEL = "Enter output name:"
        NEW_BLOCK_TITLE = "New Block"
        NEW_BLOCK_LABEL = "Enter block name:"
        RENAME_BLOCK_TITLE = "Rename Block"
        RENAME_BLOCK_LABEL = "Enter new name:"
        RENAME_DIAGRAM_PIN_TITLE = "Rename Diagram Pin"
        RENAME_DIAGRAM_PIN_LABEL = "Enter new name:"
        # Dialog Titles for Warnings
        ADD_PIN_FAILED_TITLE = "Add Pin Failed"
        RENAME_FAILED_TITLE = "Rename Failed"
        CREATION_FAILED_TITLE = "Creation Failed"
        OPTIMIZATION_FAILED_TITLE = "Optimization Failed"
        OPTIMIZER_UNEXPECTED_ERROR_MSG = "An unexpected error occurred during optimization. See console for details."
        EXPORT_DIALOG_TITLE = "Export to SVG"
        EXPORT_SVG_FILTER = "Scalable Vector Graphics (*.svg)"
        DIALOG_DEFAULT_CHOICE_INDEX = 0

    class SVG:
        """Strings used for SVG generation."""
        TITLE = "Block Diagram"
        DESCRIPTION = "Exported from Qt5 Block Diagram Editor"

    class Serializer:
        """Strings and constants for the DiagramSerializer."""
        FORMAT_VERSION = "1.0"
        BLOCK_NAME_FORMAT = "{part_id}:{part_class}"

    class Log:
        """Strings used for logging messages to the console."""
        NO_BLOCK_SELECTED = "No block selected. Select a block to add a pin."
        NOT_A_BLOCK = "Selected item is not a block. Select a block to add a pin."
        ADDED_INPUT_BLOCK_PIN = "Added input pin '{pin_name}' to block '{selected_block.name}'"
        ADDED_OUTPUT_BLOCK_PIN = "Added output pin '{pin_name}' to block '{selected_block.name}'"
        WIRE_CONNECTED = "Wire connected from {source_desc} to {dest_desc}"
        WIRE_CREATION_FAILED_NO_PIN = "Cannot create wire: start or end pin is None."
        WIRE_CREATION_FAILED_PIN_TYPE = "Invalid connection: Must connect an output pin to an input pin."
        WIRE_CREATION_FAILED_INPUT_FULL = "Cannot create wire: Input pin '{pin_name}' is already connected."
        CREATION_FAILED_DUPLICATE_NAME = "Creation failed: Item of type '{item_type}' with name '{name}' already exists."
        CONNECTION_EXISTS = "Connection already exists."
        NO_VALID_PIN = "No valid pin to connect to."
        BLOCK_RENAMED = "Block '{old_name}' renamed to '{new_name}'"
        DIAGRAM_PIN_RENAMED = "Diagram pin '{old_name}' renamed to '{new_name}'"
        ADDED_NEW_BLOCK = "Added new block '{name}' at scene position: ({pos_x}, {pos_y})"
        ADDED_NEW_DIAGRAM_INPUT = "Added new diagram input '{name}' at scene position: ({pos_x}, {pos_y})"
        ADDED_AUTOPLACED_BLOCK = "Added auto-placed block '{name}' at scene position: ({pos_x}, {pos_y})"
        ADDED_NEW_DIAGRAM_OUTPUT = "Added new diagram output '{name}' at scene position: ({pos_x}, {pos_y})"

        # Programmatic API and Optimizer Logs
        BLOCK_MOVED = "Moved block '{block_name}' to ({x}, {y})."
        BLOCK_NOT_FOUND = "Error: Could not find block named '{block_name}'."
        BLOCK_PIN_REORDER_MISMATCH = "Error: Pin names for '{block_name}' do not match existing pins."
        BLOCK_PINS_REORDERED = "Reordered {pin_type} pins for block '{block_name}'."
        DIAGRAM_PIN_REORDER_INVALID_TYPE = "Error: Invalid pin type specified for diagram pin reordering."
        DIAGRAM_PIN_REORDER_MISMATCH = "Error: Pin names for diagram {type_name}s do not match existing pins."
        DIAGRAM_PINS_REORDERED = "Reordered diagram {type_name} pins."
        DIAGRAM_COST_BREAKDOWN = "Diagram cost components: intersection_score={intersection_score}, wire_length_score={wire_length_score:.2f}"
        DIAGRAM_COST_TOTAL = "Total diagram cost: {cost:.2f}"

        # Optimizer Logs
        OPTIMIZER_START = "Starting layout optimization..."
        OPTIMIZER_NO_BLOCKS = "No blocks to optimize."
        OPTIMIZER_NO_MOVES = "No optimizable moves available (e.g., only one block, no pins to reorder)."
        OPTIMIZER_INITIAL_COST = "Initial cost: {cost:.2f}"
        OPTIMIZER_ITERATION_STATUS = "Iteration {iteration}/{total_iterations}... Current cost: {cost:.2f}"
        OPTIMIZER_COMPLETE = "Optimization complete. Final cost: {cost:.2f}"
        OPTIMIZER_NOT_CONFIGURED = "Error: No optimizer function has been provided."
        OPTIMIZER_RHC_PARAMS = "Randomized Hill Climbing parameters: iterations={iterations}, move_step_grid_units={move_step_grid_units}."
        OPTIMIZER_SA_PARAMS = "Simulated Annealing parameters: initial_temp={initial_temp}, cooling_rate={cooling_rate}."
        OPTIMIZER_ACCEPTED_BAD_MOVE = "Accepted non-improving move with cost {new_cost:.2f} (delta: {delta:.2f}) at temp {temperature:.2f}."
        OPTIMIZER_CANCELLED = "Optimization cancelled by user."
        OPTIMIZER_UNEXPECTED_ERROR_LOG = "An unexpected error occurred during optimization: {error}"
        UNLOCKED_ALL_ITEMS = "Unlocked all items."
        EXPORT_SUCCESS = "Diagram successfully exported to {file_path}"
        EXPORT_EMPTY_DIAGRAM = "Cannot export an empty diagram."
        SERIALIZATION_ONLY_STRUCTURAL = "Serialization is only supported for structural parts."
        JSON_MISSING_ROOT_PART = "JSON data is missing the root 'part' object."

        # Generic Error Messages
        ROUTING_MANAGER_INVALID = "Wire requires a routing_manager instance with a 'calculate_path' method."
        NOT_IMPLEMENTED_ERROR_SUBCLASS = "Subclasses must implement this method."
        QAPP_INSTANCE_REQUIRED = "A QApplication instance must be created before calling start()."
        PIN_ALREADY_EXISTS = "A pin named '{pin_name}' already exists on this block."
        ITEM_NAME_ALREADY_EXISTS = "An item of type '{item_type}' with the name '{name}' already exists."