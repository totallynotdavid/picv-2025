import logging
from waitress import serve
from flask import Flask
from flask_cors import CORS
from config import Config
from services.map_service import MapService
from services.calculation_service import CalculationService
from services.plot_service import PlotService
from api.validators import ParameterValidator
from api.routes import TsunamiAPI


def create_app(config):
    """Application factory."""
    app = Flask(__name__)
    CORS(app)

    # Initialize services
    map_service = MapService(config)
    calculation_service = CalculationService(config, map_service)
    plot_service = PlotService(config, map_service)
    validator = ParameterValidator(config)

    # Initialize API
    api = TsunamiAPI(config, calculation_service, plot_service, validator)
    api.register_routes(app)

    return app


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("tsunami_api.log"), logging.StreamHandler()],
    )

    config = Config()
    app = create_app(config)

    # Run app with production server
    serve(app, host="0.0.0.0", port=5000, threads=4)
