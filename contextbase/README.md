# Memoria del proyecto

Esta carpeta guarda lo que el proyecto sabe de sí mismo: objetivo, estructura, decisiones, estado, tareas y cambios. Es la fuente de contexto para cualquier persona o agente que retome el trabajo.

## Documentos

| Archivo | Contenido |
|---|---|
| `fundamentos.md` | Objetivo, alcance, estructura, funcionamiento, decisiones y reglas |
| `changelog.md` | Historial de cambios y resultados por fecha |
| `tasklist.md` | Tareas completadas y pendientes |
| `componentes.md` | Versiones, dependencias, artefactos y notas de seguridad |

## Estado vigente

| Concepto | Valor |
|---|---|
| Versión | 1.0 |
| Estado | Funcional y validada sobre el PDF de muestra |
| Entrada | `entrada/cambiar.pdf`, 120 páginas |
| Salida | `entrega/ejemplo/cambiar_logo_nuevo.pdf`, 120 páginas |
| Reemplazos | 240, repartidos en 120 de encabezado y 120 de pie |
| Repositorio | Publicado en `main`, commit `b676aa9` |
| Lote real | Pendiente: 30 PDF que todavía no están en la carpeta |

## Consulta rápida

```powershell
contextbase status
contextbase context
```

`contextbase audit` regenera `componentes.md`. En este equipo consulta el Python global, que no es el mismo runtime con el que se construyó el EXE. Para reproducir la versión 1.0, manda la tabla de `componentes.md`.

## Regla de actualización

Todo cambio de código o de entrega termina actualizando `changelog.md` y `tasklist.md`. Si cambia la estructura, una dependencia o una decisión técnica, también se actualiza `fundamentos.md`.
