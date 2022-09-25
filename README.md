# S0 Pulse Counter

This script read readings from a [S0 pulse counter](https://www.sossolutions.nl/5-kanaals-s0-pulse-meter-op-usb)
and exposes them via a rest API.

## Pre-requisites

```sh
sudo apt install python3 python3-serial
```

## Usage

Identify the pulse counter device. It is typically named `/dev/ttyACM0` but
may be named differently.

Launch the service, with `DEVICE` replaced by the name of the pulse counter.

```sh
./run_counter.py --device DEVICE
```

Use a browser and point it to <http://localhost:8000> to access the readings.
Individual counters can be accessed at <http://localhost:8000/0>,
<http://localhost:8000/1>, etc.

If you want [Home
Assistant](https://www.home-assistant.io/integrations/sensor.rest) to use
the readings, add the following to your `configuration.yaml`, and replace
`IP` by the IP address where the service is running, and `COUNTER` by a
digit 0--4 representing the counter id.

```yaml
sensor:
  - platform: rest
    name: S0 pulse counter
    resource: http://IP:8000/COUNTER
    device_class: energy
    unit_of_measurement: Wh
    state_class: total
```
