import logging

import numpy as np
import scipy.io as sio  # For reading .mat files
from config import Config

logger = logging.getLogger(__name__)


class MapService:
    def __init__(self, config: Config):
        self.config = config
        self.map_data = {}

    def load_map_data(self):
        """Load and cache map data."""
        try:
            MAP_DATA_FILES = {
                "maper1.mat": ["xa", "ya", "A"],
                "maper2.mat": "B",
                "maper3.mat": "C",
                "pacifico.mat": None,  # Example; adjust as needed.
            }

            for file, var_names in MAP_DATA_FILES.items():
                self._process_map_file(file, var_names)

            return self.map_data

        except Exception as e:
            logger.error(f"Error loading map data: {e}")
            raise

    def _process_map_file(self, file: str, var_names):
        """Process individual map file."""
        npy_file = self.config.MODEL_PATH / file.replace(".mat", ".npy")

        if not npy_file.exists():
            self._convert_mat_to_npy(file, var_names, npy_file)
        else:
            self._load_npy_file(npy_file, var_names)

    def _convert_mat_to_npy(self, file, var_names, npy_file):
        """Convert .mat file to .npy."""
        try:
            mat_data = sio.loadmat(self.config.MODEL_PATH / file)
            if isinstance(var_names, list):
                for var_name in var_names:
                    self.map_data[var_name] = mat_data[var_name]
                    np.save(
                        npy_file, mat_data[var_name]
                    )  # This will overwrite! Adjust as needed.
            elif isinstance(var_names, str):  # Single variable
                self.map_data[var_names] = mat_data[var_names]
                np.save(npy_file, mat_data[var_names])
            elif var_names is None:  # Load entire .mat
                self.map_data.update(mat_data)  # Be mindful of variable names
                np.save(npy_file, mat_data)  # Again, overwriting. Adjust logic.

        except Exception as e:
            logger.error(f"Error converting .mat to .npy: {e}")
            raise

    def _load_npy_file(self, npy_file, var_names):
        """Load data from .npy file."""
        try:
            data = np.load(
                npy_file, allow_pickle=True
            )  # allow_pickle for complex .mat structure
            if isinstance(
                var_names, list
            ):  # Multiple variables assumed saved as a dict
                for var_name in var_names:
                    self.map_data[var_name] = data.item().get(
                        var_name
                    )  # For dictionaries, use .item().get()
            elif isinstance(var_names, str):
                self.map_data[var_names] = data  # Load single variable
            elif var_names is None:
                self.map_data = data.item() if isinstance(data.item(), dict) else data

        except Exception as e:
            logger.error(f"Error loading .npy file: {e}")
            raise
