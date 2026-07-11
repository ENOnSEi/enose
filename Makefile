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

# --- Full stack (docker compose) ----------------------------------------------

.PHONY: up
up: ## Start API + Mosquitto + Postgres (build if needed)
	docker compose up --build

.PHONY: down
down: ## Stop the stack
	docker compose down

.PHONY: down-v
down-v: ## Stop the stack and wipe volumes (drops the local DB)
	docker compose down -v

.PHONY: logs
logs: ## Follow the stack logs
	docker compose logs -f
