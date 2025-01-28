import os
from datetime import datetime
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from typing import Tuple, Dict, Any

app = Flask(__name__)
CORS(app)

# Constantes globales
RADIO_TIERRA = 6371.0     # Radio de la Tierra en kilómetros
MÓDULO_CORTE = 4.5e10     # Módulo de corte para cálculos de momento sísmico
CONSTANTE_MOMENTO = 1e21  # Constante para normalización del momento sísmico


def calcular_distancia_geodésica(
    lon0: float, lat0: float, lon1: float, lat1: float
) -> float:
    """
    Calcula la distancia geodésica entre dos puntos utilizando la fórmula de Haversine.

    Args:
        lon0 (float): Longitud del primer punto
        lat0 (float): Latitud del primer punto
        lon1 (float): Longitud del segundo punto
        lat1 (float): Latitud del segundo punto

    Retorna:
        float: Distancia en kilómetros
    """
    lon0, lat0, lon1, lat1 = map(np.radians, [lon0, lat0, lon1, lat1])
    dlon = lon1 - lon0
    dlat = lat1 - lat0

    a = np.sin(dlat / 2) ** 2 + np.cos(lat0) * np.cos(lat1) * np.sin(dlon / 2) ** 2
    return RADIO_TIERRA * 2 * np.arcsin(np.sqrt(a))


def obtener_mecanismo_focal(
    lon0: float, lat0: float, ruta_mecfoc: str = os.path.abspath("./model/mecfoc.dat")
) -> Tuple[float, float]:
    """
    Obtiene el mecanismo focal más cercano basado en la ubicación geográfica.

    Args:
        lon0 (float): Longitud del punto de origen
        lat0 (float): Latitud del punto de origen
        ruta_mecfoc (str, opcional): Ruta al archivo de mecanismo focal

    Retorna:
        Tuple[float, float]: Ángulo de rumbo (azimut) e inclinación
    """
    try:
        mecfoc = np.loadtxt(ruta_mecfoc, delimiter=",")

        # Cálculo de distancias optimizado
        distancias = np.sqrt((mecfoc[:, 0] - lon0) ** 2 + (mecfoc[:, 1] - lat0) ** 2)
        índice_más_cercano = np.argmin(distancias)

        return mecfoc[índice_más_cercano, 2], mecfoc[índice_más_cercano, 3]

    except FileNotFoundError:
        raise FileNotFoundError(
            f"El archivo de mecanismo focal no se encuentra en {ruta_mecfoc}"
        )
    except Exception as e:
        raise RuntimeError(f"Error procesando mecfoc.dat: {e}")


def validar_parámetros(datos: Dict[str, Any]) -> bool:
    """
    Valida la presencia y tipo de los parámetros de entrada.

    Args:
        datos (Dict[str, Any]): Diccionario de parámetros de entrada

    Retorna:
        bool: Indica si los parámetros son válidos
    """
    parámetros_requeridos = ["Mw", "h", "lat0", "lon0"]
    return all(
        isinstance(datos.get(param), (int, float)) for param in parámetros_requeridos
    )


@app.route("/api/tsunami/source_params", methods=["POST"])
def calcular_parámetros_fuente() -> Tuple[jsonify, int]:
    """
    Calcula los parámetros de la fuente del tsunami basado en las características sísmicas.

    Retorna:
        Tuple[jsonify, int]: Resultados de los parámetros de la fuente y código de estado HTTP
    """
    try:
        datos = request.get_json()

        if not validar_parámetros(datos):
            return jsonify({"error": "Parámetros inválidos o incompletos"}), 400

        Mw = float(datos["Mw"])
        h = float(datos["h"])
        lat0 = float(datos["lat0"])
        lon0 = float(datos["lon0"])

        # Cálculos optimizados usando operaciones vectoriales
        L = 10 ** (0.55 * Mw - 2.19)
        W = 10 ** (0.31 * Mw - 0.63)
        M0 = 10 ** (1.5 * Mw + 9.1)
        D = M0 / (MÓDULO_CORTE * L * 1000 * W * 1000)

        resultados = {
            "Largo": L,
            "Ancho": W,
            "Dislocación": D,
            "Momento_sísmico": M0 / CONSTANTE_MOMENTO,
            "lat0": lat0,
            "lon0": lon0,
        }

        return jsonify(resultados), 200

    except Exception as e:
        return jsonify({"error": f"Error inesperado: {str(e)}"}), 500

@app.route("/api/calculate-tsunami", methods=["POST"])
def mock_calculate_tsunami():
    """Mock endpoint for tsunami calculation"""
    return jsonify({
        "id": "mock-calculation-001",
        "timestamp": datetime.now().isoformat(),
        "input_parameters": {
            "magnitude": 7.8,
            "depth": 30,
            "latitude": -33.4569,
            "longitude": -70.6483
        },
        "results": {
            "max_wave_height": 5.2,
            "arrival_time": "2024-01-20T15:30:00Z",
            "inundation_distance": 2.1,
            "alert_level": "high",
            "wave_propagation": {
                "times": [0, 10, 20, 30, 40, 50],
                "heights": [0, 1.2, 2.5, 4.1, 5.2, 4.8]
            }
        },
        "metadata": {
            "calculation_duration": 0.5,
            "model_version": "mock-1.0.0"
        }
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
