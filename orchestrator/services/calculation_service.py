from models import SourceParameters


class CalculationService:
    def __init__(self, config, map_service):
        self.config = config
        self.map_service = map_service

    def calculate_source_parameters(self, Mw: float) -> SourceParameters:
        """Calculate earthquake source parameters."""
        L = 10 ** (0.55 * Mw - 2.19)
        W = 10 ** (0.31 * Mw - 0.63)
        M0 = 10 ** (1.5 * Mw + 9.1)
        D = M0 / (self.config.SHEAR_MODULUS * L * 1000 * W * 1000)

        return SourceParameters(L, W, M0, D)

    def determine_tsunami_potential(
        self, Mw: float, h: float, h0: float, dist_min: float
    ) -> str:
        """Determine tsunami potential based on parameters."""
        if h0 > 0 and dist_min < 50:
            return "El epicentro esta en Tierra, pero podría generar Tsunami"
        elif h0 > 0 and dist_min >= 50:
            return "El epicentro esta en Tierra. NO genera Tsunami"
        elif h0 <= 0:
            if 7.0 <= Mw < 7.9 and h <= 60:
                return "Epicentro en el Mar. Probable Tsunami pequeño y local"
            elif 7.9 <= Mw < 8.4 and h <= 60:
                return "Epicentro en el Mar. Genera un Tsunami pequeño"
            elif 8.4 <= Mw < 8.8 and h <= 60:
                return (
                    "Epicentro en el Mar. Genera un Tsunami potencialmente destructivo"
                )
            elif Mw >= 8.8 and h <= 60:
                return "Epicentro en el Mar. Genera un Tsunami grande y destructivo"
            elif h > 60 or Mw < 7.0:
                return "El epicentro esta en el Mar y NO genera Tsunami"

        return "Tsunami potential undetermined"
