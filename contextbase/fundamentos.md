# Fundamentos del Proyecto: Reemplazador de logo PDF

## 1. Objetivo

Sustituir el logo antiguo de iVerificate por el logo de Turnitin en un lote de reportes PDF, sin editar cada página a mano. El logo aparece en la esquina superior izquierda y en el pie de cada página. La herramienta debe detectarlo, eliminarlo e insertar el logo nuevo en la misma posición.

El caso de uso original es un lote de 30 archivos de aproximadamente 120 páginas cada uno. El PDF de muestra disponible en `entrada/cambiar.pdf` tiene 120 páginas y 240 apariciones del logo.

## 2. Estado actual

| Concepto | Valor |
|---|---|
| Versión de la aplicación | 1.0 |
| Estado | Funcional y validada sobre el PDF de muestra |
| Entrada de prueba | `entrada/cambiar.pdf` (120 páginas, 1 429 667 bytes) |
| Salida de prueba | `entrega/ejemplo/cambiar_logo_nuevo.pdf` (120 páginas, 1 143 860 bytes) |
| Reemplazos en la prueba | 240: 120 en encabezado y 120 en pie |
| Verificación | Texto, metadatos, marcadores y tamaños de página sin cambios; 0 referencias a la imagen antigua |
| Tiempo observado | 5,9 s en la validación inicial; 8,6 s en la prueba posterior a la reorganización |
| Repositorio Git | Publicado en `main`; commit inicial `b676aa9` |
| Lote real de 30 archivos | Pendiente: los archivos no están en esta carpeta |

## 3. Estructura

```text
marco/
├── README.md                  guía breve de uso
├── requirements.txt           dependencias Python
├── app/                       código fuente y recursos de compilación
│   ├── app_gui.py             interfaz Tkinter
│   ├── logo_engine.py         detección, reemplazo y verificación
│   ├── reemplazador_logo.py   lanzador
│   └── assets/                iconos de la aplicación
├── entrada/                   PDF original de muestra, no versionado
├── entrega/                   EXE y resultados locales
│   ├── ReemplazadorLogoPDF.exe
│   ├── newlogo.jpg
│   ├── HASHES.txt
│   └── ejemplo/               PDF procesado, reporte y comparación visual
└── contextbase/               esta memoria técnica
```

Regla de organización: el código vive en `app/`, los insumos en `entrada/`, los entregables en `entrega/` y la memoria en `contextbase/`. No se duplican binarios ni documentos entre carpetas.

## 4. Flujo de uso

1. Abrir `entrega/ReemplazadorLogoPDF.exe`.
2. Agregar una carpeta o varios PDF.
3. Confirmar el logo nuevo. El EXE lo busca junto a sí mismo y también lo lleva incluido.
4. Analizar el primer archivo y revisar la vista "Detalle".
5. Procesar el lote.
6. Revisar `reporte_reemplazo.csv` y abrir algunos PDF de salida.

Cada salida se llama `nombre_original_logo_nuevo.pdf`. Si el nombre ya existe, se agrega un número. Los originales no se modifican.

## 5. Cómo funciona

1. PyMuPDF recorre las imágenes visibles de cada página en una sola pasada.
2. El motor filtra las imágenes pequeñas de la zona izquierda y las agrupa por contenido. Si no hay una huella exacta repetida, agrupa por posición y tamaño.
3. Elige el grupo con mayor presencia en el encabezado. El pie se incluye si la opción está activa.
4. Calcula el rectángulo del logo nuevo a partir del ancho del logo antiguo y la proporción de `newlogo.jpg`. Lo centra verticalmente en la posición anterior.
5. Elimina las operaciones `/Nombre Do` que dibujan la imagen antigua en el contenido de la página.
6. Inserta el logo nuevo y limpia los objetos que quedaron sin uso.
7. Si la imagen antigua está dentro de un formulario XObject y no se puede borrar del flujo, cubre la zona con blanco y dibuja el logo encima. El reporte lo advierte.
8. Verifica que el número de páginas no cambie y compara una huella del texto extraído de cada página.

## 6. Decisiones técnicas

- Se elimina la imagen antigua del contenido en lugar de dejar un parche blanco. El parche queda solo como respaldo.
- Se reemplazan encabezado y pie por defecto, porque el logo antiguo se repite en ambos.
- El ancho del logo nuevo iguala el ancho del logo detectado al 100 %. La altura se calcula con la proporción real para no deformarlo.
- El procesamiento es local. No hay llamadas a servicios externos.
- La interfaz usa Tkinter para no agregar dependencias de escritorio.
- El EXE se construye con PyInstaller en modo un solo archivo. Se excluyen pandas, openpyxl, lxml, matplotlib y scipy para reducir el tamaño.
- El ejecutable no está firmado digitalmente.

## 7. Reglas de mantenimiento

1. Todo cambio de código termina actualizando `contextbase/changelog.md` y `contextbase/tasklist.md`. Si cambia la estructura o una decisión, también este documento.
2. No se edita `entrada/cambiar.pdf`; es la muestra de referencia.
3. No se agregan binarios nuevos a `app/`. Los entregables van en `entrega/`.
4. La documentación y los registros se escriben en español.
5. Después de un cambio se ejecuta `contextbase audit` y se revisa `contextbase/componentes.md`.
6. Antes de publicar un cambio del EXE se actualiza `entrega/HASHES.txt`.
7. Los PDF con datos personales no se versionan. `.gitignore` excluye `entrada/*.pdf`, `entrega/ejemplo/*.pdf` y el EXE.
8. El push a GitHub requiere autorización explícita del usuario. Preparar el commit no autoriza el push.

### Control de versiones

- Repositorio remoto: `https://github.com/REGT-URRED/LOMPLAZ.git`.
- Autor: `REGT-URRED <U19211826@utp.edu.pe>`.
- Rama: `main`.
- El token de GitHub no se guarda en el repositorio ni en la URL del remoto.
- El EXE y los PDF de muestra quedan fuera de Git. Se pueden publicar como release o entregar aparte.
- El push inicial se completó el 2026-11-10 sobre `main`. El repositorio remoto estaba vacío y no se usó `--force`.

## 8. Comandos

Ejecutar desde la raíz:

```powershell
contextbase status
contextbase context
contextbase audit
```

Ejecutar la aplicación desde la raíz:

```powershell
python -m pip install -r requirements.txt
python app/reemplazador_logo.py
```

Reconstruir el EXE desde `app/`:

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name ReemplazadorLogoPDF --icon assets/app.ico `
  --add-data "..\entrega\newlogo.jpg;." `
  --exclude-module pandas --exclude-module openpyxl --exclude-module lxml `
  --exclude-module matplotlib --exclude-module scipy reemplazador_logo.py
```

El resultado queda en `app/dist/ReemplazadorLogoPDF.exe` y se copia a `entrega/`.

## 9. Validación realizada

| Comprobación | Resultado |
|---|---|
| Páginas de entrada y salida | 120 y 120 |
| Apariciones reemplazadas | 240 |
| Encabezado / pie | 120 / 120 |
| Imágenes antiguas restantes | 0 |
| Imágenes nuevas de 1056 × 290 | 240 |
| Texto por página | Idéntico |
| Metadatos y marcadores | Idénticos |
| Tamaños de página | Idénticos |
| PDF de salida abierto con PyMuPDF | Correcto |

La comparación visual está en `entrega/ejemplo/vista_antes_despues.png`.

## 10. Límites conocidos

- No detecta logos vectoriales ni logos dentro de una página escaneada como una sola imagen.
- No procesa PDF protegidos con contraseña.
- No busca logos en el centro ni a la derecha.
- Modificar un PDF invalida firmas digitales y cambia su hash.
- No corrige el contenido del reporte; solo cambia la imagen del logo.

## 11. Pendientes

- Procesar los 30 PDF reales cuando estén disponibles.
- Revisar una muestra de cada lote y el reporte CSV.
- Agregar pruebas automáticas para el motor.
- Evaluar la firma digital del EXE si se distribuye fuera del equipo.
