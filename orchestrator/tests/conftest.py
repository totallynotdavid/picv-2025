import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

from orchestrator.main import app


# Create test client
@pytest.fixture
def client():
    return TestClient(app)


# Mock data fixture
@pytest.fixture
def mock_earthquake_data():
    return {
        "Mw": 7.5,
        "h": 30.0,
        "lat0": -20.5,
        "lon0": -70.5,
        "dia": "15",
        "hhmm": "1430",
    }


# Setup mock model directory and files
@pytest.fixture(autouse=True)
def setup_mock_model_files(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    # Create mock pacifico.mat
    mock_bathymetry = np.random.rand(100, 100)
    mock_xa = np.linspace(-80, -60, 100)
    mock_ya = np.linspace(-30, -10, 100)

    np.save(model_dir / "mock_bathymetry.npy", mock_bathymetry)
    np.save(model_dir / "mock_xa.npy", mock_xa)
    np.save(model_dir / "mock_ya.npy", mock_ya)

    # Create mock mecfoc.dat
    mock_mecfoc = np.random.rand(10, 3)
    np.savetxt(model_dir / "mecfoc.dat", mock_mecfoc)

    # Create mock puertos.txt
    with open(model_dir / "puertos.txt", "w") as f:
        f.write("ARICA           -70.32 -18.47\n")
        f.write("IQUIQUE         -70.15 -20.20\n")

    # Create mock job.run
    with open(model_dir / "job.run", "w") as f:
        f.write("#!/bin/bash\necho 'Mock TSDHN execution'")

    os.environ["MODEL_DIR"] = str(model_dir)
    return model_dir
