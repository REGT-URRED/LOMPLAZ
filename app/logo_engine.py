"""Motor de reemplazo de logos en PDF.

Detecta una imagen pequeña y repetida en la zona izquierda del encabezado o del
pie de página, elimina sus instrucciones de dibujo y coloca en su lugar el logo
nuevo, conservando el resto del contenido y el número de páginas.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

import pymupdf
from PIL import Image


class LogoEngineError(Exception):
    """Error controlado del motor."""


class PdfEncryptedError(LogoEngineError):
    """El PDF requiere contraseña."""


class LogoNotFoundError(LogoEngineError):
    """No se encontró un logo candidato."""


@dataclass(frozen=True)
class Placement:
    page: int
    xref: int
    digest: bytes
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float

    @property
    def rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(self.bbox)

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def is_header(self) -> bool:
        return self.bbox[1] <= self.page_height * 0.22

    @property
    def is_footer(self) -> bool:
        return self.bbox[1] >= self.page_height * 0.72


@dataclass
class LogoAsset:
    path: Path
    width: int
    height: int
    aspect: float
    original_path: Path


@dataclass
class Detection:
    source: Path
    page_count: int
    selected: list[Placement]
    group: list[Placement]
    method: str
    confidence: float
    header_count: int
    footer_count: int
    logo_width: float
    logo_height: float
    warnings: list[str] = field(default_factory=list)

    @property
    def pages_with_logo(self) -> int:
        return len({p.page for p in self.group})

    @property
    def replacements(self) -> int:
        return len(self.selected)


@dataclass
class ReplaceResult:
    source: Path
    output: Path
    page_count: int
    replacements: int
    header_replacements: int
    footer_replacements: int
    pages_with_removal: int
    old_removed: bool
    verified: bool
    elapsed: float
    warnings: list[str] = field(default_factory=list)


ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


# ---------------------------------------------------------------------------
# Logo nuevo
# ---------------------------------------------------------------------------


def load_logo_asset(path: str | Path) -> LogoAsset:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise LogoEngineError(f"No existe el logo nuevo: {p}")
    try:
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            width, height = im.size
            if width < 8 or height < 8:
                raise LogoEngineError("El logo nuevo es demasiado pequeño.")
            aspect = width / height
    except LogoEngineError:
        raise
    except Exception as exc:
        raise LogoEngineError(f"No se pudo leer el logo nuevo: {exc}") from exc

    # PyMuPDF inserta de forma fiable PNG y JPEG. Los demás formatos se
    # convierten a PNG en una carpeta temporal administrada por el llamador.
    if p.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise LogoEngineError(
            "Usa un logo en PNG o JPG. Otros formatos deben convertirse antes."
        )
    return LogoAsset(
        path=p, width=width, height=height, aspect=aspect, original_path=p
    )


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------


def _collect_placements(doc: pymupdf.Document) -> list[Placement]:
    """Todas las imágenes visibles, en una sola pasada por el documento."""
    placements: list[Placement] = []
    seen: set[tuple] = set()
    for pno, page in enumerate(doc):
        page_rect = page.rect
        for info in page.get_image_info(xrefs=True):
            bbox = pymupdf.Rect(info["bbox"])
            if bbox.is_empty or bbox.width <= 0 or bbox.height <= 0:
                continue
            visible = bbox & page_rect
            if visible.is_empty:
                continue
            if visible.get_area() < bbox.get_area() * 0.20:
                continue
            key = (
                pno,
                int(info["xref"]),
                round(bbox.x0, 2),
                round(bbox.y0, 2),
                round(bbox.x1, 2),
                round(bbox.y1, 2),
            )
            if key in seen:
                continue
            seen.add(key)
            placements.append(
                Placement(
                    page=pno,
                    xref=int(info["xref"]),
                    digest=bytes(info["digest"]),
                    bbox=(bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                    page_width=page_rect.width,
                    page_height=page_rect.height,
                )
            )
    return placements


def _looks_like_logo(p: Placement) -> bool:
    """Filtro geométrico para candidatos: pequeño y en la mitad izquierda."""
    if p.width < 8 or p.height < 3:
        return False
    if p.width > p.page_width * 0.42 or p.height > p.page_height * 0.20:
        return False
    if p.bbox[0] < -1 or p.bbox[2] > p.page_width * 0.62:
        return False
    aspect = p.width / p.height
    return 0.8 <= aspect <= 22


def _group_by_digest(placements: Sequence[Placement]) -> dict[bytes, list[Placement]]:
    groups: dict[bytes, list[Placement]] = defaultdict(list)
    for p in placements:
        groups[p.digest].append(p)
    return groups


def _coverage(group: Sequence[Placement], page_count: int, kind: str) -> float:
    if kind == "header":
        pages = {p.page for p in group if p.is_header}
    elif kind == "footer":
        pages = {p.page for p in group if p.is_footer}
    else:
        pages = {p.page for p in group}
    return len(pages) / max(page_count, 1)


def _candidate_score(group: Sequence[Placement], page_count: int) -> tuple:
    header = _coverage(group, page_count, "header")
    footer = _coverage(group, page_count, "footer")
    total = _coverage(group, page_count, "all")
    widths = sorted(p.width for p in group)
    median_width = widths[len(widths) // 2] if widths else 0
    # Prioriza el encabezado; el pie sirve como desempate.
    return (header, total, footer, -median_width)


def _is_good_candidate(group: Sequence[Placement], page_count: int) -> bool:
    if not group:
        return False
    header = _coverage(group, page_count, "header")
    footer = _coverage(group, page_count, "footer")
    needed = 1.0 if page_count == 1 else 0.35
    if page_count == 1:
        return bool(header or footer)
    return header >= needed or footer >= needed


def detect_logo(
    doc: pymupdf.Document, include_footer: bool = True
) -> Detection:
    page_count = doc.page_count
    if page_count == 0:
        raise LogoEngineError("El PDF no contiene páginas.")
    placements = _collect_placements(doc)
    if not placements:
        raise LogoNotFoundError(
            "No se encontraron imágenes en el PDF. "
            "Es posible que el logo sea vectorial o que el PDF esté escaneado."
        )
    candidates_all = [p for p in placements if _looks_like_logo(p)]
    if not candidates_all:
        raise LogoNotFoundError(
            "No se encontraron imágenes pequeñas en la zona izquierda. "
            "Es posible que el logo sea vectorial o que el PDF esté escaneado."
        )

    groups = _group_by_digest(candidates_all)
    candidates = [g for g in groups.values() if _is_good_candidate(g, page_count)]

    method = "imagen repetida"
    if candidates:
        group = max(candidates, key=lambda g: _candidate_score(g, page_count))
        target_digests = {group[0].digest}
        group_all = [p for p in placements if p.digest in target_digests]
    else:
        # Respaldo: agrupa por posición y tamaño. Sirve cuando el generador
        # recompone la misma imagen en objetos distintos.
        by_geometry: dict[tuple, list[Placement]] = defaultdict(list)
        for p in candidates_all:
            key = (
                int(round(p.bbox[0] / 2)),
                int(round(p.bbox[1] / 2)),
                int(round(p.width / 2)),
                int(round(p.height / 2)),
            )
            by_geometry[key].append(p)
        geo_candidates = [
            g for g in by_geometry.values() if _is_good_candidate(g, page_count)
        ]
        if not geo_candidates:
            raise LogoNotFoundError(
                "No se encontró un logo repetido en la zona izquierda. "
                "Revisa que el PDF tenga el logo como imagen y que se repita en varias páginas."
            )
        cluster = max(geo_candidates, key=lambda g: _candidate_score(g, page_count))
        target_digests = {p.digest for p in cluster}
        group_all = [p for p in placements if p.digest in target_digests]
        group = cluster
        method = "posición repetida"

    if not group_all:
        raise LogoNotFoundError(
            "Se detectó el logo, pero no se pudieron leer sus apariciones."
        )

    if include_footer:
        selected = list(group_all)
    else:
        selected = [p for p in group_all if p.is_header]

    if not selected:
        raise LogoNotFoundError(
            "Se detectó el logo, pero no quedaron apariciones para reemplazar."
        )

    header_count = sum(1 for p in selected if p.is_header)
    footer_count = sum(1 for p in selected if p.is_footer)
    pages_with_logo = len({p.page for p in group_all})
    confidence = pages_with_logo / page_count

    widths = sorted(p.width for p in group_all)
    heights = sorted(p.height for p in group_all)
    logo_width = widths[len(widths) // 2]
    logo_height = heights[len(heights) // 2]

    warnings: list[str] = []
    if page_count > 2 and pages_with_logo < page_count:
        warnings.append(
            f"El logo aparece en {pages_with_logo} de {page_count} páginas."
        )
    if footer_count == 0 and include_footer:
        warnings.append("No se detectó una aparición en el pie de página.")
    if method == "posición repetida":
        warnings.append(
            "Se detectó por posición y tamaño, no por huella exacta de la imagen."
        )
    if page_count == 1:
        warnings.append(
            "El PDF tiene una sola página: confirma visualmente el resultado."
        )

    return Detection(
        source=Path(doc.name or ""),
        page_count=page_count,
        selected=selected,
        group=group_all,
        method=method,
        confidence=confidence,
        header_count=header_count,
        footer_count=footer_count,
        logo_width=logo_width,
        logo_height=logo_height,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Geometria y limpieza
# ---------------------------------------------------------------------------


def _fit_rect(
    placement: Placement,
    page_rect: pymupdf.Rect,
    aspect: float,
    scale: float = 1.0,
) -> pymupdf.Rect:
    old = placement.rect
    width = old.width * max(0.4, min(1.5, scale))
    height = width / max(aspect, 0.1)

    max_height = page_rect.height * 0.18
    if height > max_height:
        height = max_height
        width = height * aspect

    x0 = old.x0
    if x0 + width > page_rect.x1 - 6:
        x0 = max(page_rect.x0 + 6, page_rect.x1 - 6 - width)

    center_y = (old.y0 + old.y1) / 2
    y0 = center_y - height / 2
    y1 = y0 + height
    top_limit = page_rect.y0 + 6
    bottom_limit = page_rect.y1 - 6
    if y0 < top_limit:
        y0 = top_limit
        y1 = y0 + height
    if y1 > bottom_limit:
        y1 = bottom_limit
        y0 = y1 - height
    return pymupdf.Rect(x0, y0, x0 + width, y1)


def _remove_draw_ops(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    names: Iterable[str],
) -> bool:
    """Quita las operaciones /Nombre Do del contenido de la página.

    Devuelve True si al menos una operacion fue eliminada. Las llamadas q/Q y
    la matriz cm pueden quedar sin efecto; son inofensivas.
    """
    clean_names = [n for n in names if n]
    if not clean_names:
        return False
    changed_any = False
    for xref in page.get_contents():
        try:
            data = doc.xref_stream(xref)
        except Exception:
            continue
        new_data = data
        for name in clean_names:
            pattern = rb"\s*/" + re.escape(name.encode("latin-1", "ignore")) + rb"\s+Do\b"
            new_data, n = re.subn(pattern, b"", new_data)
            if n:
                changed_any = True
        if new_data != data:
            doc.update_stream(xref, new_data)
    return changed_any


def _cover_rect(
    page: pymupdf.Page, old_rects: Sequence[pymupdf.Rect], new_rects: Sequence[pymupdf.Rect]
) -> pymupdf.Rect | None:
    rects = list(old_rects) + list(new_rects)
    if not rects:
        return None
    cover = pymupdf.Rect(rects[0])
    for r in rects[1:]:
        cover |= r
    cover = pymupdf.Rect(cover.x0 - 1, cover.y0 - 1, cover.x1 + 1, cover.y1 + 1)
    cover &= page.rect
    return cover if not cover.is_empty else None


def _page_has_white_background(page: pymupdf.Page, rect: pymupdf.Rect) -> bool:
    """Comprueba una franja exterior para decidir si el fondo es blanco."""
    try:
        sample = pymupdf.Rect(
            max(page.rect.x0, rect.x0 - 8),
            max(page.rect.y0, rect.y0 - 3),
            min(page.rect.x1, rect.x0 + max(4, rect.width * 0.5)),
            max(page.rect.y0 + 1, rect.y0 - 1),
        )
        if sample.is_empty:
            return True
        pix = page.get_pixmap(dpi=72, clip=sample, alpha=False)
        if pix.width == 0 or pix.height == 0:
            return True
        data = pix.samples
        n = pix.n
        total = 0
        white = 0
        for i in range(0, len(data), n):
            r, g, b = data[i], data[i + 1], data[i + 2]
            total += 1
            if r > 245 and g > 245 and b > 245:
                white += 1
        return total == 0 or white / total > 0.85
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Proceso principal
# ---------------------------------------------------------------------------


def _text_fingerprints(doc: pymupdf.Document) -> list[str]:
    result: list[str] = []
    for page in doc:
        try:
            text = page.get_text("text")
        except Exception:
            text = ""
        result.append(hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest())
    return result


def replace_pdf(
    source: str | Path,
    output: str | Path,
    logo: LogoAsset,
    *,
    include_footer: bool = True,
    scale: float = 1.0,
    verify: bool = True,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
) -> ReplaceResult:
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if source == output:
        raise LogoEngineError("El archivo de salida no puede ser el mismo PDF de entrada.")
    if not source.is_file():
        raise LogoEngineError(f"No existe el PDF: {source}")

    start = time.perf_counter()
    doc: pymupdf.Document | None = None
    tmp_path: Path | None = None
    warnings: list[str] = []
    try:
        doc = pymupdf.open(source)
        if doc.needs_pass:
            raise PdfEncryptedError(
                "El PDF está protegido con contraseña. Quita la protección antes de procesarlo."
            )
        if doc.page_count == 0:
            raise LogoEngineError("El PDF no contiene páginas.")

        detection = detect_logo(doc, include_footer=include_footer)
        warnings.extend(detection.warnings)
        page_count = doc.page_count
        before_text = _text_fingerprints(doc) if verify else []

        # Todas las apariciones del mismo objeto se reemplazan para no dejar
        # copias antiguas ocultas o en zonas de la página no previstas.
        all_group = detection.group
        target_xrefs = {p.xref for p in all_group}
        if include_footer:
            selected = list(all_group)
            direct_remove = True
        else:
            selected = [p for p in all_group if p.is_header]
            direct_remove = len(selected) == len(all_group)
            if not direct_remove:
                warnings.append(
                    "Se conserva el logo del pie porque la opción está desactivada."
                )

        by_page_selected: dict[int, list[Placement]] = defaultdict(list)
        for p in selected:
            by_page_selected[p.page].append(p)

        removed_pages = 0
        fallback_pages = 0
        processed_pages = 0

        for pno, page in enumerate(doc):
            if cancel and cancel():
                raise LogoEngineError("Proceso cancelado por el usuario.")
            page_selected = by_page_selected.get(pno, [])
            if not page_selected:
                continue

            page_rect = page.rect
            if page.rotation:
                warnings.append(
                    f"La página {pno + 1} está rotada; revisa la vista previa."
                )

            # Nombres de recurso que dibujan el logo viejo en esta página.
            names: set[str] = set()
            try:
                for img in page.get_images(full=True):
                    if img and img[0] in target_xrefs and len(img) > 7 and img[7]:
                        names.add(str(img[7]))
            except Exception:
                names = set()

            removable = False
            if direct_remove and names:
                # Se comprueba antes de insertar para no dejar la página sin
                # logo si el contenido está dentro de un formulario XObject.
                for xref in page.get_contents():
                    try:
                        data = doc.xref_stream(xref)
                    except Exception:
                        continue
                    for name in names:
                        pattern = (
                            rb"\s*/"
                            + re.escape(name.encode("latin-1", "ignore"))
                            + rb"\s+Do\b"
                        )
                        if re.search(pattern, data):
                            removable = True
                            break
                    if removable:
                        break

            new_rects: list[pymupdf.Rect] = []
            old_rects: list[pymupdf.Rect] = []
            for p in page_selected:
                rect = _fit_rect(p, page_rect, logo.aspect, scale)
                new_rects.append(rect)
                old_rects.append(p.rect)

            # Si no se puede quitar la imagen del flujo, se tapa con el color
            # de fondo y se dibuja encima el logo nuevo.
            if not removable:
                if not _page_has_white_background(page, old_rects[0]):
                    warnings.append(
                        f"La página {pno + 1} no tiene fondo blanco; el parche puede notarse."
                    )
                cover = _cover_rect(page, old_rects, new_rects)
                if cover:
                    page.draw_rect(
                        cover,
                        color=None,
                        fill=(1, 1, 1),
                        overlay=True,
                        width=0,
                    )
                fallback_pages += 1
            else:
                removed_pages += 1

            for rect in new_rects:
                page.insert_image(
                    rect,
                    filename=str(logo.path),
                    overlay=True,
                    keep_proportion=False,
                )

            if removable:
                _remove_draw_ops(doc, page, names)

            try:
                page.clean_contents()
            except Exception:
                pass

            processed_pages += 1
            if progress:
                progress(pno + 1, page_count, f"Página {pno + 1} de {page_count}")

        if processed_pages == 0:
            raise LogoNotFoundError("No se pudo reemplazar ninguna aparición del logo.")

        output.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output.with_name(
            f".{output.stem}.{os.getpid()}.{int(time.time() * 1000)}.tmp.pdf"
        )
        doc.save(tmp_path, garbage=4, deflate=True)
        doc.close()
        doc = None
        os.replace(tmp_path, output)
        tmp_path = None

        verified = False
        if verify:
            check: pymupdf.Document | None = None
            try:
                check = pymupdf.open(output)
                if check.page_count != page_count:
                    warnings.append(
                        f"El número de páginas cambió: {page_count} -> {check.page_count}."
                    )
                else:
                    after_text = _text_fingerprints(check)
                    if before_text and after_text != before_text:
                        warnings.append(
                            "El texto extraído cambió en alguna página. Revisa el resultado."
                        )
                    else:
                        verified = True
                if direct_remove:
                    remaining = sum(
                        1
                        for page in check
                        for img in page.get_images(full=True)
                        if img and img[0] in target_xrefs
                    )
                    if remaining:
                        warnings.append(
                            f"Quedaron {remaining} referencias a la imagen antigua; revisa la vista previa."
                        )
            except Exception as exc:
                warnings.append(f"No se pudo verificar el PDF de salida: {exc}")
            finally:
                if check is not None:
                    try:
                        check.close()
                    except Exception:
                        pass

        warnings = list(dict.fromkeys(warnings))
        elapsed = time.perf_counter() - start
        return ReplaceResult(
            source=source,
            output=output,
            page_count=page_count,
            replacements=len(selected),
            header_replacements=sum(1 for p in selected if p.is_header),
            footer_replacements=sum(1 for p in selected if p.is_footer),
            pages_with_removal=removed_pages,
            old_removed=fallback_pages == 0,
            verified=verified,
            elapsed=elapsed,
            warnings=warnings,
        )
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def unique_output_path(source: Path, output_dir: Path) -> Path:
    stem = f"{source.stem}_logo_nuevo"
    candidate = output_dir / f"{stem}.pdf"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{stem}_{counter}.pdf"
        counter += 1
    return candidate


def find_pdfs(folder: str | Path, recursive: bool = False) -> list[Path]:
    root = Path(folder).expanduser().resolve()
    pattern = "**/*.pdf" if recursive else "*.pdf"
    files = [
        p
        for p in root.glob(pattern)
        if p.is_file() and "_logo_nuevo" not in p.stem.lower()
    ]
    return sorted(files, key=lambda p: p.name.lower())
