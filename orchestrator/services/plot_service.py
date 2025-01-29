import logging
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from config import Config
from services.map_service import MapService

logger = logging.getLogger(__name__)


class PlotService:
    def __init__(self, config: Config, map_service: MapService):
        self.config = config
        self.map_service = map_service
        try:
            self.map_data = map_service.load_map_data()
            logger.info("Map data loaded successfully in PlotService.")
        except Exception as e:
            logger.error(f"Error loading map data in PlotService: {e}")
            raise  # Re-raise to halt execution if map data loading fails

    def create_analysis_plot(
        self,
        Mw: float,
        h: float,
        lat0: float,
        lon0: float,
        L: float,
        W: float,
        D: float,
        M0: float,
        sx: np.ndarray,
        sy: np.ndarray,
        titulo: str,
    ) -> str:
        """Create analysis plot and return filename."""
        try:
            plt.figure(figsize=(12, 8))

            # Plot bathymetry
            plt.pcolormesh(
                self.map_data["xa"] - 360,
                self.map_data["ya"],
                self.map_data["A"],
                shading="flat",
                cmap="terrain",
            )
            plt.contour(
                self.map_data["xa"] - 360,
                self.map_data["ya"],
                self.map_data["A"],
                [0, 0],
                colors="black",
            )

            # Plot epicenter and fault plane
            if Mw < 7.0:
                plt.plot(lon0, lat0, "ro", markersize=8, label="Epicenter")
            else:
                plt.plot(lon0, lat0, "ro", markersize=8, label="Epicenter")
                plt.plot(sx, sy, "k-", linewidth=2, label="Fault Plane")

            # Add location labels with error handling
            for lon, lat, name in self.config.LOCATIONS:
                try:
                    plt.text(lon, lat, name, fontsize=8)
                except Exception as e:
                    logger.warning(f"Error adding location label {name}: {e}")

            if lat0 < -20:  # Specific location handling
                plt.text(-70.4044, -23.6531, "Antofagasta")

            # Add parameter text
            param_text = (
                f"Largo    L  = {int(L)} km\n"
                f"Ancho    W  = {int(W)} km\n"
                f"Dislocacion = {D:.2f} m\n"
                f"Mom. sismico= {M0 / self.config.MOMENT_CONSTANT:.3f}e21 N.m"
            )
            plt.text(
                lon0 + 15,
                lat0 - 2.0,
                param_text,
                bbox=dict(facecolor="white", alpha=0.7),
            )

            # Customize plot
            plt.grid(True)
            plt.axis("equal")
            plt.xlabel("Longitud")
            plt.ylabel("Latitud")
            plt.xlim([lon0 - 10, lon0 + 35])
            plt.ylim([lat0 - 10, lat0 + 10])
            plt.title(titulo)

            # Save plot with error handling
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tsunami_plot_{timestamp}.png"
            try:
                plt.savefig(
                    self.config.STATIC_DIR / filename, dpi=300, bbox_inches="tight"
                )
                logger.info(f"Plot saved to {self.config.STATIC_DIR / filename}")
            except Exception as e:  # Handle potential save errors
                logger.error(f"Error saving plot: {e}")
                return None

            plt.close()  # Close the plot to free resources
            return filename

        except Exception as e:  # Handle any other exceptions during plotting
            logger.error(f"An error occurred during plotting: {e}")
            return None  # Or raise the exception
