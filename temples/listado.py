from docxtpl import DocxTemplate
from datetime import datetime

#from mapa.distancias import *
import os
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent

directorio = APP_PATH / "listado.docx"


def _remove_paragraph(paragraph):
    p = paragraph._element
    p.getparent().remove(p)


def _limpiar_espacios_previos(doc):
    # El template deja parrafos vacios/tabs antes de la tabla; se limpian para evitar
    # paginas en blanco o grandes espacios entre encabezado y listado.
    for paragraph in list(doc.paragraphs):
        has_table = bool(paragraph._element.xpath(".//w:tbl"))
        has_drawing = bool(paragraph._element.xpath(".//w:drawing"))
        has_page_break = bool(paragraph._element.xpath(".//w:br[@w:type='page']"))
        texto = (paragraph.text or "").replace("\t", "").replace("\xa0", "").strip()

        if has_page_break and not has_table and not has_drawing:
            _remove_paragraph(paragraph)
            continue

        if texto:
            continue

        if not has_table and not has_drawing:
            _remove_paragraph(paragraph)

def crear_word_informe_listado(self, informacion):
    doc = DocxTemplate(str(directorio))
                    
    fecha =datetime.now()
    # fecha=datetime.strptime(fecha, '%d/%m/%Y')
    fecha = fecha.strftime('%d-%m-%Y %H-%M-%S')
    nombre = "Listado de Personal " 
    continiuacion_hr = fecha

    hola = ( 
        (1, 'Geek 1')

    ) 

    context = { 
            'fecha_elaboracion':fecha,
            'continuación_doc' : continiuacion_hr,

            'hola' : hola[1]
                
    }
    doc.render(context)
    _limpiar_espacios_previos(doc)

    numero = 0
    

    table2 = doc.add_table(rows=1, cols=26) 
    table2.style = 'unidades' 
    row = table2.rows[0].cells 

    
    row[1].merge(row[0])
    row[0].paragraphs[0].add_run("No.").bold = True

    row[3].merge(row[2])
    row[2].paragraphs[0].add_run("GRD").bold = True

    
    row[14].merge(row[4])
    row[4].paragraphs[0].add_run("NOMBRES Y APELLIDOS").bold = True
    
    row[17].merge(row[15])
    row[15].paragraphs[0].add_run("CEDULA").bold = True
        
    row[20].merge(row[18])
    row[18].paragraphs[0].add_run("TELEFONO").bold = True
            
    row[22].merge(row[21])
    row[21].paragraphs[0].add_run("RH").bold = True

    row[25].merge(row[23])
    row[23].paragraphs[0].add_run("UNIDAD").bold = True

    for dato in informacion:
        numero = numero +1

        row = table2.add_row().cells 
        
        row[1].merge(row[0])
        row[0].text = str(numero)
                
        row[3].merge(row[2])
        row[2].text = str(dato[0])
                        
        row[14].merge(row[4])
        row[4].text = str(dato[1])
                                
        row[17].merge(row[15])
        row[15].text = str(dato[2])
                                        
        row[20].merge(row[18])
        row[18].text = str(dato[15])
                                                
        row[22].merge(row[21])
        row[21].text = str(dato[16])

        unidad = f"{'' if dato[6] is None else dato[6]} - {'' if dato[7] is None else dato[7]}"
                                                        
        row[25].merge(row[23])
        row[23].text = str(unidad)


    directorio_salida = APP_PATH.parent / "uploads" / "word"
    directorio_salida.mkdir(parents=True, exist_ok=True)

    ruta_archivo = directorio_salida / f"{nombre}{fecha}.docx"

    doc.save(str(ruta_archivo))

    return str(ruta_archivo), ruta_archivo.name


def crear_word_informe_listado_emergencia(self, informacion):
    doc = DocxTemplate(str(directorio))
                    
    fecha =datetime.now()
    # fecha=datetime.strptime(fecha, '%d/%m/%Y')
    fecha = fecha.strftime('%d-%m-%Y %H-%M-%S')
    nombre = "Listado de Personal contacto emergencia " 
    continiuacion_hr = fecha

    hola = ( 
        (1, 'Geek 1')

    ) 

    context = { 
            'fecha_elaboracion':fecha,
            'continuación_doc' : continiuacion_hr,

            'hola' : hola[1]
                
    }
    doc.render(context)
    _limpiar_espacios_previos(doc)

    numero = 0
    

    table2 = doc.add_table(rows=1, cols=25) 
    table2.style = 'unidades' 
    row = table2.rows[0].cells 

    
    row[0].merge(row[0])
    row[0].paragraphs[0].add_run("No.").bold = True

    row[1].merge(row[1])
    row[1].paragraphs[0].add_run("GRD").bold = True

    
    row[9].merge(row[2])
    row[2].paragraphs[0].add_run("NOMBRES Y APELLIDOS").bold = True
    
    row[17].merge(row[10])
    row[10].paragraphs[0].add_run("CONTACTO").bold = True
        
    row[19].merge(row[18])
    row[18].paragraphs[0].add_run("TELEFONO").bold = True
            
    row[24].merge(row[20])
    row[20].paragraphs[0].add_run("PARENTESCO").bold = True


    for dato in informacion:
        numero = numero +1

        row = table2.add_row().cells 
        
        row[0].merge(row[0])
        row[0].text = str(numero)
                
        row[1].merge(row[1])
        row[1].text = str(dato[0])
                        
        row[9].merge(row[2])
        row[2].text = str(dato[1])
                                
        row[17].merge(row[10])
        row[10].text = str(dato[17])
                                        
        row[19].merge(row[18])
        row[18].text = str(dato[18])
                                                
        row[24].merge(row[20])
        row[20].text = str(dato[19])

    directorio_salida = APP_PATH.parent / "uploads" / "word"
    directorio_salida.mkdir(parents=True, exist_ok=True)

    ruta_archivo = directorio_salida / f"{nombre}{fecha}.docx"

    doc.save(str(ruta_archivo))

    return str(ruta_archivo), ruta_archivo.name

