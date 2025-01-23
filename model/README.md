MANUAL DEL MODELO TSDHN PARA EL CALCULO DE

PARÁMETROS DE TSUNAMI DE ORIGEN LEJANO

DESDE UN CLIENTE EN LINUX

1) En el sistema operativo Linux, entrar al directorio tsdhn2022

2) Abrir una Terminal (dentro del directorio tsdhn2022) para ejecutar en línea de comandos.

3) Tipear el comando: ./job.run

4) La aplicación le solicitará los parámetros hipocentrales del terremoto: Tiempo origen, Longitud, latitud, profundidad focal (en km) y la magnitud de momento Mw.

5) El modelo se ejecutará y puede demorar alrededor de 30 min (en una PC Intel i7).

6) Al término de la ejecución del modelo, se presentan los resultados en forma automática en un reporte en formato pdf: reporte.pdf, donde se muestra información relevante sobre el terremoto, un mapa de tiempo de arribo del tsunami, los mareogramas virtuales en las estaciones de Talara, Callao y Matarani, así como una tabla con los tiempos de arribo y máxima altura del tsunami en dichas estaciones. También se genera un archivo en formato texto: salida.txt, compatible con el formato del modelo Pre-Tsunami.

DESDE UN CLIENTE EN WINDOWS

1) Abrir el programa Putty y hacer doble click en "servidor dhn"

login as: Geo01

password: cjimenez

bash <Enter>

2) Entrar al directorio tsdhn2022, para ejecutar en línea de comandos: cd tsdhn2022

3) Tipear el comando: ./job.run

4) La aplicación le solicitará los parámetros hipocentrales del terremoto: Hora origen, longitud, latitud, profundidad focal (en km) y la magnitud de momento Mw.

5) El modelo Tsdhn se ejecutará y puede demorar alrededor de 30 min (en una PC Intel i7).

6) Al término de la ejecución del modelo, se presentan los resultados en forma automática en un reporte en formato pdf: reporte.pdf, donde se muestra información relevante sobre el terremoto, un mapa de tiempo de arribo del tsunami, los mareogramas virtuales en las estaciones de Talara, Callao y Matarani, así como una tabla con los tiempos de arribo y máxima altura del tsunami en dichas estaciones. También se genera un archivo en formato texto: salida.txt, compatible con el formato del modelo Pre-Tsunami.

7) Transferir los resultados (reporte.pdf, salida.txt) a la PC en Windows:

Abrir el programa FileZilla

En la flecha abajo de "Conexión rápida", seleccionar: sftp://Geo01@192.168.3.31

En la ventana "Marcadores", seleccionar: "servidor_dhn"

En la ventana "Sitio remoto" (ventana derecha), buscar los archivos "reporte.pdf" y "salida.txt", dar doble click sobre cada archivo para transferirlo a la PC ("Sitio local").

Dr. Cesar Jimenez T.

cjimenezt@unmsm.edu.pe