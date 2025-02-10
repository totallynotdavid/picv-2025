# Documentación del Orchestrator TSDHN

El modelo TSDHN es una herramienta para la estimación de parámetros de tsunamis de origen lejano mediante simulaciones numéricas. Combina un **modelo escrito en Fortran** (ubicado en la carpeta [`/model`](/model/)) con una **API escrita en Python** ([`/orchestrator`](/orchestrator/)) que procesa datos sísmicos iniciales —como ubicación y magnitud de terremotos— para calcular variables como: dimensiones de ruptura sísmica, momento sísmico y desplazamiento de la corteza. Estos resultados alimentan la simulación principal, cuyo resultado incluye un informe PDF con mapas de propagación, gráficos de mareógrafos y datos técnicos, además de un archivo de texto con tiempos de arribo a estaciones costeras.

> [!IMPORTANT]
> La lógica de cálculo reside en este repositorio, mientras la [interfaz web](https://github.com/totallynotdavid/picv-2025-web) (que gestiona solicitudes y entrega informes) opera en un entorno separado.

A continuación, se muestra un diagrama que ilustra el flujo general de la API:

```mermaid
flowchart TB
    subgraph "TSDHN API v0.1.0"
        subgraph Endpoints["Endpoints de la API"]
            Calculate["/calculate
            Cálculo de parámetros sísmicos"]
            TravelTimes["/tsunami-travel-times
            Tiempos de arribo"]
            RunModel["/run-tsdhn
            Ejecución de simulación"]
        end

        subgraph Core["Procesamiento"]
            Calculator["Class TsunamiCalculator"]
            ModelFiles["Modelo
            (hypo.dat + job.run)"]
        end

        subgraph Output["Resultados"]
            Files["PDF + salida.txt"]
        end
    end

    Calculate --> Calculator
    TravelTimes --> Calculator
    Calculator --> ModelFiles
    RunModel --> ModelFiles
    ModelFiles --> Files
```

## Instalación

> [!WARNING]
> El proyecto está diseñado para ejecutarse en Linux (Ubuntu 20.04). Usuarios de Windows deben utilizar Windows Subsystem for Linux (WSL 2.0+). [Instalación de WSL](https://learn.microsoft.com/es-es/windows/wsl/install)

**Prerrequisitos:**

1. Python 3.10.0
   ```bash
   sudo apt update -y && sudo apt upgrade -y
   python3 --version
   sudo apt install -y python3-pip
   ```
2. Poetry 2.0.1 (utilizamos Poetry para manejar nuestras dependencias)

   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   poetry --version
   ```

3. [MATLAB R2014](https://drive.google.com/file/d/1VhLnwXX78Y7O8huwlRuE-shOW2LKlVpd/view?usp=drive_link) (solo necesario si piensas ejecutar la interfaz gráfica original)

4. gfortran 11.4.0
   ```bash
   sudo apt install -y gfortran
   gfortran --version
   ```

En cuanto al hardware, se recomienda tener al menos 8 GB de RAM, un CPU con 4 núcleos físicos y 5 GB de espacio libre en disco.

**Pasos de instalación:**

1. Clonar el repositorio:

```bash
git clone https://github.com/totallynotdavid/picv-2025
cd picv-2025
```

2. Instalar dependencias con Poetry:

```bash
poetry install
eval $(poetry env activate)
```

3. Verificar la instalación ejecutando:

```bash
poetry run pytest
```

## Estructura del proyecto

El repositorio se organiza en dos componentes principales:

```txt
picv-2025/
├── orchestrator/
│   ├── core/
│   │   ├── calculator.py         # Contiene la clase TsunamiCalculator y la lógica central de los cálculos.
│   │   └── config.py             # Define constantes globales y la configuración del logging.
│   ├── main.py                   # Punto de entrada de la API con FastAPI y definición de los endpoints.
│   ├── models/
│   │   └── schemas.py            # Modelos Pydantic para la validación y transformación de los datos.
│   └── utils/
│       └── geo.py                # Funciones auxiliares para cálculos geográficos (distancias, formatos, etc.).
└── model/
    ├── pacifico.mat              # Datos de batimetría del océano Pacífico.
    ├── maper1.mat                # Datos de puntos costeros.
    ├── mecfoc.dat                # Base de datos de mecanismos focales históricos.
    ├── puertos.txt               # Lista de puertos utilizados en el cálculo de tiempos de arribo.
    ├── job.run                   # Script C Shell para ejecutar la simulación.
    ├── reporte.pdf               # Reporte generado con el mapa de tiempos y mareogramas.
    └── salida.txt                # Archivo de salida con datos del epicentro y tiempos de arribo.
```

## Flujo de procesamiento

El proceso inicia cuando el usuario envía datos sísmicos desde la interfaz web. La API gestiona los siguientes endpoints:

1. [`/calculate`](orchestrator/main.py?plain=1#L25) recibe magnitud (Mw), profundidad (h) y coordenadas del epicentro. Calcula geometría de la ruptura, momento sísmico y evalúa riesgo de tsunami. Genera el archivo hypo.dat que se usará en la simulación.

Ejemplo de solicitud (POST):

```json
POST /calculate
{
    "Mw": 7.5,
    "h": 10.0,
    "lat0": -20.5,
    "lon0": -70.5,
    "dia": "15",
    "hhmm": "1430"
}
```

Respuesta esperada:

```json
{
  "length": 120.5,
  "width": 80.3,
  "dislocation": 2.5,
  "seismic_moment": 3.2e20,
  "tsunami_warning": "Alerta de tsunami para costas cercanas",
  "distance_to_coast": 45.2,
  "azimuth": 18.5,
  "dip": 30.0,
  "epicenter_location": "mar"
}
```

2. [`/tsunami-travel-times`](orchestrator/main.py?plain=1#L43) utiliza los mismos datos de entrada y realiza una serie de integraciones vectorizadas para calcular los tiempos de arribo a puertos predefinidos ([`puertos.txt`](/model/puertos.txt)). La respuesta es un objeto JSON que incluye tanto los tiempos de arribo como las distancias a cada estación.
3. [`/run-tsdhn`](orchestrator/main.py?plain=1#L59) llama al script job.run, que procesa hypo.dat y genera resultados en ~12 minutos (i9). Produce:

- [`salida.txt`](model/salida.txt): Tiempos de arribo brutos.
- [`reporte.pdf`](model/reporte.pdf): Mapas de altura de olas, mareógrafos y parámetros técnicos.

> [!WARNING]
> Los endpoints deben invocarse en orden estricto: `/calculate` -> `/tsunami-travel-times` -> `/run-tsdhn`, ya que cada uno depende del resultado del anterior.

## Parámetros de entrada

El modelo TSDHN requiere los siguientes parámetros para la simulación. Estos datos son proporcionados por el usuario a través de las solicitudes a la API:

| Parámetro | Descripción                | Unidad       |
| --------- | -------------------------- | ------------ |
| `Mw`      | Magnitud momento sísmico   | Adimensional |
| `h`       | Profundidad del hipocentro | km           |
| `lat0`    | Latitud del epicentro      | grados       |
| `lon0`    | Longitud del epicentro     | grados       |
| `dia`     | Día del mes del evento     |              |
| `hhmm`    | Hora y minutos del evento  |              |

Ten en cuenta que los modelos Pydantic (definidos en schemas.py) se encargan de validar y, en algunos casos, transformar estos parámetros para asegurar que el formato sea el correcto.

## Notas adicionales

- Toda la información relevante y los posibles errores se registran en el archivo `tsunami_api.log` (configurado en [`config.py`](/orchestrator/core/config.py)), lo que te ayudará a depurar cualquier problema. Este archivo se crea automáticamente luego de la primera vez que ejecutas la API.
- Cada vez que realices cambios en el código, es buena práctica ejecutar:
  ```bash
  poetry run pytest
  poetry poe format
  ```
  para formatear el código y asegurarte de todo sigue funcionando correctamente.
