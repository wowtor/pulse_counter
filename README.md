# S0 Pulse Counter

This script read readings from a S0 pulse counter [https://www.sossolutions.nl/5-kanaals-s0-pulse-meter-op-usb] and exposes them via a rest API.

## Pre-requisites

```sh
sudo apt install python3 python3-serial
```

## Usage

Run the script.

```sh
./run_counter.py
```

Use a browser and point it to [http://localhost:8000] to access the readings.
Individual counters can be accessed at [http://localhost:8000/0],
[http://localhost:8000/1], etc.
