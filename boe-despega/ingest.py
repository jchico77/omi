#!/usr/bin/env python3
"""BOE Despega — Fase 0: ingesta local.

Recibe una fecha, descarga el sumario diario de la API de datos abiertos de la
AEBOE, clasifica cada disposición con las reglas v1 y vuelca el resultado como
JSON a disco.

Uso:
    python ingest.py 2026-07-24
    python ingest.py 20260724 --out data/

Un día sin BOE (la API devuelve 404, p. ej. domingos) se trata como día vacío:
se escribe un JSON con cero disposiciones y el script termina con código 0.
Un fallo de red o un error de la API distinto de 404 termina con código != 0.
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

API_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"
TIMEOUT_S = 30

# Mapeo de códigos de sección de la API al formato del esquema.
SECCIONES = {
    "1": "I",
    "2A": "II-A",
    "2B": "II-B",
    "3": "III",
    "4": "IV",
    "5": "V",
    "5A": "V-A",
    "5B": "V-B",
    "5C": "V-C",
    "T": "TC",
}

# Festivos nacionales (fiestas laborales de ámbito estatal publicadas en el BOE).
# Fijos todos los años + Viernes Santo (móvil). Usados para la señal
# "víspera de festivo nacional" del índice de entierro.
FESTIVOS_FIJOS_MMDD = {
    "01-01",  # Año Nuevo
    "01-06",  # Epifanía
    "05-01",  # Fiesta del Trabajo
    "08-15",  # Asunción
    "10-12",  # Fiesta Nacional
    "11-01",  # Todos los Santos
    "12-06",  # Constitución
    "12-08",  # Inmaculada
    "12-25",  # Navidad
}
VIERNES_SANTO = {
    2024: date(2024, 3, 29),
    2025: date(2025, 4, 18),
    2026: date(2026, 4, 3),
    2027: date(2027, 3, 26),
}


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar criterios del clasificador."""
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


ORGANISMOS = r"(comisionad[oa]|observatorio|oficina|consejo|agencia)"

# Reglas v1 del clasificador: (etiqueta, secciones aplicables o None, regex
# sobre el título normalizado). Todas las que casan se añaden a `categorias`.
REGLAS = [
    ("nombramiento", {"II-A"}, re.compile(r"se nombra|nombramiento")),
    ("cese", {"II-A"}, re.compile(r"se dispone el cese|\bceses?\b")),
    ("libre_designacion", None, re.compile(r"libre designacion")),
    # La spec pide "indulto", pero la fórmula real del BOE es "por el que se
    # indulta a don ...": se amplía al lexema para no perder esos títulos.
    ("indulto", None, re.compile(r"\bindult")),
    ("subvencion_directa", None, re.compile(r"(?=.*concesion directa)(?=.*(subvencion|ayuda))")),
    ("credito_extraordinario", None, re.compile(r"creditos? extraordinarios?|suplementos? de credito")),
    ("organismo_nuevo", {"I"}, re.compile(rf"(?=.*se crea)(?=.*\b{ORGANISMOS}\b)")),
    ("organismo_suprimido", None, re.compile(rf"(?=.*se suprimen?)(?=.*\b{ORGANISMOS}\b)")),
    ("convenio", None, re.compile(r"\bconvenios?\b")),
]


def clasificar(titulo: str, seccion: str) -> list:
    t = normalizar(titulo)
    etiquetas = []
    for etiqueta, secciones, patron in REGLAS:
        if secciones is not None and seccion not in secciones:
            continue
        if patron.search(t):
            etiquetas.append(etiqueta)
    return etiquetas


def es_festivo_nacional(d: date) -> bool:
    if d.strftime("%m-%d") in FESTIVOS_FIJOS_MMDD:
        return True
    return VIERNES_SANTO.get(d.year) == d


def indice_entierro(fecha: date) -> int:
    """Índice de entierro 0-100 según las señales computables en Fase 0.

    La componente "volumen del día > percentil 90" (+15) requiere el histórico
    del backfill (Fase 3): aquí no se computa y no se inventa.
    """
    puntos = 0
    if fecha.weekday() == 4:  # viernes
        puntos += 30
    if es_festivo_nacional(fecha + timedelta(days=1)):
        puntos += 30
    en_navidad = (fecha.month == 12 and fecha.day >= 24) or (fecha.month == 1 and fecha.day <= 6)
    if fecha.month == 8 or en_navidad:
        puntos += 25
    return min(puntos, 100)


def como_lista(nodo):
    """La conversión XML→JSON de la API devuelve objeto en vez de lista cuando
    hay un solo elemento; normaliza siempre a lista."""
    if nodo is None:
        return []
    if isinstance(nodo, list):
        return nodo
    return [nodo]


def url_texto(nodo):
    """Los campos url_* llegan como cadena o como objeto con clave `texto`."""
    if nodo is None:
        return None
    if isinstance(nodo, str):
        return nodo or None
    if isinstance(nodo, dict):
        return nodo.get("texto") or None
    return None


def extraer_items(sumario: dict, fecha: date, avisos: list) -> list:
    """Recorre diario → sección → departamento → [epígrafe] → item."""
    registros = []
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ind_entierro = indice_entierro(fecha)

    for diario in como_lista(sumario.get("diario")):
        for seccion in como_lista(diario.get("seccion")):
            codigo = str(seccion.get("codigo", "")).strip()
            seccion_norm = SECCIONES.get(codigo, codigo or None)
            if seccion_norm is None:
                avisos.append(f"Sección sin código: {seccion.get('nombre')!r}")
            for depto in como_lista(seccion.get("departamento")):
                nombre_depto = depto.get("nombre") or None
                items = como_lista(depto.get("item"))
                for epigrafe in como_lista(depto.get("epigrafe")):
                    items.extend(como_lista(epigrafe.get("item")))
                for item in items:
                    boe_id = item.get("identificador")
                    titulo = item.get("titulo")
                    if not boe_id or not titulo:
                        avisos.append(f"Item sin identificador o título en {nombre_depto!r}")
                        continue
                    registros.append(
                        {
                            "boe_id": boe_id,
                            "fecha": fecha.isoformat(),
                            "seccion": seccion_norm,
                            "departamento": nombre_depto,
                            "titulo": titulo,
                            "url_html": url_texto(item.get("url_html")),
                            "url_pdf": url_texto(item.get("url_pdf")),
                            "url_xml": url_texto(item.get("url_xml")),
                            "categorias": clasificar(titulo, seccion_norm or ""),
                            "resumen": None,
                            "indice_entierro": ind_entierro,
                            "publicado_tg": False,
                            "created_at": ahora,
                        }
                    )
    return registros


def extraer_nodo_sumario(cuerpo: dict):
    sumario = (cuerpo.get("data") or {}).get("sumario")
    if not isinstance(sumario, dict):
        raise ValueError(f"Respuesta sin nodo data.sumario (claves: {sorted(cuerpo)})")
    return sumario


def descargar_sumario(fecha: date):
    """Devuelve (sumario|None, hubo_boe). 404 => (None, False), día sin BOE."""
    url = API_SUMARIO.format(fecha=fecha.strftime("%Y%m%d"))
    respuesta = requests.get(url, headers={"Accept": "application/json"}, timeout=TIMEOUT_S)
    if respuesta.status_code == 404:
        return None, False
    respuesta.raise_for_status()
    return extraer_nodo_sumario(respuesta.json()), True


def leer_sumario_local(ruta: Path):
    """Lee un sumario descargado a mano (mismo JSON que devuelve la API).

    Para entornos sin salida a boe.es: descarga en otra máquina con
        curl -H "Accept: application/json" \\
             https://www.boe.es/datosabiertos/api/boe/sumario/AAAAMMDD -o AAAAMMDD.json
    y pásalo con --fichero. Un fichero vacío o con {"status":...,"code":"404"}
    se trata como día sin BOE.
    """
    contenido = ruta.read_text(encoding="utf-8").strip()
    if not contenido:
        return None, False
    cuerpo = json.loads(contenido)
    estado = cuerpo.get("status")
    if isinstance(estado, dict) and str(estado.get("code")) == "404":
        return None, False
    return extraer_nodo_sumario(cuerpo), True


def parsear_fecha(texto: str) -> date:
    for formato in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Fecha no válida: {texto!r} (usa AAAA-MM-DD o AAAAMMDD)")


def ingerir(fecha: date, dir_salida: Path, fichero: Path = None) -> dict:
    avisos = []
    if fichero is not None:
        sumario, hubo_boe = leer_sumario_local(fichero)
    else:
        sumario, hubo_boe = descargar_sumario(fecha)
    registros = extraer_items(sumario, fecha, avisos) if hubo_boe else []

    por_seccion = {}
    por_categoria = {}
    for r in registros:
        por_seccion[r["seccion"]] = por_seccion.get(r["seccion"], 0) + 1
        for c in r["categorias"]:
            por_categoria[c] = por_categoria.get(c, 0) + 1

    resultado = {
        "fecha": fecha.isoformat(),
        "boe_publicado": hubo_boe,
        "total_disposiciones": len(registros),
        "indice_entierro_dia": indice_entierro(fecha),
        "por_seccion": dict(sorted(por_seccion.items())),
        "por_categoria": dict(sorted(por_categoria.items())),
        "avisos": avisos,
        "disposiciones": registros,
    }

    dir_salida.mkdir(parents=True, exist_ok=True)
    ruta = dir_salida / f"{fecha.strftime('%Y%m%d')}.json"
    ruta.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    resultado["_ruta"] = str(ruta)
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingesta local del sumario diario del BOE (Fase 0).")
    parser.add_argument("fecha", type=parsear_fecha, help="Fecha del BOE (AAAA-MM-DD o AAAAMMDD)")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data", help="Directorio de salida")
    parser.add_argument(
        "--fichero",
        type=Path,
        default=None,
        help="Sumario JSON descargado a mano (misma respuesta de la API); si se indica, no se llama a la red",
    )
    args = parser.parse_args()

    try:
        resultado = ingerir(args.fecha, args.out, fichero=args.fichero)
    except requests.RequestException as e:
        print(f"[ERROR] Fallo de red o de la API para {args.fecha.isoformat()}: {e}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"[ERROR] Respuesta o fichero inválido para {args.fecha.isoformat()}: {e}", file=sys.stderr)
        return 1

    if not resultado["boe_publicado"]:
        print(f"{resultado['fecha']}: sin BOE (404). Escrito día vacío en {resultado['_ruta']}")
        return 0

    print(
        f"{resultado['fecha']}: {resultado['total_disposiciones']} disposiciones, "
        f"índice de entierro del día {resultado['indice_entierro_dia']}. Escrito en {resultado['_ruta']}"
    )
    print(f"  Por sección: {resultado['por_seccion']}")
    print(f"  Por categoría: {resultado['por_categoria']}")
    for aviso in resultado["avisos"]:
        print(f"  [AVISO] {aviso}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
