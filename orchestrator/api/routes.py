from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)

class TsunamiAPI:
    def __init__(self, config, calculation_service, plot_service, validator):
        self.config = config
        self.calculation_service = calculation_service
        self.plot_service = plot_service
        self.validator = validator
        self.map_service = calculation_service.map_service  # Assign map_service

    def register_routes(self, app):
        """Register API routes."""

        @app.route("/api/tsunami/source_params", methods=["POST"])
        def calculate_source_parameters():
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No data provided"}), 400

                self.validator.validate_source_parameters(data)

                params = self._extract_parameters(data)
                result = self.calculation_service.calculate_source_parameters(**params)

                return jsonify(result), 200

            except Exception as e:
                return self._handle_error(e)

        @app.route("/api/tsunami/potential", methods=["POST"])
        def calculate_tsunami_potential():
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No data provided"}), 400

                self.validator.validate_potential_parameters(data)

                params = self._extract_parameters(data, for_source=False)

                h0 = self.map_service.get_depth(
                    params["lat0"], params["lon0"]
                )  # Use map_service directly
                dist_min = self.map_service.get_min_distance_to_coast(
                    params["lat0"], params["lon0"]
                )

                result = self.calculation_service.determine_tsunami_potential(
                    params["Mw"], params["h"], h0, dist_min
                )

                return jsonify({"potential": result}), 200

            except Exception as e:
                return self._handle_error(e)

    def _extract_parameters(self, data, for_source=True):
        """Extract parameters from request data."""
        if for_source:
            return {"Mw": float(data["Mw"])}
        else:
            return {
                "Mw": float(data.get("Mw")),
                "h": float(data.get("h")),
                "lat0": float(data.get("lat0")),
                "lon0": float(data.get("lon0")),
            }

    def _handle_error(self, error):
        """Handle different types of errors."""
        if isinstance(error, ValueError):
            return jsonify({"error": "Validation error", "message": str(error)}), 400
        elif isinstance(error, TimeoutError):
            return jsonify(
                {"error": "Request timeout", "message": "Calculation took too long"}
            ), 408
        else:
            logger.error(f"Error processing request: {error}", exc_info=True)
            return jsonify({"error": "Processing error", "message": str(error)}), 500
