# -*- coding: utf-8 -*-
"""
A Python module for creating a Qt5 canvas to design block diagrams with
connectable input and output pins.

This module provides the following classes:
- `Pin`: A namespace for pin type constants.
- `BlockPin`: Represents an input or output pin on a block.
- `DiagramPin`: A base class for standalone diagram input and output pins.
- `DiagramInputPin`: Represents a diagram's overall input.
- `DiagramOutputPin`: Represents a diagram's overall output.
- `Wire`: Represents a connection between two pins.
- `Block`: Represents a draggable and resizable block with pins.
- `RoutingManager`: Calculates smooth paths for wires.
- `BlockDiagramScene`: A QGraphicsScene for managing blocks and wires.
- `BlockDiagramView`: A QGraphicsView for displaying the scene, enabling panning and zooming.
- `MainWindow`: A QMainWindow to host the block diagram editor.
"""

from PyQt5.QtWidgets import (
    QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView, QMainWindow,
    QGraphicsEllipseItem, QGraphicsPathItem, QMenu, QStyle, QStatusBar, QProgressBar,
    QGraphicsRectItem, QGraphicsTextItem, QInputDialog, QGraphicsSceneContextMenuEvent, QGraphicsPolygonItem, QMessageBox, QGraphicsSceneMouseEvent, QGraphicsSceneHoverEvent,
    QStyleOptionGraphicsItem, QWidget, QFileDialog
)
from PyQt5.QtCore import ( # Added QObject to imports
    Qt, QPointF, QRectF, QLineF, QPoint,
    pyqtSignal)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QFont, QPainterPath, QPolygonF, QPainterPathStroker, QColor, QKeyEvent, QWheelEvent, QMouseEvent, QCloseEvent, QTransform
)
from PyQt5.QtSvg import (
    QSvgGenerator
)
import diagrams.conf as conf
from enum import Enum
import functools
from typing import Optional, Callable, Dict, Tuple, Union, List, Any
import math # For math.ceil
import itertools
import traceback

class PinType(Enum):
    """Defines the type of a pin, either as an input or an output."""
    INPUT = 0
    OUTPUT = 1

class MoveType(Enum):
    """Defines the type of optimization move."""
    MOVE_BLOCK = 0
    REORDER_BLOCK_PINS = 1
    REORDER_DIAGRAM_PINS = 2

class OptimizationError(Exception):
    """Custom exception for errors during the optimization process."""
    pass

class PinMixin:
    """
    A mixin for Pin classes (BlockPin, DiagramPin) to share common logic.

    This mixin provides attributes and methods related to connections (wires),
    locking, and basic properties like name and type.

    It assumes the class using it is a QGraphicsItem and that `init_pin` is called.
    """
    def init_pin(self, parent_block: Optional['Block'], pin_type: PinType, name: str):
        """Initializes the common attributes for a pin."""
        self.parent_block = parent_block
        self.pin_type = pin_type
        self._name = name
        self.wires: List['Wire'] = []

    def scenePos(self) -> QPointF:
        """
        Returns the absolute scene position of the pin's center.

        Returns:
            QPointF: The center position of the pin in scene coordinates.
        """
        return self.mapToScene(0, 0)

    @property
    def is_locked(self) -> bool:
        """A pin is considered locked if any of its connected wires are locked."""
        return any(wire.is_locked for wire in self.wires)

    def update_lock_state(self) -> None:
        """Updates the pin's appearance and movability based on its lock state."""
        is_locked = self.is_locked # Check the dynamic property
        self.setFlag(QGraphicsItem.ItemIsMovable, not is_locked)
        if is_locked:
            self.setBrush(QBrush(self.locked_color))
        else:
            # Revert to normal color. HoverMixin will handle hover highlight.
            self.setBrush(QBrush(self.color))
        self.update()

    def update_connected_wires(self) -> None:
        """Updates the geometry of all wires connected to this pin."""
        for wire in self.wires:
            wire.update_geometry()

def single_selection_only(func: Callable) -> Callable:
    """
    Decorator for contextMenuEvent methods to ensure they only run
    when a single item is selected.
    """
    @functools.wraps(func)
    def wrapper(self: QGraphicsItem, event: QGraphicsSceneContextMenuEvent) -> None:
        if self.scene() and len(self.scene().selectedItems()) > 1:
            # Let the base class handle it, which might be nothing.
            # This prevents showing an item-specific menu for a multi-selection.
            super(self.__class__, self).contextMenuEvent(event)
            return
        return func(self, event)
    return wrapper

def _is_rect_overlapping(scene: QGraphicsScene, rect: QRectF, item_to_ignore: QGraphicsItem) -> bool:
    """
    Checks if a rectangle overlaps with any Block or DiagramPin in the scene.

    Args:
        scene (QGraphicsScene): The scene to check within.
        rect (QRectF): The rectangle to check for overlaps.
        item_to_ignore (QGraphicsItem): The item instance being placed, to
            exclude it from collision checks.

    Returns:
        bool: True if the rectangle overlaps with an existing item, False otherwise.
    """
    for item in scene.items():
        if item == item_to_ignore:
            continue
        # We only care about collisions with other Blocks and DiagramPins
        if isinstance(item, (Block, DiagramPin)):
            if rect.intersects(item.sceneBoundingRect()):
                return True
    return False

def find_safe_placement(scene: QGraphicsScene,
                        item_width: float,
                        item_height: float,
                        item_to_ignore: QGraphicsItem,
                        search_center_hint: Optional[QPointF] = None,
                        is_centered: bool = False
                        ) -> QPointF:
    """
    Finds a non-overlapping position for an item in the scene.

    Performs a deterministic spiral search outwards from the `search_center_hint`
    to find the nearest available spot.

    Args:
        scene (QGraphicsScene): The scene to search within.
        item_width (float): The width of the item to place.
        item_height (float): The height of the item to place.
        item_to_ignore (QGraphicsItem): The item instance being placed, to
            exclude it from collision checks.
        search_center_hint (QPointF, optional): The center point for the
            search. Defaults to the scene origin.
        is_centered (bool, optional): If True, the returned position is the
            item's center. If False, it's the top-left corner. Defaults to False.

    Returns:
        QPointF: A safe position for the item.
    """
    if search_center_hint is None:
        search_center_hint = QPointF(0, 0)

    # Start at the hint position, snapped to the grid
    if is_centered:
        start_pos = QPointF(round(search_center_hint.x() / conf.GRID_SIZE) * conf.GRID_SIZE, round(search_center_hint.y() / conf.GRID_SIZE) * conf.GRID_SIZE)
    else:
        start_pos = QPointF(round((search_center_hint.x() - item_width / 2) / conf.GRID_SIZE) * conf.GRID_SIZE, round((search_center_hint.y() - item_height / 2) / conf.GRID_SIZE) * conf.GRID_SIZE)

    # Check the initial position first before starting the spiral.
    initial_top_left = QPointF(start_pos.x() - item_width / 2, start_pos.y() - item_height / 2) if is_centered else start_pos
    initial_rect = QRectF(initial_top_left.x(), initial_top_left.y(), item_width, item_height)
    if not _is_rect_overlapping(scene, initial_rect, item_to_ignore):
        return start_pos

    x, y = 0, 0
    dx, dy = 0, -conf.GRID_SIZE
    max_radius_sq = conf.BLOCK_PLACEMENT_SEARCH_MAX_RADIUS ** 2

    while x*x + y*y < max_radius_sq:
        # This condition checks if we are at a "corner" of the spiral,
        # which is where we need to turn. It generates the sequence:
        # (right, down, left, left, up, up, right, right, right...)
        if x == y or (x < 0 and x == -y) or (x > 0 and x == 1 - y):
            dx, dy = -dy, dx
        x, y = x + dx, y + dy

        current_pos = QPointF(start_pos.x() + x, start_pos.y() + y)
        potential_top_left = QPointF(current_pos.x() - item_width / 2, current_pos.y() - item_height / 2) if is_centered else current_pos
        potential_rect = QRectF(potential_top_left.x(), potential_top_left.y(), item_width, item_height)

        if not _is_rect_overlapping(scene, potential_rect, item_to_ignore):
            return current_pos # Success

    # If even the spiral search fails (scene is extremely crowded), return the
    # original hint position as a last resort.
    return start_pos

class SelectableMovableItemMixin:
    """
    A mixin class to provide common mouse press event handling for selectable
    and movable QGraphicsItems.

    This mixin handles:
    - Multi-selection with the Shift key.
    - Single selection on right-click to prepare for a context menu,
      clearing other selections if necessary.
    """
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handles mouse press events for selection.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse press event.
        """
        # Handle multi-selection with Shift key
        if event.button() == Qt.LeftButton and event.modifiers() == Qt.ShiftModifier:
            self.setSelected(not self.isSelected())
            return # Event handled

        # Handle right-click for context menu
        if event.button() == Qt.RightButton:
            if not self.isSelected():
                if self.scene():
                    self.scene().clearSelection()
                self.setSelected(True)
            return

        super().mousePressEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        """
        Handles item changes for snapping, wire updates, and selection.

        This method is called by Qt when the item's state changes. It handles:
        - Snapping the item to the grid when moved (`ItemPositionChange`).
        - Updating connected wires after a move (`ItemPositionHasChanged`).
        - Highlighting the item when selected (`ItemSelectedChange`).

        Args:
            change (QGraphicsItem.GraphicsItemChange): The type of change.
            value: The new value associated with the change.

        Returns:
            The result of the base class's itemChange method.
        """
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos = value
            snapped_x = round(new_pos.x() / conf.GRID_SIZE) * conf.GRID_SIZE
            snapped_y = round(new_pos.y() / conf.GRID_SIZE) * conf.GRID_SIZE
            return QPointF(snapped_x, snapped_y)
        elif change == QGraphicsItem.ItemPositionHasChanged:
            self.update_connected_wires()
        elif change == QGraphicsItem.ItemSelectedChange:
            # The class using this mixin is responsible for defining
            # these pen attributes if it wants selection highlighting.
            if value and hasattr(self, 'highlight_pen'):
                self.setPen(self.highlight_pen)
            elif not value and hasattr(self, 'normal_pen'):
                self.setPen(self.normal_pen)
        return super().itemChange(change, value)

class HoverHighlightMixin:
    """
    A mixin class to provide hover highlighting functionality.

    This mixin assumes the class has `color` and `highlight_color` attributes
    and that hover events have been enabled on the item.
    """
    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """
        Highlights the item by changing its brush to the highlight color.

        If the item has an 'is_locked' attribute and it is True, the
        highlighting is skipped.

        Args:
            event (QGraphicsSceneHoverEvent): The hover event.
        """
        if hasattr(self, 'is_locked') and self.is_locked:
            super().hoverEnterEvent(event)
            return # Do not highlight if locked
        self.setBrush(QBrush(self.highlight_color))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """
        Resets the item's brush to its default color when the mouse leaves.

        If the item is locked, the brush is set to its 'locked_color' instead.
        """
        if hasattr(self, 'is_locked') and self.is_locked:
            # If it's locked, ensure it has the locked brush.
            if hasattr(self, 'locked_color'):
                self.setBrush(QBrush(self.locked_color))
            super().hoverLeaveEvent(event)
            return
        self.setBrush(QBrush(self.color))
        super().hoverLeaveEvent(event)

class BlockPin(PinMixin, HoverHighlightMixin, QGraphicsEllipseItem):
    """
    Represents an input or output pin on a block.

    Pins are circular QGraphicsEllipseItem instances attached to a Block.
    They handle their own positioning, display, and hover events.

    Attributes:
        parent_block (Block): The block this pin belongs to.
        pin_type (PinType): The type of the pin (PinType.INPUT or PinType.OUTPUT).
        name (str): The name of the pin, displayed next to it.
        index (int): The vertical index of the pin on its side of the block.
        wires (list): A list of Wire objects connected to this pin.
        color (QColor): The default color of the pin.
        highlight_color (QColor): The color of the pin on hover.
        text_item (QGraphicsTextItem): The text label for the pin.
    """
    def __init__(self, parent_block: 'Block', pin_type: PinType, name: str = "", index: int = 0) -> None:
        """
        Initializes a BlockPin.

        Args:
            parent_block (Block): The parent Block item.
            pin_type (PinType): The type of the pin (PinType.INPUT or PinType.OUTPUT).
            name (str, optional): The name of the pin. Defaults to "".
            index (int, optional): The index of the pin, used for vertical positioning. Defaults to 0.
        """
        super().__init__(-conf.BLOCK_PIN_RADIUS, -conf.BLOCK_PIN_RADIUS, conf.BLOCK_PIN_DIAMETER_SCALE * conf.BLOCK_PIN_RADIUS, conf.BLOCK_PIN_DIAMETER_SCALE * conf.BLOCK_PIN_RADIUS, parent=parent_block)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True) # Must be true for itemChange to be called
        self.setAcceptHoverEvents(True)

        self.init_pin(parent_block, pin_type, name)
        self.index = index  # Index among pins of the same type

        self.color = conf.BLOCK_PIN_COLOR
        self.highlight_color = conf.BLOCK_PIN_HIGHLIGHT_COLOR
        self.locked_color = conf.BLOCK_PIN_LOCKED_COLOR
        self.setBrush(QBrush(self.color))
        self.setPen(QPen(conf.PEN_STYLE_NO_PEN)) # Pins don't have a border by default
        self.setZValue(conf.Z_VALUE_PIN)  # Pins should be on top of the block

        self.text_item = QGraphicsTextItem(self.name, self)
        self.text_item.setDefaultTextColor(conf.BLOCK_TEXT_COLOR)
        font = QFont()
        font.setPointSize(conf.FONT_SIZE_BLOCK_PIN)
        self.text_item.setFont(font)
        self.text_item.setZValue(conf.Z_VALUE_TEXT) # Text on top of pin

        self.update_lock_state()
        self.update_position()

    @property
    def name(self) -> str:
        """Returns the name of the pin."""
        return self._name

    def update_position(self) -> None:
        """
        Recalculates and sets the position of the pin and its text.
        
        The position is based on a fixed vertical spacing defined in conf.py,
        ensuring pins are always on the grid.
        """
        block_width = self.parent_block.rect().width()

        # Calculate Y position based on fixed, grid-aligned spacing.
        # This is independent of the block's final height.
        y = conf.BLOCK_PIN_TOP_PADDING + (self.index * conf.BLOCK_PIN_VERTICAL_SPACING)

        if self.pin_type == PinType.INPUT:
            x = 0
            self.setPos(x, y)
            self.text_item.setPos(conf.BLOCK_PIN_RADIUS + conf.BLOCK_PIN_TEXT_PADDING, -self.text_item.boundingRect().height() / 2)
        else: # OUTPUT
            x = block_width
            self.setPos(x, y)
            self.text_item.setPos(-conf.BLOCK_PIN_RADIUS - conf.BLOCK_PIN_TEXT_PADDING - self.text_item.boundingRect().width(), -self.text_item.boundingRect().height() / 2)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        """
        Handles item changes to constrain movement and trigger realignment.

        Args:
            change (QGraphicsItem.GraphicsItemChange): The type of change.
            value (Any): The new value associated with the change.

        Returns:
            Any: The result of the base class's itemChange method.
        """
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = value
            
            # Determine the correct, fixed x-position based on pin type.
            # The pin's position is relative to the parent block.
            if self.pin_type == PinType.INPUT:
                fixed_x = 0
            else: # OUTPUT
                fixed_x = self.parent_block.rect().width()

            # Clamp y within the block's vertical bounds
            block_height = self.parent_block.rect().height()
            clamped_y = max(0, min(new_pos.y(), block_height))

            # Return the constrained position.
            return QPointF(fixed_x, clamped_y)

        return super().itemChange(change, value)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Starts a wire drag on Ctrl+Click, otherwise prepares for movement
        by disabling parent block's pin realignment.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse press event.
        """
        if event.button() == Qt.LeftButton and event.modifiers() == Qt.ControlModifier:
            if self.scene():
                # The scene is responsible for managing wire creation
                self.scene()._start_wire_drag(self)
                event.accept()
                return # Consume event

        # For regular clicks that will initiate a move, disable realignment.
        if self.parent_block and hasattr(self.parent_block, 'set_pin_realign_enabled'):
            self.parent_block.set_pin_realign_enabled(False)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Re-enables and triggers pin realignment on the parent block after a drag.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse release event.
        """
        super().mouseReleaseEvent(event)
        if self.parent_block and hasattr(self.parent_block, 'set_pin_realign_enabled'):
            self.parent_block.set_pin_realign_enabled(True)
            self.parent_block.realign_pins()

class DiagramPin(PinMixin, HoverHighlightMixin, SelectableMovableItemMixin, QGraphicsPolygonItem):
    """
    Base class for standalone diagram input and output pins.

    These pins are not attached to a block and represent the overall inputs
    and outputs of the diagram. They are movable and can be renamed.
    This class handles common functionality like movement, selection,
    hover effects, and context menus.

    Attributes:
        name (str): The name of the pin, displayed next to it.
        wires (list): A list of Wire objects connected to this pin.
        parent_block (None): Diagram pins are standalone.
        log_func (callable): A function for logging messages.
        color (QColor): The default color of the pin.
        highlight_color (QColor): The color of the pin on hover.
        pin_type (PinType): The type of the pin (PinType.INPUT or PinType.OUTPUT).
        text_item (QGraphicsTextItem): The text label for the pin.
    """
    # Class-level constant for the diamond shape to avoid recreating it on every instantiation.
    DIAMOND_POLYGON = QPolygonF([
        QPointF(0, -conf.DIAGRAM_PIN_RADIUS * conf.DIAGRAM_PIN_DIAMOND_SCALE),
        QPointF(conf.DIAGRAM_PIN_RADIUS * conf.DIAGRAM_PIN_DIAMOND_SCALE, 0),
        QPointF(0, conf.DIAGRAM_PIN_RADIUS * conf.DIAGRAM_PIN_DIAMOND_SCALE),
        QPointF(-conf.DIAGRAM_PIN_RADIUS * conf.DIAGRAM_PIN_DIAMOND_SCALE, 0)
    ])
    def __init__(self,
                 name: str,
                 pin_type: PinType,
                 x: Optional[float],
                 y: Optional[float],
                 scene_for_auto_placement: Optional[QGraphicsScene] = None,
                 placement_hint: Optional[QPointF] = None,
                 log_func: Optional[Callable[[str], None]] = None
                 ) -> None:
        """
        Initializes a DiagramPin.

        Args:
            name (str): The name of the pin.
            x (Optional[float]): The initial x-coordinate. If None, auto-placement is used.
            y (Optional[float]): The initial y-coordinate. If None, auto-placement is used.
            pin_type (PinType): The type of the pin (PinType.INPUT or PinType.OUTPUT).
            scene_for_auto_placement (Optional[QGraphicsScene]): The scene for auto-placement.
            placement_hint (QPointF, optional): A hint for where to place the pin
                during auto-placement. Defaults to None.
            log_func (Optional[Callable[[str], None]]): A function for logging messages.
        """
        super().__init__(self.DIAMOND_POLYGON) # Call QGraphicsPolygonItem constructor
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(conf.Z_VALUE_PIN)

        self.normal_pen = QPen(conf.BLOCK_BORDER_COLOR, conf.PEN_WIDTH_NORMAL)
        self.highlight_pen = QPen(conf.BLOCK_HIGHLIGHT_COLOR, conf.PEN_WIDTH_HIGHLIGHT)
        self.setPen(self.normal_pen)

        self.init_pin(parent_block=None, pin_type=pin_type, name=name)
        self.log_func = log_func if log_func else print # log_func is specific to DiagramPin/Block

        # Set colors based on pin type
        if self.pin_type == PinType.OUTPUT: # DiagramInputPin
            self.color = conf.DIAGRAM_PIN_COLOR
            self.highlight_color = conf.DIAGRAM_PIN_HIGHLIGHT_COLOR
            self.locked_color = conf.DIAGRAM_PIN_LOCKED_COLOR
        else: # INPUT, for DiagramOutputPin
            self.color = conf.DIAGRAM_OUTPUT_PIN_COLOR
            self.highlight_color = conf.DIAGRAM_OUTPUT_PIN_HIGHLIGHT_COLOR
            self.locked_color = conf.DIAGRAM_OUTPUT_PIN_LOCKED_COLOR

        self.setBrush(QBrush(self.color))

        self.text_item = QGraphicsTextItem(self._name, self)
        self.text_item.setDefaultTextColor(conf.DIAGRAM_PIN_TEXT_COLOR)
        font = QFont()
        font.setPointSize(conf.FONT_SIZE_DIAGRAM_PIN)
        self.text_item.setFont(font)
        self.text_item.setZValue(conf.Z_VALUE_TEXT)
        self.update_lock_state()
        self._update_text_position()

        if x is not None and y is not None:
            # Snap to grid if coordinates are provided manually
            snapped_x = round(x / conf.GRID_SIZE) * conf.GRID_SIZE
            snapped_y = round(y / conf.GRID_SIZE) * conf.GRID_SIZE
            self.setPos(snapped_x, snapped_y)
        elif scene_for_auto_placement is not None:
            pin_rect = self.boundingRect()
            item_width = pin_rect.width()
            item_height = pin_rect.height()
            safe_pos = find_safe_placement(
                scene_for_auto_placement,
                item_width,
                item_height,
                item_to_ignore=self,
                search_center_hint=placement_hint,
                is_centered=True  # DiagramPin position is its center
            )
            self.setPos(safe_pos)

    def _update_text_position(self) -> None:
        """Positions the text label relative to the pin."""
        text_rect = self.text_item.boundingRect()
        text_y = -text_rect.height() / 2

        # Common horizontal offset from the diamond's edge
        horizontal_offset = conf.DIAGRAM_PIN_RADIUS * conf.DIAGRAM_PIN_DIAMOND_SCALE + conf.DIAGRAM_PIN_TEXT_PADDING

        # DiagramInputPin acts as an OUTPUT, text on the left.
        # DiagramOutputPin acts as an INPUT, text on the right.
        if self.pin_type == PinType.OUTPUT:
            # Position text to the left
            text_x = -horizontal_offset - text_rect.width()
        else:  # INPUT
            # Position text to the right
            text_x = horizontal_offset

        self.text_item.setPos(text_x, text_y)

    @property
    def name(self) -> str:
        """Returns the name of the diagram pin."""
        return self._name

    @name.setter
    def name(self, new_name: str) -> None:
        """
        Sets a new name for the pin and updates its visual representation.

        Args:
            new_name (str): The new name for the pin.
        """
        self._name = new_name
        self.text_item.setPlainText(self._name)
        self._update_text_position()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Disables scene-wide pin realignment during a drag operation.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse press event.
        """
        if self.scene() and hasattr(self.scene(), 'set_realign_enabled'):
            self.scene().set_realign_enabled(False)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Re-enables and triggers scene-wide pin realignment after a drag.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse release event.
        """
        super().mouseReleaseEvent(event)
        if self.scene() and hasattr(self.scene(), 'set_realign_enabled'):
            self.scene().set_realign_enabled(True)
            # Trigger a final realignment now that the drag is complete.
            self.scene().realign_diagram_pins()

    def request_rename(self) -> None:
        """
        Handles the logic for when a rename is requested from the context menu.

        Emits the `renameDiagramPinRequested` signal on the scene.
        """
        if self.scene():
            if hasattr(self.scene(), 'renameDiagramPinRequested'):
                self.scene().renameDiagramPinRequested.emit(self)

    def _get_context_menu_texts(self) -> Tuple[str, str]:
        """Abstract method to be implemented by subclasses for context menu text."""
        raise NotImplementedError(conf.UI.Log.NOT_IMPLEMENTED_ERROR_SUBCLASS)

    def _base_context_menu(self, event: QGraphicsSceneContextMenuEvent, rename_text: str, delete_text: str) -> None:
        """
        Helper for creating the context menu.

        Args:
            event (QGraphicsSceneContextMenuEvent): The context menu event.
            rename_text (str): The text for the 'Rename' action.
            delete_text (str): The text for the 'Delete' action.
        """
        menu = QMenu()
        rename_action = menu.addAction(rename_text)
        delete_action = menu.addAction(delete_text)
        action = menu.exec_(event.screenPos())

        if action == delete_action:
            if self.scene():
                self.setSelected(True)
                self.scene().delete_selected_items()
        elif action == rename_action:
            self.request_rename()

    @single_selection_only
    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """
        Shows a context menu for the diagram pin.

        Args:
            event (QGraphicsSceneContextMenuEvent): The context menu event.
        """
        rename_text, delete_text = self._get_context_menu_texts()
        self._base_context_menu(event, rename_text, delete_text)


class DiagramInputPin(DiagramPin):
    """
    Represents a standalone input pin for the entire diagram.
    It acts as an output pin within the diagram's logic, providing a signal source.
    """
    def __init__(self,
                 name: str,
                 x: Optional[float] = None,
                 y: Optional[float] = None,
                 scene_for_auto_placement: Optional[QGraphicsScene] = None,
                 placement_hint: Optional[QPointF] = None,
                 log_func: Optional[Callable[[str], None]] = None
                 ) -> None:
        """
        Initializes a DiagramInputPin.

        Args:
            name (str): The name of the pin.
            x (Optional[float]): The initial x-coordinate. Defaults to None.
            y (Optional[float]): The initial y-coordinate. Defaults to None.
            scene_for_auto_placement (Optional[QGraphicsScene]): The scene for auto-placement.
            placement_hint (QPointF, optional): A hint for auto-placement.
            log_func (Optional[Callable[[str], None]]): A function for logging.
        """
        super().__init__(name=name,
                         pin_type=PinType.OUTPUT,
                         x=x, y=y,
                         scene_for_auto_placement=scene_for_auto_placement,
                         placement_hint=placement_hint,
                         log_func=log_func)

    def _get_context_menu_texts(self) -> Tuple[str, str]:
        """Provides the specific context menu texts for a DiagramInputPin."""
        return (conf.UI.Menu.RENAME_DIAGRAM_INPUT, conf.UI.Menu.DELETE_DIAGRAM_INPUT)
class DiagramOutputPin(DiagramPin):
    """
    Represents a standalone output pin for the entire diagram.
    It acts as an input pin within the diagram's logic, providing a signal sink.
    """
    def __init__(self,
                 name: str,
                 x: Optional[float] = None,
                 y: Optional[float] = None,
                 scene_for_auto_placement: Optional[QGraphicsScene] = None,
                 placement_hint: Optional[QPointF] = None,
                 log_func: Optional[Callable[[str], None]] = None
                 ) -> None:
        """
        Initializes a DiagramOutputPin.

        Args:
            name (str): The name of the pin.
            x (Optional[float]): The initial x-coordinate. Defaults to None.
            y (Optional[float]): The initial y-coordinate. Defaults to None.
            scene_for_auto_placement (Optional[QGraphicsScene]): The scene for auto-placement.
            placement_hint (QPointF, optional): A hint for auto-placement.
            log_func (Optional[Callable[[str], None]]): A function for logging.
        """
        super().__init__(name=name,
                         pin_type=PinType.INPUT,
                         x=x, y=y,
                         scene_for_auto_placement=scene_for_auto_placement,
                         placement_hint=placement_hint,
                         log_func=log_func)

    def _get_context_menu_texts(self) -> Tuple[str, str]:
        """Provides the specific context menu texts for a DiagramOutputPin."""
        return (conf.UI.Menu.RENAME_DIAGRAM_OUTPUT, conf.UI.Menu.DELETE_DIAGRAM_OUTPUT)

Pin = Union[BlockPin, DiagramPin]
class Wire(SelectableMovableItemMixin, QGraphicsPathItem):
    """
    Represents a visual connection (wire) between two pins.

    The wire is drawn as a cubic Bezier curve. It handles its own
    geometry updates when connected pins move. It also manages its
    selection state and provides a context menu for deletion.

    Attributes:
        start_pin (Pin): The pin where the wire originates (source).
        end_pin (Pin): The pin where the wire terminates (destination).
        routing_manager (RoutingManager): The object responsible for
            calculating the wire's path.
        _temp_end_pos (QPointF): A temporary position for the end of the
            wire, used when the user is dragging a new connection.
    """
    def __init__(self,
                 start_pin: Pin,
                 end_pin: Optional[Pin] = None,
                 routing_manager: Optional['RoutingManager'] = None
                 ) -> None:
        """
        Initializes a Wire.

        Args:
            start_pin (Pin): The pin where the wire starts.
            end_pin (Optional[Pin]): The pin where the wire ends. Can be None for
                a temporary wire during creation. Defaults to None.
            routing_manager (Optional['RoutingManager']): The manager for calculating
                the wire's path. Defaults to None.
        """
        super().__init__()
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.normal_pen = QPen(conf.WIRE_COLOR, conf.PEN_WIDTH_NORMAL)
        self.highlight_pen = QPen(conf.WIRE_HIGHLIGHT_COLOR, conf.PEN_WIDTH_HIGHLIGHT)
        self.locked_pen = QPen(conf.WIRE_LOCKED_COLOR, conf.PEN_WIDTH_NORMAL)
        self.setPen(self.normal_pen)
        self.setZValue(conf.Z_VALUE_WIRE) # Wires should be below blocks (blocks are Z=2)

        self.is_locked = False
        self.start_pin = start_pin
        self.end_pin = end_pin
        self._temp_end_pos = None # For drawing wire during creation drag

        # Use duck-typing to ensure the routing manager has the required method.
        if not routing_manager or not hasattr(routing_manager, 'calculate_path') or not callable(getattr(routing_manager, 'calculate_path')):
            raise ValueError(conf.UI.Log.ROUTING_MANAGER_INVALID)
        self.routing_manager = routing_manager

        if self.start_pin: # start_pin could be None if wire is created improperly (defensive)
            self.start_pin.wires.append(self)
        if self.end_pin:
            self.end_pin.wires.append(self)

        self.update_geometry() # Initial draw

    def shape(self) -> QPainterPath:
        """
        Returns the shape of this item as a QPainterPath for collision detection.

        This implementation returns a wider path than the drawn one to make
        it easier to click on the wire.

        Returns:
            QPainterPath: The shape of the wire for hit testing.
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(conf.WIRE_CLICKABLE_WIDTH)
        return stroker.createStroke(self.path())

    def set_locked(self, locked: bool) -> None:
        """
        Sets the locked state of the wire, preventing pin reordering and changing its appearance.
        """
        self.is_locked = locked
        if locked:
            self.setPen(self.locked_pen)
        else:
            # Revert to normal or highlight pen based on selection state
            if self.isSelected():
                self.setPen(self.highlight_pen)
            else:
                self.setPen(self.normal_pen)
        self.update()
        # Notify connected pins that their lock state may have changed.
        if self.start_pin and hasattr(self.start_pin, 'update_lock_state'):
            self.start_pin.update_lock_state()
        if self.end_pin and hasattr(self.end_pin, 'update_lock_state'):
            self.end_pin.update_lock_state()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        """
        Overrides the mixin's itemChange to handle selection changes for locked wires.

        Args:
            change (QGraphicsItem.GraphicsItemChange): The type of change.
            value (Any): The new value associated with the change.

        Returns:
            Any: The result of the base class's itemChange method.
        """
        if change == QGraphicsItem.ItemSelectedChange and self.is_locked:
            # Don't change the pen for selection if locked.
            return QGraphicsPathItem.itemChange(self, change, value)
        return super().itemChange(change, value)

    def set_end_pin(self, pin: Pin) -> None:
        """
        Sets or updates the end pin of the wire and updates geometry.

        Args:
            pin (Pin): The new end pin for the wire.
        """
        # Remove from old end_pin's wire list if it exists and is different
        if self.end_pin and self.end_pin != pin and self in self.end_pin.wires:
            self.end_pin.wires.remove(self)
        
        self.end_pin = pin
        self._temp_end_pos = None # No longer a temporary wire being dragged
        
        if self.end_pin:
            if self not in self.end_pin.wires:
                self.end_pin.wires.append(self)
            if hasattr(self.end_pin, 'update_lock_state'):
                self.end_pin.update_lock_state()
        self.update_geometry()

    def update_temp_end_pos(self, scene_pos: QPointF) -> None:
        """
        Updates the temporary end position when dragging a new wire.

        Args:
            scene_pos (QPointF): The current mouse position in scene coordinates.
        """
        if self.end_pin is None: # Only if it's a temporary wire
            self._temp_end_pos = scene_pos
            self.update_geometry()

    def update_geometry(self) -> None:
        """
        Updates the wire's line based on the current positions of its
        start and end pins, using the routing manager.
        """
        if not self.start_pin or not self.routing_manager:
            self.setPath(QPainterPath()) # Empty path
            return

        start_pos = self.start_pin.scenePos()
        path = QPainterPath() # Default to empty path

        if self.end_pin:
            end_pos = self.end_pin.scenePos()
            path = self.routing_manager.calculate_path(
                start_pos,
                end_pos,
                self.start_pin.pin_type,
                self.end_pin.pin_type,
                is_temporary=False,
                wire_being_routed=self
            )
        elif self._temp_end_pos:
            path = self.routing_manager.calculate_path(
                start_pos,
                self._temp_end_pos,
                self.start_pin.pin_type,
                end_pin_type=None, # Not applicable for temp wire's moving end
                is_temporary=True,
                wire_being_routed=self
            )
        # path will be empty if no end_pin or temp_end_pos, or if routing_manager returns empty.
        self.setPath(path) # Set the calculated path

    @single_selection_only
    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """
        Shows a context menu for the wire.

        Args:
            event (QGraphicsSceneContextMenuEvent): The context menu event.
        """
        menu = QMenu()

        # Add Lock/Unlock action
        lock_text = conf.UI.Menu.UNLOCK_WIRE if self.is_locked else conf.UI.Menu.LOCK_WIRE
        lock_action = menu.addAction(lock_text)
        menu.addSeparator()

        delete_action = menu.addAction(conf.UI.Menu.DELETE_WIRE)

        # The scene() method gives us access to the BlockDiagramScene instance
        # which has the logic to properly remove wires.
        action = menu.exec_(event.screenPos())

        if action == lock_action:
            self.set_locked(not self.is_locked)
        elif action == delete_action:
            if self.scene():
                self.scene().remove_wire(self)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        """
        Custom paint method to prevent drawing the default selection rectangle,
        as selection is indicated by changing the wire's color and width.

        Args:
            painter (QPainter): The painter to use.
            option (QStyleOptionGraphicsItem): The style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        # We need to save and restore the state of the option, as it's
        # passed by reference and modifying it can have side effects.
        original_state = option.state

        # If the item is selected, we remove the 'Selected' state flag
        # before calling the parent's paint method.
        if option.state & QStyle.State_Selected:
            option.state &= ~QStyle.State_Selected

        super().paint(painter, option, widget)

        # Restore the original state
        option.state = original_state

class Block(SelectableMovableItemMixin, QGraphicsRectItem):
    """
    Represents a draggable block with a title and connectable pins.

    The block can be moved and selected. It automatically adjusts its size
    based on its title and the number of input/output pins. It provides
    a context menu for actions like renaming and adding pins.

    Attributes:
        name (str): The name of the block, displayed as its title.
        input_pins (dict): A dictionary of input pins, keyed by pin name.
        output_pins (dict): A dictionary of output pins, keyed by pin name.
        log_func (callable): A function for logging messages.
        title_item (QGraphicsTextItem): The text item for the block's title.
    """
    def __init__(self,
                 name: str = 'Block',
                 x: Optional[float] = None,
                 y: Optional[float] = None,
                 scene_for_auto_placement: Optional[QGraphicsScene] = None,
                 placement_hint: Optional[QPointF] = None,
                 log_func: Optional[Callable[[str], None]] = None
                 ) -> None:
        """
        Initializes a Block.

        Args:
            name (str, optional): The name of the block. Defaults to 'Block'.
            x (float, optional): The initial x-coordinate. Defaults to None for auto-placement.
            y (float, optional): The initial y-coordinate. Defaults to None for auto-placement.
            scene_for_auto_placement (QGraphicsScene, optional): The scene for auto-placement.
            placement_hint (QPointF, optional): A hint for auto-placement.
            log_func (Callable[[str], None], optional): A function for logging.
        """
        super().__init__(conf.INITIAL_ITEM_X, conf.INITIAL_ITEM_Y, conf.MIN_ITEM_DIMENSION, conf.MIN_ITEM_DIMENSION) # Initialize with min rect, set_size will fix it
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(conf.Z_VALUE_BLOCK) # Blocks should be above wires

        self.is_locked = False
        self.log_func = log_func if log_func else print
        self._pin_realign_enabled = True

        self.setBrush(QBrush(conf.BLOCK_COLOR))
        self.normal_pen = QPen(conf.BLOCK_BORDER_COLOR, conf.PEN_WIDTH_NORMAL)
        self.highlight_pen = QPen(conf.BLOCK_HIGHLIGHT_COLOR, conf.PEN_WIDTH_HIGHLIGHT)
        self.locked_pen = QPen(conf.BLOCK_LOCKED_BORDER_COLOR, conf.PEN_WIDTH_NORMAL)
        self.setPen(self.normal_pen)

        self._name = name
        self.input_pins = {}
        self.output_pins = {}

        self.title_item = QGraphicsTextItem(self._name, self)

        # Use a dark color for the title, as it's now outside the block.
        self.title_item.setDefaultTextColor(conf.DIAGRAM_PIN_TEXT_COLOR)
        font = QFont()
        font.setPointSize(conf.FONT_SIZE_BLOCK_TITLE)
        font.setWeight(conf.FONT_WEIGHT_BLOCK_TITLE)
        self.title_item.setFont(font)
        self.title_item.setZValue(conf.Z_VALUE_TEXT)

        # Calculate initial dimensions based on title and (empty) pin lists
        auto_width, auto_height = self._get_auto_dimensions()
        self.set_size(auto_width, auto_height) # Set size first, this will also position the title
        
        if x is not None and y is not None:
            snapped_x = round(x / conf.GRID_SIZE) * conf.GRID_SIZE
            snapped_y = round(y / conf.GRID_SIZE) * conf.GRID_SIZE
            self.setPos(snapped_x, snapped_y)
        elif scene_for_auto_placement is not None:
            item_width = self.rect().width()
            item_height = self.rect().height()
            safe_pos = find_safe_placement(
                scene_for_auto_placement,
                item_width,
                item_height,
                item_to_ignore=self,
                search_center_hint=placement_hint,
                is_centered=False  # Block position is top-left
            )
            self.setPos(safe_pos)
        else:
            # Default initial position if x,y not provided.
            self.setPos(conf.INITIAL_ITEM_X, conf.INITIAL_ITEM_Y)

    def boundingRect(self) -> QRectF:
        """Returns the bounding rectangle of the block, including its external title."""
        base_rect = self.rect()
        # The title's bounding rect is in its own coordinate system.
        # We need to map it to the block's coordinate system by using its position.
        title_rect_in_block_coords = QRectF(self.title_item.pos(), self.title_item.boundingRect().size())
        # The final bounding box is the union of the block's rectangle and its title.
        return base_rect.united(title_rect_in_block_coords)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        """
        Overrides the base itemChange to trigger diagram pin realignment on move
        and handle selection changes for locked blocks.

        Args:
            change (QGraphicsItem.GraphicsItemChange): The type of change.
            value (Any): The new value associated with the change.

        Returns:
            Any: The result of the base class's itemChange method.
        """
        # If the block is locked, we want to prevent the selection highlight from
        # changing the pen color. The mixin's itemChange does this, so we
        # intercept the event here and handle it differently.
        if change == QGraphicsItem.ItemSelectedChange and self.is_locked:
            # We still want the item to be selected/deselected, but we don't
            # want to change the pen. We call the grandparent's itemChange
            # to bypass the mixin's visual feedback logic.
            return QGraphicsRectItem.itemChange(self, change, value)

        # For all other cases, or if the block is not locked, proceed with the
        # normal behavior from the mixin (snapping, selection highlight)
        # and the block's own logic (realigning diagram pins).
        # First, call the superclass implementation to get snapping and wire updates.
        result = super().itemChange(change, value)

        # After the position has changed, the super block is dirty.
        if change == QGraphicsItem.ItemPositionHasChanged:
            if self.scene() and hasattr(self.scene(), 'realign_diagram_pins'):
                self.scene().realign_diagram_pins()
        return result

    def _update_title_position(self) -> None:
        """Positions the title text centered horizontally above the block's rectangle."""
        title_rect = self.title_item.boundingRect()
        block_rect = self.rect()
        x = (block_rect.width() - title_rect.width()) / 2
        y = -title_rect.height() - conf.BLOCK_TITLE_TOP_MARGIN
        self.title_item.setPos(x, y)

    def _calculate_auto_height(self) -> float:
        """
        Calculates the optimal block height based on its pin count.

        The height is determined by the space required to accommodate the pins
        with fixed vertical spacing.
        """
        max_pins = max(len(self.input_pins), len(self.output_pins))
        if max_pins == 0:
            # For a block with no pins, give it a minimal default height.
            return float(conf.GRID_SIZE * 2)

        # Height is from the top of the block to the center of the last pin, plus a bottom margin.
        height_for_pins = conf.BLOCK_PIN_TOP_PADDING + ((max_pins - 1) * conf.BLOCK_PIN_VERTICAL_SPACING) + conf.BLOCK_PIN_BOTTOM_PADDING
        return float(height_for_pins)
    def _get_max_pin_label_span(self, pins: Dict[str, 'BlockPin']) -> float:
        """Calculates the maximum horizontal space required by a set of pin labels."""
        if not pins:
            return 0
        
        max_span = 0
        for pin in pins.values():
            # Span = pin circle radius + padding to text + text width + internal block padding
            span = conf.BLOCK_PIN_RADIUS + conf.BLOCK_PIN_TEXT_PADDING + pin.text_item.boundingRect().width() + conf.MIN_BLOCK_INTERNAL_PADDING
            if span > max_span:
                max_span = span
        return float(max_span)
    def _calculate_auto_width(self) -> float:
        """Calculates the optimal width for the block."""
        title_rect = self.title_item.boundingRect()
        # Min width for title.
        required_width_for_title = title_rect.width()

        # Calculate required width for pin labels using a helper
        required_width_for_input_labels = self._get_max_pin_label_span(self.input_pins)
        required_width_for_output_labels = self._get_max_pin_label_span(self.output_pins)

        # The total width required for pins is the sum of the space needed for
        # input labels on the left and output labels on the right.
        required_width_for_pins = required_width_for_input_labels + required_width_for_output_labels

        # The final width is the maximum of the default width, the width needed for the title,
        # and the width needed for the pins.
        return float(max(conf.STANDARD_BLOCK_WIDTH, required_width_for_title, required_width_for_pins))
    def _get_auto_dimensions(self) -> Tuple[float, float]:
        """
        Calculates the optimal width and height for the block by calling helper methods.
        """
        auto_width = self._calculate_auto_width()
        auto_height = self._calculate_auto_height()
        return auto_width, auto_height
    def set_size(self, width: float, height: float) -> None:
        """
        Sets the size of the block, snapping to the grid, and updates pins.

        Args:
            width (float): The desired width of the block.
            height (float): The desired height of the block.
        """
        snapped_width = max(conf.MIN_ITEM_DIMENSION, math.ceil(width / conf.GRID_SIZE) * conf.GRID_SIZE) # Snap up to nearest grid multiple
        snapped_height = max(conf.MIN_ITEM_DIMENSION, math.ceil(height / conf.GRID_SIZE) * conf.GRID_SIZE) # Snap up to nearest grid multiple
        
        self.setRect(0, 0, snapped_width, snapped_height)
        self.update_pin_positions()
        self._update_title_position()
    def add_input_pin(self, name: str) -> Optional['BlockPin']:
        """
        Adds an input pin to the block.

        Args:
            name (str): The name for the new input pin.

        Returns:
            BlockPin or None: The newly created input pin, or None if a pin
            with that name already exists.
        """
        if name in self.input_pins or name in self.output_pins:
            self.log_func(conf.UI.Log.PIN_ALREADY_EXISTS.format(pin_name=name))
            return None

        pin = BlockPin(self, PinType.INPUT, name, len(self.input_pins))
        self.input_pins[name]=pin
        self.auto_adjust_size() # Recalculate dimensions and update
        return pin
    def add_output_pin(self, name: str) -> Optional['BlockPin']:
        """
        Adds an output pin to the block.

        Args:
            name (str): The name for the new output pin.

        Returns:
            BlockPin or None: The newly created output pin, or None if a pin
            with that name already exists.
        """
        if name in self.input_pins or name in self.output_pins:
            self.log_func(conf.UI.Log.PIN_ALREADY_EXISTS.format(pin_name=name))
            return None

        pin = BlockPin(self, PinType.OUTPUT, name, len(self.output_pins))
        self.output_pins[name]=pin
        self.auto_adjust_size() # Recalculate dimensions and update
        return pin
    def auto_adjust_size(self) -> None:
        """
        Automatically adjusts the block's size based on its content.
        """
        auto_width, auto_height = self._get_auto_dimensions()
        self.set_size(auto_width, auto_height)

    def set_locked(self, locked: bool) -> None:
        """
        Sets the locked state of the block, preventing movement and changing its appearance.

        Args:
            locked (bool): True to lock the block, False to unlock.
        """
        self.is_locked = locked
        self.setFlag(QGraphicsItem.ItemIsMovable, not locked)
        if locked:
            self.setPen(self.locked_pen)
        else:
            # Revert to normal or highlight pen based on selection state
            if self.isSelected():
                self.setPen(self.highlight_pen)
            else:
                self.setPen(self.normal_pen)
        self.update() # Force a repaint to show the new border color

    def set_pin_realign_enabled(self, enabled: bool) -> None:
        """
        Enables or disables the automatic realignment of this block's pins.
        """
        self._pin_realign_enabled = enabled

    def realign_pins(self) -> None:
        """
        Re-sorts and re-indexes input and output pins based on their current
        vertical position, then updates their visual layout.
        """
        if not self._pin_realign_enabled:
            return

        # Re-index input pins
        sorted_inputs = sorted(self.input_pins.values(), key=lambda p: p.y())
        for i, pin in enumerate(sorted_inputs):
            pin.index = i

        # Re-index output pins
        sorted_outputs = sorted(self.output_pins.values(), key=lambda p: p.y())
        for i, pin in enumerate(sorted_outputs):
            pin.index = i

        # Apply the new layout based on new indices. This also updates wires.
        self.update_pin_positions()

    @property
    def name(self) -> str:
        """Returns the name of the block."""
        return self._name

    @name.setter
    def name(self, new_name: str) -> None:
        """
        Sets a new name for the block and updates its visual representation.

        Args:
            new_name (str): The new name for the block.
        """
        self._name = new_name
        self.title_item.setPlainText(self._name)
        self.auto_adjust_size() # Adjust size in case the new name is longer/shorter
    def update_pin_positions(self) -> None:
        """
        Recalculates and updates the positions of all pins on the block.
        This is called after adding/removing pins or resizing the block.
        """
        for pin in list(self.input_pins.values()) + list(self.output_pins.values()):
            pin.update_position()
        self.update_connected_wires()
    def update_connected_wires(self) -> None:
        """Updates the geometry of all wires connected to this block's pins."""
        for pin in list(self.input_pins.values()) + list(self.output_pins.values()):
            for wire in pin.wires:
                wire.update_geometry()
    def request_rename(self) -> None:
        """
        Handles the logic for when a rename is requested from the context menu.

        Emits the `renameBlockRequested` signal on the scene.
        """
        if self.scene():
            if hasattr(self.scene(), 'renameBlockRequested'):
                self.scene().renameBlockRequested.emit(self)
    def request_add_pin(self) -> None:
        """
        Handles the logic for when adding a pin is requested from the context menu.

        Emits the `addPinToBlockRequested` signal on the scene.
        """
        if self.scene() and hasattr(self.scene(), 'addPinToBlockRequested'):
            self.scene().addPinToBlockRequested.emit()
    @single_selection_only
    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """
        Shows a context menu for the block.

        Args:
            event (QGraphicsSceneContextMenuEvent): The context menu event.
        """
        menu = QMenu()
        rename_action = menu.addAction(conf.UI.Menu.RENAME_BLOCK)
        add_pin_action = menu.addAction(conf.UI.Menu.ADD_BLOCK_PIN)

        menu.addSeparator()

        # Add Lock/Unlock action
        lock_text = conf.UI.Menu.UNLOCK_BLOCK_POSITION if self.is_locked else conf.UI.Menu.LOCK_BLOCK_POSITION
        lock_action = menu.addAction(lock_text)

        menu.addSeparator()
        delete_action = menu.addAction(conf.UI.Menu.DELETE_BLOCK)
        
        action = menu.exec_(event.screenPos())

        if action == lock_action:
            self.set_locked(not self.is_locked)
        elif action == rename_action:
            self.request_rename()
        elif action == add_pin_action:
            self.request_add_pin()
        elif action == delete_action:
            if self.scene():
                # This will delete this block and any other selected items.
                self.scene().delete_selected_items()

class RoutingManager:
    """
    Manages the calculation of paths for wires, generating smooth
    Bezier curves between pins.
    """
    def __init__(self, scene=None):
        """
        Initializes the RoutingManager.

        Args:
            scene (QGraphicsScene, optional): The scene context. Defaults to None.
        """
        self.scene = scene  # Kept for potential future use, e.g. simple obstacle avoidance for curves

    def calculate_path(self, start_pos, end_pos_or_temp, start_pin_type, end_pin_type=None, is_temporary=False, wire_being_routed=None):
        """
        Calculates a smooth cubic Bezier curve path for a wire.

        The curve is shaped by two control points that extend horizontally
        from the start and end pins, creating a pleasing "S" or "C" shape.

        Args:
            start_pos (QPointF): Starting position of the wire.
            end_pos_or_temp (QPointF): Ending or temporary mouse position.
            start_pin_type (PinType): Type of the start pin.
            end_pin_type (int, optional): Type of the end pin. Defaults to None.
            is_temporary (bool, optional): True if the wire is being dragged.
            wire_being_routed (Wire, optional): The wire being routed.

        Returns:
            QPainterPath: The calculated path for the wire.
        """
        path = QPainterPath()
        path.moveTo(start_pos)
        end_pos = end_pos_or_temp

        # Calculate horizontal distance to determine the curve's "strength"
        dx = end_pos.x() - start_pos.x()
        
        # The horizontal offset for the control points. A larger offset creates a wider, more gentle curve.
        # We use a base offset and add a factor of the horizontal distance.
        offset = max(abs(dx) * conf.BEZIER_DX_FACTOR, conf.WIRE_STUB_LENGTH * conf.BEZIER_STUB_FACTOR)

        # Control point 1, extending from the start pin
        cp1_x = start_pos.x()
        if start_pin_type == PinType.OUTPUT:
            cp1_x += offset
        else:  # TYPE_INPUT
            cp1_x -= offset
        cp1 = QPointF(cp1_x, start_pos.y())

        # Control point 2, extending from the end pin
        cp2_x = end_pos.x()
        
        # For temporary wires, the end pin type is unknown. We infer a logical target.
        effective_end_pin_type = end_pin_type
        if is_temporary:
            # If dragging from an output, assume the target is an input, and vice-versa.
            effective_end_pin_type = PinType.INPUT if start_pin_type == PinType.OUTPUT else PinType.OUTPUT

        if effective_end_pin_type == PinType.INPUT:
            cp2_x -= offset
        elif effective_end_pin_type == PinType.OUTPUT: # Can happen if connecting input -> output
            cp2_x += offset
        else: # Fallback for non-temporary wires with no valid end_pin_type
             cp2_x -= offset

        cp2 = QPointF(cp2_x, end_pos.y())

        path.cubicTo(cp1, cp2, end_pos)
        return path

class BlockDiagramScene(QGraphicsScene):
    """
    A QGraphicsScene for managing blocks, wires, and diagram pins.

    This class handles user interactions like creating and connecting items,
    context menus, and deletion. It also provides the grid background.

    Attributes:
        routing_manager (RoutingManager): Manages wire path calculations.
        temp_wire (Wire): A temporary wire being dragged by the user.
        start_pin_for_wire (Pin): The starting pin for the temp_wire.
        hovered_pin (Pin): The pin currently under the mouse during a drag.
        log_func (callable): A function for logging messages.
    """
    # The 'object' type is used for the log_func callable, as it's a common way to pass callables in signals.
    addBlockRequested = pyqtSignal(QPointF, object)
    addDiagramInputRequested = pyqtSignal() # Signal to request adding a diagram input pin
    addDiagramOutputRequested = pyqtSignal() # Signal to request adding a diagram output pin
    addPinToBlockRequested = pyqtSignal() # Signal to request adding a pin to the selected block
    renameBlockRequested = pyqtSignal(Block) # Signal to request renaming a block
    renameDiagramPinRequested = pyqtSignal(DiagramPin) # Signal to request renaming a diagram pin
    fitInViewRequested = pyqtSignal() # Signal to request fitting all items in the view
    optimizePlacementRequested = pyqtSignal()
    unlockAllRequested = pyqtSignal()
    exportSvgRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initializes the BlockDiagramScene.

        Args:
            parent (QWidget, optional): The parent object. Defaults to None.
        """
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(Qt.white))
        self.routing_manager = RoutingManager(scene=self)
        self.setSceneRect(conf.SCENE_RECT_X, conf.SCENE_RECT_Y, conf.SCENE_RECT_WIDTH, conf.SCENE_RECT_HEIGHT)

        self.temp_wire: Optional[Wire] = None
        self.start_pin_for_wire: Optional[Pin] = None
        self.hovered_pin: Optional[Pin] = None
        self.log_func: Callable[[str], None] = print # Default logger
        self._realign_enabled = True
        self.optimizer_available = False

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """
        Draws a grid in the background of the scene.

        Args:
            painter (QPainter): The painter to use for drawing.
            rect (QRectF): The rectangle defining the area to be redrawn.
        """
        super().drawBackground(painter, rect)

        left = int(rect.left()) - (int(rect.left()) % conf.GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % conf.GRID_SIZE)

        lines = []
        for x in range(left, int(rect.right()), conf.GRID_SIZE):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(top, int(rect.bottom()), conf.GRID_SIZE):
            lines.append(QLineF(rect.left(), y, rect.right(), y))

        pen = QPen(conf.GRID_COLOR_LIGHT, conf.PEN_WIDTH_GRID)
        painter.setPen(pen)
        painter.drawLines(lines)

    def set_realign_enabled(self, enabled: bool) -> None:
        """
        Enables or disables the automatic realignment of diagram pins.

        Used to prevent realignment during a user drag operation on a DiagramPin.
        """
        self._realign_enabled = enabled

    def _start_wire_drag(self, pin: Pin) -> None:
        """Helper to start dragging a new wire from a pin."""
        self.start_pin_for_wire = pin
        self.temp_wire = Wire(self.start_pin_for_wire, None, routing_manager=self.routing_manager)
        self.addItem(self.temp_wire)
        # Use the pin's own highlight color attribute
        self.start_pin_for_wire.setBrush(QBrush(self.start_pin_for_wire.highlight_color))

    def _get_valid_target_pin(self, item_under_mouse: QGraphicsItem) -> Optional[Pin]:
        """
        Checks if the item under the mouse is a valid target for the current wire drag.

        Args:
            item_under_mouse (QGraphicsItem): The item to check.

        Returns:
            Pin or None: The pin if it's a valid target, otherwise None.
        """
        if not isinstance(item_under_mouse, (BlockPin, DiagramPin)):
            return None
        if item_under_mouse == self.start_pin_for_wire:
            return None

        start_pin = self.start_pin_for_wire
        target_pin = item_under_mouse

        # Rule: At least one pin must belong to a block (prevents DiagramInput -> DiagramOutput).
        if start_pin.parent_block is None and target_pin.parent_block is None:
            return None

        # Rule: Connection must be between opposite types (output -> input).
        if start_pin.pin_type == target_pin.pin_type:
            return None

        # Rule: The destination (input) pin must be empty.
        if target_pin.pin_type == PinType.INPUT and len(target_pin.wires) > 0:
            return None

        return target_pin

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handles mouse press events for initiating wire connections or selecting.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse press event.
        """
        item = self.itemAt(event.scenePos(), self.views()[0].transform())

        # A Ctrl+left-click on a DiagramPin starts a wire.
        # BlockPin handles its own wire drag initiation via its mousePressEvent.
        if event.button() == Qt.LeftButton and event.modifiers() == Qt.ControlModifier and isinstance(item, DiagramPin):
            self._start_wire_drag(item)
            event.accept() # Consume the event
        else:
            # For all other mouse press events, delegate to the base class.
            # This allows items to handle their own press events (e.g., selection,
            # movement, or BlockPin starting a wire).
            super().mousePressEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """
        Shows a context menu for adding items when right-clicking on empty space.

        Args:
            event (QGraphicsSceneContextMenuEvent): The context menu event.
        """
        # Check if the right-click was on an item. If so, let the item handle it.
        # This is important because Wire and Block also have contextMenuEvent.
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if item:
            super().contextMenuEvent(event) # Let the item's context menu handle it
            return

        # If no item was clicked, show the scene's context menu
        if event.reason() == QGraphicsSceneContextMenuEvent.Mouse: # Ensure it's a mouse right-click
            menu = QMenu()
            add_block_action = menu.addAction(conf.UI.Menu.ADD_BLOCK)
            menu.addSeparator()
            add_sys_input_action = menu.addAction(conf.UI.Menu.ADD_DIAGRAM_INPUT)
            add_sys_output_action = menu.addAction(conf.UI.Menu.ADD_DIAGRAM_OUTPUT)
            menu.addSeparator()
            fit_view_action = menu.addAction(conf.UI.Menu.FIT_TO_VIEW)

            optimize_placement_action = None
            if self.optimizer_available:
                menu.addSeparator()
                optimize_placement_action = menu.addAction(conf.UI.Menu.OPTIMIZE_PLACEMENT)

            menu.addSeparator()
            export_svg_action = menu.addAction(conf.UI.Menu.EXPORT_TO_SVG)

            unlock_all_action = menu.addAction(conf.UI.Menu.UNLOCK_EVERYTHING)

            action = menu.exec_(event.screenPos())

            if action == add_block_action:
                self.addBlockRequested.emit(event.scenePos(), self.log_func)
            elif action == unlock_all_action:
                self.unlockAllRequested.emit()
            elif action == add_sys_input_action:
                self.addDiagramInputRequested.emit()
            elif action == add_sys_output_action:
                self.addDiagramOutputRequested.emit()
            elif action == fit_view_action:
                self.fitInViewRequested.emit()
            elif action == optimize_placement_action: # Safe, as action is None if item not created
                self.optimizePlacementRequested.emit()
            elif action == export_svg_action:
                self.exportSvgRequested.emit()
            event.accept() # Accept the event to prevent further propagation
        else:
            # Let the base class handle other context menu events (e.g., from keyboard)
            super().contextMenuEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handles mouse move events for dragging temporary wires and highlighting
        potential connection targets.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse move event.
        """
        if self.temp_wire:
            self.temp_wire.update_temp_end_pos(event.scenePos())
            
            item_under_mouse = self.itemAt(event.scenePos(), self.views()[0].transform())
            new_hovered_pin = self._get_valid_target_pin(item_under_mouse)

            # If we moved off a previously hovered pin, reset its color
            if self.hovered_pin and self.hovered_pin != new_hovered_pin:
                # hoverLeaveEvent is not triggered during drag, so we manually reset color
                self.hovered_pin.setBrush(QBrush(self.hovered_pin.color))

            # If we moved onto a new valid pin, highlight it
            if new_hovered_pin and new_hovered_pin != self.hovered_pin:
                # hoverEnterEvent is not triggered during drag, so we manually set color
                new_hovered_pin.setBrush(QBrush(new_hovered_pin.highlight_color))

            self.hovered_pin = new_hovered_pin
            # End of highlighting logic

        super().mouseMoveEvent(event)

    def _finalize_wire_connection(self, start_pin: Pin, end_pin: Pin) -> None:
        """
        Completes a wire connection between two pins.

        This helper determines the correct source and destination pins and
        uses `create_wire` to perform validation and create the final wire.

        Args:
            start_pin (Pin): The pin where the drag started.
            end_pin (Pin): The pin where the drag ended.
        """
        # Determine the source (output) and destination (input) pins regardless of draw direction
        source_pin = start_pin if start_pin.pin_type == PinType.OUTPUT else end_pin
        dest_pin = end_pin if start_pin.pin_type == PinType.OUTPUT else start_pin

        # create_wire handles validation (e.g., existing connections) and creation
        self.create_wire(source_pin, dest_pin)

    def _reset_wire_drag_state(self) -> None:
        """Resets all visual and state variables after a wire drag operation."""
        # Remove the temporary wire from the scene and the start pin's list
        if self.temp_wire:
            if self.start_pin_for_wire and self.temp_wire in self.start_pin_for_wire.wires:
                self.start_pin_for_wire.wires.remove(self.temp_wire)
            self.removeItem(self.temp_wire)

        # Reset the color of the pin where the drag started
        if self.start_pin_for_wire:
            self.start_pin_for_wire.setBrush(QBrush(self.start_pin_for_wire.color))

        # Reset the color of the pin that was being hovered over
        if self.hovered_pin:
            self.hovered_pin.setBrush(QBrush(self.hovered_pin.color))

        # Clear all state variables
        self.hovered_pin = None
        self.start_pin_for_wire = None
        self.temp_wire = None

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handles mouse release events for completing or canceling wire connections.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse release event.
        """
        if self.temp_wire:
            end_pin = self.hovered_pin
            if end_pin:
                self._finalize_wire_connection(self.start_pin_for_wire, end_pin)
            else:
                self.log_func(conf.UI.Log.NO_VALID_PIN)
            
            self._reset_wire_drag_state()

        super().mouseReleaseEvent(event)
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        Handles key press events, e.g., deleting selected items with the
        Delete key.

        Args:
            event (QKeyEvent): The key press event.
        """
        if event.key() == Qt.Key_Delete:
            self.delete_selected_items()
        super().keyPressEvent(event)

    def delete_selected_items(self) -> None:
        """Deletes all selected blocks, wires, and diagram pins."""
        selected_items = self.selectedItems()
        
        wires_to_remove = set()
        nodes_to_remove = set()

        # First, collect all items to be removed
        for item in selected_items:
            if isinstance(item, Wire):
                wires_to_remove.add(item)
            elif isinstance(item, (Block, DiagramPin)):
                nodes_to_remove.add(item)
                # Also collect all wires connected to this node
                pins_to_check = []
                if isinstance(item, Block):
                    pins_to_check.extend(item.input_pins.values())
                    pins_to_check.extend(item.output_pins.values())
                else: # DiagramPin
                    pins_to_check.append(item)
                
                for pin in pins_to_check:
                    for wire in pin.wires:
                        wires_to_remove.add(wire)

        # Now, remove the items in the correct order: wires first, then nodes.
        for wire in wires_to_remove:
            self.remove_wire(wire)
        
        for node in nodes_to_remove:
            self.removeItem(node)

        # After removing items, the super block may have changed.
        self.realign_diagram_pins()

    def remove_wire(self, wire: Wire) -> None:
        """
        Removes a wire from the scene and disconnects it from its pins.

        Args:
            wire (Wire): The wire to be removed.
        """
        if wire.start_pin and wire in wire.start_pin.wires:
            wire.start_pin.wires.remove(wire)
            if hasattr(wire.start_pin, 'update_lock_state'):
                wire.start_pin.update_lock_state()
        if wire.end_pin and wire in wire.end_pin.wires:
            wire.end_pin.wires.remove(wire)
            if hasattr(wire.end_pin, 'update_lock_state'):
                wire.end_pin.update_lock_state()
        self.removeItem(wire)

    def create_wire(self, start_pin: Pin, end_pin: Pin) -> Optional[Wire]:
        """
        Creates a wire, adds it to the scene, and returns it.

        This is a convenience method for programmatic wire creation. It ensures
        the connection is valid before creating the wire.

        Args:
            start_pin (Pin): The source pin (must be an output type).
            end_pin (Pin): The destination pin (must be an input type).

        Returns:
            Wire or None: The created Wire object, or None if the connection
            is invalid.
        """
        # --- Validation ---
        if not start_pin or not end_pin:
            self.log_func(conf.UI.Log.WIRE_CREATION_FAILED_NO_PIN)
            return None

        # Rule 1: Connection must be between opposite types (output -> input).
        if start_pin.pin_type != PinType.OUTPUT or end_pin.pin_type != PinType.INPUT:
            self.log_func(conf.UI.Log.WIRE_CREATION_FAILED_PIN_TYPE)
            return None

        # Rule 2: The destination (input) pin must be empty.
        if len(end_pin.wires) > 0:
            self.log_func(conf.UI.Log.WIRE_CREATION_FAILED_INPUT_FULL.format(pin_name=end_pin.name))
            return None

        # --- Creation ---
        new_wire = Wire(start_pin, end_pin, self.routing_manager)
        self.addItem(new_wire)
        source_desc = start_pin.name if start_pin.parent_block is None else f"{start_pin.parent_block.name}:{start_pin.name}"
        dest_desc = end_pin.name if end_pin.parent_block is None else f"{end_pin.parent_block.name}:{end_pin.name}"
        self.log_func(conf.UI.Log.WIRE_CONNECTED.format(source_desc=source_desc, dest_desc=dest_desc))
        return new_wire

    def get_blocks_bounding_box(self) -> QRectF:
        """
        Calculates and returns the smallest bounding box that contains all Block items.

        This method iterates through all items in the scene, identifies the
        `Block` instances, and computes their collective bounding rectangle.

        Returns:
            QRectF: The bounding rectangle that encloses all blocks. Returns
            a default (empty) QRectF if no blocks are present in the scene.
        """
        total_bounding_box = QRectF()
        first_block_found = False

        for item in self.items():
            if isinstance(item, Block):
                if not first_block_found:
                    total_bounding_box = item.sceneBoundingRect()
                    first_block_found = True
                else:
                    total_bounding_box = total_bounding_box.united(item.sceneBoundingRect())

        return total_bounding_box

    def get_super_block(self) -> QRectF:
        """
        Calculates the bounding box of all blocks and adds a margin.

        This method first finds the bounding box of all `Block` items and then
        expands it by the margins defined in `conf.SUPER_BLOCK_MARGIN_X` and
        `conf.SUPER_BLOCK_MARGIN_Y`.

        Returns:
            QRectF: The expanded bounding rectangle, or an empty QRectF if
            no blocks are present.
        """
        blocks_bbox = self.get_blocks_bounding_box()
        if not blocks_bbox.isEmpty():
            # QRectF.adjusted(x1, y1, x2, y2) adds to the coordinates.
            # To expand, x1 and y1 must be negative.
            return blocks_bbox.adjusted(-conf.SUPER_BLOCK_MARGIN_X,
                                        -conf.SUPER_BLOCK_MARGIN_Y,
                                        conf.SUPER_BLOCK_MARGIN_X,
                                        conf.SUPER_BLOCK_MARGIN_Y)
        return blocks_bbox # Return the empty rect if no blocks

    def realign_diagram_pins(self) -> None:
        """
        Re-calculates the positions of all DiagramInputPin and DiagramOutputPin
        items to distribute them evenly along the vertical edges of the super block.
        """
        if not self._realign_enabled:
            return

        super_block = self.get_super_block()
        if super_block.isEmpty():
            return  # Nothing to align to

        # --- Align Input Pins ---
        input_pins = sorted([item for item in self.items() if isinstance(item, DiagramInputPin)], key=lambda p: p.scenePos().y())
        num_input_pins = len(input_pins)
        if num_input_pins > 0:
            super_block_height = super_block.height()
            segment_height = super_block_height / (num_input_pins + 1)
            for i, pin in enumerate(input_pins):
                new_y = super_block.top() + (i + 1) * segment_height
                pin.setPos(super_block.left(), new_y)

        # --- Align Output Pins ---
        output_pins = sorted([item for item in self.items() if isinstance(item, DiagramOutputPin)], key=lambda p: p.scenePos().y())
        num_output_pins = len(output_pins)
        if num_output_pins > 0:
            super_block_height = super_block.height()
            segment_height = super_block_height / (num_output_pins + 1)
            for i, pin in enumerate(output_pins):
                new_y = super_block.top() + (i + 1) * segment_height
                pin.setPos(super_block.right(), new_y)

    def draw_bounding_box(self, rect: QRectF, pen_color: QColor = conf.DEBUG_BBOX_COLOR, pen_style: Qt.PenStyle = conf.DEBUG_BBOX_PEN_STYLE) -> Optional[QGraphicsRectItem]:
        """
        Draws a rectangle on the scene, typically for debugging or visualization.

        Args:
            rect (QRectF): The rectangle to draw.
            pen_color (QColor, optional): The color of the rectangle's border.
                Defaults to Qt.black.
            pen_style (Qt.PenStyle, optional): The style of the border.
                Defaults to Qt.DashLine.

        Returns:
            QGraphicsRectItem or None: The created item, or None if rect is empty.
        """
        if rect.isEmpty():
            return None

        pen = QPen(pen_color)
        pen.setStyle(pen_style)
        pen.setWidth(conf.DEBUG_BBOX_PEN_WIDTH)
        rect_item = self.addRect(rect, pen, QBrush(Qt.NoBrush))
        rect_item.setZValue(0)  # Draw it behind most items but above the grid
        return rect_item

class BlockDiagramView(QGraphicsView):
    """
    A QGraphicsView for displaying the BlockDiagramScene.

    This view enables user interaction like panning (middle mouse button) and
    zooming (mouse wheel or Ctrl +/-). It uses an anchor under the mouse for
    zooming and resizing operations, providing an intuitive user experience.

    The transformation anchor is set to `AnchorUnderMouse`, which means
    scaling operations are centered on the mouse cursor's position.

    Attributes:
        _zoom_factor (float): The current zoom level.
        _panning (bool): True if a pan operation is in progress.
        _pan_start_mouse_pos (QPointF): The mouse position at the start of a pan.
        _pan_start_scene_pos (QPointF): The scene position at the start of a pan.
    """
    def __init__(self, scene: QGraphicsScene, parent: Optional[QWidget] = None) -> None:
        """
        Initializes the BlockDiagramView.

        Args:
            scene (QGraphicsScene): The scene to be displayed.
            parent (Optional[QWidget]): The parent widget. Defaults to None.
        """
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True) # Enable mouse tracking for hover events
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._zoom_factor = conf.INITIAL_ZOOM_FACTOR
        self._panning = False
        self._last_pan_pos = QPoint()
        self.min_zoom = conf.MIN_ZOOM_FACTOR
        self.max_zoom = conf.MAX_ZOOM_FACTOR

    def fit_all_items_in_view(self) -> None:
        """
        Adjusts the zoom level and centers the view to fit all items, respecting the
        defined zoom limits.

        This method uses a robust, two-stage approach. It first temporarily
        shrinks the scene's bounding rectangle to match the content. This gives
        `fitInView` an unambiguous context to correctly calculate the scale and
        center the view. After the transform is set and clamped, the original
        large scene rectangle is restored to allow for free panning.
        """
        if not self.scene() or not self.scene().items():
            return

        # 1. Get the bounding rect of all items and add a margin.
        items_rect = self.scene().itemsBoundingRect()
        if items_rect.isEmpty():
            return
        
        margin = conf.FIT_VIEW_MARGIN
        target_rect = items_rect.adjusted(-margin, -margin, margin, margin)

        # 2. Store the original scene rect and then temporarily shrink it.
        original_scene_rect = self.scene().sceneRect()
        self.scene().setSceneRect(target_rect)

        try:
            # 3. Let fitInView calculate the perfect transform in the tight scene.
            self.fitInView(target_rect, Qt.KeepAspectRatio)

            # 4. Now, clamp the zoom level if it's outside our defined limits.
            current_scale = self.transform().m11()
            clamped_scale = max(self.min_zoom, min(current_scale, self.max_zoom))

            if abs(current_scale - clamped_scale) > conf.FLOAT_COMPARISON_EPSILON:
                scale_correction = clamped_scale / current_scale
                self.scale(scale_correction, scale_correction)

            # 5. Update our internal zoom factor to the correct, final scale.
            self._zoom_factor = self.transform().m11()

        finally:
            # 6. CRITICAL: Restore the original large scene rect to allow free panning.
            self.scene().setSceneRect(original_scene_rect)

    def _zoom(self, factor: float, anchor_pos: QPoint) -> None:
        """
        Zooms the view by a given factor. Relies on AnchorUnderMouse.
        
        This implementation calculates the desired absolute scale, clamps it to
        the defined min/max limits, and then applies the necessary relative
        scale factor. This provides smooth zooming up to the limits and avoids
        conflicts with the view's `AnchorUnderMouse` setting.

        Args:
            factor (float): The zoom factor (e.g., 1.15 for zoom in).
            anchor_pos (QPoint): The QPoint in view coordinates to zoom towards.
                                 This is handled by AnchorUnderMouse.
        """
        # Calculate the target scale based on the current zoom factor
        target_scale = self._zoom_factor * factor

        # Clamp the target scale to the min/max limits
        if target_scale < self.min_zoom:
            target_scale = self.min_zoom
        elif target_scale > self.max_zoom:
            target_scale = self.max_zoom
        
        # If the clamped target scale is the same as the current scale, do nothing.
        if abs(target_scale - self._zoom_factor) < conf.FLOAT_COMPARISON_EPSILON:
            return

        scale_factor = target_scale / self._zoom_factor
        self._zoom_factor = target_scale
        self.scale(scale_factor, scale_factor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Handles zooming with the mouse wheel.

        Args:
            event (QWheelEvent): The wheel event.
        """
        zoom_in_factor = conf.ZOOM_STEP_FACTOR
        zoom_out_factor = 1 / conf.ZOOM_STEP_FACTOR

        if event.angleDelta().y() > 0:
            self._zoom(zoom_in_factor, event.pos())
        else:
            self._zoom(zoom_out_factor, event.pos())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        Handles keyboard events for zooming and other shortcuts.

        Args:
            event (QKeyEvent): The key press event.
        """
        zoom_in_factor = conf.ZOOM_STEP_FACTOR
        zoom_out_factor = 1 / conf.ZOOM_STEP_FACTOR

        if event.modifiers() == Qt.ControlModifier:
            if event.key() == Qt.Key_Plus or event.key() == Qt.Key_Equal:
                self._zoom(zoom_in_factor, self.viewport().rect().center())
                event.accept()
            elif event.key() == Qt.Key_Minus:
                self._zoom(zoom_out_factor, self.viewport().rect().center())
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handles mouse press for panning.

        Args:
            event (QMouseEvent): The mouse press event.
        """
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Handles mouse move for panning by adjusting the scrollbars.

        This method provides a robust way to pan without directly manipulating
        the view's transformation matrix, which can interfere with zooming.

        Args:
            event (QMouseEvent): The mouse move event.
        """
        if self._panning:
            delta = event.pos() - self._last_pan_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._last_pan_pos = event.pos()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Handles mouse release for panning.

        Args:
            event (QMouseEvent): The mouse release event.
        """
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

class MainWindow(QMainWindow):
    """
    The main application window for the block diagram editor.
    Provides controls for adding blocks and displaying the canvas.
    """
    def __init__(self, enable_logging: bool = True, optimizer_func: Optional[Callable] = None) -> None:
        """
        Initializes the MainWindow.

        Args:
            enable_logging (bool, optional): If True, enables printing log messages
                to the console. Defaults to True.
            optimizer_func (Callable, optional): A function that takes a
                main_window instance and a list of possible moves to run a
                layout optimization. It should return the final cost score as
                a float. If provided, an "Optimize Placement" option will be
                available.
        """
        super().__init__()
        self.setWindowTitle(conf.UI.MAIN_WINDOW_TITLE) # Set window title from constant
        self.setGeometry(conf.MAIN_WINDOW_DEFAULT_X, conf.MAIN_WINDOW_DEFAULT_Y, conf.MAIN_WINDOW_DEFAULT_WIDTH, conf.MAIN_WINDOW_DEFAULT_HEIGHT) # Set window geometry from constants

        self.log_enabled = enable_logging
        self.optimizer_func = optimizer_func
        self.optimizer_is_running = False
        self.is_shutting_down = False
        # Pass the log_message method to the scene
        self.scene = BlockDiagramScene(self) 
        self.scene.log_func = self.log_message # Assign the log function to the scene
        self.scene.optimizer_available = self.optimizer_func is not None

        self.view = BlockDiagramView(self.scene, self)
        self.setCentralWidget(self.view)

        self.scene.addBlockRequested.connect(self.add_new_block_from_signal) # Connect to a new handler
        self.scene.addDiagramInputRequested.connect(self.add_new_diagram_input)
        self.scene.addDiagramOutputRequested.connect(self.add_new_diagram_output)
        self.scene.addPinToBlockRequested.connect(self.add_pin_to_selected_block)
        self.scene.renameBlockRequested.connect(self.rename_block)
        self.scene.renameDiagramPinRequested.connect(self.rename_diagram_pin)
        self.scene.fitInViewRequested.connect(self.view.fit_all_items_in_view)
        self.scene.optimizePlacementRequested.connect(self.optimize_placement)
        self.scene.unlockAllRequested.connect(self.unlock_all_items)
        self.scene.exportSvgRequested.connect(self.export_to_svg)

        self._create_toolbar()

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        # addPermanentWidget makes it appear on the right side
        self.status_bar.addPermanentWidget(self.progress_bar)

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handles the window close event to allow graceful shutdown during optimization.

        If the optimizer is running, it sets a flag to stop the loop and
        ignores the close event. The optimizer will re-trigger the close
        once it has terminated.
        """
        self.is_shutting_down = True
        if self.optimizer_is_running:
            self.show_status_message("Finishing optimization before closing...", 0)
            event.ignore()  # Prevent closing immediately
        else:
            event.accept()  # Allow closing

    def _is_name_unique(self, name: str, item_class_or_tuple: Union[type, Tuple[type, ...]], item_to_ignore: Optional[QGraphicsItem] = None) -> bool:
        """Checks if a name is unique for a given item type in the scene."""
        for item in self.scene.items():
            # Ignore the item being renamed
            if item == item_to_ignore:
                continue
            # Check if an item of the same type and name already exists
            if isinstance(item, item_class_or_tuple) and hasattr(item, 'name') and item.name == name:
                return False
        return True

    def log_message(self, message: str) -> None:
        """
        Prints a message to the console if logging is enabled.

        Args:
            message (str): The message to log.
        """
        if self.log_enabled:
            print(message)

    def _create_toolbar(self) -> None:
        """Creates and configures the toolbar with actions."""
        toolbar = self.addToolBar(conf.UI.Menu.TOOLBAR_ACTIONS) # Create a toolbar
        toolbar.setMovable(False)
        # The "Add Block" button is removed from the toolbar.
        # It will now be available via right-click context menu on the canvas.
        # add_block_btn = QPushButton("Add Block", self)
        # The "Add Pin" button is also removed and moved to the Block's context menu.
        # add_pin_btn = QPushButton("Add Pin to Selected", self)
        # add_pin_btn.clicked.connect(self.add_pin_to_selected_block) # Connect to the slot
        # toolbar.addWidget(add_pin_btn)

    def show_status_message(self, message: str, timeout: int = 0) -> None:
        """Shows a message in the status bar for a specified duration."""
        self.status_bar.showMessage(message, timeout)

    def show_progress_bar(self, max_value: int) -> None:
        """Shows and configures the progress bar in the status bar."""
        self.progress_bar.setMaximum(max_value)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def update_progress_bar(self, value: int) -> None:
        """Updates the value of the progress bar."""
        self.progress_bar.setValue(value)

    def hide_progress_bar(self) -> None:
        """Hides the progress bar from the status bar."""
        self.progress_bar.setVisible(False)

    def add_pin_to_selected_block(self) -> None:
        """
        Opens a series of dialogs to add a new pin to the selected block.

        This method first checks for a uniquely selected block. It then prompts
        the user for the new pin's name and type (input or output). If the
        user provides valid input, a new pin is added to the block, and the
        block's size is automatically adjusted.
        """
        selected_items = self.scene.selectedItems()
        if not selected_items:
            self.log_message(conf.UI.Log.NO_BLOCK_SELECTED)
            return

        selected_block = None
        for item in selected_items:
            if isinstance(item, Block):
                selected_block = item
                break

        if not isinstance(selected_block, Block): # Ensure it's a Block instance
            self.log_message(conf.UI.Log.NOT_A_BLOCK)
            return

        pin_name, ok = QInputDialog.getText(self, conf.UI.Dialog.NEW_BLOCK_PIN_TITLE, conf.UI.Dialog.NEW_BLOCK_PIN_LABEL)
        if not ok or not pin_name:
            return

        # Check for duplicate pin names on this specific block
        if pin_name in selected_block.input_pins or pin_name in selected_block.output_pins:
            QMessageBox.warning(self, conf.UI.Dialog.ADD_PIN_FAILED_TITLE,
                                conf.UI.Log.PIN_ALREADY_EXISTS.format(pin_name=pin_name))
            return

        pin_type_options = {
            conf.UI.Dialog.BLOCK_PIN_TYPE_INPUT_STR: PinType.INPUT,
            conf.UI.Dialog.BLOCK_PIN_TYPE_OUTPUT_STR: PinType.OUTPUT
        }
        pin_type_str, ok = QInputDialog.getItem(self, conf.UI.Dialog.BLOCK_PIN_TYPE_TITLE, conf.UI.Dialog.BLOCK_PIN_TYPE_LABEL,
                                             list(pin_type_options.keys()), conf.UI.Dialog.DIALOG_DEFAULT_CHOICE_INDEX, False)
        if ok and pin_type_str:
            pin_type = pin_type_options[pin_type_str]
            if pin_type == PinType.INPUT:
                selected_block.add_input_pin(pin_name)
                self.log_message(conf.UI.Log.ADDED_INPUT_BLOCK_PIN.format(pin_name=pin_name, selected_block=selected_block))
            else:
                selected_block.add_output_pin(pin_name)
                self.log_message(conf.UI.Log.ADDED_OUTPUT_BLOCK_PIN.format(pin_name=pin_name, selected_block=selected_block))
            
            # Adding a pin changes the block's size, so the super block is dirty.
            self.scene.realign_diagram_pins()

    def _rename_item(self, item_to_rename: QGraphicsItem, item_type: Union[type, Tuple[type, ...]], dialog_title: str, dialog_label: str, log_format_str: str) -> None:
        """
        Generic helper to rename a diagram item (Block or DiagramPin).

        Args:
            item_to_rename (QGraphicsItem): The item to rename.
            item_type (Union[type, Tuple[type, ...]]): The expected type(s) of the item.
            dialog_title (str): The title for the input dialog.
            dialog_label (str): The label for the input dialog.
            log_format_str (str): The format string for the log message.
        """
        if not isinstance(item_to_rename, item_type):
            return

        old_name = item_to_rename.name
        new_name, ok = QInputDialog.getText(self, dialog_title,
                                            dialog_label,
                                            text=old_name)
        if ok and new_name and new_name != old_name:
            # Check for name uniqueness before applying the change
            if not self._is_name_unique(new_name, item_type, item_to_ignore=item_to_rename):
                type_name = item_to_rename.__class__.__name__
                QMessageBox.warning(self, conf.UI.Dialog.RENAME_FAILED_TITLE,
                                    conf.UI.Log.ITEM_NAME_ALREADY_EXISTS.format(item_type=type_name, name=new_name))
                return

            item_to_rename.name = new_name
            self.log_message(log_format_str.format(old_name=old_name, new_name=new_name))
            # If a block was renamed, its size might have changed, affecting the super block.
            if isinstance(item_to_rename, Block):
                self.scene.realign_diagram_pins()

    def rename_block(self, block_to_rename: Block) -> None:
        """
        Opens a dialog to rename the given block.

        Args:
            block_to_rename (Block): The block item to be renamed.
        """
        self._rename_item(block_to_rename, Block, conf.UI.Dialog.RENAME_BLOCK_TITLE, conf.UI.Dialog.RENAME_BLOCK_LABEL, conf.UI.Log.BLOCK_RENAMED)

    def rename_diagram_pin(self, pin_to_rename: DiagramPin) -> None:
        """
        Opens a dialog to rename the given diagram pin.

        Args:
            pin_to_rename (DiagramPin): The diagram pin item to be renamed.
        """
        self._rename_item(pin_to_rename, (DiagramInputPin, DiagramOutputPin), conf.UI.Dialog.RENAME_DIAGRAM_PIN_TITLE, conf.UI.Dialog.RENAME_DIAGRAM_PIN_LABEL, conf.UI.Log.DIAGRAM_PIN_RENAMED)

    def add_new_block_from_signal(self, placement_hint: QPointF, log_func: Callable[[str], None]) -> None:
        """
        Slot to handle the `addBlockRequested` signal from the scene.

        This method is connected to the `BlockDiagramScene.addBlockRequested`
        signal and calls `add_new_block` with the position and logging
        function provided by the signal.

        Args:
            placement_hint (QPointF): The scene position for the new block.
            log_func (callable): The logging function to be used by the block.
        """
        self.add_new_block(placement_hint=placement_hint, log_func=log_func)

    def _add_new_item(self,
                      item_class: type,
                      dialog_title: str,
                      dialog_label: str,
                      log_format_str: str,
                      placement_hint: Optional[QPointF] = None,
                      log_func: Optional[Callable[[str], None]] = None) -> None:
        """
        Generic helper to add a new named item (Block or DiagramPin) to the scene.

        This method prompts the user for a name, then creates and places the
        item on the scene using auto-placement logic.

        Args:
            item_class (type): The class of the item to create (e.g., Block).
            dialog_title (str): The title for the input dialog.
            dialog_label (str): The label for the input dialog.
            log_format_str (str): The format string for the log message.
            placement_hint (QPointF, optional): A hint for placement. Defaults to None.
            log_func (callable, optional): The logging function to use. Defaults to None.
        """
        name, ok = QInputDialog.getText(self, dialog_title, dialog_label)
        if ok and name:
            # Check for name uniqueness before creating the item
            if not self._is_name_unique(name, item_class):
                QMessageBox.warning(self, conf.UI.Dialog.CREATION_FAILED_TITLE,
                                    conf.UI.Log.ITEM_NAME_ALREADY_EXISTS.format(item_type=item_class.__name__, name=name))
                return

            if placement_hint is None:
                placement_hint = self.view.mapToScene(self.view.viewport().rect().center())

            effective_log_func = log_func if log_func else self.log_message

            new_item = item_class(name=name,
                                  scene_for_auto_placement=self.scene,
                                  placement_hint=placement_hint,
                                  log_func=effective_log_func)
            self.scene.addItem(new_item)
            pos = new_item.scenePos()
            self.log_message(log_format_str.format(name=name, pos_x=pos.x(), pos_y=pos.y()))

            # If a block was added, the super block has changed, so realign pins.
            if isinstance(new_item, Block):
                self.scene.realign_diagram_pins()

    def add_new_block(self, placement_hint: Optional[QPointF] = None, log_func: Optional[Callable[[str], None]] = None) -> None:
        """
        Prompts for a name and creates a new block on the canvas.
        """
        self._add_new_item(Block, conf.UI.Dialog.NEW_BLOCK_TITLE, conf.UI.Dialog.NEW_BLOCK_LABEL, conf.UI.Log.ADDED_NEW_BLOCK, placement_hint, log_func)

    def unlock_all_items(self) -> None:
        """
        Finds and unlocks all locked blocks and wires in the scene.
        """
        unlocked_count = 0
        for item in self.scene.items():
            if isinstance(item, Block) and item.is_locked:
                item.set_locked(False)
                unlocked_count += 1
            elif isinstance(item, Wire) and item.is_locked:
                item.set_locked(False)
                unlocked_count += 1
        if unlocked_count > 0:
            self.log_message(conf.UI.Log.UNLOCKED_ALL_ITEMS)

    def add_new_diagram_input(self) -> None:
        """
        Prompts for a name and creates a new DiagramInput pin on the canvas,
        which is then automatically aligned with other diagram pins.
        """
        name, ok = QInputDialog.getText(self, conf.UI.Dialog.NEW_SYS_INPUT_TITLE, conf.UI.Dialog.NEW_SYS_INPUT_LABEL)
        if not ok or not name:
            return

        if not self._is_name_unique(name, DiagramInputPin):
            QMessageBox.warning(self, conf.UI.Dialog.CREATION_FAILED_TITLE,
                                conf.UI.Log.ITEM_NAME_ALREADY_EXISTS.format(item_type=DiagramInputPin.__name__, name=name))
            return

        # Create the item without a specific position. It will be auto-placed temporarily.
        new_item = DiagramInputPin(name=name, scene_for_auto_placement=self.scene, log_func=self.log_message)
        self.scene.addItem(new_item)

        # Realign all diagram pins to evenly space them, including the new one.
        self.scene.realign_diagram_pins()

        scene_pos = new_item.scenePos() # Get position after realignment
        self.log_message(conf.UI.Log.ADDED_NEW_DIAGRAM_INPUT.format(name=name, pos_x=scene_pos.x(), pos_y=scene_pos.y()))

    def add_new_diagram_output(self) -> None:
        """
        Prompts for a name and creates a new DiagramOutput pin on the canvas,
        which is then automatically aligned with other diagram pins.
        """
        name, ok = QInputDialog.getText(self, conf.UI.Dialog.NEW_SYS_OUTPUT_TITLE, conf.UI.Dialog.NEW_SYS_OUTPUT_LABEL)
        if not ok or not name:
            return

        if not self._is_name_unique(name, DiagramOutputPin):
            QMessageBox.warning(self, conf.UI.Dialog.CREATION_FAILED_TITLE,
                                conf.UI.Log.ITEM_NAME_ALREADY_EXISTS.format(item_type=DiagramOutputPin.__name__, name=name))
            return

        # Create the item without a specific position. It will be auto-placed temporarily.
        new_item = DiagramOutputPin(name=name, scene_for_auto_placement=self.scene, log_func=self.log_message)
        self.scene.addItem(new_item)

        # Realign all diagram pins to evenly space them, including the new one.
        self.scene.realign_diagram_pins()

        scene_pos = new_item.scenePos() # Get position after realignment
        self.log_message(conf.UI.Log.ADDED_NEW_DIAGRAM_OUTPUT.format(name=name, pos_x=scene_pos.x(), pos_y=scene_pos.y()))

    # --- Programmatic API for Layout and Analysis ---

    def move_block(self, block_name: str, x: float, y: float) -> bool:
        """
        Programmatically moves a block to a new position.

        The position is snapped to the grid automatically by the item's itemChange handler.

        Args:
            block_name (str): The name of the block to move.
            x (float): The new x-coordinate for the block's top-left corner.
            y (float): The new y-coordinate for the block's top-left corner.

        Returns:
            bool: True if the block was found and moved, False otherwise.
        """
        for item in self.scene.items():
            if isinstance(item, Block) and item.name == block_name:
                item.setPos(x, y) # itemChange will handle snapping and realignment
                self.log_message(conf.UI.Log.BLOCK_MOVED.format(block_name=block_name, x=x, y=y))
                return True
        self.log_message(conf.UI.Log.BLOCK_NOT_FOUND.format(block_name=block_name))
        return False

    def set_block_pin_order(self, block_name: str, pin_type: PinType, ordered_pin_names: List[str]) -> bool:
        """
        Programmatically sets the vertical order of pins on a block.

        Args:
            block_name (str): The name of the target block.
            pin_type (PinType): The type of pins to reorder (PinType.INPUT or PinType.OUTPUT).
            ordered_pin_names (List[str]): A list of pin names in the desired new order.
                This list must contain all and only the existing pins of the specified type.

        Returns:
            bool: True if the pins were successfully reordered, False otherwise.
        """
        block = None
        for item in self.scene.items():
            if isinstance(item, Block) and item.name == block_name:
                block = item
                break
        if not block:
            self.log_message(conf.UI.Log.BLOCK_NOT_FOUND.format(block_name=block_name))
            return False

        pins_to_reorder = block.input_pins if pin_type == PinType.INPUT else block.output_pins

        # Validate that the provided list of names matches the existing pins
        if set(ordered_pin_names) != set(pins_to_reorder.keys()):
            self.log_message(conf.UI.Log.BLOCK_PIN_REORDER_MISMATCH.format(block_name=block_name))
            return False

        # Update the index of each pin according to the new order
        for i, pin_name in enumerate(ordered_pin_names):
            pins_to_reorder[pin_name].index = i

        # Trigger a visual update of the pin positions on the block
        block.update_pin_positions()
        self.log_message(conf.UI.Log.BLOCK_PINS_REORDERED.format(pin_type=pin_type.name.lower(), block_name=block_name))
        return True

    def set_diagram_pin_order(self, pin_type: PinType, ordered_pin_names: List[str]) -> bool:
        """
        Programmatically sets the vertical order of diagram pins.

        Args:
            pin_type (PinType): The logical type of pins to reorder. Use PinType.OUTPUT
                for DiagramInputPins (sources) and PinType.INPUT for DiagramOutputPins (sinks).
            ordered_pin_names (List[str]): A list of pin names in the desired new order.
                This list must contain all and only the existing pins of the specified type.

        Returns:
            bool: True if the pins were successfully reordered, False otherwise.
        """
        # Determine the target class based on the logical pin type
        if pin_type == PinType.OUTPUT: # DiagramInputPins are logical outputs
            target_class = DiagramInputPin
            type_name = conf.UI.PIN_TYPE_INPUT_LOWER
        elif pin_type == PinType.INPUT: # DiagramOutputPins are logical inputs
            target_class = DiagramOutputPin
            type_name = conf.UI.PIN_TYPE_OUTPUT_LOWER
        else:
            self.log_message(conf.UI.Log.DIAGRAM_PIN_REORDER_INVALID_TYPE)
            return False

        pins_to_reorder = {item.name: item for item in self.scene.items() if isinstance(item, target_class)}

        if set(ordered_pin_names) != set(pins_to_reorder.keys()):
            self.log_message(conf.UI.Log.DIAGRAM_PIN_REORDER_MISMATCH.format(type_name=type_name))
            return False

        # Temporarily set the Y position of each pin based on the desired order.
        # The realign_diagram_pins function sorts by Y position, so this establishes the new order.
        for i, pin_name in enumerate(ordered_pin_names):
            pin = pins_to_reorder.get(pin_name)
            if pin:
                pin.setPos(pin.scenePos().x(), i) # Y-value establishes sort order

        self.scene.realign_diagram_pins()
        self.log_message(conf.UI.Log.DIAGRAM_PINS_REORDERED.format(type_name=type_name))
        return True

    def _calculate_intersection_score(self) -> float:
        """
        Calculates the intersection score for the diagram.

        The score is a sum of penalties for intersections. The penalty is
        proportional to the area of the intersection, providing a more
        granular measure than a simple count.

        Returns:
            float: The total intersection score.
        """
        wires = [item for item in self.scene.items() if isinstance(item, Wire)]
        blocks = [item for item in self.scene.items() if isinstance(item, Block)]
        intersection_score = 0.0

        # 1. Calculate wire-wire intersections
        for wire1, wire2 in itertools.combinations(wires, 2):
            pins1 = {wire1.start_pin, wire1.end_pin}
            pins2 = {wire2.start_pin, wire2.end_pin}

            # Ignore intersections between wires that share a pin, as they
            # are expected to intersect at the pin.
            if pins1.isdisjoint(pins2):
                # Use the wire's shape (the clickable area) for intersection.
                if conf.USE_DETAILED_INTERSECTION_CHECK:
                    intersection = wire1.shape().intersected(wire2.shape())
                    if not intersection.isEmpty():
                        # The penalty is the area of the bounding box of the intersection.
                        penalty = intersection.boundingRect().width() * intersection.boundingRect().height()
                        intersection_score += penalty
                else:
                    if wire1.path().intersects(wire2.path()):
                        intersection_score += 1.0

        # 2. Calculate wire-block intersections
        for wire in wires:
            connected_blocks = {p.parent_block for p in (wire.start_pin, wire.end_pin) if p and p.parent_block}
            wire_shape = wire.shape()
            for block in blocks:
                if block not in connected_blocks:                    
                    block_path = QPainterPath()
                    block_path.addRect(block.sceneBoundingRect())
                    if conf.USE_DETAILED_INTERSECTION_CHECK:
                        intersection = wire_shape.intersected(block_path)
                        if not intersection.isEmpty():
                            penalty = intersection.boundingRect().width() * intersection.boundingRect().height()
                            intersection_score += penalty
                    else:
                        if wire.path().intersects(block.sceneBoundingRect()):
                            intersection_score += 1.0

        return intersection_score

    def _calculate_total_wire_length(self) -> float:
        """
        Calculates the total length of all wires in the diagram.

        Returns:
            float: The sum of all wire lengths, in scene units.
        """
        total_length = 0.0
        wires = [item for item in self.scene.items() if isinstance(item, Wire)]
        for wire in wires:
            total_length += wire.path().length()
        return total_length

    def calculate_diagram_cost(self, cost_params: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculates a total cost score for the current diagram layout.

        The cost is a weighted sum of different metrics, such as wire
        intersections and total wire length. The weights can be passed via
        `cost_params` or will default to the values in conf.py.

        Args:
            cost_params (Dict[str, Any], optional): A dictionary containing
                'intersection_weight' and 'wirelength_weight'.

        Returns:
            float: The total weighted cost score for the diagram.
        """
        if cost_params is None:
            cost_params = {}

        intersection_weight = cost_params.get('intersection_weight', conf.COST_FUNCTION_INTERSECTION_WEIGHT)
        wirelength_weight = cost_params.get('wirelength_weight', conf.COST_FUNCTION_WIRELENGTH_WEIGHT)

        intersection_score = self._calculate_intersection_score()
        wire_length_score = self._calculate_total_wire_length()

        total_cost = (intersection_score * intersection_weight) + \
                     (wire_length_score * wirelength_weight)

        self.log_message(conf.UI.Log.DIAGRAM_COST_BREAKDOWN.format(intersection_score=intersection_score, wire_length_score=wire_length_score))
        self.log_message(conf.UI.Log.DIAGRAM_COST_TOTAL.format(cost=total_cost))

        return total_cost

    def optimize_placement(self) -> None:
        """
        Gathers optimizable items and runs the placement optimization algorithm.

        This method prepares the data (blocks, pins, etc.) and then calls the
        optimizer function that was provided during initialization.
        """
        if not self.optimizer_func:
            self.log_message(conf.UI.Log.OPTIMIZER_NOT_CONFIGURED)
            return
        
        self.optimizer_is_running = True
        self.view.setEnabled(False)
        try:
            self._run_optimizer_logic()
        finally:
            # This block ensures that the optimizer state is reset and the UI is
            # cleaned up, regardless of whether the optimizer completes or is cancelled.
            self.optimizer_is_running = False
            self.hide_progress_bar()
            self.view.setEnabled(True)

            # If a shutdown was requested, re-trigger the close event now that the
            # long-running process has finished.
            if self.is_shutting_down:
                self.close()

    def _run_optimizer_logic(self) -> None:
        """
        Helper method that prepares data and wraps the optimizer call.

        This wrapper handles the final reporting of the optimization result,
        while the injected optimizer function is responsible for the core
        algorithm and its own progress reporting.
        """
        self.log_message(conf.UI.Log.OPTIMIZER_START)

        # --- Gather all optimizable items ---
        blocks = [item for item in self.scene.items() if isinstance(item, Block)]
        diagram_inputs = [item for item in self.scene.items() if isinstance(item, DiagramInputPin)]
        diagram_outputs = [item for item in self.scene.items() if isinstance(item, DiagramOutputPin)]

        if not blocks:
            message = conf.UI.Log.OPTIMIZER_NO_BLOCKS
            self.log_message(message)
            self.show_status_message(message, conf.STATUS_BAR_TIMEOUT_MS)
            return # Exit gracefully

        # --- Build a list of possible optimization "moves" ---
        possible_moves = []
        for block in blocks:
            if not block.is_locked:
                possible_moves.append({conf.Key.MOVE_TYPE: MoveType.MOVE_BLOCK, conf.Key.BLOCK: block})
        for block in blocks:
            if len(block.input_pins) > 1 and not any(p.is_locked for p in block.input_pins.values()):
                possible_moves.append({conf.Key.MOVE_TYPE: MoveType.REORDER_BLOCK_PINS, conf.Key.BLOCK: block, conf.Key.PIN_TYPE: PinType.INPUT})
            if len(block.output_pins) > 1 and not any(p.is_locked for p in block.output_pins.values()):
                possible_moves.append({conf.Key.MOVE_TYPE: MoveType.REORDER_BLOCK_PINS, conf.Key.BLOCK: block, conf.Key.PIN_TYPE: PinType.OUTPUT})
        if len(diagram_inputs) > 1 and not any(p.is_locked for p in diagram_inputs):
            possible_moves.append({conf.Key.MOVE_TYPE: MoveType.REORDER_DIAGRAM_PINS, conf.Key.PIN_TYPE: PinType.OUTPUT, conf.Key.PINS: diagram_inputs})
        if len(diagram_outputs) > 1 and not any(p.is_locked for p in diagram_outputs):
            possible_moves.append({conf.Key.MOVE_TYPE: MoveType.REORDER_DIAGRAM_PINS, conf.Key.PIN_TYPE: PinType.INPUT, conf.Key.PINS: diagram_outputs})

        # Centralized check for optimizable moves.
        if not possible_moves:
            message = conf.UI.Log.OPTIMIZER_NO_MOVES
            self.log_message(message)
            self.show_status_message(message, conf.STATUS_BAR_TIMEOUT_MS)
            return

        try:
            # Call the optimizer function with the prepared data
            final_cost = self.optimizer_func(self, possible_moves)

            # Show completion message, but only if the process wasn't cancelled by shutdown
            if not self.is_shutting_down:
                final_message = conf.UI.Log.OPTIMIZER_COMPLETE.format(cost=final_cost)
                self.show_status_message(final_message, conf.STATUS_BAR_TIMEOUT_MS)
                self.log_message(final_message)
        except OptimizationError as e:
            # If the optimizer raises a specific error (e.g., no moves), log it.
            self.log_message(str(e))
            self.show_status_message(str(e), conf.STATUS_BAR_TIMEOUT_MS)
        except Exception as e:
            # Log detailed error for the developer
            self.log_message(conf.UI.Log.OPTIMIZER_UNEXPECTED_ERROR_LOG.format(error=e))
            traceback.print_exc()
            # Show a user-friendly message
            QMessageBox.critical(self, conf.UI.Dialog.OPTIMIZATION_FAILED_TITLE, conf.UI.Dialog.OPTIMIZER_UNEXPECTED_ERROR_MSG)

    # --- Programmatic API ---
    def _create_item(self, item_class: type, name: str, log_format_str: str, pos: Optional[QPointF] = None) -> Optional[QGraphicsItem]:
        """
        Generic helper to programmatically create and add an item to the scene.

        This method handles name uniqueness checks and determines the item's
        initial position. If a position (`pos`) is not provided, it calculates
        a "smart" placement hint:
        - If the scene is empty, it uses the center of the current view.
        - If items exist, it places the new item to the right of the
          bounding box of all existing items, preventing crowding.

        Args:
            item_class (type): The class of the item to create (e.g., Block).
            name (str): The name for the new item.
            log_format_str (str): The format string for the success log message.
            pos (QPointF, optional): The desired position for the item. If None,
                auto-placement is used. Defaults to None.

        Returns:
            QGraphicsItem or None: The created item, or None if an item with
            the same name and type already exists.
        """
        if not self._is_name_unique(name, item_class):
            self.log_message(conf.UI.Log.CREATION_FAILED_DUPLICATE_NAME.format(item_type=item_class.__name__, name=name))
            return None

        # If a position is explicitly provided, use it.
        if pos is not None:
            placement_hint = pos
        else:
            # If no position is provided, calculate a smart placement hint.
            items_rect = self.scene.itemsBoundingRect()
            if items_rect.isEmpty():
                # If the scene is empty, place it in the center of the view.
                placement_hint = self.view.mapToScene(self.view.viewport().rect().center())
            else:
                # Otherwise, place it to the right of existing items.
                offset = conf.STANDARD_BLOCK_WIDTH
                placement_hint = QPointF(items_rect.right() + offset, items_rect.center().y())

        item = item_class(name=name,
                          scene_for_auto_placement=self.scene,
                          placement_hint=placement_hint,
                          log_func=self.log_message)
        self.scene.addItem(item)
        scene_pos = item.scenePos()
        self.log_message(log_format_str.format(name=name, pos_x=scene_pos.x(), pos_y=scene_pos.y()))
        return item

    def create_block(self, name: str, pos: Optional[QPointF] = None, input_pins: Optional[List[str]] = None, output_pins: Optional[List[str]] = None) -> Optional[Block]:
        """
        Programmatically creates and adds a block to the scene.

        If `pos` is not provided, the block is auto-placed to the right of
        existing items to avoid overlap.

        Args:
            name (str): The name for the new block.
            pos (QPointF, optional): The desired top-left position for the block.
                If None, auto-placement is used. Defaults to None.
            input_pins (list[str], optional): A list of names for input pins
                to be created on the block.
            output_pins (list[str], optional): A list of names for output pins
                to be created on the block.

        Returns:
            Block or None: The created Block object, or None on failure (e.g.,
            if the name is not unique).
        """
        block = self._create_item(Block, name, conf.UI.Log.ADDED_NEW_BLOCK, pos)
        if isinstance(block, Block):
            if input_pins:
                for pin_name in input_pins:
                    block.add_input_pin(pin_name)
            if output_pins:
                for pin_name in output_pins:
                    block.add_output_pin(pin_name)
            # After adding a block and its pins, the super block has changed.
            # Realign all diagram pins to the new super block boundaries.
            self.scene.realign_diagram_pins()
        return block

    def create_diagram_input(self, name: str) -> Optional[DiagramInputPin]:
        """
        Programmatically creates and adds a diagram input pin to the scene.

        The pin is automatically aligned with other diagram pins.

        Args:
            name (str): The name for the new diagram input pin.

        Returns:
            DiagramInputPin or None: The created pin, or None on failure.
        """
        if not self._is_name_unique(name, DiagramInputPin):
            self.log_message(conf.UI.Log.CREATION_FAILED_DUPLICATE_NAME.format(item_type=DiagramInputPin.__name__, name=name))
            return None

        new_item = DiagramInputPin(name=name, scene_for_auto_placement=self.scene, log_func=self.log_message)
        self.scene.addItem(new_item)

        self.scene.realign_diagram_pins()

        scene_pos = new_item.scenePos() # Get position after realignment
        self.log_message(conf.UI.Log.ADDED_NEW_DIAGRAM_INPUT.format(name=name, pos_x=scene_pos.x(), pos_y=scene_pos.y()))
        return new_item

    def create_diagram_output(self, name: str) -> Optional[DiagramOutputPin]:
        """
        Programmatically creates and adds a diagram output pin to the scene.

        The pin is automatically aligned with other diagram pins.

        Args:
            name (str): The name for the new diagram output pin.

        Returns:
            DiagramOutputPin or None: The created pin, or None on failure.
        """
        if not self._is_name_unique(name, DiagramOutputPin):
            self.log_message(conf.UI.Log.CREATION_FAILED_DUPLICATE_NAME.format(item_type=DiagramOutputPin.__name__, name=name))
            return None

        new_item = DiagramOutputPin(name=name, scene_for_auto_placement=self.scene, log_func=self.log_message)
        self.scene.addItem(new_item)

        self.scene.realign_diagram_pins()

        scene_pos = new_item.scenePos() # Get position after realignment
        self.log_message(conf.UI.Log.ADDED_NEW_DIAGRAM_OUTPUT.format(name=name, pos_x=scene_pos.x(), pos_y=scene_pos.y()))
        return new_item

    def export_to_svg(self) -> None:
        """
        Opens a file dialog to export the current diagram to an SVG file.
        """
        if not self.scene.items():
            self.show_status_message(conf.UI.Log.EXPORT_EMPTY_DIAGRAM, conf.STATUS_BAR_TIMEOUT_MS)
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            conf.UI.Dialog.EXPORT_DIALOG_TITLE,
            "",
            conf.UI.Dialog.EXPORT_SVG_FILTER
        )

        if not file_path:
            return

        if not file_path.lower().endswith('.svg'):
            file_path += '.svg'

        # Get the rectangle of the visible area in scene coordinates.
        # This captures the current pan and zoom of the view.
        source_rect = self.view.mapToScene(self.view.viewport().rect()).boundingRect()

        svg_generator = QSvgGenerator()
        svg_generator.setFileName(file_path)
        svg_generator.setSize(source_rect.size().toSize())
        svg_generator.setViewBox(source_rect)
        svg_generator.setTitle(conf.UI.SVG.TITLE)
        svg_generator.setDescription(conf.UI.SVG.DESCRIPTION)

        painter = QPainter(svg_generator)
        # Render the entire scene. The SVG's viewBox will act as a camera,
        # showing only the portion of the scene that was visible in the view.
        self.scene.render(painter)
        painter.end()

        status_message = conf.UI.Log.EXPORT_SUCCESS.format(file_path=file_path)
        self.show_status_message(status_message, conf.STATUS_BAR_TIMEOUT_MS)
        self.log_message(status_message)

    def start(self) -> int:
        """
        Shows the window and starts the Qt application event loop.
 
        This method requires that a QApplication instance has already been
        created. It should be called after the window has been populated with
        items.

        Returns:
            int: The exit status from the application.
        """
        # A QApplication instance must exist before this method is called.
        # The user of the library is responsible for creating it.
        app = QApplication.instance()
        if not app:
            # This prevents the application from crashing with a less clear
            # error if the user forgets to create the QApplication.
            raise RuntimeError(conf.UI.Log.QAPP_INSTANCE_REQUIRED)

        self.show()
        return app.exec_()