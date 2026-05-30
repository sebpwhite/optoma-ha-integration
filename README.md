# Optoma Projector

Home Assistant custom integration for controlling an Optoma projector over
RS-232. It is designed to work with local serial ports and ESPHome serial
proxies through Home Assistant's serial port selector.

## Repository Layout

- `custom_components/optoma_projector/` contains the HACS-installable Home
  Assistant integration.
- `esphome/ProjectorController.yaml` contains the ESPHome firmware that exposes
  the projector UART as an ESPHome serial proxy.

## Basic Use

1. Flash the ESPHome firmware from `esphome/ProjectorController.yaml`.
2. Install the `optoma_projector` integration in Home Assistant.
3. Add the integration from the Home Assistant UI and select the ESPHome serial
   proxy from the serial port dropdown.

The current integration implements power, input selection, useful projector
settings, status sensors, and a re-sync action for the GT1080HDR.
Power state is polled regularly so Home Assistant notices manual power-button
changes and automatic shutdowns.

## Entities

- Media player: power and input source selection.
- Sensors: projector status, lamp hours, and temperature.
- Switches: AV mute, freeze, 3D mode, and 3D sync invert.
- Selects: display mode, aspect ratio, brightness mode, and 3D format.
- Numbers: brightness, contrast, and vertical keystone.
- Button: re-sync.
