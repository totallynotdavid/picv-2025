import datetime
from pathlib import Path
from string import Template
from typing import List, Tuple


# Define a custom Template class that uses "@" as the delimiter.
class LatexTemplate(Template):
    delimiter = '@'

def read_meca_dat(filepath: Path = Path("meca.dat")) -> Tuple[float, float, float, float, float, float, float, int, int, str]:
    content = filepath.read_text(encoding="utf-8")
    tokens = content.split()
    if len(tokens) < 10:
        raise ValueError("meca.dat does not contain at least 10 tokens.")
    xep, yep, zep = float(tokens[0]), float(tokens[1]), float(tokens[2])
    Az, echado, rake = float(tokens[3]), float(tokens[4]), float(tokens[5])
    Mw = float(tokens[6])
    # cero1 and cero2 are read but not used further.
    cero1, cero2 = int(tokens[7]), int(tokens[8])
    t0 = tokens[9]
    if xep > 180.0:
        xep -= 360.0
    return xep, yep, zep, Az, echado, rake, Mw, cero1, cero2, t0

def read_ttt_max_dat(filepath: Path = Path("ttt_max.dat")) -> Tuple[List[float], List[float], List[int], List[int]]:
    lines = filepath.read_text(encoding="utf-8").splitlines()
    ttt_list = []
    max_list = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            ttt_list.append(float(parts[0]))
            max_list.append(float(parts[1]))
    if len(ttt_list) != 17:
        raise ValueError(f"Expected 17 lines in {filepath}, got {len(ttt_list)}")
    hh = [int(t // 60) for t in ttt_list]
    mm = [int(round(t % 60)) for t in ttt_list]
    return ttt_list, max_list, hh, mm

def get_current_datetime_info() -> Tuple[str, str, Tuple[int, int, int], str]:
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    year, month, day = now.year, now.month, now.day
    month_map = {
        1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Set", 10: "Oct", 11: "Nov", 12: "Dic"
    }
    mes = month_map.get(month, "")
    return date_str, time_str, (year, month, day), mes

def write_reporte_tex(context: dict,
                      template_path: Path = Path("reporte_template.tex"),
                      outpath: Path = Path("reporte.tex")) -> None:
    """
    Reads the LaTeX template file, substitutes placeholders using our custom
    LatexTemplate (with "@" as delimiter), and writes the resulting report.
    """
    template_text = template_path.read_text(encoding="utf-8")
    t = LatexTemplate(template_text)
    rendered = t.substitute(context)
    outpath.write_text(rendered, encoding="utf-8")
    print(f"Created LaTeX report: {outpath}")

def write_salida_txt(yep: float, xep: float, zep: float, Mw: float, t0: str,
                     date_str: str, time_str: str, date_info: Tuple[int, int, int], mes: str,
                     hh: List[int], mm: List[int], max_list: List[float],
                     outpath: Path = Path("salida.txt")) -> None:
    year, _, day = date_info
    stations = [
        ("Tumbes",      "La Cruz",   0),
        ("Piura",       "Talara",    1),
        ("Piura",       "Paita",     2),
        ("Lambayeque",  "Pimentel",  3),
        ("La_Libertad", "Salaverry", 4),
        ("Ancash",      "Chimbote",  5),
        ("Ancash",      "Huarmey",   6),
        ("Lima",        "Huacho",    7),
        ("Lima",        "Callao",    8),
        ("Lima",        "Cerro Azul",9),
        ("Ica",         "Pisco",    10),
        ("Ica",         "San Juan", 11),
        ("Arequipa",    "Atico",    12),
        ("Arequipa",    "Camana",   13),
        ("Arequipa",    "Matarani", 14),
        ("Moquegua",    "Ilo",      15),
        ("Chile",       "Arica",    16)
    ]
    def station_line(dept: str, port: str, h: int, m: int, max_val: float) -> str:
        time_fmt = f"{h}:{m:02d}"
        return f"{(dept + ' ' + port):27s}{time_fmt:>5s}   {max_val:6.2f}     {time_fmt:>5s}"
    lines = [
        f"{'ESTIMACION DEL TIEMPO DE ARRIBO DE TSUNAMIS':43s}",
        f"{'Coordenadas del epicentro: ':26s}",
        f"Fecha    = {day:2d} {mes} {year:4d}",
        f"Hora     = {t0}",
        f"Latitud  =  {yep:7.2f}",
        f"Longitud =  {xep:7.2f}",
        f"Profund  =  {zep:5.1f} km",
        f"Magnitud =  {Mw:3.1f}",
        f"Tiempo actual: {date_str} {time_str}",
        f"{'Departamento Puertos    Hora_llegada  Hmax(m)  T_arribo':55s}"
    ]
    for dept, port, idx in stations:
        lines.append(station_line(dept, port, hh[idx], mm[idx], max_list[idx]))
    lines.append(f"{'* La altura estimada NO considera la fase lunar ni oleaje anomalo':65s}")
    outpath.write_text("\n".join(lines), encoding="utf-8")
    print(f"Created text summary: {outpath}")

def main() -> None:
    # Read input files
    xep, yep, zep, Az, echado, rake, Mw, _, _, t0 = read_meca_dat()
    ttt_list, max_list, hh, mm = read_ttt_max_dat()

    # Build context for the LaTeX template using "@" placeholders.
    context = {
        "title": "REPORTE: ESTIMACIÓN DE PARÁMETROS DE TSUNAMI DE ORIGEN LEJANO",
        "author": "Cesar Jimenez (Version: 1.3)",
        "lat": f"{yep:.2f}",
        "lon": f"{xep:.2f}",
        "depth": f"{zep:.1f}",
        "magnitude": f"{Mw:.1f}",
        "strike": f"{Az:.1f}",
        "dip": f"{echado:.1f}",
        "rake": f"{rake:.1f}",
        "station1_name": "Talara",
        "station1_time": f"{hh[1]}:{mm[1]:02d}",
        "station1_max": f"{max_list[1]:6.2f}",
        "station2_name": "Callao",
        "station2_time": f"{hh[8]}:{mm[8]:02d}",
        "station2_max": f"{max_list[8]:6.2f}",
        "station3_name": "Matarani",
        "station3_time": f"{hh[14]}:{mm[14]:02d}",
        "station3_max": f"{max_list[14]:6.2f}"
    }

    # Create the LaTeX report from the template.
    write_reporte_tex(context)

    # Get current date/time info for the text summary.
    date_str, time_str, date_info, mes = get_current_datetime_info()
    write_salida_txt(yep, xep, zep, Mw, t0, date_str, time_str, date_info, mes, hh, mm, max_list)

if __name__ == "__main__":
    main()
