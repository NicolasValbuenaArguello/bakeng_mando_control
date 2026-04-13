# =========================================================
# IMPORTACIONES
# =========================================================

import os
import traceback
import warnings
from datetime import datetime
from io import BytesIO
from typing import Optional

import pandas as pd

from psycopg_pool import ConnectionPool

from fastapi import FastAPI, APIRouter, UploadFile, File, Depends, HTTPException, Form, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
from auth.dependencies import verificar_token
from temples.listado import *

from temples.ayuda_pdf import *

# =========================================================
# VARIABLES ENTORNO
# =========================================================

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "test")


# =========================================================
# CONEXION POSTGRES
# =========================================================

DATABASE_URL = f"""
dbname={DB_NAME}
user={DB_USER}
password={DB_PASSWORD}
host={DB_HOST}
port={DB_PORT}
"""

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=2,
    max_size=10
)

def get_conn():
    return pool.connection()


# =========================================================
# APP
# =========================================================

app = FastAPI()
router = APIRouter()


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# FUNCIONES SEGURAS
# =========================================================
def safe_int(value):
    try:
        if value is None:
            return None
        if str(value).lower() == "nan":
            return None
        return int(float(value))
    except:
        return None

def safe_float(value):
    try:
        if value is None:
            return None
        if str(value).lower() == "nan":
            return None
        return float(value)
    except:
        return None

def safe_str(value):
    if value is None:
        return None

    val = str(value).strip()

    if val.lower() in ["nan", "none", ""]:
        return None

    return val

def safe_iloc(row, index):
    if index >= len(row):
        return None
    return row.iloc[index]


def _add_text_filter(filtros, parametros, columna, valor):
    if valor is None:
        return

    valor_limpio = str(valor).strip()
    if not valor_limpio:
        return

    valor_normalizado = valor_limpio.lower()
    if valor_normalizado in {"none", "null", "undefined", "nan", "todos", "todas", "todo", "all", "*"}:
        return

    filtros.append(f"TRIM(COALESCE({columna}::text, '')) ILIKE %s")
    parametros.append(valor_limpio)


def _build_personal_filters(
    fecha_filtro,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
    peloton: Optional[int] = None,
    relacion_mando: Optional[str] = None,
    ciclo: Optional[str] = None,
    actividad: Optional[str] = None,
    ubicacion: Optional[str] = None,
):
    filtros = ["fecha_informacion = %s"]
    parametros = [fecha_filtro]

    _add_text_filter(filtros, parametros, "division", division)
    _add_text_filter(filtros, parametros, "brigada", brigada)
    _add_text_filter(filtros, parametros, "batallon", batallon)
    _add_text_filter(filtros, parametros, "compania", compania)

    if peloton is not None:
        filtros.append("peloton = %s")
        parametros.append(peloton)

    _add_text_filter(filtros, parametros, "relacion_mando", relacion_mando)
    _add_text_filter(filtros, parametros, "ciclo", ciclo)
    _add_text_filter(filtros, parametros, "actividad", actividad)
    _add_text_filter(filtros, parametros, "ubicacion", ubicacion)

    return " AND ".join(filtros), tuple(parametros)


def _coalesce_query_text(*values):
    for value in values:
        if value is None:
            continue

        value_str = str(value).strip()
        if not value_str:
            continue

        if value_str.lower() in {"none", "null", "undefined", "nan"}:
            continue

        return value_str

    return None


def _safe_count(value):
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _build_parte_diario_tables(personal_rows, toe_row=None):
    detalle_grados = [
        "GR", "MG", "BG", "CR", "TC", "MY", "CT", "TE", "ST",
        "SMC", "SM", "SP", "SV", "SS", "CP", "CS", "C3", "SLP", "SL18", "SL12"
    ]
    detalle_map = {grado: idx for idx, grado in enumerate(detalle_grados)}

    resumen_labels = ["OFI", "SUB", "SLP", "SL18", "SL12", "H", "M"]
    resumen_categories = [
        "EFECTIVOS", "HOMBRES", "MUJERES", "NOVEDADES", "DISPONIBLES", "ORGÁNICA",
        "SEGREGACIONES", "AGREGADOS", "ARÉA DE OPERACIONES", "PDMAT", "PMAD",
        "OPERACIONES", "DESCANSO", "ENTRENAMIENTO",
    ]

    detalle_categories = [
        "EFECTIVOS", "HOMBRES", "MUJERES", "NOVEDADES", "DISPONIBLES", "ORGÁNICA",
        "SEGREGACIONES", "AGREGADOS", "ARÉA DE OPERACIONES", "PDMAT", "PMAD",
        "OPERACIONES", "DESCANSO", "ENTRENAMIENTO",
    ]

    resumen = {categoria: [0] * len(resumen_labels) for categoria in resumen_categories}
    detalle = {categoria: [0] * len(detalle_grados) for categoria in detalle_categories}

    oficiales = {"GR", "MG", "BG", "CR", "TC", "MY", "CT", "TE"}
    suboficiales = {"ST", "SMC", "SM", "SP", "SV", "SS", "CP", "CS", "C3"}

    for row in personal_rows:
        grado = (row[0] or "").strip().upper()
        sexo = (row[1] or "").strip().upper()
        tipo = (row[2] or "").strip().upper()
        estado = (row[3] or "").strip().upper()
        actividad = (row[4] or "").strip().upper()
        ubicacion = (row[5] or "").strip().upper()

        resumen_idx = None
        if grado in oficiales:
            resumen_idx = 0
        elif grado in suboficiales:
            resumen_idx = 1
        elif grado == "SLP":
            resumen_idx = 2
        elif grado == "SL18":
            resumen_idx = 3
        elif grado == "SL12":
            resumen_idx = 4

        sexo_idx = 5 if sexo.startswith("MASC") or sexo in {"M", "H", "HOMBRE"} else 6
        detalle_idx = detalle_map.get(grado)

        if resumen_idx is not None:
            resumen["EFECTIVOS"][resumen_idx] += 1
        resumen["EFECTIVOS"][sexo_idx] += 1
        if detalle_idx is not None:
            detalle["EFECTIVOS"][detalle_idx] += 1

        if sexo.startswith("MASC") or sexo in {"M", "H", "HOMBRE"}:
            if resumen_idx is not None:
                resumen["HOMBRES"][resumen_idx] += 1
            resumen["HOMBRES"][sexo_idx] += 1
            if detalle_idx is not None:
                detalle["HOMBRES"][detalle_idx] += 1
        else:
            if resumen_idx is not None:
                resumen["MUJERES"][resumen_idx] += 1
            resumen["MUJERES"][sexo_idx] += 1
            if detalle_idx is not None:
                detalle["MUJERES"][detalle_idx] += 1

        if ubicacion.startswith("AREA DE OPERACIONES") or ubicacion.startswith("ARÉA DE OPERACIONES"):
            target = "ARÉA DE OPERACIONES"
        elif ubicacion.startswith("PDMAT"):
            target = "PDMAT"
        elif ubicacion.startswith("PMAD"):
            target = "PMAD"
        else:
            target = None
        if target:
            if resumen_idx is not None:
                resumen[target][resumen_idx] += 1
            resumen[target][sexo_idx] += 1
            if detalle_idx is not None:
                detalle[target][detalle_idx] += 1

        if actividad.startswith("OPERACIONES"):
            target = "OPERACIONES"
        elif actividad.startswith("DESCANSO"):
            target = "DESCANSO"
        elif actividad.startswith("ENTRENAMIENTO"):
            target = "ENTRENAMIENTO"
        else:
            target = None
        if target:
            if resumen_idx is not None:
                resumen[target][resumen_idx] += 1
            resumen[target][sexo_idx] += 1
            if detalle_idx is not None:
                detalle[target][detalle_idx] += 1

        target = "NOVEDADES" if "NOVED" in estado else "DISPONIBLES"
        if resumen_idx is not None:
            resumen[target][resumen_idx] += 1
        resumen[target][sexo_idx] += 1
        if detalle_idx is not None:
            detalle[target][detalle_idx] += 1

        if "SEGREGADO" in tipo:
            target = "SEGREGACIONES"
        elif "ORGÁNICA" in tipo or "ORGANICA" in tipo:
            target = "ORGÁNICA"
        else:
            target = "AGREGADOS"
        if resumen_idx is not None:
            resumen[target][resumen_idx] += 1
        resumen[target][sexo_idx] += 1
        if detalle_idx is not None:
            detalle[target][detalle_idx] += 1

    if toe_row is not None:
        fila_toe_resumen = [
            "TOE",
            _safe_count(toe_row[12]),
            _safe_count(toe_row[21]),
            _safe_count(toe_row[24]),
            _safe_count(toe_row[27]),
            _safe_count(toe_row[28]),
            0,
            0,
        ]
        fila_toe_resumen.append(sum(fila_toe_resumen[1:6]))

        campos_toe = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 24, 27, 28]
        fila_toe_detalle = ["TOE"] + [_safe_count(toe_row[idx]) for idx in campos_toe]
        fila_toe_detalle.append(sum(fila_toe_detalle[1:]))
    else:
        fila_toe_resumen = ["TOE", 0, 0, 0, 0, 0, 0, 0, 0]
        fila_toe_detalle = ["TOE"] + ([0] * len(detalle_grados)) + [0]

    tabla1 = [fila_toe_resumen]
    for categoria in resumen_categories:
        fila = [categoria] + resumen[categoria]
        fila.append(sum(fila[1:6]))
        tabla1.append(fila)

    tabla2 = [fila_toe_detalle]
    for categoria in detalle_categories:
        fila = [categoria] + detalle[categoria]
        fila.append(sum(fila[1:]))
        tabla2.append(fila)

    return tabla1, tabla2


def _resolve_toe_row(cur, batallon=None, brigada=None, division=None, unidad_usuario=None):
    candidatos = []
    for valor in (batallon, brigada, division, unidad_usuario):
        if valor is None:
            continue
        valor_limpio = str(valor).strip()
        if not valor_limpio:
            continue
        if valor_limpio.lower() in {"none", "null", "undefined", "nan", "todos", "todas", "todo", "all", "*"}:
            continue
        if valor_limpio not in candidatos:
            candidatos.append(valor_limpio)

    for candidato in candidatos:
        cur.execute(
            """
            SELECT *
            FROM TOE_BATALLON
            WHERE TRIM(COALESCE(sigla, '')) ILIKE %s
            ORDER BY sigla
            LIMIT 1
            """,
            (f"{candidato}%",),
        )
        row = cur.fetchone()
        if row:
            return row

    return None


# =========================================================
# HEALTH
# =========================================================

@router.get("/")
def home():
    return {"status": "ok"}


# =========================================================
# GUARDAR EXCEL
# =========================================================

@router.post("/api/excel/guardar")
async def guardar_excel(
    payload: dict = Depends(verificar_token),
    archivo: UploadFile = File(...),
    fecha_informacion: str = Form(...)
):
    print("Archivo recibido:", archivo.filename)
    print("Fecha información:", fecha_informacion)
    if not archivo.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Archivo no válido")

    try:
        try:
            fecha_informacion_date = datetime.strptime(fecha_informacion, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="fecha_informacion debe tener formato YYYY-MM-DD"
            )

        usuario = payload.get("sub") or payload.get("usuario")
        user_id = payload.get("user_id")

        if not usuario and not user_id:
            raise HTTPException(status_code=401, detail="Token sin usuario válido")

        nivel_unidad = payload.get("nivel_unidad")
        unidad_usuario = payload.get("unidad_usuario")

        if not nivel_unidad or not unidad_usuario:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if user_id:
                        cur.execute("""
                        SELECT usuario, nivel_unidad, unidad_usuario
                        FROM usuarios
                        WHERE id = %s
                        """, (user_id,))
                    else:
                        cur.execute("""
                        SELECT usuario, nivel_unidad, unidad_usuario
                        FROM usuarios
                        WHERE usuario = %s
                        """, (usuario,))

                    user_row = cur.fetchone()

            if not user_row:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")

            usuario = user_row[0]
            nivel_unidad = user_row[1]
            unidad_usuario = user_row[2]

        contenido = await archivo.read()

        # 📊 Leer Excel
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Data Validation extension is not supported and will be removed",
                category=UserWarning,
            )
            df = pd.read_excel(BytesIO(contenido), header=0)

        # 🔥 Convertir NaN → None
        df = df.where(pd.notnull(df), None)

        registros = []
        omitidos_sin_cc = 0

        for _, row in df.iterrows():

            cc_valor = safe_int(safe_iloc(row, 2))
            if cc_valor is None:
                omitidos_sin_cc += 1
                continue

            registros.append((
                safe_str(safe_iloc(row, 0)),
                safe_str(safe_iloc(row, 1)),
                cc_valor,

                safe_str(safe_iloc(row, 3)),
                safe_str(safe_iloc(row, 4)),
                safe_str(safe_iloc(row, 5)),
                safe_str(safe_iloc(row, 6)),
                safe_int(safe_iloc(row, 7)),

                safe_str(safe_iloc(row, 8)),

                safe_str(safe_iloc(row, 9)),
                safe_str(safe_iloc(row, 10)),

                safe_str(safe_iloc(row, 11)),
                safe_str(safe_iloc(row, 12)),

                safe_str(safe_iloc(row, 13)),
                safe_int(safe_iloc(row, 14)),
                safe_str(safe_iloc(row, 15)),

                safe_str(safe_iloc(row, 16)),
                safe_int(safe_iloc(row, 17)),
                safe_str(safe_iloc(row, 18)),

                None,
                None,

                safe_int(safe_iloc(row, 21)),
                safe_str(safe_iloc(row, 22)),
                safe_str(safe_iloc(row, 23)),

                safe_str(safe_iloc(row, 24)),
                safe_str(safe_iloc(row, 25)),

                safe_str(safe_iloc(row, 26)),

                safe_str(safe_iloc(row, 27)),
                safe_float(safe_iloc(row, 28)),

                fecha_informacion_date,

                usuario,
                nivel_unidad,
                unidad_usuario
            ))

        if not registros:
            raise HTTPException(
                status_code=400,
                detail="No se encontraron registros validos con cédula (cc) en el archivo"
            )

        with get_conn() as conn:
            with conn.cursor() as cur:
                # 🔥 HISTORICO DIARIO (no elimina informacion)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS personal_novedades_historial (
                    id SERIAL PRIMARY KEY,
                    grado VARCHAR(10),
                    apellidos_nombres TEXT,
                    cc BIGINT,
                    division VARCHAR(10),
                    brigada VARCHAR(10),
                    batallon VARCHAR(50),
                    compania VARCHAR(20),
                    peloton INTEGER,
                    relacion_mando VARCHAR(50),
                    ciclo VARCHAR(50),
                    actividad VARCHAR(100),
                    ubicacion TEXT,
                    cargo_especialidad TEXT,
                    sexo VARCHAR(20),
                    telefono BIGINT,
                    rh VARCHAR(5),
                    contacto_emergencia TEXT,
                    telefono_emergencia BIGINT,
                    parentesco VARCHAR(50),
                    fecha_inicio_novedad DATE,
                    fecha_termino_novedad DATE,
                    hijos INTEGER,
                    estado_civil VARCHAR(50),
                    escolaridad VARCHAR(100),
                    correo_personal TEXT,
                    correo_institucional TEXT,
                    cursos_combte TEXT,
                    actitud_psicofisica VARCHAR(50),
                    porcentaje_discapacidad NUMERIC(5,2),
                    fecha_informacion DATE,
                    usuario_ingreso TEXT,
                    nivel_unidad TEXT,
                    unidad_usuario TEXT,
                    fecha_carga TIMESTAMP DEFAULT NOW()
                )
                """)

                cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_personal_hist_cc_fecha
                ON personal_novedades_historial (cc, fecha_informacion)
                """)

                cur.executemany("""
                INSERT INTO personal_novedades_historial (
                    grado,
                    apellidos_nombres,
                    cc,
                    division,
                    brigada,
                    batallon,
                    compania,
                    peloton,
                    relacion_mando,
                    ciclo,
                    actividad,
                    ubicacion,
                    cargo_especialidad,
                    sexo,
                    telefono,
                    rh,
                    contacto_emergencia,
                    telefono_emergencia,
                    parentesco,
                    fecha_inicio_novedad,
                    fecha_termino_novedad,
                    hijos,
                    estado_civil,
                    escolaridad,
                    correo_personal,
                    correo_institucional,
                    cursos_combte,
                    actitud_psicofisica,
                    porcentaje_discapacidad,
                    fecha_informacion,
                    usuario_ingreso,
                    nivel_unidad,
                    unidad_usuario
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s
                )
                ON CONFLICT (cc, fecha_informacion)
                DO UPDATE SET
                    grado = EXCLUDED.grado,
                    apellidos_nombres = EXCLUDED.apellidos_nombres,
                    division = EXCLUDED.division,
                    brigada = EXCLUDED.brigada,
                    batallon = EXCLUDED.batallon,
                    compania = EXCLUDED.compania,
                    peloton = EXCLUDED.peloton,
                    relacion_mando = EXCLUDED.relacion_mando,
                    ciclo = EXCLUDED.ciclo,
                    actividad = EXCLUDED.actividad,
                    ubicacion = EXCLUDED.ubicacion,
                    cargo_especialidad = EXCLUDED.cargo_especialidad,
                    sexo = EXCLUDED.sexo,
                    telefono = EXCLUDED.telefono,
                    rh = EXCLUDED.rh,
                    contacto_emergencia = EXCLUDED.contacto_emergencia,
                    telefono_emergencia = EXCLUDED.telefono_emergencia,
                    parentesco = EXCLUDED.parentesco,
                    fecha_inicio_novedad = EXCLUDED.fecha_inicio_novedad,
                    fecha_termino_novedad = EXCLUDED.fecha_termino_novedad,
                    hijos = EXCLUDED.hijos,
                    estado_civil = EXCLUDED.estado_civil,
                    escolaridad = EXCLUDED.escolaridad,
                    correo_personal = EXCLUDED.correo_personal,
                    correo_institucional = EXCLUDED.correo_institucional,
                    cursos_combte = EXCLUDED.cursos_combte,
                    actitud_psicofisica = EXCLUDED.actitud_psicofisica,
                    porcentaje_discapacidad = EXCLUDED.porcentaje_discapacidad,
                    usuario_ingreso = EXCLUDED.usuario_ingreso,
                    nivel_unidad = EXCLUDED.nivel_unidad,
                    unidad_usuario = EXCLUDED.unidad_usuario,
                    fecha_carga = NOW()
                """, registros)

                # 🔥 UPSERT POR cc PARA CARGA DIARIA
                cur.executemany("""
                INSERT INTO personal_novedades (
                    grado,
                    apellidos_nombres,
                    cc,
                    division,
                    brigada,
                    batallon,
                    compania,
                    peloton,
                    relacion_mando,
                    ciclo,
                    actividad,
                    ubicacion,
                    cargo_especialidad,
                    sexo,
                    telefono,
                    rh,
                    contacto_emergencia,
                    telefono_emergencia,
                    parentesco,
                    fecha_inicio_novedad,
                    fecha_termino_novedad,
                    hijos,
                    estado_civil,
                    escolaridad,
                    correo_personal,
                    correo_institucional,
                    cursos_combte,
                    actitud_psicofisica,
                    porcentaje_discapacidad,
                    fecha_informacion,
                    usuario_ingreso,
                    nivel_unidad,
                    unidad_usuario
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s
                )
                ON CONFLICT (cc)
                DO UPDATE SET
                    grado = EXCLUDED.grado,
                    apellidos_nombres = EXCLUDED.apellidos_nombres,
                    division = EXCLUDED.division,
                    brigada = EXCLUDED.brigada,
                    batallon = EXCLUDED.batallon,
                    compania = EXCLUDED.compania,
                    peloton = EXCLUDED.peloton,
                    relacion_mando = EXCLUDED.relacion_mando,
                    ciclo = EXCLUDED.ciclo,
                    actividad = EXCLUDED.actividad,
                    ubicacion = EXCLUDED.ubicacion,
                    cargo_especialidad = EXCLUDED.cargo_especialidad,
                    sexo = EXCLUDED.sexo,
                    telefono = EXCLUDED.telefono,
                    rh = EXCLUDED.rh,
                    contacto_emergencia = EXCLUDED.contacto_emergencia,
                    telefono_emergencia = EXCLUDED.telefono_emergencia,
                    parentesco = EXCLUDED.parentesco,
                    fecha_inicio_novedad = EXCLUDED.fecha_inicio_novedad,
                    fecha_termino_novedad = EXCLUDED.fecha_termino_novedad,
                    hijos = EXCLUDED.hijos,
                    estado_civil = EXCLUDED.estado_civil,
                    escolaridad = EXCLUDED.escolaridad,
                    correo_personal = EXCLUDED.correo_personal,
                    correo_institucional = EXCLUDED.correo_institucional,
                    cursos_combte = EXCLUDED.cursos_combte,
                    actitud_psicofisica = EXCLUDED.actitud_psicofisica,
                    porcentaje_discapacidad = EXCLUDED.porcentaje_discapacidad,
                    fecha_informacion = EXCLUDED.fecha_informacion,
                    usuario_ingreso = EXCLUDED.usuario_ingreso,
                    nivel_unidad = EXCLUDED.nivel_unidad,
                    unidad_usuario = EXCLUDED.unidad_usuario
                """, registros)

            conn.commit()

        return {
            "mensaje": "Datos cargados correctamente (actual + historico diario)",
            "total": len(registros),
            "omitidos_sin_cc": omitidos_sin_cc,
            "fecha_informacion": str(fecha_informacion_date),
            "usuario": usuario,
            "nivel_unidad": nivel_unidad,
            "unidad_usuario": unidad_usuario
        }

    except Exception as e:
        print(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/api/personal/cargas")
async def obtener_cargas(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                        SELECT
                            usuario_ingreso,
                            nivel_unidad,
                            unidad_usuario,
                            fecha_informacion,
                            COUNT(*) as total_registros
                        FROM personal_novedades_historial
                        GROUP BY
                            usuario_ingreso,
                            nivel_unidad,
                            unidad_usuario,
                            fecha_informacion
                        ORDER BY fecha_informacion DESC
                        """)

            rows = cur.fetchall()

    return [
        {
            "usuario_ingreso": r[0],
            "nivel_unidad": r[1],
            "unidad_usuario": r[2],
            "fecha_informacion": str(r[3]),
            "total_registros": r[4]
        }
        for r in rows
    ]


@router.get("/api/personal/estadisticas")
async def matriz_personal(
    request: Request,
    filtroFecha: Optional[str] = None,
    fecha: Optional[str] = None,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
    peloton: Optional[int] = None,
    relacion_mando: Optional[str] = None,
    ciclo: Optional[str] = None,
    actividad: Optional[str] = None,
    ubicacion: Optional[str] = None,
    payload: dict = Depends(verificar_token)
    ):

    qp = request.query_params

    fecha_param = _coalesce_query_text(
        filtroFecha,
        fecha,
        qp.get("filtroFecha"),
        qp.get("fecha"),
        qp.get("fechaInformacion"),
        qp.get("fecha_informacion"),
    )

    division = _coalesce_query_text(division, qp.get("filtroDivision"), qp.get("divisionFiltro"))
    brigada = _coalesce_query_text(brigada, qp.get("filtroBrigada"), qp.get("brigadaFiltro"))
    batallon = _coalesce_query_text(batallon, qp.get("filtroBatallon"), qp.get("batallonFiltro"))
    compania = _coalesce_query_text(compania, qp.get("filtroCompania"), qp.get("companiaFiltro"))
    relacion_mando = _coalesce_query_text(
        relacion_mando,
        qp.get("relacionMando"),
        qp.get("filtroRelacionMando"),
    )
    ciclo = _coalesce_query_text(ciclo, qp.get("filtroCiclo"), qp.get("cicloFiltro"))
    actividad = _coalesce_query_text(actividad, qp.get("filtroActividad"), qp.get("actividadFiltro"))
    ubicacion = _coalesce_query_text(ubicacion, qp.get("filtroUbicacion"), qp.get("ubicacionFiltro"))

    peloton_raw = _coalesce_query_text(
        peloton,
        qp.get("filtroPeloton"),
        qp.get("pelotonFiltro"),
    )
    if peloton_raw is None:
        peloton = None
    else:
        try:
            peloton = int(str(peloton_raw))
        except ValueError:
            raise HTTPException(status_code=400, detail="peloton debe ser un numero entero")

    if not fecha_param:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar filtroFecha o fecha en formato YYYY-MM-DD"
        )

    try:
        fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato YYYY-MM-DD"
        )

    where_sql, parametros = _build_personal_filters(
        fecha_filtro=fecha_filtro,
        division=division,
        brigada=brigada,
        batallon=batallon,
        compania=compania,
        peloton=peloton,
        relacion_mando=relacion_mando,
        ciclo=ciclo,
        actividad=actividad,
        ubicacion=ubicacion,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:

            # 🔥 TODOS LOS GRADOS EXISTENTES
            cur.execute("""
            SELECT DISTINCT grado
            FROM personal_novedades_historial
            WHERE {where_sql}
            ORDER BY grado
            """.format(where_sql=where_sql), parametros)
            grados = [r[0] for r in cur.fetchall()]

            # =========================================================
            # 🧠 FUNCIÓN PARA ARMAR MATRIZ
            # =========================================================
            def construir_categoria(nombre, campo):

                cur.execute(f"""
                SELECT grado, {campo}, COUNT(*)
                FROM personal_novedades_historial
                WHERE {where_sql}
                GROUP BY grado, {campo}
                """, parametros)

                rows = cur.fetchall()

                resultado = {}

                for grado, categoria, total in rows:
                    if categoria is None:
                        continue

                    if categoria not in resultado:
                        resultado[categoria] = {g: 0 for g in grados}

                    resultado[categoria][grado] = total

                # 🔥 convertir a filas tipo tabla
                filas = []
                for cat, valores in resultado.items():
                    fila = {"categoria": f"{nombre} - {cat}"}
                    fila.update(valores)
                    filas.append(fila)

                return filas

            # =========================================================
            # 🔥 ARMAR TODO
            # =========================================================

            data = []

            data += construir_categoria("SEXO", "sexo")
            data += construir_categoria("RELACION", "relacion_mando")
            data += construir_categoria("CICLO", "ciclo")
            data += construir_categoria("ACTIVIDAD", "actividad")
            data += construir_categoria("UBICACION", "ubicacion")
            data += construir_categoria("CARGO", "cargo_especialidad")
            data += construir_categoria("COMPANIA", "compania")

    filtros_aplicados = {
        "fecha_informacion": str(fecha_filtro),
        "division": (division or "").strip() or None,
        "brigada": (brigada or "").strip() or None,
        "batallon": (batallon or "").strip() or None,
        "compania": (compania or "").strip() or None,
        "peloton": peloton,
        "relacion_mando": (relacion_mando or "").strip() or None,
        "ciclo": (ciclo or "").strip() or None,
        "actividad": (actividad or "").strip() or None,
        "ubicacion": (ubicacion or "").strip() or None,
    }

    filtros_aplicados = {k: v for k, v in filtros_aplicados.items() if v is not None}

    return {
        "grados": grados,
        "data": data,
        "filtros_aplicados": filtros_aplicados
    }


@router.get("/api/personal/listado")
async def matriz_personal(
    filtroFecha: Optional[str] = None,
    fecha: Optional[str] = None,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
    peloton: Optional[int] = None,
    relacion_mando: Optional[str] = None,
    ciclo: Optional[str] = None,
    actividad: Optional[str] = None,
    ubicacion: Optional[str] = None,
    payload: dict = Depends(verificar_token)
    ):

    fecha_param = filtroFecha or fecha
    if not fecha_param:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar filtroFecha o fecha en formato YYYY-MM-DD"
        )

    try:
        fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato YYYY-MM-DD"
        )

    with get_conn() as conn:
        with conn.cursor() as cur:
            where_sql, parametros = _build_personal_filters(
                fecha_filtro=fecha_filtro,
                division=division,
                brigada=brigada,
                batallon=batallon,
                compania=compania,
                peloton=peloton,
                relacion_mando=relacion_mando,
                ciclo=ciclo,
                actividad=actividad,
                ubicacion=ubicacion,
            )

            cur.execute(f"""
            SELECT
                grado,
                apellidos_nombres,
                cc,
                division,
                brigada,
                batallon,
                compania,
                peloton,
                relacion_mando,
                ciclo,
                actividad,
                ubicacion,
                cargo_especialidad,
                sexo,
                contacto_emergencia,
                telefono,
                rh
            FROM personal_novedades_historial
            WHERE {where_sql}
            ORDER BY grado, apellidos_nombres
            """, parametros)

            informacion = cur.fetchall()

    if not informacion:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron registros para los filtros enviados"
        )

    ruta_archivo, nombre_archivo = crear_word_informe_listado(None, informacion)

    return FileResponse(
        path=ruta_archivo,
        filename=nombre_archivo,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@router.get("/api/personal/listado-json")
async def listado_json(
    filtroFecha: Optional[str] = None,
    fecha: Optional[str] = None,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
    peloton: Optional[int] = None,
    relacion_mando: Optional[str] = None,
    ciclo: Optional[str] = None,
    actividad: Optional[str] = None,
    ubicacion: Optional[str] = None,
    payload: dict = Depends(verificar_token)
):

    fecha_param = filtroFecha or fecha
    if not fecha_param:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar filtroFecha o fecha en formato YYYY-MM-DD"
        )

    try:
        fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato YYYY-MM-DD"
        )

    with get_conn() as conn:
        with conn.cursor() as cur:
            where_sql, parametros = _build_personal_filters(
                fecha_filtro=fecha_filtro,
                division=division,
                brigada=brigada,
                batallon=batallon,
                compania=compania,
                peloton=peloton,
                relacion_mando=relacion_mando,
                ciclo=ciclo,
                actividad=actividad,
                ubicacion=ubicacion,
            )

            cur.execute(f"""
            SELECT
                grado,
                apellidos_nombres,
                cc,
                division,
                brigada,
                batallon,
                compania,
                peloton,
                relacion_mando,
                ciclo,
                actividad,
                ubicacion,
                cargo_especialidad,
                sexo,
                contacto_emergencia,
                telefono,
                rh,
                fecha_informacion
            FROM personal_novedades_historial
            WHERE {where_sql}
            ORDER BY grado, apellidos_nombres
            """, parametros)

            rows = cur.fetchall()

    data = [
        {
            "grado": r[0],
            "apellidos_nombres": r[1],
            "cc": r[2],
            "division": r[3],
            "brigada": r[4],
            "batallon": r[5],
            "compania": r[6],
            "peloton": r[7],
            "relacion_mando": r[8],
            "ciclo": r[9],
            "actividad": r[10],
            "ubicacion": r[11],
            "cargo_especialidad": r[12],
            "sexo": r[13],
            "contacto_emergencia": r[14],
            "telefono": r[15],
            "rh": r[16],
            "fecha_informacion": str(r[17]) if r[17] is not None else None,
        }
        for r in rows
    ]

    filtros_aplicados = {
        "fecha_informacion": str(fecha_filtro),
        "division": (division or "").strip() or None,
        "brigada": (brigada or "").strip() or None,
        "batallon": (batallon or "").strip() or None,
        "compania": (compania or "").strip() or None,
        "peloton": peloton,
        "relacion_mando": (relacion_mando or "").strip() or None,
        "ciclo": (ciclo or "").strip() or None,
        "actividad": (actividad or "").strip() or None,
        "ubicacion": (ubicacion or "").strip() or None,
    }
    filtros_aplicados = {k: v for k, v in filtros_aplicados.items() if v is not None}

    return {
        "total": len(data),
        "filtros_aplicados": filtros_aplicados,
        "data": data,
    }


@router.get("/api/personal/parte-diario-pdf")
async def parte_diario_pdf(
    request: Request,
    filtroFecha: Optional[str] = None,
    fecha: Optional[str] = None,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
    peloton: Optional[int] = None,
    relacion_mando: Optional[str] = None,
    ciclo: Optional[str] = None,
    actividad: Optional[str] = None,
    ubicacion: Optional[str] = None,
    payload: dict = Depends(verificar_token)
):

    qp = request.query_params

    fecha_param = _coalesce_query_text(
        filtroFecha,
        fecha,
        qp.get("filtroFecha"),
        qp.get("fecha"),
        qp.get("fechaInformacion"),
        qp.get("fecha_informacion"),
    )

    division = _coalesce_query_text(division, qp.get("filtroDivision"), qp.get("divisionFiltro"))
    brigada = _coalesce_query_text(brigada, qp.get("filtroBrigada"), qp.get("brigadaFiltro"))
    batallon = _coalesce_query_text(batallon, qp.get("filtroBatallon"), qp.get("batallonFiltro"))
    compania = _coalesce_query_text(compania, qp.get("filtroCompania"), qp.get("companiaFiltro"))
    relacion_mando = _coalesce_query_text(
        relacion_mando,
        qp.get("relacionMando"),
        qp.get("filtroRelacionMando"),
    )
    ciclo = _coalesce_query_text(ciclo, qp.get("filtroCiclo"), qp.get("cicloFiltro"))
    actividad = _coalesce_query_text(actividad, qp.get("filtroActividad"), qp.get("actividadFiltro"))
    ubicacion = _coalesce_query_text(ubicacion, qp.get("filtroUbicacion"), qp.get("ubicacionFiltro"))

    peloton_raw = _coalesce_query_text(
        peloton,
        qp.get("filtroPeloton"),
        qp.get("pelotonFiltro"),
    )
    if peloton_raw is None:
        peloton = None
    else:
        try:
            peloton = int(str(peloton_raw))
        except ValueError:
            raise HTTPException(status_code=400, detail="peloton debe ser un numero entero")

    if not fecha_param:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar filtroFecha o fecha en formato YYYY-MM-DD"
        )

    try:
        fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato YYYY-MM-DD"
        )

    where_sql, parametros = _build_personal_filters(
        fecha_filtro=fecha_filtro,
        division=division,
        brigada=brigada,
        batallon=batallon,
        compania=compania,
        peloton=peloton,
        relacion_mando=relacion_mando,
        ciclo=ciclo,
        actividad=actividad,
        ubicacion=ubicacion,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
            SELECT
                UPPER(COALESCE(NULLIF(TRIM(grado), ''), '')) AS grado,
                UPPER(COALESCE(NULLIF(TRIM(sexo), ''), '')) AS sexo,
                UPPER(COALESCE(NULLIF(TRIM(relacion_mando), ''), '')) AS relacion_mando,
                UPPER(COALESCE(NULLIF(TRIM(ciclo), ''), '')) AS ciclo,
                UPPER(COALESCE(NULLIF(TRIM(actividad), ''), '')) AS actividad,
                UPPER(COALESCE(NULLIF(TRIM(ubicacion), ''), '')) AS ubicacion
            FROM personal_novedades_historial
            WHERE {where_sql}
            ORDER BY apellidos_nombres
            """, parametros)
            personal_rows = cur.fetchall()

            toe_row = _resolve_toe_row(
                cur,
                batallon=batallon,
                brigada=brigada,
                division=division,
                unidad_usuario=payload.get("unidad_usuario"),
            )

    if not personal_rows:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron registros para los filtros enviados"
        )

    tabla1, tabla2 = _build_parte_diario_tables(personal_rows, toe_row)

    output_dir = os.path.join("uploads", "pdfs")
    os.makedirs(output_dir, exist_ok=True)
    nombre_archivo = os.path.join(
        output_dir,
        f"parte_diario_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    ruta_pdf = generar_parte_diario_pdf(
        tabla2=tabla2,
        tabla1=tabla1,
        fila_para_qr=None,
        nombre_archivo=nombre_archivo,
        abrir=False,
    )

    return FileResponse(
        path=ruta_pdf,
        filename=os.path.basename(ruta_pdf),
        media_type="application/pdf"
    )


@router.get("/api/personal/listado-pdf")
async def listado_pdf(
    cc: int,
    filtroFecha: Optional[str] = None,
    fecha: Optional[str] = None,
    informacion: str = "LISTADO DE PERSONAL",
    payload: dict = Depends(verificar_token)
):
    print("CC solicitado:", cc)
    fecha_filtro = None
    fecha_param = filtroFecha or fecha
    if fecha_param:
        try:
            fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="La fecha debe tener formato YYYY-MM-DD"
            )

    with get_conn() as conn:
        with conn.cursor() as cur:
            if fecha_filtro is not None:
                where_sql = "cc = %s AND fecha_informacion = %s"
                parametros = (cc, fecha_filtro)
            else:
                where_sql = "cc = %s"
                parametros = (cc,)

            cur.execute(f"""
            SELECT
                grado,
                apellidos_nombres,
                cc,
                division,
                brigada,
                batallon,
                compania,
                peloton,
                relacion_mando,
                ciclo,
                actividad,
                ubicacion,
                cargo_especialidad,
                telefono,
                rh,
                contacto_emergencia,
                telefono_emergencia,
                parentesco
            FROM personal_novedades_historial
            WHERE {where_sql}
            ORDER BY fecha_informacion DESC, id DESC
            LIMIT 1
            """, parametros)

            row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="No se encontro informacion para la cedula enviada"
        )

    grado_persona = row[0] or ""
    nombre_completo = row[1] or "SIN NOMBRE"
    partes_nombre = str(nombre_completo).split()
    nombre_1 = partes_nombre[0] if partes_nombre else "SIN"
    nombre_2 = " ".join(partes_nombre[1:]) if len(partes_nombre) > 1 else "NOMBRE"

    titulo_pdf = f"{grado_persona} {nombre_completo}".strip()
    if not titulo_pdf:
        titulo_pdf = "SIN INFORMACION"

    # Si no llega un titulo personalizado, usar grado + apellidos_nombres.
    info_limpia = (informacion or "").strip()
    if not info_limpia or info_limpia.upper() == "LISTADO DE PERSONAL":
        informacion = titulo_pdf

    datos_pdf = (
        nombre_1,
        nombre_2,
        row[2],
        row[3],
        row[4],
        row[5],
        row[6],
        row[7],
        row[8],
        row[9],
        row[10],
        row[11],
        row[12],
        None,
        None,
        row[13],
        row[14],
        row[15],
        row[16],
        row[17],
        grado_persona,
    )

    ruta_pdf = informacion_basica(None, datos_pdf, informacion, abrir=False)

    nombre_archivo = os.path.basename(ruta_pdf)
    return FileResponse(
        path=ruta_pdf,
        filename=nombre_archivo,
        media_type="application/pdf"
    )


@router.get("/api/personal/listado-emergencia")
async def listado_emergencia(
    filtroFecha: Optional[str] = None,
    fecha: Optional[str] = None,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
    peloton: Optional[int] = None,
    relacion_mando: Optional[str] = None,
    ciclo: Optional[str] = None,
    actividad: Optional[str] = None,
    ubicacion: Optional[str] = None,
    payload: dict = Depends(verificar_token)
):

    fecha_param = filtroFecha or fecha
    if not fecha_param:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar filtroFecha o fecha en formato YYYY-MM-DD"
        )

    try:
        fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato YYYY-MM-DD"
        )

    with get_conn() as conn:
        with conn.cursor() as cur:
            where_sql, parametros = _build_personal_filters(
                fecha_filtro=fecha_filtro,
                division=division,
                brigada=brigada,
                batallon=batallon,
                compania=compania,
                peloton=peloton,
                relacion_mando=relacion_mando,
                ciclo=ciclo,
                actividad=actividad,
                ubicacion=ubicacion,
            )

            # Mantiene el orden de columnas esperado por crear_word_informe_listado_emergencia.
            cur.execute(f"""
            SELECT
                grado,
                apellidos_nombres,
                cc,
                division,
                brigada,
                batallon,
                compania,
                peloton,
                relacion_mando,
                ciclo,
                actividad,
                ubicacion,
                cargo_especialidad,
                sexo,
                telefono,
                rh,
                NULL::TEXT AS reservado,
                contacto_emergencia,
                telefono_emergencia,
                parentesco
            FROM personal_novedades_historial
            WHERE {where_sql}
            ORDER BY grado, apellidos_nombres
            """, parametros)

            informacion = cur.fetchall()

    if not informacion:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron registros para los filtros enviados"
        )

    ruta_archivo, nombre_archivo = crear_word_informe_listado_emergencia(None, informacion)

    return FileResponse(
        path=ruta_archivo,
        filename=nombre_archivo,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


# =========================================================
# REGISTRAR ROUTER
# =========================================================

app.include_router(router)


# =========================================================
# CERRAR POOL
# =========================================================

@app.on_event("shutdown")
def shutdown():
    pool.close()