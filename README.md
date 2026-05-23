# Electronic Nose Project

ML pipeline for wine quality classification using an electronic nose (6 MQ chemoresistive sensors).
Implements signal processing and SVM classification following Macias et al., *Sensors* 2013.

## Project Structure

```
Electronic Nose Project/
├── main.py                          # Pipeline entry point
├── requirements.txt
├── pyrightconfig.json               # VS Code / Pylance config
├── PIPELINE_INSTRUCTIONS.md        # How to run the pipeline
│
├── src/
│   ├── config.py                   # Centralized configuration (all parameters here)
│   ├── utils.py                    # Shared utilities and logging
│   ├── phase_1_3_feature_extraction.py  # Signal processing + feature extraction
│   ├── phase_4_dataset_generation.py    # Master dataset builder
│   └── phase_5_model_training.py        # SVM training with GridSearchCV
│
├── data/
│   ├── raw/                        # Sensor measurement files (.txt) + master CSV
│   │   ├── AQ_Wines/               # Low-quality wine samples
│   │   ├── HQ_Wines/               # High-quality wine samples
│   │   ├── LQ_Wines/               # Medium-quality wine samples
│   │   └── Ethanol/                # Control samples
│   └── processed/                  # Generated: model .pkl files, visualizations
│
├── docs/
│   ├── DOCUMENTACION_TECNICA.md    # Full technical documentation (math + design)
│   ├── CHANGELOG.md                # Version history (V1, V2, V3)
│   └── modules_reference.md        # Module API reference
│
├── tests/
└── notebooks/
```

## Quick Start

```bash
pip install -r requirements.txt

# Full pipeline (feature extraction + training)
python main.py

# Feature extraction only (Phase 4)
python main.py --phase 4

# Model training only (Phase 5, requires dataset)
python main.py --phase 5
```

See [PIPELINE_INSTRUCTIONS.md](PIPELINE_INSTRUCTIONS.md) for full usage.

## Pipeline Overview

| Phase | Module | Description |
|-------|--------|-------------|
| 1-3 | `phase_1_3_feature_extraction.py` | Savitzky-Golay smoothing, baseline normalization, windowed feature extraction |
| 4 | `phase_4_dataset_generation.py` | Builds master CSV from all sensor files |
| 5 | `phase_5_model_training.py` | StandardScaler + SVM + GridSearchCV |

## Feature Extraction Modes

Controlled by `FEATURE_MODE` in `src/config.py`:

| Mode | Description | Features per sample |
|------|-------------|---------------------|
| `pca_signal` (default) | PCA on raw signal curves, one model per (sensor x window) | Variable (explained variance >= 0.95) |
| `handcrafted` | Max, AUC, slope per window per sensor | 54 (6 sensors x 3 windows x 3 stats) |

## Outputs

| File | Description |
|------|-------------|
| `data/raw/dataset_maestro_vinos.csv` | Master dataset |
| `data/processed/best_model.pkl` | Trained SVM pipeline |
| `data/processed/pca_transformers.pkl` | PCA models (required for inference in `pca_signal` mode) |
| `data/processed/training_results.pkl` | Metrics and evaluation results |
| `data/processed/visualizations/` | Confusion matrix, accuracy plots, etc. |

## Configuration

All parameters are in `src/config.py`. Key settings:

```python
FEATURE_MODE = 'pca_signal'   # or 'handcrafted'
PCA_CONFIG = {'explained_variance_threshold': 0.95, 'whiten': False}
SIGNAL_PROCESSING_V2 = {'sampling_frequency': 18.5, 'savgol_window': 15, ...}
ML_CONFIG = {'n_splits_cv': 3, 'scoring_metric': 'accuracy'}
```

## Reference

Macias, M. M. et al. "Electronic Nose for Wine Discrimination." *Sensors* 13.5 (2013): 5528-5543.
