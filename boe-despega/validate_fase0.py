#!/usr/bin/env python3
"""BOE Despega — Fase 0: validación del clasificador v1 con fechas reales.

Ejecuta la ingesta para 10 fechas reales variadas y genera un informe markdown
(`data/validacion_fase0.md`) con los contadores por etiqueta y todos los
títulos etiquetados, para revisar a mano la precisión de las reglas.

Uso:
    python validate_fase0.py
"""

import sys
from datetime import date
from pathlib import Path

import requests

from ingest import ingerir

# 10 fechas reales variadas (2024-2026), según la Fase 0 de la spec:
# incluyen un viernes de julio y un día post-Consejo de Ministros (miércoles).
FECHAS = [
    (date(2026, 7, 24), "viernes de julio"),
    (date(2026, 8, 26), "miércoles post-Consejo de Ministros, agosto"),
    (date(2026, 8, 23), "domingo — se espera día sin BOE (404)"),
    (date(2024, 12, 24), "víspera de Navidad, ventana navideña"),
    (date(2025, 4, 17), "jueves, víspera de Viernes Santo"),
    (date(2024, 8, 16), "viernes de agosto"),
    (date(2025, 1, 2), "primer BOE del año, ventana navideña"),
    (date(2025, 10, 11), "sábado, víspera de la Fiesta Nacional"),
    (date(2024, 6, 5), "miércoles ordinario post-Consejo"),
    (date(2026, 2, 13), "viernes ordinario"),
]

DIR_DATOS = Path(__file__).parent / "data"


def main() -> int:
    resultados = []
    fallos = []
    for fecha, motivo in FECHAS:
        try:
            resultado = ingerir(fecha, DIR_DATOS)
        except (requests.RequestException, ValueError) as e:
            print(f"[ERROR] {fecha.isoformat()}: {e}", file=sys.stderr)
            fallos.append((fecha, motivo, str(e)))
            continue
        resultado["_motivo"] = motivo
        resultados.append(resultado)
        print(
            f"{fecha.isoformat()} ({motivo}): "
            + (
                f"{resultado['total_disposiciones']} disposiciones, {resultado['por_categoria']}"
                if resultado["boe_publicado"]
                else "sin BOE (404)"
            )
        )

    lineas = ["# Validación Fase 0 — clasificador v1", ""]
    total_por_categoria = {}
    for r in resultados:
        lineas.append(f"## {r['fecha']} — {r['_motivo']}")
        if not r["boe_publicado"]:
            lineas.append("Sin BOE este día (404). Tratado como día vacío. ✓")
            lineas.append("")
            continue
        lineas.append(
            f"{r['total_disposiciones']} disposiciones. Índice de entierro del día: {r['indice_entierro_dia']}."
        )
        lineas.append(f"Por sección: `{r['por_seccion']}`")
        lineas.append(f"Por categoría: `{r['por_categoria']}`")
        lineas.append("")
        etiquetadas = [d for d in r["disposiciones"] if d["categorias"]]
        for d in etiquetadas:
            lineas.append(f"- `{', '.join(d['categorias'])}` — [{d['boe_id']}] ({d['seccion']}) {d['titulo']}")
        lineas.append("")
        for cat, n in r["por_categoria"].items():
            total_por_categoria[cat] = total_por_categoria.get(cat, 0) + n

    lineas.append("## Totales por categoría (todas las fechas)")
    for cat, n in sorted(total_por_categoria.items()):
        lineas.append(f"- `{cat}`: {n}")
    lineas.append("")

    if fallos:
        lineas.append("## Fechas con error")
        for fecha, motivo, error in fallos:
            lineas.append(f"- {fecha.isoformat()} ({motivo}): {error}")
        lineas.append("")

    ruta = DIR_DATOS / "validacion_fase0.md"
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    print(f"\nInforme escrito en {ruta}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
