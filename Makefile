# ENose — run every component from the repo root, no `cd` needed.
#
# Each subproject keeps its own libraries:
#   - api/          Python deps in api/pyproject.toml (managed by uv)
#   - esp32s3/      Arduino libs in esp32s3/platformio.ini (managed by PlatformIO)
#
# This Makefile just dispatches to each tool with the right project directory
# (`uv --directory api …`, `pio … -d esp32s3`) so you never have to cd.

API_DIR := api
ESP_DIR := esp32s3
UV      := uv --directory $(API_DIR)
PIO     := pio
COMPOSE := podman compose

# Overridable connection settings for the check targets below.
MQTT_HOST ?= localhost
MQTT_PORT ?= 1883
API_URL   ?= http://localhost:8000
READINGS_TOPIC ?= enose/readings
COMMANDS_TOPIC ?= enose/commands

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- API (Python / uv) ---------------------------------------------------------

.PHONY: api-install
api-install: ## Install API dependencies
	$(UV) sync

.PHONY: api-dev
api-dev: ## Run the API with autoreload (dev)
	$(UV) run uvicorn main:app --reload

.PHONY: api-run
api-run: ## Run the API (production-style)
	$(UV) run fastapi run main.py --port 8000

.PHONY: api-test
api-test: ## Run the analyzer tests (no DB or board needed)
	$(UV) run python tests/test_analyzer.py

.PHONY: api-calibrate
api-calibrate: ## Calibrate the slope threshold against datasets/
	$(UV) run python tools/calibrate.py

# --- ESP32-S3 firmware (PlatformIO) -------------------------------------------

.PHONY: esp-build
esp-build: ## Compile the ESP32 firmware
	$(PIO) run -d $(ESP_DIR)

.PHONY: esp-upload
esp-upload: ## Flash the ESP32 firmware
	$(PIO) run -d $(ESP_DIR) -t upload

.PHONY: esp-monitor
esp-monitor: ## Open the ESP32 serial monitor
	$(PIO) device monitor -d $(ESP_DIR)

.PHONY: esp-clean
esp-clean: ## Clean the ESP32 build artifacts
	$(PIO) run -d $(ESP_DIR) -t clean

# --- Full stack (podman compose) ----------------------------------------------

.PHONY: up
up: ## Start API + Mosquitto + Postgres
	$(COMPOSE) up -d
 
.PHONY: up-build
up-build: ## Start API + Mosquitto + Postgres (build if needed)
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: down-v
down-v: ## Stop the stack and wipe volumes (drops the local DB)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Follow the stack logs
	$(COMPOSE) logs -f

# --- MQTT / broker checks (need mosquitto-clients; broker must be running) ------

.PHONY: mqtt-ping
mqtt-ping: ## Check the broker is reachable (publishes to a test topic)
	mosquitto_pub -h $(MQTT_HOST) -p $(MQTT_PORT) -t enose/ping -m ok \
		&& echo "broker $(MQTT_HOST):$(MQTT_PORT) OK"

.PHONY: mqtt-commands
mqtt-commands: ## Watch commands the API sends to the board (Ctrl-C to stop)
	mosquitto_sub -h $(MQTT_HOST) -p $(MQTT_PORT) -t $(COMMANDS_TOPIC) -v

.PHONY: mqtt-readings
mqtt-readings: ## Watch readings the board sends to the API (Ctrl-C to stop)
	mosquitto_sub -h $(MQTT_HOST) -p $(MQTT_PORT) -t $(READINGS_TOPIC) -v

.PHONY: mqtt-fake-reading
mqtt-fake-reading: ## Publish one fake sensor reading (simulates the ESP32)
	mosquitto_pub -h $(MQTT_HOST) -p $(MQTT_PORT) -t $(READINGS_TOPIC) \
		-m '{"type":"reading","arduino_ms":1000,"values":{"tgs2620":100,"tgs2611":200,"tgs2602":300,"tgs2600":400}}' \
		&& echo "published fake reading to $(READINGS_TOPIC)"

# --- API run control (needs curl; API must be running) -------------------------

.PHONY: run-start
run-start: ## Start a measurement run (NAME=test N=1 MIN=5)
	curl -fsS -X POST "$(API_URL)/serial/start?name=$(or $(NAME),test)&n_repetitions=$(or $(N),1)&min_medicion_seconds=$(or $(MIN),5)" ; echo

.PHONY: run-stop
run-stop: ## Stop the current run
	curl -fsS -X POST "$(API_URL)/serial/stop" ; echo

.PHONY: run-status
run-status: ## Show the board/MQTT connection status
	curl -fsS "$(API_URL)/serial/status" ; echo
