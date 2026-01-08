# Future Enhancements for the `diagrams` Editor

This document tracks potential future enhancements and features for the `diagrams` block diagram editor.

1.  **Refactor Logging**: Replace the current `print`-based logging with Python's standard `logging` module for better control over levels, formatting, and output handlers.

2.  **Persistent Settings**: Use `QSettings` to remember the main window's size and position, as well as the last view's zoom level and scroll position between sessions.

3.  **Fix Pan/Zoom Behavior**: Correct the behavior of "Fit to View" and manual zooming, especially when the diagram is wide and zoom levels are clamped, to prevent the view from being shifted and cropping content.

4.  **Fix SVG Export**: Ensure that SVG export correctly captures the current view (WYSIWYG), which is affected by the same pan/zoom issues.

5.  **Copy/Paste Functionality**: Implement copy and paste for blocks and diagram pins.

6.  **Externalize Configuration**: Move graphical configuration (colors, sizes, shapes, fonts, etc.) from `conf.py` to a more flexible format like JSON or YAML to allow for easier theming.

7.  **Undo/Redo Functionality**: Add an undo/redo stack for actions like adding, removing, and moving blocks and wires.

8.  **Grid Options**: Add an option to toggle the visibility of the background grid.

9.  **Placement Optimization**: Improve automatic placement
