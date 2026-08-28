#!/usr/bin/env python3
"""Tests unitarios de las funciones puras de la ingesta (sin red).

Los títulos de los casos son fixtures de test que siguen las fórmulas
literales del BOE; no forman parte de ningún dato de salida del producto.

Uso:
    python -m pytest test_clasificador.py -q   # o: python test_clasificador.py
"""

from datetime import date

from ingest import clasificar, como_lista, indice_entierro, normalizar, url_texto


def test_normalizar_quita_tildes_y_mayusculas():
    assert normalizar("Concesión DIRECTA de subvención") == "concesion directa de subvencion"


def test_nombramiento_solo_en_seccion_2a():
    titulo = "Real Decreto 100/2026 por el que se nombra Directora General a doña N.N."
    assert clasificar(titulo, "II-A") == ["nombramiento"]
    assert clasificar(titulo, "III") == []


def test_cese_con_limite_de_palabra():
    assert "cese" in clasificar("Real Decreto por el que se dispone el cese de don N.N.", "II-A")
    # "procese"/"cesen" no deben casar como "cese"
    assert clasificar("Orden por la que se procesen las solicitudes", "II-A") == []


def test_libre_designacion_sin_tildes_y_en_cualquier_seccion():
    titulo = "Orden por la que se convoca la provisión de puestos por el sistema de libre designación"
    assert "libre_designacion" in clasificar(titulo, "II-B")


def test_indulto_cubre_sustantivo_y_formula_verbal():
    # La fórmula real del BOE es "por el que se indulta a don ...".
    assert "indulto" in clasificar("Real Decreto por el que se indulta a don N.N.", "III")
    assert "indulto" in clasificar("Real Decreto de concesión de indulto a don N.N.", "III")
    assert "indulto" in clasificar("Real Decreto de concesión de indultos", "III")
    assert clasificar("Orden sobre el sector vinícola", "III") == []


def test_subvencion_directa_requiere_ambas_partes():
    assert "subvencion_directa" in clasificar(
        "Real Decreto por el que se regula la concesión directa de una subvención", "III"
    )
    assert "subvencion_directa" in clasificar(
        "Real Decreto por el que se regula la concesión directa de ayudas", "III"
    )
    assert clasificar("Real Decreto por el que se regula la concesión directa de un premio", "III") == []
    assert clasificar("Extracto de la convocatoria de subvenciones en concurrencia competitiva", "III") == []


def test_credito_extraordinario_y_suplemento():
    assert "credito_extraordinario" in clasificar("Ley por la que se concede un crédito extraordinario", "I")
    assert "credito_extraordinario" in clasificar("Ley de concesión de créditos extraordinarios", "I")
    assert "credito_extraordinario" in clasificar("Ley por la que se concede un suplemento de crédito", "I")


def test_organismo_nuevo_solo_seccion_1_y_con_sustantivo():
    titulo = "Real Decreto por el que se crea el Observatorio de la Vivienda"
    assert "organismo_nuevo" in clasificar(titulo, "I")
    assert clasificar(titulo, "III") == []
    assert clasificar("Real Decreto por el que se crea la Medalla al Mérito", "I") == []


def test_organismo_suprimido():
    assert "organismo_suprimido" in clasificar(
        "Real Decreto por el que se suprime la Oficina del Comisionado", "I"
    )


def test_convenio():
    assert "convenio" in clasificar("Resolución por la que se publica el Convenio con la Comunidad de Madrid", "III")


def test_multietiqueta():
    etiquetas = clasificar(
        "Real Decreto por el que se dispone el cese y se nombra Subsecretario a don N.N.", "II-A"
    )
    assert set(etiquetas) == {"nombramiento", "cese"}


def test_indice_entierro():
    assert indice_entierro(date(2026, 2, 13)) == 30  # viernes normal
    assert indice_entierro(date(2024, 6, 5)) == 0  # miércoles normal
    assert indice_entierro(date(2024, 8, 16)) == 55  # viernes + agosto
    assert indice_entierro(date(2025, 4, 17)) == 30  # víspera de Viernes Santo
    assert indice_entierro(date(2024, 12, 24)) == 55  # víspera de Navidad + ventana navideña
    assert indice_entierro(date(2025, 10, 11)) == 30  # víspera del 12 de octubre
    assert indice_entierro(date(2025, 1, 3)) == 55  # viernes en ventana navideña


def test_como_lista_normaliza_objeto_unico():
    assert como_lista(None) == []
    assert como_lista({"a": 1}) == [{"a": 1}]
    assert como_lista([1, 2]) == [1, 2]


def test_url_texto_cadena_u_objeto():
    assert url_texto("https://example.invalid/x.pdf") == "https://example.invalid/x.pdf"
    assert url_texto({"texto": "https://example.invalid/x.pdf", "szBytes": 1}) == "https://example.invalid/x.pdf"
    assert url_texto({}) is None
    assert url_texto(None) is None
    assert url_texto("") is None


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    raise SystemExit(1 if fallos else 0)
