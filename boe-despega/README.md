# BOE Despega — Fase 0 (ingesta local)

Script local que descarga el sumario diario del BOE desde la API de datos
abiertos de la AEBOE, clasifica cada disposición con las reglas v1 y vuelca el
resultado como JSON a `data/AAAAMMDD.json`. Spec completa del proyecto en el
documento «BOE Despega — Spec del proyecto».

## Uso

```bash
pip install requests            # única dependencia externa
python ingest.py 2026-07-24     # también acepta AAAAMMDD
python validate_fase0.py        # ingesta las 10 fechas de validación + informe
python test_clasificador.py     # tests unitarios del clasificador (sin red)
```

- Día sin BOE (domingos, algunos festivos): la API devuelve 404, se escribe un
  JSON de día vacío y el script termina con código 0.
- Fallo de red o error de la API: mensaje a stderr y código 1. Nada se rompe.

## Salida

`data/AAAAMMDD.json` con resumen del día (`total_disposiciones`,
`por_seccion`, `por_categoria`, `indice_entierro_dia`) y la lista
`disposiciones` con el esquema de la tabla DynamoDB de la spec (`boe_id`,
`fecha`, `seccion`, `departamento`, `titulo`, `url_html/pdf/xml`,
`categorias`, `resumen` (null en MVP), `indice_entierro`, `publicado_tg`,
`created_at`).

## Clasificador v1 — desviaciones respecto a la spec

- `indulto`: la spec pide título que contenga «indulto», pero la fórmula real
  del BOE es «por el que se **indulta** a don…». La regla usa el lexema
  `indult` para cubrir ambas formas.
- `cese`: se exige límite de palabra (`cese`/`ceses`) para evitar falsos
  positivos por subcadena.
- `indice_entierro`: en Fase 0 se computan las señales de calendario (viernes
  +30, víspera de festivo nacional +30, agosto o 24 dic–6 ene +25). La señal
  «volumen del día > percentil 90» (+15) requiere el histórico del backfill
  (Fase 3) y no se computa: no se inventa el dato.

## Estado de la validación con fechas reales

`validate_fase0.py` ingesta 10 fechas reales variadas de 2024–2026 (incluye un
viernes de julio, un miércoles post-Consejo de Ministros y un domingo sin BOE)
y genera `data/validacion_fase0.md` con todos los títulos etiquetados para la
revisión manual de precisión (>90 % sobre muestra de 100).

**Pendiente de ejecutar**: el entorno remoto donde se desarrolló esta fase
bloquea el egreso a `boe.es` y `www.boe.es` por política de red, así que la
validación no pudo correrse ahí. Ejecutar `python validate_fase0.py` desde una
máquina con salida a internet (o permitir esos dominios en la política de red
del entorno) y revisar el informe antes de dar por buena la v1.

## Modo offline (entornos sin salida a boe.es)

Los sumarios se pueden descargar en otra máquina y procesar sin red:

```bash
# En una máquina con internet (una línea por fecha de validación):
for d in 20260724 20260826 20260823 20241224 20250417 20240816 20250102 20251011 20240605 20260213; do
  curl -sS -H "Accept: application/json" \
    "https://www.boe.es/datosabiertos/api/boe/sumario/$d" -o "$d.json"
done

# En el entorno sin red, tras copiar los ficheros a data/raw/:
python validate_fase0.py                       # detecta data/raw/ automáticamente
python ingest.py 2026-07-24 --fichero data/raw/20260724.json   # fecha suelta
```

Un fichero vacío o con `{"status":{"code":"404"}}` se trata como día sin BOE.
