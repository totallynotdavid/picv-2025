import os
from datetime import datetime
import numpy as np
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from typing import Tuple, Dict, Any

app = Flask(__name__)
CORS(app)

# Constantes
RADIO_TIERRA = 6371.0  # Radio de la Tierra en kilómetros
MÓDULO_CORTE = 4.5e10  # Módulo de corte para cálculos de momento sísmico
CONSTANTE_MOMENTO = 1e21  # Constante para normalización del momento sísmico
MODEL_PATH = Path("model")
INPUT_FILE = MODEL_PATH / "pfalla.inp"


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


def validate_model_parameters(data):
    """
    Validates input parameters and their ranges for the model
    """
    required_params = {
        "Mw": (5.0, 9.5),  # Min and max magnitude
        "h": (0, 700),  # Depth range in km
        "lat0": (-90, 90),  # Latitude range
        "lon0": (-180, 180),  # Longitude range
    }

    for param, (min_val, max_val) in required_params.items():
        if param not in data:
            raise ValueError(f"Missing parameter: {param}")

        value = float(data[param])
        if not min_val <= value <= max_val:
            raise ValueError(f"{param} must be between {min_val} and {max_val}")


def create_input_file(data):
    """
    Creates the input file for the model
    """
    input_content = (
        f"{data['lat0']:.4f} {data['lon0']:.4f}\n{data['h']:.1f}\n{data['Mw']:.1f}\n"
    )

    with open(INPUT_FILE, "w") as f:
        f.write(input_content)


def run_tsunami_model():
    """
    Runs the tsunami model and returns the PDF path
    """
    try:
        # Ensure job.run is executable
        job_script = MODEL_PATH / "job.run"
        job_script.chmod(0o755)

        # Run the model
        subprocess.run(
            ["./job.run"], cwd=MODEL_PATH, capture_output=True, text=True, check=True
        )

        # Check if PDF was generated
        pdf_path = MODEL_PATH / "reporte.pdf"
        if not pdf_path.exists():
            raise FileNotFoundError("PDF report was not generated")

        return pdf_path

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Model execution failed: {e.stdout}\n{e.stderr}")


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
        # h = float(datos["h"])
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
def calculate_tsunami():
    """
    Endpoint to run tsunami model and return PDF report
    """
    try:
        data = request.get_json()

        validate_model_parameters(data)

        create_input_file(data)

        pdf_path = run_tsunami_model()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"tsunami_report_{timestamp}.pdf"

        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=output_filename,
        )

    except ValueError as e:
        return jsonify(
            {
                "error": "Validation error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        ), 400

    except Exception as e:
        return jsonify(
            {
                "error": "Processing error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        ), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
