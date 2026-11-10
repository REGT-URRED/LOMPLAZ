# Componentes y seguridad preventiva

Inventario del entorno con el que se construyó y probó la versión 1.0. Fecha de verificación: 2026-11-10.

## Inventario de Componentes

- **Python / pip** — manifiesto `requirements.txt`, última modificación: 2026-11-10
  - Python 3.12.14
  - PyMuPDF 2.1
  - Pillow 12.3.0
  - PyInstaller 6.22.3, solo para reconstruir el EXE
- **Aplicación** — `app/`, interfaz Tkinter sobre Tcl-Tk 8.6
- **ContextBase CLI** — 1.4.0
- **Sistema de compilación** — Windows 11, build 10.0.26300

## Estado de Actualización

- El entorno anterior es el runtime con el que se generó `entrega/ReemplazadorLogoPDF.exe`.
- `contextbase audit` consulta el Python global del equipo y puede mostrar otras versiones. Para reproducir la versión 1.0 manda esta tabla.
- No se ejecutó `pip list --outdated` en el runtime de compilación. No hay una certificación de frescura.

## Brechas de Seguridad Detectadas

- No se ejecutó `pip-audit` ni otro escáner de vulnerabilidades. No hay certificación de seguridad.
- El EXE no tiene firma digital. Windows puede mostrar SmartScreen.
- La aplicación no abre conexiones de red y no envía archivos.
- Las dependencias se instalaron desde PyPI en el entorno de compilación.

## Artefactos

| Archivo | Tamaño | SHA-256 |
|---|---:|---|
| `entrega/ReemplazadorLogoPDF.exe` | 94 823 057 bytes | `9c9666bf570cde866d433d918552e40ba4f29ba7d5e3ba0ce3b3166679ac1a28` |
| `entrega/ejemplo/cambiar_logo_nuevo.pdf` | 1 143 860 bytes | `dc155b9fff121b992a003139b738ef97847b18f8f8613ddf2062ed2d85a0cd31` |
| `entrega/newlogo.jpg` | 25 268 bytes | `735612ebcb795decdc8625fc4ee6808d240bf35f6fb32b5e15f8f919d9fbb238` |

El EXE y el PDF de muestra no se versionan en Git. Permanecen en la copia local y están excluidos por `.gitignore` para evitar binarios pesados y datos personales.

## Exclusions del empaquetado

El EXE excluye pandas, openpyxl, lxml, matplotlib y scipy. No se usan en la aplicación y aumentaban el tamaño y el tiempo de arranque.

## Mantenimiento

Antes de publicar una versión nueva:

1. Actualizar las versiones de esta tabla.
2. Reconstruir el EXE.
3. Actualizar `entrega/HASHES.txt`.
4. Ejecutar `contextbase audit` y anotar cualquier diferencia relevante.
