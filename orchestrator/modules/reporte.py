import datetime
import shutil
from pathlib import Path
from string import Template
from typing import Dict, List, Tuple

MONTH_MAP = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Oct",
    11: "Nov",
    12: "Dic",
}


class LatexTemplate(Template):
    delimiter = "@"


def generate_reports(working_dir: Path) -> None:
    """Main entry point for report generation in the job workspace"""
    coords = read_meca_dat(working_dir)
    ttt_data = read_ttt_max_dat(working_dir)
    datetime_info = get_current_datetime_info()

    context = build_template_context(coords, ttt_data)
    copy_template(working_dir)
    write_reporte_tex(context, working_dir)
    write_salida_txt(coords, ttt_data, datetime_info, working_dir)


def read_meca_dat(working_dir: Path) -> Tuple[float, ...]:
    filepath = working_dir / "meca.dat"
    content = filepath.read_text(encoding="utf-8")
    tokens = content.split()

    if len(tokens) < 10:
        raise ValueError(
            f"Invalid meca.dat format - expected 10+ tokens, got {len(tokens)}"
        )

    values = tokens[:10]
    xep, yep, zep = map(float, values[:3])
    az, dip, rake = map(float, values[3:6])
    mw = float(values[6])
    t0 = values[9]

    if xep > 180.0:
        xep -= 360.0

    return (xep, yep, zep, az, dip, rake, mw, int(values[7]), int(values[8]), t0)


def read_ttt_max_dat(working_dir: Path) -> Tuple[List[float], ...]:
    filepath = working_dir / "ttt_max.dat"
    lines = filepath.read_text(encoding="utf-8").splitlines()
    data = []

    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            data.append((float(parts[0]), float(parts[1])))

    if len(data) != 17:
        raise ValueError(f"Expected 17 entries in ttt_max.dat, got {len(data)}")

    ttt, max_vals = zip(*data, strict=False)
    hours = [int(t // 60) for t in ttt]
    minutes = [int(round(t % 60)) for t in ttt]

    return (list(ttt), list(max_vals), hours, minutes)


def get_current_datetime_info() -> Tuple[str, str, Tuple[int, int, int], str]:
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    year_month_day = (now.year, now.month, now.day)
    return (date_str, time_str, year_month_day, MONTH_MAP[now.month])


def build_template_context(
    coords: Tuple[float, ...], ttt_data: Tuple[List[float], ...]
) -> Dict[str, str]:
    _, max_vals, hours, minutes = ttt_data
    return {
        "title": "REPORTE: ESTIMACIÓN DE PARÁMETROS DE TSUNAMI DE ORIGEN LEJANO",
        "author": "Cesar Jimenez",
        "lat": f"{coords[1]:.2f}",
        "lon": f"{coords[0]:.2f}",
        "depth": f"{coords[2]:.1f}",
        "magnitude": f"{coords[6]:.1f}",
        "strike": f"{coords[3]:.1f}",
        "dip": f"{coords[4]:.1f}",
        "rake": f"{coords[5]:.1f}",
        "station1_name": "Talara",
        "station1_time": f"{hours[1]}:{minutes[1]:02d}",
        "station1_max": f"{max_vals[1]:6.2f}",
        "station2_name": "Callao",
        "station2_time": f"{hours[8]}:{minutes[8]:02d}",
        "station2_max": f"{max_vals[8]:6.2f}",
        "station3_name": "Matarani",
        "station3_time": f"{hours[14]}:{minutes[14]:02d}",
        "station3_max": f"{max_vals[14]:6.2f}",
    }


def copy_template(working_dir: Path) -> None:
    """Copy LaTeX template from package resources to job directory"""
    template_path = Path(__file__).parent / "templates" / "reporte_template.tex"
    dest_path = working_dir / "reporte_template.tex"
    shutil.copy(template_path, dest_path)


def write_reporte_tex(context: Dict[str, str], working_dir: Path) -> None:
    template_path = working_dir / "reporte_template.tex"
    out_path = working_dir / "reporte.tex"

    template = template_path.read_text(encoding="utf-8")
    rendered = LatexTemplate(template).substitute(context)
    out_path.write_text(rendered, encoding="utf-8")


def write_salida_txt(
    coords: Tuple[float, ...],
    ttt_data: Tuple[List[float], ...],
    datetime_info: Tuple[str, str, Tuple[int, int, int], str],
    working_dir: Path,
) -> None:
    yep, xep, zep, _, _, _, mw, _, _, t0 = coords
    date_str, time_str, (year, month, day), mes = datetime_info
    _, max_list, hours, minutes = ttt_data

    stations = [
        ("Tumbes", "La Cruz", 0),
        ("Piura", "Talara", 1),
        ("Piura", "Paita", 2),
        ("Lambayeque", "Pimentel", 3),
        ("La_Libertad", "Salaverry", 4),
        ("Ancash", "Chimbote", 5),
        ("Ancash", "Huarmey", 6),
        ("Lima", "Huacho", 7),
        ("Lima", "Callao", 8),
        ("Lima", "Cerro Azul", 9),
        ("Ica", "Pisco", 10),
        ("Ica", "San Juan", 11),
        ("Arequipa", "Atico", 12),
        ("Arequipa", "Camana", 13),
        ("Arequipa", "Matarani", 14),
        ("Moquegua", "Ilo", 15),
        ("Chile", "Arica", 16),
    ]

    lines = [
        f"{'ESTIMACION DEL TIEMPO DE ARRIBO DE TSUNAMIS':^43}",
        f"{'Coordenadas del epicentro: ':26}",
        f"Fecha    = {day:2d} {mes} {year}",
        f"Hora     = {t0}",
        f"Latitud  =  {yep:7.2f}",
        f"Longitud =  {xep:7.2f}",
        f"Profund  =  {zep:5.1f} km",
        f"Magnitud =  {mw:3.1f}",
        f"Tiempo actual: {date_str} {time_str}",
        f"{'Departamento Puertos    Hora_llegada  Hmax(m)  T_arribo':55}",
    ]

    for dept, port, idx in stations:
        h = hours[idx]
        m = minutes[idx]
        val = max_list[idx]
        lines.append(f"{f'{dept} {port}':27}{h}:{m:02d}   {val:6.2f}     {h}:{m:02d}")

    lines.append("* La altura estimada NO considera la fase lunar ni oleaje anomalo")

    out_path = working_dir / "salida.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
