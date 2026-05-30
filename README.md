# Electronic Nose Project

ML pipeline for wine quality classification using an electronic nose (6 MQ chemoresistive sensors).
Implements signal processing and SVM classification following Macias et al., *Sensors* 2013.

## Architecture

The project follows a **Specification → Design → Development** structure:

| Layer | Folder | Purpose |
|---|---|---|
| Spec | `spec/contracts/` | Python `Protocol` classes — formal interfaces for each pipeline stage |
| Spec | `spec/schemas/` | Pydantic models — data validation at system boundaries |
| Design | `design/adr/` | Architecture Decision Records — why the system is built this way |
| Dev | `src/enose/` | Implementations — organized by domain, swappable via Protocols |

## Project Structure

```
Electronic Nose Project/
├── main.py                        # Pipeline entry point (CLI)
├── requirements.txt
├── pyrightconfig.json
│
├── spec/
│   ├── contracts/                 # Python Protocols (interfaces)
│   │   ├── processor.py           # SignalProcessorProtocol
│   │   ├── extractor.py           # HandcraftedExtractorProtocol, SignalExtractorProtocol
│   │   └── classifier.py          # ClassifierProtocol
│   └── schemas/                   # Pydantic models (boundary validation)
│       ├── sensor_reading.py      # SensorReading — raw input
│       ├── feature_vector.py      # FeatureVector — post-extraction
│       └── prediction.py          # Prediction — model output
│
├── design/
│   └── adr/                       # Architecture Decision Records
│       ├── 001-spec-design-dev-architecture.md
│       ├── 002-pca-vs-handcrafted-features.md
│       └── 003-svm-classifier.md
│
├── src/enose/                     # Main package
│   ├── io/reader.py               # Sensor file reading, label extraction
│   ├── signal/processor.py        # Savitzky-Golay smoothing + normalization
│   ├── features/
│   │   ├── pca.py                 # PCAFeatureExtractor
│   │   └── handcrafted.py         # HandcraftedExtractor (max, AUC, slope)
│   ├── model/trainer.py           # SVM training with GridSearchCV
│   ├── pipeline/dataset.py        # DatasetGenerator + load/validate helpers
│   ├── config.py                  # Typed config (frozen dataclasses)
│   └── utils.py                   # Logging, plots, validation
│
├── data/
│   ├── raw/                       # Sensor .txt files + master CSV
│   │   ├── AQ_Wines/
│   │   ├── HQ_Wines/
│   │   ├── LQ_Wines/
│   │   └── Ethanol/
│   └── processed/                 # Generated: model .pkl files, visualizations
│
├── tests/
│   ├── contracts/                 # Contract tests (verify Protocol compliance)
│   │   ├── test_processor_contract.py
│   │   ├── test_extractor_contract.py
│   │   └── test_schemas.py
│   └── unit/
│       ├── test_imports.py        # Import smoke test
│       └── test_phase5.py         # End-to-end training test
│
├── docs/
│   ├── CHANGELOG.md
│   └── modules_reference.md
└── notebooks/
```

## Quick Start

```bash
pip install -r requirements.txt

# Full pipeline (feature extraction + training)
python main.py

# Feature extraction only (Phase 4)
python main.py --phase 4

# Model training only (Phase 5 — requires dataset)
python main.py --phase 5
```

## Pipeline Overview

```
Phase 4: Feature Extraction
  io/reader.py       → load .txt sensor files
  signal/processor.py → Savitzky-Golay + baseline normalization
  features/pca.py    → PCA projection per (sensor × window)   [pca_signal mode]
  features/handcrafted.py → max, AUC, slope per window        [handcrafted mode]
  pipeline/dataset.py → aggregate → dataset_maestro_vinos.csv

Phase 5: Model Training
  pipeline/dataset.py → load + validate CSV
  model/trainer.py   → StandardScaler → SVM → GridSearchCV → best_model.pkl
```

## Feature Extraction Modes

Controlled by `FEATURE_MODE` in `src/enose/config.py`:

| Mode | Description | Features/sample | Artifacts needed for inference |
|---|---|---|---|
| `pca_signal` (default) | PCA on signal curves per (sensor × window) | ~15–20 (95% var) | `best_model.pkl` + `pca_transformers.pkl` |
| `handcrafted` | Max, AUC, slope per window | 54 fixed | `best_model.pkl` only |

## Outputs

| File | Description |
|---|---|
| `data/raw/dataset_maestro_vinos.csv` | Master dataset |
| `data/processed/best_model.pkl` | Trained SVM pipeline (StandardScaler + SVM) |
| `data/processed/pca_transformers.pkl` | PCA models — required for inference in `pca_signal` mode |
| `data/processed/training_results.pkl` | Metrics and evaluation results |
| `data/processed/visualizations/` | Confusion matrix, accuracy plots, classification report |

## Configuration

All parameters are in `src/enose/config.py` as typed, frozen dataclasses:

```python
# Feature extraction mode
FEATURE_MODE = 'pca_signal'   # or 'handcrafted'

# Signal processing
SIGNAL_CONFIG = SignalConfig(
    sampling_frequency=18.5,
    savgol_window=15,
    baseline_seconds=2.0,
    time_windows=((0, 2), (2, 10), (10, 20)),
)

# PCA
PCA_CONFIG = PCAConfig(explained_variance_threshold=0.95)

# SVM
ML_CONFIG = MLConfig(n_splits_cv=3, scoring_metric='accuracy')
```

## Extending the Pipeline

The Spec layer defines the contracts. To add a new feature extractor:

1. Implement `SignalExtractorProtocol` (see `spec/contracts/extractor.py`)
2. Add your class to `src/enose/features/`
3. Wire it in `src/enose/pipeline/dataset.py`
4. Add contract tests in `tests/contracts/`

No other files need to change.

## Running Tests

```bash
# Contract tests (Protocol compliance + schema validation)
python -m pytest tests/contracts/ -v

# Import smoke test
python tests/unit/test_imports.py

# Full training test (requires dataset)
python tests/unit/test_phase5.py
```

## Reference

Macias, M. M. et al. "Electronic Nose for Wine Discrimination." *Sensors* 13.5 (2013): 5528–5543.
