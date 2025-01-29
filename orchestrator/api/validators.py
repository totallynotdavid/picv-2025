import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ParameterValidator:
    def __init__(self, config):
        self.config = config

    def _validate_parameter(self, data: Dict[str, Any], param: str) -> None:
        """Validate a single parameter."""
        if param not in data:
            raise ValueError(f"Missing parameter: {param}")

        try:
            value = float(data[param])
        except (TypeError, ValueError) as err:
            raise ValueError(f"{param} must be a valid number") from err

        min_val, max_val = self.config.PARAM_RANGES.get(param, (None, None))
        if min_val is not None and value < min_val:
            raise ValueError(f"{param} must be greater than or equal to {min_val}")
        if max_val is not None and value > max_val:
            raise ValueError(f"{param} must be less than or equal to {max_val}")

    def validate_source_parameters(self, data: Dict[str, Any]) -> None:
        """Validate parameters for source calculations."""
        try:
            self._validate_parameter(data, "Mw")
        except ValueError as e:
            logger.error(f"Source parameter validation error: {e}")
            raise

    def validate_potential_parameters(self, data: Dict[str, Any]) -> None:
        """Validate parameters for tsunami potential calculations."""
        try:
            for param in ["Mw", "h", "lat0", "lon0"]:  # List parameters to validate
                self._validate_parameter(data, param)
        except ValueError as e:
            logger.error(f"Tsunami potential parameter validation error: {e}")
            raise
