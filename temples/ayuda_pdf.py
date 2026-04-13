from fpdf import FPDF
from datetime import datetime
import os


def caligrafia_ingreso(pdf):
    # ayuda_pdf.py está en: MANDO_CONTROL/temples/

    pdf.add_font("Calibri", "B", fname="img/font/calibrib_plain.ttf", uni=True)
    pdf.add_font("Calibri", "", fname="img/font/calibril_plain.ttf", uni=True)
    pdf.add_font("BebasNeue", "", fname="img/font/BebasNeue_Regular.ttf", uni=True)

    pdf.add_font("Arial Narrow", "", fname="img/font/arialnarrow.ttf", uni=True)
    pdf.add_font("Arial Narrow", "B", fname="img/font/arialnarrow_bold.ttf", uni=True)
    pdf.add_font("Arial Narrow", "BI", fname="img/font/arialnarrow_bolditalic.ttf", uni=True)
    pdf.add_font("Arial Narrow", "I", fname="img/font/arialnarrow_italic.ttf", uni=True)

    
import qrcode
from fpdf import FPDF


class PDF(FPDF):
    def header(self):
        pass

    def footer(self):
         pass
        # Firma
        # self.set_xy(10, qr_y + qr_size - 20)
        #self.set_font("Arial", "B", 11)
        #self.cell(60, 10, "Firma autorizada", align="L")

        # Pie institucional
        #self.set_xy(10, 252)
        #self.set_font("Arial", "I", 9)
        #self.set_text_color(150, 0, 0)
        #self.cell(0, 5, "Documento generado automáticamente - Uso institucional")

        
    def rounded_rect(self, x, y, w, h, r=2, style=''):
        # Dibuja un rectángulo con esquinas redondeadas (compatible FPDF2)
        op = {'': 'S', 'F': 'f', 'FD': 'B', 'DF': 'B'}.get(style, 'S')

        MyArc = 4 / 3 * (2**0.5 - 1) * r

        self._out(f"{x + r} {self.h - y} m")

        # Arriba
        self._out(f"{x + w - r} {self.h - y} l")
        self._out("".join([
            f"{x + w - r + MyArc} {self.h - (y)} ",
            f"{x + w} {self.h - (y + r - MyArc)} ",
            f"{x + w} {self.h - (y + r)} c"
        ]))

        # Derecha
        self._out(f"{x + w} {self.h - (y + h - r)} l")
        self._out("".join([
            f"{x + w} {self.h - (y + h - r + MyArc)} ",
            f"{x + w - r + MyArc} {self.h - (y + h)} ",
            f"{x + w - r} {self.h - (y + h)} c"
        ]))

        # Abajo
        self._out(f"{x + r} {self.h - (y + h)} l")
        self._out("".join([
            f"{x + r - MyArc} {self.h - (y + h)} ",
            f"{x} {self.h - (y + h - r + MyArc)} ",
            f"{x} {self.h - (y + h - r)} c"
        ]))

        # Izquierda
        self._out(f"{x} {self.h - (y + r)} l")
        self._out("".join([
            f"{x} {self.h - (y + r - MyArc)} ",
            f"{x + r - MyArc} {self.h - (y)} ",
            f"{x + r} {self.h - (y)} c"
        ]))

        self._out(op)

def generar_qr(datos, path="qr_temp.png"):
    """Genera un QR con texto limpio y sin llaves JSON."""

    grado = ""
    if len(datos) > 20 and datos[20] is not None:
        grado = str(datos[20]).strip()

    nombre_qr = f"{grado} {datos[0]} {datos[1]}".strip()

    texto = f"""
IDENTIFICACIÓN
- Cédula: {datos[2]}
- Nombre: {nombre_qr}

UNIDAD
- División: {datos[3]}
- Brigada: {datos[4]}
- Batallón: {datos[5]}
- Compañía: {datos[6]} {datos[7]}

CONTACTO EMERGENCIA
- Nombre: {datos[17]}
- Parentesco: {datos[19]}
- Teléfono: {datos[18]}

TELÉFONOS
- Personal: {datos[15]}
""".strip()

    qr = qrcode.QRCode(
        version=4,  # un poco más grande para texto limpio
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=7,
        border=2
    )

    qr.add_data(texto)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img.save(path)
    return path
def informacion_basica(self, datos, informacion, abrir=False):

    pdf = PDF(orientation='L', unit='mm', format='letter')
    pdf.set_auto_page_break(False)

    caligrafia_ingreso(pdf)
    pdf.add_page()

    # ===================== ENCABEZADO ======================
    unidad_titulo = f"{datos[3]} - {datos[4]} - {datos[5]} - {datos[6]}{datos[7]}"

    pdf.set_font("BebasNeue", "", size=34)
    pdf.set_text_color(40, 40, 40)
    pdf.set_xy(14, 10)
    pdf.cell(0, 12, unidad_titulo, ln=True)

    pdf.set_font("BebasNeue", "", size=50)
    pdf.set_text_color(170, 0, 0)
    pdf.set_x(14)
    pdf.cell(0, 20, informacion.upper(), ln=True)

    pdf.set_draw_color(180, 0, 0)
    pdf.set_line_width(0.7)
    pdf.line(12, 42, 268, 42)

    # ==========================================================
    #  PANEL IZQUIERDO - IDENTIFICACIÓN / CONTACTO
    # ==========================================================

    left_x = 14
    y = 50

    # IDENTIFICACIÓN
    pdf.set_font("BebasNeue", "", size=26)
    pdf.set_text_color(20, 20, 20)
    pdf.set_xy(left_x, y)
    pdf.cell(0, 10, "IDENTIFICACIÓN")
    y += 14

    campos = [
        ("CÉDULA", datos[2]),
        ("TELÉFONO", datos[15]),
        ("RH", datos[16]),
    ]

    for titulo, valor in campos:
        pdf.set_font("BebasNeue", "", size=18)
        pdf.set_text_color(150, 0, 0)
        pdf.set_xy(left_x, y)
        pdf.cell(0, 6, titulo)

        pdf.set_font("BebasNeue", "", size=28)
        pdf.set_text_color(35, 35, 35)
        pdf.set_xy(left_x, y + 7)
        pdf.cell(0, 10, str(valor))

        y += 21

    pdf.set_draw_color(180, 0, 0)
    pdf.line(12, y, 140, y)
    y += 8

    # CONTACTO EMERGENCIA
    pdf.set_font("BebasNeue", "", size=26)
    pdf.set_text_color(20, 20, 20)
    pdf.set_xy(left_x, y)
    pdf.cell(0, 10, "CONTACTO DE EMERGENCIA")
    y += 14

    contacto = [
        ("NOMBRE", datos[17]),
        ("PARENTESCO", datos[19]),
        ("TELÉFONO", datos[18]),
    ]

    for titulo, valor in contacto:
        pdf.set_font("BebasNeue", "", size=18)
        pdf.set_text_color(150, 0, 0)
        pdf.set_xy(left_x, y)
        pdf.cell(0, 6, titulo)

        pdf.set_font("BebasNeue", "", size=26)
        pdf.set_text_color(35, 35, 35)
        pdf.set_xy(left_x, y + 6)
        pdf.cell(0, 10, str(valor))

        y += 20

    # ==========================================================
    # PANEL DERECHO - INFORMACIÓN PROFESIONAL
    # ==========================================================

    right_x = 150
    y2 = 50

    pdf.set_font("BebasNeue", "", size=26)
    pdf.set_text_color(20, 20, 20)
    pdf.set_xy(right_x, y2)
    pdf.cell(0, 10, "INFORMACIÓN PROFESIONAL")
    y2 += 14

    profesional = [
        ("CARGO", datos[12]),
        ("CODE", datos[10] if datos[9] == "CODE" else datos[9]),
        ("RELACIÓN MANDO", datos[8]),
    ]

    for titulo, valor in profesional:
        pdf.set_font("BebasNeue", "", size=18)
        pdf.set_text_color(150, 0, 0)
        pdf.set_xy(right_x, y2)
        pdf.cell(0, 6, titulo)

        pdf.set_font("BebasNeue", "", size=28)
        pdf.set_text_color(35, 35, 35)
        pdf.set_xy(right_x, y2 + 6)
        pdf.cell(0, 10, str(valor))

        y2 += 20

    # ==========================================================
    #                           QR
    # ==========================================================

    qr_path = generar_qr(datos)
    pdf.image(qr_path, x=230, y=165, w=42)

    # ==========================================================
    # GUARDAR PDF y ABRIR
    # ==========================================================
    filename = f"../{datos[0]}_{datos[1]}.pdf"
  
    # ===== ABRIR AUTOMÁTICAMENTE =====
    # Carpeta donde quieres guardar todos los PDFs
    output_dir = os.path.join(os.path.dirname(__file__), "pdfs")

    # Crear carpeta si no existe
    os.makedirs(output_dir, exist_ok=True)

    filename = os.path.join(output_dir, f"{datos[0]}_{datos[1]}.pdf")

    pdf.output(filename)

    if abrir and os.name == "nt":
        os.startfile(filename)

    return filename

    # Para Linux:
    # os.system(f"xdg-open '{filename}'")

    # Para Mac:
    # os.system(f"open '{filename}'")

# ----------------------------
# QR limpio
# ----------------------------
def generar_qr_texto_limpio(datos, path="qr_temp.png"):
    lines = []
    lines.append("IDENTIFICACIÓN")
    lines.append(f"CEDULA: {datos[2]}")
    lines.append(f"NOMBRE: {datos[0]} {datos[1]}")
    lines.append("")
    lines.append("UNIDAD")
    lines.append(f"DIV: {datos[3]}")
    lines.append(f"BRIG: {datos[4]}")
    lines.append(f"BAT: {datos[5]}")
    lines.append(f"COMP: {datos[6]} {datos[7]}")
    lines.append("")
    lines.append("CONTACTO EMERGENCIA")
    lines.append(f"NOMBRE: {datos[17]}")
    lines.append(f"PARENTESCO: {datos[19]}")
    lines.append(f"TEL: {datos[18]}")
    lines.append("")
    lines.append(f"TEL PERSONAL: {datos[15]}")

    contenido = "\n".join(lines)

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=5,
        border=2
    )
    qr.add_data(contenido)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(path)
    return path


# ----------------------------
# PDF mejorado - CUADRO ARRIBA Y ABAJO
# ----------------------------
def generar_parte_diario_pdf(tabla2, tabla1, fila_para_qr=None,
                             nombre_archivo="parte_diario.pdf",
                             abrir=True):

    pdf = FPDF(orientation='P', unit='mm', format='letter')
    pdf.add_page()

    # -------------------------------------
    # Encabezado general
    # -------------------------------------
    pdf.set_font("Arial", "B", 18)
    pdf.set_xy(10, 10)
    pdf.cell(0, 8, "PARTE DIARIO - RESUMEN DE EFECTIVOS", ln=True)

    pdf.set_draw_color(90, 90, 90)
    pdf.set_line_width(0.3)
    pdf.line(10, 20, 200, 20)

    # ==========================================================
    # CUADRO 1 (arriba)
    # ==========================================================

    y = 25
    pdf.set_xy(10, y)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 7, "CUADRO 1 - RESUMEN", ln=True)

    y += 8

    headers1 = ["CATEGORÍA","OFI","SUB","SLP","SL18","SL12","H","M","TOTAL"]

    col_widths = [45, 17, 17, 17, 17, 17, 17, 17, 17]

    pdf.set_font("Arial", "B", 9)
    pdf.set_xy(10, y)

    for h, w in zip(headers1, col_widths):
        pdf.cell(w, 7, h, border=1, align="C", fill=False)

    y += 7
    pdf.set_font("Arial", "", 9)

    for fila in tabla1:
        pdf.set_xy(10, y)
        for dato, w in zip(fila, col_widths):
            if isinstance(dato, str):
                pdf.cell(w, 5, str(dato), border=1, align="L")
            elif isinstance(dato, (int, float)) and dato > 0:
                pdf.cell(w, 5, str(dato), border=1, align="C")
            else:
                # Ceros o negativos → celda vacía
                pdf.cell(w, 5, "", border=1, align="C")
        y += 5

    # ==========================================================
    # CUADRO 2 (abajo)
    # ==========================================================

    y += 6
    pdf.set_xy(10, y)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 7, "CUADRO 2 - DESGLOSE POR GRADOS", ln=True)

    y += 8

    headers2 = ["CATEGORÍA","GR","MG","BG","CR","TC","MY","CT","TE",
                "ST","SMC","SM","SP","SV","SS","CP","CS","C3",
                "SLP","SL18","SL12","TOTAL"]

    col2_widths = [32] + [8]*20 + [10]

    pdf.set_font("Arial", "B", 7)
    pdf.set_xy(10, y)
    for h, w in zip(headers2, col2_widths):
        pdf.cell(w, 5, h, border=1, align="C", fill=False)

    y += 5
    pdf.set_font("Arial", "", 7)

    for fila in tabla2:
        pdf.set_xy(10, y)
        for dato, w in zip(fila, col2_widths):

            if isinstance(dato, str):
                # Texto alineado a la izquierda
                pdf.cell(w, 5, dato, border=1, align="L")

            elif isinstance(dato, (int, float)) and dato > 0:
                # Números mayores a 0 alineados a la izquierda
                pdf.cell(w, 5, str(dato), border=1, align="C")

            else:
                # Ceros o negativos → celda vacía
                pdf.cell(w, 5, "", border=1, align="C")

        y += 5


    # ==========================================================
    # QR y firma abajo
    # ==========================================================

    qr_size = 40
    qr_x = 155
    qr_y = 255 - qr_size

    if fila_para_qr:
        qr_path = generar_qr_texto_limpio(fila_para_qr)
        pdf.image(qr_path, x=qr_x, y=qr_y, w=qr_size)

    # Firma
    pdf.set_xy(20, qr_y + qr_size - 20)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(60, 10, "Firma autorizada", align="L")

    # Pie institucional
    pdf.set_xy(10, 252)
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(150, 0, 0)
    pdf.cell(0, 5, "Documento generado automáticamente - Uso institucional")

    # Guardar
    ruta = os.path.abspath(nombre_archivo)
    pdf.output(ruta)

    if abrir and os.name == "nt":
        os.startfile(ruta)

    return ruta


# ----------------------------
# PDF mejorado - CUADRO ARRIBA Y ABAJO
# ----------------------------
def generar_parte_diario_armamento_pdf(cabecera_0, tabla_0, cabecera_1, tabla_1, cabecera_2, tabla_2, fila_para_qr=None,
                             nombre_archivo="parte_diario.pdf",
                             abrir=True):

    pdf = FPDF(orientation='L', unit='mm', format='letter')
    pdf.add_page()

    # -------------------------------------
    # Encabezado general
    # -------------------------------------
    pdf.set_font("Arial", "B", 18)
    pdf.set_xy(10, 10)
    pdf.cell(0, 8, "PARTE DIARIO - RESUMEN DE ARMAMENTO", ln=True)

    pdf.set_draw_color(90, 90, 90)
    pdf.set_line_width(0.3)
    pdf.line(10, 20, 200, 20)

    # ==========================================================
    # CUADRO 1 (arriba)
    # ==========================================================

    y = 25
    pdf.set_xy(10, y)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 7, "CUADRO 1 - RESUMEN", ln=True)

    y += 8

    headers1 = cabecera_0
    sublista = cabecera_0[1:6]

    col_widths = [32] + [25]*len(sublista)+[15]*(len(headers1)-len(sublista))

    pdf.set_font("Arial", "B", 9)
    pdf.set_xy(10, y)

    for h, w in zip(headers1, col_widths):
        pdf.cell(w, 7, h, border=1, align="C", fill=False)

    y += 7
    pdf.set_font("Arial", "", 9)

    for fila in tabla_0:
        pdf.set_xy(10, y)
        for dato, w in zip(fila, col_widths):
            if isinstance(dato, str):
                pdf.cell(w, 5, str(dato), border=1, align="L")
            elif isinstance(dato, (int, float)) and dato > 0:
                pdf.cell(w, 5, str(dato), border=1, align="C")
            else:
                # Ceros o negativos → celda vacía
                pdf.cell(w, 5, "", border=1, align="C")
        y += 5

    # ==========================================================
    # CUADRO 2 (abajo)
    # ==========================================================

    y += 6
    pdf.set_xy(10, y)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 7, "CUADRO 2 - Municiones", ln=True)

    y += 8

    headers2 = cabecera_1

    col2_widths = [25]*(len(headers2))

    pdf.set_font("Arial", "B", 7)
    pdf.set_xy(10, y)
    for h, w in zip(headers2, col2_widths):
        pdf.cell(w, 5, h, border=1, align="C", fill=False)

    y += 5
    pdf.set_font("Arial", "", 7)

    for fila in tabla_1:
        pdf.set_xy(10, y)
        for dato, w in zip(fila, col2_widths):

            if isinstance(dato, str):
                # Texto alineado a la izquierda
                pdf.cell(w, 5, dato, border=1, align="L")

            elif isinstance(dato, (int, float)) and dato > 0:
                # Números mayores a 0 alineados a la izquierda
                pdf.cell(w, 5, str(dato), border=1, align="C")

            else:
                # Ceros o negativos → celda vacía
                pdf.cell(w, 5, "", border=1, align="C")

        y += 5
    # ==========================================================
    # CUADRO 3 (abajo)
    # ==========================================================

    y += 6
    pdf.set_xy(10, y)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 7, "CUADRO 3 - Municiones", ln=True)

    y += 8

    headers3 = cabecera_2

    col2_widths = [25]*(len(headers3))

    pdf.set_font("Arial", "B", 7)
    pdf.set_xy(10, y)
    for h, w in zip(headers3, col2_widths):
        pdf.cell(w, 5, h, border=1, align="C", fill=False)

    y += 5
    pdf.set_font("Arial", "", 7)

    for fila in tabla_2:
        pdf.set_xy(10, y)
        for dato, w in zip(fila, col2_widths):

            if isinstance(dato, str):
                # Texto alineado a la izquierda
                pdf.cell(w, 5, dato, border=1, align="L")

            elif isinstance(dato, (int, float)) and dato > 0:
                # Números mayores a 0 alineados a la izquierda
                pdf.cell(w, 5, str(dato), border=1, align="C")

            else:
                # Ceros o negativos → celda vacía
                pdf.cell(w, 5, "", border=1, align="C")

        y += 5

    # ==========================================================
    # QR y firma abajo
    # ==========================================================

    # QR y firma abajo
    qr_size = 40
    qr_x = 155
    qr_y = 190 - qr_size   # MAX PARA LETTER HORIZONTAL

    if fila_para_qr:
        qr_path = generar_qr_texto_limpio(fila_para_qr)
        pdf.image(qr_path, x=qr_x, y=qr_y, w=qr_size)

    # Firma
    pdf.set_xy(10, qr_y + qr_size - 15)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(60, 10, "Firma autorizada", align="L")

    # Pie institucional
    pdf.set_xy(10, 185)
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(150, 0, 0)
    pdf.cell(0, 5, "Documento generado automáticamente - Uso institucional")


    # Guardar
    ruta = os.path.abspath(nombre_archivo)
    pdf.output(ruta)

    if abrir and os.name == "nt":
        os.startfile(ruta)

    return ruta
