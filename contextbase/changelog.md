# Bitácora del Proyecto

Registro de cambios, decisiones y resultados del reemplazador de logos PDF.

---

## Cambios realizados

### 2026-11-10: Preparación de Git y privacidad

- Se creó `.gitignore` para excluir entornos, credenciales, cachés, builds, `node_modules`, archivos del sistema, el EXE y los PDF con datos personales.
- Se dejó `entrada/README.md` para conservar la carpeta sin subir los PDF.
- Se inicializó el repositorio local en la rama `main`.
- Se configuró el autor local `REGT-URRED <U19211826@utp.edu.pe>`.
- Se agregó el remoto `https://github.com/REGT-URRED/LOMPLAZ.git` sin incluir el token.
- El commit se preparó, pero no se ejecutó ningún push. Queda pendiente de autorización.
- Vercel no aplica al proyecto: es una aplicación de escritorio Windows con Tkinter y PyInstaller, no una aplicación web.

### 2026-11-10: Organización, ContextBase y README

- Se reorganizó la carpeta en `app/`, `entrada/`, `entrega/` y `contextbase/`.
- Se movió `requirements.txt` a la raíz y se eliminaron las copias duplicadas de documentos, código y logo.
- Se eliminaron `LEEME.md` y `GUIA_RAPIDA.txt`; el README de la raíz concentra el uso.
- Se inicializó ContextBase v1.4.0 y se inyectaron las reglas para agentes.
- Se reemplazaron los documentos genéricos de ContextBase por la memoria real del proyecto.
- Se dejó un único `README.md` breve en la raíz.
- Se actualizaron las rutas de `entrega/HASHES.txt`.
- Se verificó el motor desde `app/` y el EXE desde `entrega/` después de mover los archivos.

### 2026-11-10: Entrega de la versión 1.0

- Se generó `entrega/ReemplazadorLogoPDF.exe` con PyInstaller 6.22.3.
- Se incluyó `newlogo.jpg` dentro del EXE y se dejó una copia externa en `entrega/`.
- Se documentó el flujo de uso, los límites y la verificación.
- Se publicó `entrega/ejemplo/cambiar_logo_nuevo.pdf` como muestra.
- Se agregó `entrega/ejemplo/vista_antes_despues.png`.

### 2026-11-10: Validación sobre el PDF de 120 páginas

- Se procesó `entrada/cambiar.pdf` con 240 apariciones del logo.
- Se confirmó que la imagen antigua desaparece del contenido: 0 referencias.
- Se confirmaron 240 imágenes nuevas de 1056 × 290.
- Se comparó el texto de las 120 páginas: idéntico.
- Se compararon metadatos, marcadores y tamaños de página: idénticos.
- El tiempo de proceso fue de 5,9 s para ese archivo.

### 2026-11-10: Interfaz y procesamiento por lotes

- Se creó la interfaz Tkinter con lista de archivos, vista previa, modo "Detalle" y barra de progreso.
- Se agregó procesamiento por lotes con reporte `reporte_reemplazo.csv`.
- Se agregó la opción para reemplazar solo el encabezado o también el pie.
- Se agregó el ajuste de tamaño del logo entre 60 % y 110 %.
- Se agregó verificación de páginas y texto después de guardar.

### 2026-11-10: Motor de reemplazo

- Se analizaron las imágenes del PDF de muestra: 120 apariciones en encabezado, 120 en pie, mismo objeto de imagen.
- Se implementó la detección de imágenes pequeñas y repetidas en la zona izquierda.
- Se implementó el borrado de las operaciones de dibujo del logo anterior.
- Se implementó la inserción del logo nuevo conservando el ancho y centrando verticalmente.
- Se agregó un respaldo con parche blanco para imágenes dentro de formularios XObject.
- Se agregó la limpieza de recursos sin uso después del reemplazo.

---

## Cambios por hacer

- Procesar los 30 PDF reales y revisar el reporte del lote.
- Abrir una muestra de los PDF de salida en un lector externo.
- Agregar pruebas automáticas para el motor.
- Evaluar la firma digital del EXE si se distribuye fuera del equipo.

---

*Regla: cada cambio de código debe registrarse aquí con fecha y actualizar `tasklist.md`.*
