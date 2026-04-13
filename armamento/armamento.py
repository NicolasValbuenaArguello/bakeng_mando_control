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
# STARTUP: garantiza que la tabla historial exista
# =========================================================

@app.on_event("startup")
def crear_tablas_historial():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS armamento_general_historial (
                id                SERIAL PRIMARY KEY,
                tipo_armamento    VARCHAR(50),
                numero_serie      VARCHAR(100) NOT NULL,
                tipo_arma         VARCHAR(50),
                calibre           VARCHAR(20),
                estado            VARCHAR(20),
                cant_provedores   INTEGER,
                cantidad_municion INTEGER,
                division          VARCHAR(50),
                brigada           VARCHAR(50),
                batallon          VARCHAR(50),
                compania          VARCHAR(50),
                fecha_informacion DATE NOT NULL,
                usuario_ingreso   TEXT,
                nivel_unidad      TEXT,
                unidad_usuario    TEXT,
                fecha_carga       TIMESTAMP DEFAULT NOW()
            )
            """)
            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_armamento_general_hist_serie_fecha
            ON armamento_general_historial (numero_serie, fecha_informacion)
            """)

            # Sincroniza el snapshot actual con el historial para no dejar vacios
            # los registros cargados antes de activar la tabla historica.
            cur.execute("""
            INSERT INTO armamento_general_historial (
                tipo_armamento,
                numero_serie,
                tipo_arma,
                calibre,
                estado,
                cant_provedores,
                cantidad_municion,
                division,
                brigada,
                batallon,
                compania,
                fecha_informacion,
                usuario_ingreso,
                nivel_unidad,
                unidad_usuario
            )
            SELECT
                tipo_armamento,
                numero_serie,
                tipo_arma,
                calibre,
                estado,
                cant_provedores,
                cantidad_municion,
                division,
                brigada,
                batallon,
                compania,
                fecha_informacion,
                usuario_ingreso,
                nivel_unidad,
                unidad_usuario
            FROM armamento_general
            WHERE fecha_informacion IS NOT NULL
            ON CONFLICT (numero_serie, fecha_informacion)
            DO UPDATE SET
                tipo_armamento = EXCLUDED.tipo_armamento,
                tipo_arma = EXCLUDED.tipo_arma,
                calibre = EXCLUDED.calibre,
                estado = EXCLUDED.estado,
                cant_provedores = EXCLUDED.cant_provedores,
                cantidad_municion = EXCLUDED.cantidad_municion,
                division = EXCLUDED.division,
                brigada = EXCLUDED.brigada,
                batallon = EXCLUDED.batallon,
                compania = EXCLUDED.compania,
                usuario_ingreso = EXCLUDED.usuario_ingreso,
                nivel_unidad = EXCLUDED.nivel_unidad,
                unidad_usuario = EXCLUDED.unidad_usuario,
                fecha_carga = NOW()
            """)
        conn.commit()
    print("✅ armamento_general_historial lista")


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

@router.post("/api/armamento/guardar")
async def guardar_excel(
    payload: dict = Depends(verificar_token),
    archivo: UploadFile = File(None),
    file: UploadFile = File(None),
    fecha_informacion: str = Form(None),
    fecha: str = Form(None),
    filtroFecha: str = Form(None)
):
    archivo_cargado = archivo or file
    fecha_raw = fecha_informacion or fecha or filtroFecha

    if archivo_cargado is None:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar un archivo en el campo 'archivo' o 'file'"
        )

    print("Archivo recibido:", archivo_cargado.filename)
    print("Fecha información:", fecha_raw)

    if not archivo_cargado.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Archivo no válido")

    try:
        try:
            if not fecha_raw:
                raise ValueError("fecha vacia")
            fecha_informacion_date = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Debe enviar fecha_informacion (o fecha/filtroFecha) con formato YYYY-MM-DD"
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

        contenido = await archivo_cargado.read()

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
        omitidos_sin_serie = 0

        for _, row in df.iterrows():

            numero_serie = safe_str(safe_iloc(row, 1))
            if not numero_serie:
                omitidos_sin_serie += 1
                continue

            registros.append((
                safe_str(safe_iloc(row, 0)),  # tipo_armamento
                numero_serie,
                safe_str(safe_iloc(row, 2)),  # tipo_arma
                safe_str(safe_iloc(row, 3)),  # calibre
                safe_str(safe_iloc(row, 4)),  # estado
                safe_int(safe_iloc(row, 5)),  # cant_provedores
                safe_int(safe_iloc(row, 6)),  # cantidad_municion
                safe_str(safe_iloc(row, 7)),  # division
                safe_str(safe_iloc(row, 8)),  # brigada
                safe_str(safe_iloc(row, 9)),  # batallon
                safe_str(safe_iloc(row, 10)), # compania
                fecha_informacion_date,
                usuario,
                nivel_unidad,
                unidad_usuario,
            ))

        if not registros:
            raise HTTPException(
                status_code=400,
                detail="No se encontraron registros validos con numero de serie en el archivo"
            )

        with get_conn() as conn:
            with conn.cursor() as cur:

                # ── 1. SNAPSHOT: último estado por numero_serie ──────────────
                cur.executemany("""
                INSERT INTO armamento_general (
                    tipo_armamento,
                    numero_serie,
                    tipo_arma,
                    calibre,
                    estado, cant_provedores, cantidad_municion,
                    division, brigada, batallon, compania,
                    fecha_informacion, usuario_ingreso, nivel_unidad, unidad_usuario
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                ) ON CONFLICT (numero_serie) DO UPDATE SET
                    tipo_armamento=EXCLUDED.tipo_armamento, tipo_arma=EXCLUDED.tipo_arma,
                    calibre=EXCLUDED.calibre, estado=EXCLUDED.estado,
                    cant_provedores=EXCLUDED.cant_provedores,
                    cantidad_municion=EXCLUDED.cantidad_municion,
                    division=EXCLUDED.division, brigada=EXCLUDED.brigada,
                    batallon=EXCLUDED.batallon, compania=EXCLUDED.compania,
                    fecha_informacion=EXCLUDED.fecha_informacion,
                    usuario_ingreso=EXCLUDED.usuario_ingreso,
                    nivel_unidad=EXCLUDED.nivel_unidad,
                    unidad_usuario=EXCLUDED.unidad_usuario
                """, registros)
            conn.commit()

        # ── 2. HISTÓRICO DIARIO: transacción independiente ───────────────────
        with get_conn() as conn2:
            with conn2.cursor() as cur2:
                cur2.executemany("""
                INSERT INTO armamento_general_historial (
                    tipo_armamento, numero_serie, tipo_arma, calibre, estado,
                    cant_provedores, cantidad_municion, division, brigada,
                    batallon, compania, fecha_informacion, usuario_ingreso,
                    nivel_unidad, unidad_usuario
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                ) ON CONFLICT (numero_serie, fecha_informacion) DO UPDATE SET
                    tipo_armamento=EXCLUDED.tipo_armamento, tipo_arma=EXCLUDED.tipo_arma,
                    calibre=EXCLUDED.calibre, estado=EXCLUDED.estado,
                    cant_provedores=EXCLUDED.cant_provedores,
                    cantidad_municion=EXCLUDED.cantidad_municion,
                    division=EXCLUDED.division, brigada=EXCLUDED.brigada,
                    batallon=EXCLUDED.batallon, compania=EXCLUDED.compania,
                    usuario_ingreso=EXCLUDED.usuario_ingreso,
                    nivel_unidad=EXCLUDED.nivel_unidad,
                    unidad_usuario=EXCLUDED.unidad_usuario,
                    fecha_carga=NOW()
                """, registros)
            conn2.commit()

        return {
            "mensaje": "Datos de armamento cargados correctamente",
            "total": len(registros),
            "omitidos_sin_serie": omitidos_sin_serie,
            "tabla_actual_actualizada": len(registros),
            "tabla_historial_actualizada": len(registros),
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


@router.get("/api/armamento/cargas")
async def obtener_cargas(payload: dict = Depends(verificar_token)):
    print("Obteniendo cargas de armamento...")
    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                        SELECT
                            usuario_ingreso,
                            nivel_unidad,
                            unidad_usuario,
                            fecha_informacion,
                            COUNT(DISTINCT numero_serie) as total_registros
                        FROM armamento_general_historial
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


@router.get("/api/personal/estadisticas_armamento")
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
    filtros = ["fecha_informacion = %s"]
    parametros = [fecha_filtro]

    _add_text_filter(filtros, parametros, "division", division)
    _add_text_filter(filtros, parametros, "brigada", brigada)
    _add_text_filter(filtros, parametros, "batallon", batallon)
    _add_text_filter(filtros, parametros, "compania", compania)

    where_sql = " AND ".join(filtros)
    parametros = tuple(parametros)

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute(f"""
            SELECT
                COUNT(*) AS total_registros,
                COALESCE(SUM(cantidad_municion), 0) AS total_municion,
                COALESCE(SUM(cant_provedores), 0) AS total_provedores
            FROM armamento_general_historial
            WHERE {where_sql}
            """, parametros)
            resumen_row = cur.fetchone()

            def construir_categoria(campo):
                cur.execute(f"""
                SELECT
                    COALESCE(NULLIF(TRIM({campo}), ''), 'SIN DATO') AS categoria,
                    COUNT(*) AS total
                FROM armamento_general_historial
                WHERE {where_sql}
                GROUP BY 1
                ORDER BY 2 DESC, 1
                """, parametros)
                rows = cur.fetchall()
                return [{"categoria": r[0], "total": r[1]} for r in rows]

            estadisticas = {
                "por_estado": construir_categoria("estado"),
                "por_tipo_armamento": construir_categoria("tipo_armamento"),
                "por_tipo_arma": construir_categoria("tipo_arma"),
                "por_calibre": construir_categoria("calibre"),
                "por_division": construir_categoria("division"),
                "por_brigada": construir_categoria("brigada"),
                "por_batallon": construir_categoria("batallon"),
                "por_compania": construir_categoria("compania"),
            }

    filtros_aplicados = {
        "fecha_informacion": str(fecha_filtro),
        "division": (division or "").strip() or None,
        "brigada": (brigada or "").strip() or None,
        "batallon": (batallon or "").strip() or None,
        "compania": (compania or "").strip() or None,
    }

    filtros_aplicados = {k: v for k, v in filtros_aplicados.items() if v is not None}

    return {
        "resumen": {
            "total_registros": resumen_row[0],
            "total_municion": resumen_row[1],
            "total_provedores": resumen_row[2],
        },
        "estadisticas": estadisticas,
        "filtros_aplicados": filtros_aplicados
    }


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