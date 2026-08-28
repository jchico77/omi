#!/usr/bin/env python3
"""Demo Fase 0: pasa la muestra real de PDFs del BOE por el clasificador v1.

Lee demo/muestra_real.json (títulos reales transcritos de los PDF del BOE
2020-2022), aplica `clasificar` e `indice_entierro` de ingest.py y escribe
demo/demo_resultados.json con el resultado por documento y los agregados.

Uso:
    python demo/generar_demo.py
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import clasificar, indice_entierro

AQUI = Path(__file__).parent
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def main() -> int:
    muestra = json.loads((AQUI / "muestra_real.json").read_text(encoding="utf-8"))
    resultados = []
    por_categoria = {}
    por_seccion = {}
    for doc in muestra["documentos"]:
        f = date.fromisoformat(doc["fecha"])
        etiquetas = clasificar(doc["titulo"], doc["seccion"])
        entierro = indice_entierro(f)
        resultados.append(
            {
                **doc,
                "url_html": f"https://www.boe.es/diario_boe/txt.php?id={doc['boe_id']}",
                "categorias": etiquetas,
                "indice_entierro": entierro,
                "dia_semana": DIAS[f.weekday()],
            }
        )
        por_seccion[doc["seccion"]] = por_seccion.get(doc["seccion"], 0) + 1
        for e in etiquetas:
            por_categoria[e] = por_categoria.get(e, 0) + 1

    salida = {
        "fuente": muestra["fuente"],
        "total": len(resultados),
        "por_seccion": dict(sorted(por_seccion.items())),
        "por_categoria": dict(sorted(por_categoria.items())),
        "documentos": resultados,
    }
    ruta = AQUI / "demo_resultados.json"
    ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{salida['total']} documentos clasificados → {ruta}")
    print(f"Por sección: {salida['por_seccion']}")
    print(f"Por categoría: {salida['por_categoria']}")
    for r in resultados:
        if r["categorias"] or r["indice_entierro"] >= 50:
            print(f"  [{', '.join(r['categorias']) or 'sin etiqueta'}] entierro={r['indice_entierro']}"
                  f" ({r['dia_semana']} {r['fecha']}) {r['boe_id']}: {r['titulo'][:90]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
