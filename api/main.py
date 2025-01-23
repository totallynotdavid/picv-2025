import os
import numpy as np
from flask import Flask, request, jsonify
from typing import Tuple, Dict, Any

app = Flask(__name__)

# Constantes globales
RADIO_TIERRA = 6371.0  # Radio de la Tierra en kilómetros
MÓDULO_CORTE = 4.5e10  # Módulo de corte para cálculos de momento sísmico
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

# TODO: Error convirtiendo el string
@app.route("/api/tsunami/rupture_rectangle", methods=["POST"])
def calcular_rectángulo_ruptura() -> Tuple[jsonify, int]:
    """
    Calcula las coordenadas del rectángulo de ruptura para un evento sísmico.

    Retorna:
        Tuple[jsonify, int]: Coordenadas del rectángulo de ruptura y código de estado HTTP
    """
    try:
        datos = request.get_json()

        L = float(datos.get("Largo"))
        W = float(datos.get("Ancho"))
        lon0 = float(datos.get("lon0"))
        lat0 = float(datos.get("lat0"))

        azimut, echado = obtener_mecanismo_focal(lon0, lat0)

        # Cálculos optimizados usando NumPy
        L1 = L * 1000
        W1 = 1000 * W * np.cos(np.deg2rad(echado))

        beta = np.rad2deg(np.arctan(W1 / L1))
        alfa = azimut - 270
        h1 = np.sqrt(L1**2 + W1**2)

        a1 = 0.5 * h1 * np.sin(np.deg2rad(alfa + beta)) / 1000
        b1 = 0.5 * h1 * np.cos(np.deg2rad(alfa + beta)) / 1000

        xo = lon0 + b1 / 110
        yo = lat0 - a1 / 110

        # Cálculo de coordenadas del rectángulo usando NumPy
        dip = np.deg2rad(echado)
        a1 = np.deg2rad(-(azimut - 90))
        a2 = np.deg2rad(-azimut)

        r1 = L1 / (60 * 1853)
        r2 = W1 / (60 * 1853)

        sx = (
            np.array(
                [
                    0,
                    r1 * np.cos(a1),
                    r1 * np.cos(a1) + r2 * np.cos(a2),
                    r2 * np.cos(a2),
                    0,
                ]
            )
            + xo
        )
        sy = (
            np.array(
                [
                    0,
                    r1 * np.sin(a1),
                    r1 * np.sin(a1) + r2 * np.sin(a2),
                    r2 * np.sin(a2),
                    0,
                ]
            )
            + yo
        )

        return jsonify({"rect_x": sx.tolist(), "rect_y": sy.tolist()}), 200

    except Exception as e:
        return (
            jsonify({"error": f"Error al calcular rectángulo de ruptura: {str(e)}"}),
            500,
        )


if __name__ == "__main__":
    app.run(debug=True)
