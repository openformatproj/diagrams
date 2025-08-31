# -*- coding: utf-8 -*-
"""
This module provides serialization and deserialization logic for converting
a structural `Part` from the `ml.engine` into a JSON format that can be
imported by the `diagrams.engine`.

The JSON format is designed to capture the essential elements of a structural
part: its own interface (ports), its inner components (sub-parts), and the
connections between them.

JSON Structure Definition:

{
  "format_version": "1.0",
  "part": {
    "identifier": "TopLevelPartName",
    "class": "ClassName",
    "ports": [
      {
        "name": "port_name",
        "direction": "input" | "output"
      }
    ],
    "inner_parts": [
      {
        "identifier": "child_part_id",
        "class": "ChildClassName",
        "ports": [
          {
            "name": "child_port_name",
            "direction": "input" | "output"
          }
        ]
      }
    ],
    "connections": [
      {
        "source": {
          "part_id": "part_identifier",
          "port_id": "port_name"
        },
        "destination": {
          "part_id": "part_identifier",
          "port_id": "port_name"
        }
      }
    ]
  }
}

Details:
- `part`: The root object representing the structural part being serialized.
- `identifier`: The unique instance name of the part.
- `class`: The Python class name of the part.
- `ports`: A list of the part's own input and output ports. These will become
           `DiagramInputPin` and `DiagramOutputPin` in the diagram.
- `inner_parts`: A list of the components contained within the structural part.
                 Each of these will become a `Block` in the diagram.
- `connections`: A list of all the wires. The `part_id` in the source and
                 destination can refer to either an `inner_part`'s identifier
                 or the top-level part's own identifier.
"""

# TODO:
# - Export diagram to JSON (in serializer.py: export_canvas_to_json)
# - Update docstrings

import json
from typing import Any

# Import for type checking and functionality, aliased to be explicit about origin.
import diagrams.conf as conf
from ml.engine import Part as MlPart, Port as MlPort

# These are type hints to avoid circular dependencies.
# The actual Part and MainWindow objects will be passed at runtime.
# MlPart = Any # Replaced by MlPart
MainWindow = Any

class DiagramSerializer:
    """
    Handles the serialization of an ml.engine.Part to JSON and the
    deserialization of that JSON to a diagrams.engine canvas.
    """

    def export_part_to_json(self, part: MlPart) -> str:
        """
        Exports a structural Part's topology to a JSON string.

        This method walks the part's structure, collecting information about
        its ports, inner parts, and the connections between them.

        Args:
            part: An instance of a structural `ml.engine.Part`.

        Returns:
            A JSON formatted string representing the part's structure.

        Raises:
            TypeError: If the provided part is not a structural part.
        """
        # The serialization logic is only valid for structural parts.
        if part._Part__description != MlPart.STRUCTURAL:
            raise TypeError(conf.UI.Log.SERIALIZATION_ONLY_STRUCTURAL)

        part_data = {
            conf.Key.IDENTIFIER_KEY: part.get_identifier(),
            conf.Key.CLASS_KEY: part.__class__.__name__,
            conf.Key.PORTS_KEY: [],
            conf.Key.INNER_PARTS_KEY: [],
            conf.Key.CONNECTIONS_KEY: []
        }

        # Serialize the top-level part's own ports
        for port in part.get_ports(MlPort.IN) + part.get_ports(MlPort.OUT):
            part_data[conf.Key.PORTS_KEY].append({conf.Key.NAME_KEY: port.get_identifier(), conf.Key.DIRECTION_KEY: port.get_direction()})

        # Serialize all inner parts and their respective ports
        for inner_part in part.get_parts():
            inner_part_data = {
                conf.Key.IDENTIFIER_KEY: inner_part.get_identifier(),
                conf.Key.CLASS_KEY: inner_part.__class__.__name__,
                conf.Key.PORTS_KEY: [{conf.Key.NAME_KEY: p.get_identifier(), conf.Key.DIRECTION_KEY: p.get_direction()} for p in inner_part.get_ports(MlPort.IN) + inner_part.get_ports(MlPort.OUT)]
            }
            part_data[conf.Key.INNER_PARTS_KEY].append(inner_part_data)

        # Serialize all data connections (interfaces)
        for interface in part.get_interfaces():
            source_port = interface.get_master_port()
            dest_port = interface.get_slave_port()
            part_data[conf.Key.CONNECTIONS_KEY].append({
                conf.Key.SOURCE_KEY: {conf.Key.PART_ID_KEY: source_port.get_parent().get_identifier(), conf.Key.PORT_ID_KEY: source_port.get_identifier()},
                conf.Key.DESTINATION_KEY: {conf.Key.PART_ID_KEY: dest_port.get_parent().get_identifier(), conf.Key.PORT_ID_KEY: dest_port.get_identifier()}
            })

        return json.dumps({conf.Key.FORMAT_VERSION_KEY: conf.UI.Serializer.FORMAT_VERSION, conf.Key.PART_KEY: part_data}, indent=2)

    def import_part_from_json(self, json_data: str, main_window: MainWindow) -> None:
        """
        Builds a diagram on the MainWindow canvas from a JSON string.

        This method parses the JSON, creates all the necessary blocks and
        diagram I/O pins, and then connects them with wires as defined in
        the data.

        Args:
            json_data: A string containing the JSON data.
            main_window: An instance of the diagrams.engine.MainWindow to build
                         the diagram on.

        Raises:
            ValueError: If the JSON data is malformed or missing the root 'part' object.
        """
        data = json.loads(json_data)
        part_data = data.get(conf.Key.PART_KEY)

        if not part_data:
            raise ValueError(conf.UI.Log.JSON_MISSING_ROOT_PART)

        # Dictionaries to store created diagram items for easy lookup during wiring.
        blocks = {}
        diagram_input_pins = {}
        diagram_output_pins = {}

        top_level_part_id = part_data[conf.Key.IDENTIFIER_KEY]

        # 1. Create Diagram I/O pins from the top-level part's ports.
        for port_info in part_data.get(conf.Key.PORTS_KEY, []):
            port_name = port_info[conf.Key.NAME_KEY]
            if port_info[conf.Key.DIRECTION_KEY] == conf.UI.PIN_TYPE_INPUT_LOWER:
                pin = main_window.create_diagram_input(port_name)
                if pin: diagram_input_pins[port_name] = pin
            elif port_info[conf.Key.DIRECTION_KEY] == conf.UI.PIN_TYPE_OUTPUT_LOWER:
                pin = main_window.create_diagram_output(port_name)
                if pin: diagram_output_pins[port_name] = pin

        # 2. Create Blocks for each inner part.
        for inner_part_info in part_data.get(conf.Key.INNER_PARTS_KEY, []):
            part_id = inner_part_info[conf.Key.IDENTIFIER_KEY]
            part_class = inner_part_info[conf.Key.CLASS_KEY]
            block_name = conf.UI.Serializer.BLOCK_NAME_FORMAT.format(part_id=part_id, part_class=part_class)
            input_pins = [p[conf.Key.NAME_KEY] for p in inner_part_info.get(conf.Key.PORTS_KEY, []) if p[conf.Key.DIRECTION_KEY] == conf.UI.PIN_TYPE_INPUT_LOWER]
            output_pins = [p[conf.Key.NAME_KEY] for p in inner_part_info.get(conf.Key.PORTS_KEY, []) if p[conf.Key.DIRECTION_KEY] == conf.UI.PIN_TYPE_OUTPUT_LOWER]
            block = main_window.create_block(block_name, input_pins=input_pins, output_pins=output_pins)
            if block: blocks[part_id] = block

        # 3. Create Wires from the connections list.
        for conn_info in part_data.get(conf.Key.CONNECTIONS_KEY, []):
            source_info, dest_info = conn_info[conf.Key.SOURCE_KEY], conn_info[conf.Key.DESTINATION_KEY]
            source_part_id, source_port_id = source_info[conf.Key.PART_ID_KEY], source_info[conf.Key.PORT_ID_KEY]
            dest_part_id, dest_port_id = dest_info[conf.Key.PART_ID_KEY], dest_info[conf.Key.PORT_ID_KEY]

            source_pin = diagram_input_pins.get(source_port_id) if source_part_id == top_level_part_id else blocks.get(source_part_id, {}).output_pins.get(source_port_id)
            dest_pin = diagram_output_pins.get(dest_port_id) if dest_part_id == top_level_part_id else blocks.get(dest_part_id, {}).input_pins.get(dest_port_id)

            if source_pin and dest_pin:
                main_window.scene.create_wire(source_pin, dest_pin)

        # 4. Fit the view to the newly created diagram.
        main_window.view.fit_all_items_in_view()