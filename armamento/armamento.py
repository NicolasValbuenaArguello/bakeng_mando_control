"""API de armamento: carga, consulta histórica y generación de reportes."""

# =========================================================
# MAPA RAPIDO DEL ARCHIVO
# =========================================================
# 1. Variables de entorno:
#    Lee credenciales y datos de conexion a PostgreSQL.
#
# 2. Conexion:
#    Crea el pool de conexiones para reutilizar acceso a base de datos.
#
# 3. Helpers heredados y de compatibilidad:
#    Mantienen funcionando partes viejas del codigo sin reescribir todo.
#
# 4. Normalizacion y utilidades:
#    Funciones `safe_*` y helpers de filtros para limpiar datos y parametros.
#
# 5. Startup:
#    Crea tablas e indices auxiliares si no existen.
#
# 6. Reportes:
#    Arma los datos de armamento y municion usados para PDF y consultas.
#
# 7. Endpoints principales:
#    `/api/armamento/guardar`
#    Carga el Excel principal de armamento.
#
#    `/api/armamento/asignado/guardar`
#    Carga el Excel de asignacion arma -> persona.
#
#    `/api/armamento/cargas`
#    Lista las cargas historicas realizadas.
#
#    `/api/personal/estadisticas_armamento`
#    Devuelve conteos y agrupaciones para tableros.
#
# 8. Cierre:
#    Cierra el pool cuando la API se apaga.

import os
import traceback
import warnings
from datetime import datetime
from io import BytesIO
from types import MethodType
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from psycopg_pool import ConnectionPool

from auth.dependencies import verificar_token
from temples.ayuda_pdf import generar_parte_diario_armamento_pdf
from temples.doc_parte_per import select_dinamico_bd_personal
from temples.listado import *

# Wrapper para compatibilidad con el código existente
def select_query_bd_personal(self, **kwargs):
    return select_dinamico_bd_personal(self, **kwargs)
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
    """Pide una conexion al pool de PostgreSQL.

    Dicho facil: esta funcion nos presta una conexion lista para usar.
    """
    return pool.connection()


def datos_municion(self):
       
        q = f"SELECT municiones, cantidad, tipo, compania FROM municiones"
        datos = b_d_i.select_dinamico(self, municiones=q)

        q = f"SELECT DISTINCT municiones FROM municiones"
        self.companias = b_d_i.select_dinamico(self, municiones=q)

        
        q = f"SELECT DISTINCT compania FROM municiones"
        self.unidad = b_d_i.select_dinamico(self, municiones=q)

        header_municiones = ["Municion", "Cantidad", "Sulta", "Eslavonada"]
        unidad = []

        for y in self.companias[0]:  

            # Desempaquetamos el nombre de la munición
            nombre_municion = y[0]
            nombre_municion = nombre_municion.strip().upper()

            cantidad = 0
            suelta = 0
            eslavonada = 0

            # Iteramos sobre la lista interna de datos
            for x in datos[0]:  # <--- aquí estaba el problema, antes usabas 'datos'
                valor_x = x[0].strip().upper()
                if valor_x == nombre_municion:
                    cant = int(x[1])  # ahora x[1] es un string
                    tipo_x = x[2].strip().upper()

                    cantidad += cant
                    if tipo_x == "SUELTA":
                        suelta += cant
                    else:
                        eslavonada += cant

            dato = (nombre_municion, cantidad, suelta, eslavonada)
            unidad.append(dato)

        header_municiones_tabla_dos=["Compania / Municion"]

        for y in self.companias[0]:  

            # Desempaquetamos el nombre de la munición
            nombre_municion = y[0]
            nombre_municion = nombre_municion.strip().upper()
            header_municiones_tabla_dos.append(nombre_municion)
        
        valores_comnpañia_tabla =[]
        for x in self.unidad[0]:
            valores_comnpañia=[]
            valores_comnpañia.append(x[0])
            for y in self.companias[0]:
                cantidad = 0
                for z in datos[0]:
                    if x[0] == z[3]:
                        if y[0]==z[0]:
                            cantidad = cantidad + int(z[1])
                valores_comnpañia.append(cantidad)
            valores_comnpañia_tabla.append(valores_comnpañia)
        return [header_municiones,unidad, header_municiones_tabla_dos, valores_comnpañia_tabla]


def calcular_armamento(self):
    # 1. Obtener todos los datos
    q = "SELECT * FROM ARMAMENTO"
    data = select_query_bd_personal(self, PERSONAL=q)

    # 2. Obtener listas únicas
    consultas = {
        "armas":      "SELECT DISTINCT ARMA FROM ARMAMENTO",
        "estado":     "SELECT DISTINCT ESTADO FROM ARMAMENTO",
        "compania":   "SELECT DISTINCT COMPANIA FROM ARMAMENTO",
        "tipo":       "SELECT DISTINCT TIPO FROM ARMAMENTO",
        "calibre":    "SELECT DISTINCT CALIBRE FROM ARMAMENTO",
    }

    armas      = select_query_bd_personal(self, PERSONAL=consultas["armas"])
    estado     = select_query_bd_personal(self, PERSONAL=consultas["estado"])
    compania   = select_query_bd_personal(self, PERSONAL=consultas["compania"])
    tipo       = select_query_bd_personal(self, PERSONAL=consultas["tipo"])
    calibre    = select_query_bd_personal(self, PERSONAL=consultas["calibre"])

    armas = armas[0]
    estado = estado[0]
    compania = compania[0]
    tipo = tipo[0]
    calibre = calibre[0]

    # 3. Diccionario final
    
    armamento = []

    header =["MATERIAL", "CANTIDAD", "PROVEEDORES", "MUNICIONES", "DEPÓSITO", "MANO" ]
    for x in compania:
        if x[0].strip() != "APC" and x[0].strip() != "ASPC":
            header.append(x[0].strip()[0])
        else:
            header.append(x[0].strip())


    for x in armas:
        cantidad = 0
        provedores = 0
        municion = 0
        deposito = 0
        mano = 0
        armamento_compania = []

        # Contamos totales
        for y in data[0]:
            if x[0].strip().upper() == y[1].strip().upper():
                cantidad += 1
                provedores += int(y[3])
                municion += int(y[4])
                if y[5].strip().upper() == "DESPOSITO":
                    deposito += 1
                else:
                    mano += 1

        # Contamos por compañía
        for z in compania:
            cantidad_cp = 0
            for t in data[0]:
                if z[0].strip().upper() == t[7].strip().upper() and x[0].strip().upper() == t[1].strip().upper():
                    cantidad_cp += 1
            armamento_compania.append(cantidad_cp)

        # Creamos la tupla final "desempaquetando" armamento_compania
        datos = (x[0].strip(), cantidad, provedores, municion, deposito, mano, *armamento_compania)
        armamento.append(datos)


    return [header, armamento]
    
# =========================================================
# APP
# =========================================================

API_TAGS = [
    {"name": "General", "description": "Endpoints base de salud del servicio."},
    {
        "name": "Armamento",
        "description": "Carga de archivos, trazabilidad histórica y reportes de armamento.",
    },
    {
        "name": "Estadísticas",
        "description": "Consultas agregadas para tableros e indicadores.",
    },
]

app = FastAPI(
    title="API de Armamento",
    description=(
        "Servicio para cargar archivos Excel de armamento, consultar cargas históricas "
        "y generar reportes consolidados en PDF."
    ),
    version="1.0.0",
    openapi_tags=API_TAGS,
)
router = APIRouter()


def _resolve_fecha_param(request: Request, filtro_fecha: Optional[str], fecha: Optional[str]) -> str:
    """Obtiene la fecha desde aliases soportados en query params."""
    fecha_param = _coalesce_query_text(
        filtro_fecha,
        fecha,
        request.query_params.get("filtroFecha"),
        request.query_params.get("fecha"),
        request.query_params.get("fechaInformacion"),
        request.query_params.get("fecha_informacion"),
    )
    if not fecha_param:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar filtroFecha o fecha en formato YYYY-MM-DD",
        )
    return fecha_param


def _resolve_armamento_filters(
    request: Request,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
    peloton: Optional[int] = None,
    relacion_mando: Optional[str] = None,
    ciclo: Optional[str] = None,
    actividad: Optional[str] = None,
    ubicacion: Optional[str] = None,
) -> dict:
    """Normaliza aliases de filtros usados por frontend y clientes heredados."""
    peloton_raw = _coalesce_query_text(
        peloton,
        request.query_params.get("filtroPeloton"),
        request.query_params.get("pelotonFiltro"),
    )
    if peloton_raw is None:
        peloton_normalizado = None
    else:
        try:
            peloton_normalizado = int(str(peloton_raw))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="peloton debe ser un numero entero") from exc

    return {
        "division": _coalesce_query_text(division, request.query_params.get("filtroDivision"), request.query_params.get("divisionFiltro")),
        "brigada": _coalesce_query_text(brigada, request.query_params.get("filtroBrigada"), request.query_params.get("brigadaFiltro")),
        "batallon": _coalesce_query_text(batallon, request.query_params.get("filtroBatallon"), request.query_params.get("batallonFiltro")),
        "compania": _coalesce_query_text(compania, request.query_params.get("filtroCompania"), request.query_params.get("companiaFiltro")),
        "peloton": peloton_normalizado,
        "relacion_mando": _coalesce_query_text(relacion_mando, request.query_params.get("relacionMando"), request.query_params.get("filtroRelacionMando")),
        "ciclo": _coalesce_query_text(ciclo, request.query_params.get("filtroCiclo"), request.query_params.get("cicloFiltro")),
        "actividad": _coalesce_query_text(actividad, request.query_params.get("filtroActividad"), request.query_params.get("actividadFiltro")),
        "ubicacion": _coalesce_query_text(ubicacion, request.query_params.get("filtroUbicacion"), request.query_params.get("ubicacionFiltro")),
    }


def _build_armamento_report_context():
    """Prepara los dos bloques de datos que necesita el PDF.

    Devuelve:
    - resumen de armamento
    - resumen de municion
    """
    fake_self = type("FakeSelf", (), {})()
    fake_self.datos_municion = MethodType(datos_municion, fake_self)
    fake_self.calcular_armamento = MethodType(calcular_armamento, fake_self)

    municiones = fake_self.datos_municion()
    armamento = fake_self.calcular_armamento()
    return armamento, municiones


# =========================================================
# ENDPOINTS
# =========================================================

@router.get(
    "/api/armamento/descargar-pdf",
    tags=["Armamento"],
    summary="Descargar parte diario de armamento en PDF",
    response_description="Archivo PDF generado con el consolidado de armamento y munición.",
)
async def descargar_pdf_armamento(
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
    """
    Genera el PDF del parte diario de armamento.

    Acepta filtros de fecha y ubicacion para mantener compatibilidad con el frontend,
    aunque la generacion actual usa el consolidado completo disponible en las consultas
    heredadas de armamento y municion.
    """
    fecha_param = _resolve_fecha_param(request, filtroFecha, fecha)
    filtros_resueltos = _resolve_armamento_filters(
        request,
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

    try:
        fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato YYYY-MM-DD"
        )

    armamento, municiones = _build_armamento_report_context(
        fecha_filtro,
        division=filtros_resueltos["division"],
        brigada=filtros_resueltos["brigada"],
        batallon=filtros_resueltos["batallon"],
        compania=filtros_resueltos["compania"],
    )

    pdf_bytes = generar_parte_diario_armamento_pdf(
        armamento[0], armamento[1],
        municiones[0], municiones[1], municiones[2], municiones[3],
        fila_para_qr=None,
        nombre_archivo="parte_diario_armamento.pdf",
        abrir=False,
        return_bytes=True
    )
    filename = "parte_diario_armamento.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


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
    """Crea tablas e indices de apoyo al iniciar la API.

    Regla mental simple:
    - tabla normal = estado actual
    - tabla historial = foto de una fecha
    """
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

            cur.execute("""
            CREATE TABLE IF NOT EXISTS armamento_asignado (
                id SERIAL PRIMARY KEY,
                numero_serie VARCHAR(100) REFERENCES armamento_general(numero_serie) ON DELETE CASCADE,
                cc BIGINT REFERENCES personal_novedades(cc) ON DELETE CASCADE,
                fecha_informacion DATE,
                usuario_ingreso TEXT,
                nivel_unidad TEXT,
                unidad_usuario TEXT,
                fecha_carga TIMESTAMP DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS armamento_asignado_historial (
                id SERIAL PRIMARY KEY,
                numero_serie VARCHAR(100) NOT NULL,
                cc BIGINT NOT NULL,
                fecha_informacion DATE NOT NULL,
                usuario_ingreso TEXT,
                nivel_unidad TEXT,
                unidad_usuario TEXT,
                fecha_carga TIMESTAMP DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_armamento_asignado_hist_relacion_fecha
            ON armamento_asignado_historial (numero_serie, cc, fecha_informacion)
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
    """Convierte a entero; si falla, devuelve None."""
    try:
        if value is None:
            return None
        if str(value).lower() == "nan":
            return None
        return int(float(value))
    except:
        return None

def safe_float(value):
    """Convierte a decimal; si falla, devuelve None."""
    try:
        if value is None:
            return None
        if str(value).lower() == "nan":
            return None
        return float(value)
    except:
        return None

def safe_str(value):
    """Limpia textos vacios o valores tipo NaN/None."""
    if value is None:
        return None

    val = str(value).strip()

    if val.lower() in ["nan", "none", ""]:
        return None

    return val


def safe_date(value):
    """Convierte varios formatos de fecha a `date` cuando es posible."""
    if value is None:
        return None

    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            pass

    if isinstance(value, datetime):
        return value.date()

    valor = str(value).strip()
    if not valor or valor.lower() in {"nan", "none", "nat"}:
        return None

    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            continue

    try:
        return pd.to_datetime(valor, errors="raise").date()
    except Exception:
        return None

def safe_iloc(row, index):
    """Lee una columna por posicion sin fallar si no existe."""
    if index >= len(row):
        return None
    return row.iloc[index]


def _add_text_filter(filtros, parametros, columna, valor):
    """Agrega un filtro SQL de texto solo si el valor es util."""
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
    """Devuelve el primer texto valido entre varias opciones."""
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
    """Convierte a entero para conteos; si falla, usa 0."""
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _build_armamento_historial_where(
    fecha_informacion,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
):
    """Arma el WHERE para consultar historial de armamento."""
    filtros = ["fecha_informacion = %s"]
    parametros = [fecha_informacion]

    _add_text_filter(filtros, parametros, "division", division)
    _add_text_filter(filtros, parametros, "brigada", brigada)
    _add_text_filter(filtros, parametros, "batallon", batallon)
    _add_text_filter(filtros, parametros, "compania", compania)

    return " AND ".join(filtros), tuple(parametros)


def datos_municion(
    fecha_informacion,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
):
    """Resume la municion desde el historico para el reporte PDF."""
    where_sql, parametros = _build_armamento_historial_where(
        fecha_informacion,
        division=division,
        brigada=brigada,
        batallon=batallon,
        compania=compania,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(calibre), ''), 'SIN DATO') AS municion,
                    COALESCE(SUM(cantidad_municion), 0) AS cantidad_total
                FROM armamento_general_historial
                WHERE {where_sql}
                GROUP BY 1
                ORDER BY 1
                """,
                parametros,
            )
            resumen_municion = cur.fetchall()

            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(compania), ''), 'SIN DATO') AS compania,
                    COALESCE(NULLIF(TRIM(calibre), ''), 'SIN DATO') AS municion,
                    COALESCE(SUM(cantidad_municion), 0) AS cantidad_total
                FROM armamento_general_historial
                WHERE {where_sql}
                GROUP BY 1, 2
                ORDER BY 1, 2
                """,
                parametros,
            )
            detalle_compania = cur.fetchall()

    header_municiones = ["Municion", "Cantidad", "Suelta", "Eslavonada"]
    unidad = [(municion, cantidad, cantidad, 0) for municion, cantidad in resumen_municion]

    municiones_ordenadas = [fila[0] for fila in resumen_municion]
    header_municiones_tabla_dos = ["Compania / Municion", *municiones_ordenadas]

    detalle_por_compania = {}
    for compania_row, municion_row, cantidad in detalle_compania:
        detalle_por_compania.setdefault(compania_row, {})[municion_row] = cantidad

    valores_compania_tabla = []
    for compania_row in sorted(detalle_por_compania):
        fila = [compania_row]
        for municion_row in municiones_ordenadas:
            fila.append(detalle_por_compania[compania_row].get(municion_row, 0))
        valores_compania_tabla.append(fila)

    return [header_municiones, unidad, header_municiones_tabla_dos, valores_compania_tabla]


def calcular_armamento(
    fecha_informacion,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
):
    """Resume el armamento desde el historico para el reporte PDF."""
    where_sql, parametros = _build_armamento_historial_where(
        fecha_informacion,
        division=division,
        brigada=brigada,
        batallon=batallon,
        compania=compania,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT COALESCE(NULLIF(TRIM(compania), ''), 'SIN DATO') AS compania
                FROM armamento_general_historial
                WHERE {where_sql}
                ORDER BY 1
                """,
                parametros,
            )
            companias = [row[0] for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(tipo_armamento), ''), 'SIN DATO') AS material,
                    COUNT(*) AS cantidad,
                    COALESCE(SUM(cant_provedores), 0) AS provedores,
                    COALESCE(SUM(cantidad_municion), 0) AS municion,
                    COALESCE(SUM(
                        CASE
                            WHEN UPPER(TRIM(COALESCE(estado, ''))) IN ('DEPOSITO', 'DESPOSITO') THEN 1
                            ELSE 0
                        END
                    ), 0) AS deposito,
                    COALESCE(SUM(
                        CASE
                            WHEN UPPER(TRIM(COALESCE(estado, ''))) IN ('DEPOSITO', 'DESPOSITO') THEN 0
                            ELSE 1
                        END
                    ), 0) AS mano
                FROM armamento_general_historial
                WHERE {where_sql}
                GROUP BY 1
                ORDER BY 1
                """,
                parametros,
            )
            resumen = cur.fetchall()

            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(tipo_armamento), ''), 'SIN DATO') AS material,
                    COALESCE(NULLIF(TRIM(compania), ''), 'SIN DATO') AS compania,
                    COUNT(*) AS cantidad
                FROM armamento_general_historial
                WHERE {where_sql}
                GROUP BY 1, 2
                ORDER BY 1, 2
                """,
                parametros,
            )
            detalle_compania = cur.fetchall()

    header = ["MATERIAL", "CANTIDAD", "PROVEEDORES", "MUNICIONES", "DEPOSITO", "MANO"]
    for nombre_compania in companias:
        if nombre_compania not in {"APC", "ASPC"}:
            header.append(nombre_compania[:1] if nombre_compania else "S")
        else:
            header.append(nombre_compania)

    detalle_material = {}
    for material, compania_row, cantidad in detalle_compania:
        detalle_material.setdefault(material, {})[compania_row] = cantidad

    armamento = []
    for material, cantidad, provedores, municion, deposito, mano in resumen:
        fila = [material, cantidad, provedores, municion, deposito, mano]
        for nombre_compania in companias:
            fila.append(detalle_material.get(material, {}).get(nombre_compania, 0))
        armamento.append(tuple(fila))

    return [header, armamento]


def _build_armamento_report_context(
    fecha_informacion,
    division: Optional[str] = None,
    brigada: Optional[str] = None,
    batallon: Optional[str] = None,
    compania: Optional[str] = None,
):
    """Junta en una sola llamada los datos de armamento y de municion."""
    return (
        calcular_armamento(
            fecha_informacion,
            division=division,
            brigada=brigada,
            batallon=batallon,
            compania=compania,
        ),
        datos_municion(
            fecha_informacion,
            division=division,
            brigada=brigada,
            batallon=batallon,
            compania=compania,
        ),
    )



# =========================================================
# HEALTH
# =========================================================

@router.get("/", tags=["General"], summary="Validar estado del servicio", response_description="Estado basico de disponibilidad del API.")
def home():
    """Endpoint simple de salud para monitoreo y pruebas rapidas."""
    return {"status": "ok"}


# =========================================================
# GUARDAR EXCEL
# =========================================================

@router.post("/api/armamento/guardar", tags=["Armamento"], summary="Cargar archivo Excel de armamento", response_description="Resumen de la carga procesada en tablas actual e historial.")
async def guardar_excel(
    payload: dict = Depends(verificar_token),
    archivo: UploadFile = File(None),
    file: UploadFile = File(None),
    fecha_informacion: str = Form(None),
    fecha: str = Form(None),
    filtroFecha: str = Form(None)
):
    """
    Carga el Excel principal de armamento.

    Flujo resumido:
    1. Lee el archivo.
    2. Limpia datos vacios.
    3. Guarda el estado actual en `armamento_general`.
    4. Guarda una foto historica del dia en `armamento_general_historial`.
    """
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


@router.post(
    "/api/armamento/asignado/guardar",
    tags=["Armamento"],
    summary="Cargar archivo Excel de armamento asignado",
    response_description="Resumen de la carga procesada en tablas actual e historial de asignaciones.",
)
async def guardar_excel_armamento_asignado(
    payload: dict = Depends(verificar_token),
    archivo: UploadFile = File(None),
    file: UploadFile = File(None),
    fecha_informacion: str = Form(None),
    fecha: str = Form(None),
    filtroFecha: str = Form(None)
):
    """
    Carga el Excel de armamento asignado.

    Idea simple:
    - `armamento_asignado` = quien tiene el arma hoy
    - `armamento_asignado_historial` = quien la tenia en una fecha dada

    Orden esperado de columnas en el Excel:
    0 numero_serie
    1 cc
    """
    archivo_cargado = archivo or file
    fecha_raw = fecha_informacion or fecha or filtroFecha

    if archivo_cargado is None:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar un archivo en el campo 'archivo' o 'file'"
        )

    print("Archivo recibido asignado:", archivo_cargado.filename)
    print("Fecha informacion asignado:", fecha_raw)

    if not archivo_cargado.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Archivo no valido")

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
            raise HTTPException(status_code=401, detail="Token sin usuario valido")

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

        # Lee el Excel y evita que advertencias de formato de Office rompan la carga.
        # Lee el Excel y evita advertencias comunes de archivos de Office.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Data Validation extension is not supported and will be removed",
                category=UserWarning,
            )
            df = pd.read_excel(BytesIO(contenido), header=0)

        # Normaliza nulos de Pandas para tratarlos de forma consistente.
        df = df.where(pd.notnull(df), None)

        registros = []
        omitidos_sin_serie = 0
        omitidos_sin_cc = 0

        for _, row in df.iterrows():
            numero_serie = safe_str(safe_iloc(row, 0))
            cc = safe_int(safe_iloc(row, 1))

            if not numero_serie:
                omitidos_sin_serie += 1
                continue

            if cc is None:
                omitidos_sin_cc += 1
                continue

            registros.append((
                numero_serie,
                cc,
                fecha_informacion_date,
                usuario,
                nivel_unidad,
                unidad_usuario,
            ))

        if not registros:
            raise HTTPException(
                status_code=400,
                detail="No se encontraron registros validos de armamento asignado en el archivo"
            )

        series = sorted({registro[0] for registro in registros})
        cedulas = sorted({registro[1] for registro in registros})

        # Antes de guardar, validamos que la serie y la cedula existan.
        with get_conn() as conn_validacion:
            with conn_validacion.cursor() as cur_validacion:
                cur_validacion.execute(
                    "SELECT numero_serie FROM armamento_general WHERE numero_serie = ANY(%s)",
                    (series,),
                )
                series_existentes = {row[0] for row in cur_validacion.fetchall()}

                cur_validacion.execute(
                    "SELECT cc FROM personal_novedades WHERE cc = ANY(%s)",
                    (cedulas,),
                )
                ccs_existentes = {row[0] for row in cur_validacion.fetchall()}

        series_faltantes = [serie for serie in series if serie not in series_existentes]
        ccs_faltantes = [cc for cc in cedulas if cc not in ccs_existentes]

        if series_faltantes or ccs_faltantes:
            raise HTTPException(
                status_code=400,
                detail={
                    "mensaje": "Hay registros que no existen en las tablas relacionadas",
                    "series_no_encontradas": series_faltantes[:50],
                    "cc_no_encontradas": ccs_faltantes[:50],
                }
            )

        # Reemplaza la asignacion actual de las series cargadas.
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM armamento_asignado WHERE numero_serie = ANY(%s)",
                    (series,),
                )

                cur.executemany("""
                INSERT INTO armamento_asignado (
                    numero_serie,
                    cc,
                    fecha_informacion,
                    usuario_ingreso,
                    nivel_unidad,
                    unidad_usuario
                ) VALUES (
                    %s,%s,%s,%s,%s,%s
                )
                """, registros)
            conn.commit()

        # Guarda la foto historica de la asignacion para la fecha.
        with get_conn() as conn2:
            with conn2.cursor() as cur2:
                cur2.executemany("""
                INSERT INTO armamento_asignado_historial (
                    numero_serie,
                    cc,
                    fecha_informacion,
                    usuario_ingreso,
                    nivel_unidad,
                    unidad_usuario
                ) VALUES (
                    %s,%s,%s,%s,%s,%s
                ) ON CONFLICT (numero_serie, cc, fecha_informacion) DO UPDATE SET
                    usuario_ingreso = EXCLUDED.usuario_ingreso,
                    nivel_unidad = EXCLUDED.nivel_unidad,
                    unidad_usuario = EXCLUDED.unidad_usuario,
                    fecha_carga = NOW()
                """, registros)
            conn2.commit()

        return {
            "mensaje": "Datos de armamento asignado cargados correctamente",
            "total": len(registros),
            "omitidos_sin_serie": omitidos_sin_serie,
            "omitidos_sin_cc": omitidos_sin_cc,
            "tabla_actual_actualizada": len(registros),
            "tabla_historial_actualizada": len(registros),
            "fecha_informacion": str(fecha_informacion_date),
            "usuario": usuario,
            "nivel_unidad": nivel_unidad,
            "unidad_usuario": unidad_usuario
        }

    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/api/armamento/cargas", tags=["Armamento"], summary="Listar cargas historicas de armamento", response_description="Listado agregado por usuario y fecha de informacion.")
async def obtener_cargas(payload: dict = Depends(verificar_token)):
    """Lista las cargas hechas sobre el historico.

    Sirve como bitacora resumida: quien cargo, desde que unidad y en que fecha.
    """
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


@router.get("/api/personal/estadisticas_armamento", tags=["Estadisticas"], summary="Obtener estadisticas consolidadas de armamento", response_description="Resumen general y distribuciones por categorias del armamento cargado.")
async def obtener_estadisticas_armamento(
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
    """
    Devuelve indicadores agregados de armamento para una fecha y filtros opcionales.

    En otras palabras: arma los conteos y agrupaciones para tableros.

    El endpoint conserva aliases historicos de parametros para no romper integraciones
    existentes del frontend.
    """
    fecha_param = _resolve_fecha_param(request, filtroFecha, fecha)
    filtros_resueltos = _resolve_armamento_filters(
        request,
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
    division = filtros_resueltos["division"]
    brigada = filtros_resueltos["brigada"]
    batallon = filtros_resueltos["batallon"]
    compania = filtros_resueltos["compania"]
    peloton = filtros_resueltos["peloton"]
    relacion_mando = filtros_resueltos["relacion_mando"]
    ciclo = filtros_resueltos["ciclo"]
    actividad = filtros_resueltos["actividad"]
    ubicacion = filtros_resueltos["ubicacion"]

    try:
        fecha_filtro = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato YYYY-MM-DD"
        )
    where_sql, parametros = _build_personal_filters(
        fecha_filtro,
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


