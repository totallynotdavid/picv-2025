# Orchestrator-TSDHN

El Orchestrator-TSDHN es una herramienta para la estimación de parámetros de tsunamis de origen lejano mediante simulaciones numéricas. Combina el **modelo TSDHN escrito en Fortran** (ubicado en la carpeta [`/model`](/model/)) con una **API escrita en Python** ([`/orchestrator`](/orchestrator/)) que procesa datos sísmicos iniciales, como ubicación y magnitud de terremotos, para calcular variables como: dimensiones de ruptura sísmica, momento sísmico y desplazamiento de la corteza. Estas variables son utilizadas finalmente en la simulación principal, cuyo resultado incluye un informe en formato PDF con mapas de propagación, gráficos de mareógrafos y datos técnicos, además de un archivo de texto con tiempos de arribo a estaciones costeras.

> [!IMPORTANT]
> La lógica de los cálculos numéricos reside en este repositorio, mientras que la [interfaz web](https://github.com/totallynotdavid/picv-2025-web) (que gestiona solicitudes y entrega el informe al usuario final) opera en un entorno separado.

A continuación, se muestra un diagrama que ilustra el flujo general del Orchestrator-TSDHN:

```mermaid
flowchart TB
    subgraph "Orchestrator-TSDHN v0.1.0"
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
> Este proyecto está diseñado para entornos Linux (recomendamos **Ubuntu 20.04**). Si utilizas Windows, necesitarás configurar **Windows Subsystem for Linux** (WSL versión 2.0 o superior). Para instalar WSL, sigue la guía oficial de Microsoft: [<kbd>Instalación de WSL</kbd>](https://learn.microsoft.com/es-es/windows/wsl/install).

**Prerrequisitos:**

Antes de comenzar con la instalación, actualiza tu sistema:

```bash
sudo apt update -y && sudo apt upgrade -y
```

1. _Python_:

   <table><tr><td>**Opción A**: Usando pyenv (Recomendado)</td></tr></table>

   Con pyenv podrás manejar múltiples versiones de Python de forma sencilla.

   ```bash
   sudo apt-get install build-essential zlib1g-dev libffi-dev libssl-dev libbz2-dev libreadline-dev libsqlite3-dev liblzma-dev libncurses-dev tk-dev
   curl -fsSL https://pyenv.run | bash
   ```

   Si estás usando WSL, añade lo siguiente a tu `~/.bashrc`:

   ```bash
   echo '
   export PYENV_ROOT="$HOME/.pyenv"
   export PATH="$PYENV_ROOT/bin:$PATH"
   eval "$(pyenv init -)"' >> ~/.bashrc

   source ~/.bashrc
   pyenv install 3.13
   ```

   <table><tr><td>**Opción B**: Python predeterminado</td></tr></table>

   Si prefieres no usar pyenv:

   ```bash
   sudo apt install -y python3-pip
   ```

   En ambos casos, verifica la instalación:

   ```bash
   python3 -V
   pip3 -V
   ```

2. _Poetry_ nos auyda a gestionar las dependencias del proyecto de forma consistente entre dispositivos.

   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

> [!TIP]
> Verifica la instalación con: `poetry --version`

3. _TTTAPI_ (Tsunami Travel Time):

   ```bash
   sudo apt install git-lfs

   # Instalación de TTTAPI
   git clone https://gitlab.com/totallynotdavid/tttapi/
   cd tttapi
   make config
   make compile
   sudo make install
   sudo make datadir
   sudo make docs
   make test
   make clean
   ```

> [!NOTE]
> TTTAPI is hosted under Gitlab because the data files are big and we need to use git lfs / also for CI. The version hosted in Gitlab is just a mirror from the original authors.

4. _TeXLive_ es necesario para generar los informes en formato PDF.

   ```bash
   cd /tmp
   wget https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz
   zcat < install-tl-unx.tar.gz | tar xf -
   cd install-tl-2*

   # Creación del perfil de instalación
   cat > texlive.profile << EOF
   selected_scheme scheme-basic
   tlpdbopt_autobackup 0
   tlpdbopt_install_docfiles 0
   tlpdbopt_install_srcfiles 0
   EOF

   # Instalación
   perl ./install-tl --profile=texlive.profile \
                     --texdir "$HOME/texlive" \
                     --texuserdir "$HOME/.texlive" \
                     --no-interaction

   # Configuración del PATH
   echo -e '\nexport PATH="$HOME/texlive/bin/x86_64-linux:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

   Instalando paquetes de LaTeX con tlmgr:

   ```bash
   tlmgr update --self
   tlmgr install babel-spanish hyphen-spanish booktabs
   ```

5. Dependencias adicionales: `gfortran 11.4.0`, `redis-server`, `gmt`, `ps2eps`, `cmake` (ttt_client), `perl` (para TeXLive), `wget`

   ```bash
   sudo apt install -y gfortran redis-server ps2eps gmt gmt-dcw gmt-gshhg
   ```

   Configura Redis para que sea gestionado por systemd (en Ubuntu):

   ```bash
   sudo sed -i 's/^# \?supervised \(no\|auto\)/supervised systemd/' /etc/redis/redis.conf
   sudo systemctl restart redis-server
   ```

6. Si necesitas ejecutar la interfaz gráfica original ([<kbd>tsunami.m</kbd>](model/tsunami.m)), puedes instalar [MATLAB R2014](https://drive.google.com/file/d/1VhLnwXX78Y7O8huwlRuE-shOW2LKlVpd/view?usp=drive_link).

**Pasos de instalación:**

1. Clona el repositorio:

   ```bash
   git clone https://github.com/totallynotdavid/picv-2025
   cd picv-2025
   ```

2. Instala las dependencias con Poetry:

   ```bash
   poetry install
   poetry self add 'poethepoet[poetry_plugin]'
   eval $(poetry env activate)
   ```

3. Verifica la instalación:

   ```bash
   poetry run pytest
   ```

4. Inicia la API:

   ```bash
   poetry run start
   rq worker tsdhn_queue
   ```

   Es importante que ejecutes `rq worker tsdhn_queue` en el entorno de Poetry o rq no se encontrará.

> [!NOTE]
> La API estará disponible en `http://localhost:8000`

## Estructura del proyecto

El repositorio se organiza en dos componentes principales:

```txt
picv-2025/
├── orchestrator/
│   ├── core/
│   │   ├── calculator.py         # Class TsunamiCalculator y la lógica central de los cálculos.
│   │   └── config.py             # Define constantes globales y la configuración del logging.
│   ├── main.py                   # Punto de entrada de la API y definición de los endpoints.
│   ├── models/
│   │   └── schemas.py            # Schema para la validación y transformación de los datos.
│   └── utils/
│       └── geo.py                # Funciones para cálculos geográficos (distancias, formatos, etc.).
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

> [!WARNING]
> El modelo solo procesa magnitudes entre Mw 6.5 y Mw 9.5. Valores fuera de este rango resultarán en un error.

El proceso inicia cuando el usuario envía datos sísmicos desde la [interfaz web](https://github.com/totallynotdavid/picv-2025-web). La API gestiona los siguientes endpoints:

1. [`/calculate`](orchestrator/main.py?plain=1#L27) recibe los valores para la magnitud (Mw), profundidad (h) y coordenadas del epicentro. Luego, calcula la geometría de la ruptura, el momento sísmico y evalúa el riesgo de tsunami. Genera el archivo [`hypo.dat`](model/hypo.dat) que se usará en la simulación.

   Los siguientes campos deben enviarse en el cuerpo de la solicitud en formato JSON:

   | Parámetro | Descripción                | Unidad         |
   | --------- | -------------------------- | -------------- |
   | `Mw`      | Magnitud momento sísmico   | Adimensional   |
   | `h`       | Profundidad del hipocentro | km             |
   | `lat0`    | Latitud del epicentro      | grados         |
   | `lon0`    | Longitud del epicentro     | grados         |
   | `dia`     | Día del mes del evento     | string         |
   | `hhmm`    | Hora y minutos del evento  | formato `HHMM` |

   Ten en cuenta que los modelos Pydantic (definidos en [`schemas.py`](orchestrator/models/schemas.py)) se encargan de validar y, en algunos casos, transformar estos parámetros para asegurar que el formato sea el correcto.

   Un ejemplo de solicitud (`POST`):

   ```json
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

2. [`/tsunami-travel-times`](orchestrator/main.py?plain=1#L45) utiliza los mismos datos de entrada y realiza una serie de integraciones vectorizadas para calcular los tiempos de arribo a puertos predefinidos ([`puertos.txt`](/model/puertos.txt)). La respuesta es un objeto JSON que incluye tanto los tiempos de arribo como las distancias a cada estación.
3. [`/run-tsdhn`](orchestrator/main.py?plain=1#L61) llama al script [`job.run`](model/job.run), que procesa [`hypo.dat`](model/hypo.dat) y genera resultados en ~12 minutos (en un procesador de 8 núcleos). Produce:

   - [`salida.txt`](model/salida.txt): Tiempos de arribo brutos.
   - [`reporte.pdf`](model/reporte.pdf): Mapas de altura de olas, mareógrafos y parámetros técnicos.

> [!WARNING]
> Los endpoints deben invocarse en orden estricto: `/calculate` :arrow_right: `/tsunami-travel-times` :arrow_right: `/run-tsdhn`, ya que cada uno depende del resultado del anterior.

## Notas adicionales

- La API guarda automáticamente algunos eventos en `tsunami_api.log`. Puedes configurar el logger en [`config.py`](/orchestrator/core/config.py) si deseas. El archivo de logs se crea cuando inicias la API.
- Si estás haciendo pruebas y quieres ver los logs en tu terminal mientras usas `pytest`, solo necesitas cambiar una línea en [`pyproject.toml`](pyproject.toml):
  ```toml
  [tool.pytest.ini_options]
  log_cli = true
  ```
  Te recomiendo usar `logger.debug()` en vez de `print()` o sino pytest lo ignorará.
- Cuando termines de hacer cambios en el código, y antes de hacer commit, ejecuta:
  ```bash
  poetry run pytest
  poetry poe format
  ```
  para formatear el código y asegurarte de todo sigue funcionando correctamente.
