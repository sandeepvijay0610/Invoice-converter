"""
document_preprocessor.py
=========================
Piece 1 — Ingestor: Normalizes raw PDF/image inputs into a canonical list of
300 DPI PNG pages for downstream AI Worker Nodes.

Single responsibility: format normalization.
Every downstream component receives a list of ``ProcessedPage`` objects
backed by consistent 300 DPI PNG images.

Dependencies
------------
    pip install pymupdf pdf2image Pillow

``pdf2image`` additionally requires Poppler binaries:
    macOS  : brew install poppler
    Debian : apt-get install -y poppler-utils
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Generator, Optional

import fitz  # PyMuPDF
from pdf2image import convert_from_path, pdfinfo_from_path
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFSyntaxError,
)
from PIL import Image, UnidentifiedImageError

from .config import (
    NATIVE_TEXT_MIN_CHARS,
    OUTPUT_DIR,
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_PDF_EXTENSION,
    TARGET_DPI,
    TARGET_FORMAT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

class SourceType(Enum):
    """How the page content was obtained."""
    PDF_NATIVE_TEXT = auto()  # PyMuPDF text extraction (searchable PDF)
    PDF_RASTER = auto()       # pdf2image rasterization (scanned PDF)
    IMAGE_RASTER = auto()     # Direct image normalization


@dataclass(frozen=True)
class ProcessedPage:
    """
    Canonical output unit of the Ingestor stage.

    Attributes
    ----------
    page_number : int
        1-based page index within the source document.
    image_path : Path
        Absolute path to the 300 DPI PNG file on disk.
    source_type : SourceType
        Provenance metadata consumed by the Worker Node to choose the
        optimal OCR strategy.
    native_text : str | None
        Raw text extracted by PyMuPDF for PDF_NATIVE_TEXT pages; None
        for rasterized sources.
    width_px : int
        Image width in pixels at 300 DPI.
    height_px : int
        Image height in pixels at 300 DPI.
    metadata : dict
        Arbitrary key/value bag for pipeline-specific context
        (e.g. doc_id, tenant_id injected by the Orchestrator).
    """
    page_number: int
    image_path: Path
    source_type: SourceType
    native_text: Optional[str] = None
    width_px: int = 0
    height_px: int = 0
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class IngestorError(RuntimeError):
    """Base class for all Ingestor-specific failures."""


class UnsupportedFileTypeError(IngestorError):
    """Raised when the supplied file extension is not handled."""


class CorruptFileError(IngestorError):
    """Raised when a file cannot be opened or decoded."""


class EmptyDocumentError(IngestorError):
    """Raised when a document yields zero processable pages."""


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class DocumentPreprocessor:
    """
    Normalizes arbitrary PDF or image inputs into a uniform list of
    300 DPI PNG pages for the AI Worker Node.

    Usage
    -----
    Use as a context manager to ensure temp directory cleanup:

        with DocumentPreprocessor() as preprocessor:
            pages = preprocessor.process("invoice.pdf", metadata={"doc_id": "INV-001"})

    Or supply an explicit output_dir if you manage cleanup yourself:

        preprocessor = DocumentPreprocessor(output_dir="/mnt/pages")
        pages = preprocessor.process("invoice.pdf")

    Parameters
    ----------
    output_dir : str | Path | None
        Directory where normalized PNG files are written. Created if absent.
        When None a temporary directory is created and cleaned up on __exit__.
    dpi : int
        Rasterization resolution. Production pipelines should use 300.
    native_text_min_chars : int
        Minimum character count for a PDF page to be treated as native-text.
    """

    def __init__(
        self,
        output_dir: Optional[str | Path] = None,
        dpi: int = TARGET_DPI,
        native_text_min_chars: int = NATIVE_TEXT_MIN_CHARS,
    ) -> None:
        self._dpi = dpi
        self._native_text_min_chars = native_text_min_chars
        self._owns_tmp = output_dir is None

        if self._owns_tmp:
            self._output_dir = Path(tempfile.mkdtemp(prefix="ingestor_"))
            logger.debug("Ingestor using temp output dir: %s", self._output_dir)
        else:
            self._output_dir = Path(output_dir)
            self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Context manager — ensures temp dir is cleaned up
    # ------------------------------------------------------------------

    def __enter__(self) -> "DocumentPreprocessor":
        return self

    def __exit__(self, *_: object) -> None:
        if self._owns_tmp and self._output_dir.exists():
            import shutil
            shutil.rmtree(self._output_dir, ignore_errors=True)
            logger.debug("Cleaned up temp dir: %s", self._output_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        file_path: str | Path,
        metadata: Optional[dict] = None,
    ) -> list[ProcessedPage]:
        """
        Normalize *file_path* and return one ProcessedPage per document page.

        Parameters
        ----------
        file_path : str | Path
            Path to a PDF or image file.
        metadata : dict | None
            Caller-supplied context forwarded to every ProcessedPage.
            Must include ``doc_id`` for downstream pipeline stages.

        Returns
        -------
        list[ProcessedPage]
            Ordered list of normalized pages. Always non-empty on success.

        Raises
        ------
        FileNotFoundError, UnsupportedFileTypeError, CorruptFileError,
        EmptyDocumentError
        """
        file_path = Path(file_path).resolve()
        metadata = metadata or {}

        if "doc_id" not in metadata:
            logger.warning(
                "No 'doc_id' in metadata for '%s'. Downstream stages will "
                "report doc_id='UNKNOWN'.", file_path.name
            )

        logger.info("Ingestor starting | file=%s", file_path)
        self._validate_path(file_path)

        suffix = file_path.suffix.lower()

        if suffix == SUPPORTED_PDF_EXTENSION:
            pages = self._process_pdf(file_path, metadata)
        elif suffix in SUPPORTED_IMAGE_EXTENSIONS:
            pages = self._process_image(file_path, metadata)
        else:
            raise UnsupportedFileTypeError(
                f"Extension '{suffix}' is not supported. "
                f"Accepted: {SUPPORTED_PDF_EXTENSION}, "
                f"{', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"
            )

        if not pages:
            raise EmptyDocumentError(
                f"Document produced zero processable pages: {file_path}"
            )

        logger.info("Ingestor complete | file=%s pages=%d", file_path, len(pages))
        return pages

    # ------------------------------------------------------------------
    # PDF processing
    # ------------------------------------------------------------------

    def _process_pdf(self, file_path: Path, metadata: dict) -> list[ProcessedPage]:
        try:
            doc = fitz.open(str(file_path))
        except fitz.FileDataError as exc:
            raise CorruptFileError(
                f"PyMuPDF could not open '{file_path}': {exc}"
            ) from exc
        except Exception as exc:
            raise CorruptFileError(
                f"Unexpected error opening '{file_path}': {exc}"
            ) from exc

        pages: list[ProcessedPage] = []

        with doc:
            if doc.page_count == 0:
                raise EmptyDocumentError(f"PDF has 0 pages: {file_path}")

            native_indices: list[int] = []
            raster_indices: list[int] = []

            for page_index in range(doc.page_count):
                text = doc[page_index].get_text("text").strip()
                if len(text) >= self._native_text_min_chars:
                    native_indices.append(page_index)
                else:
                    raster_indices.append(page_index)

            logger.debug(
                "PDF analysis | file=%s native=%s raster=%s",
                file_path.name, native_indices, raster_indices,
            )

            for page_index in native_indices:
                processed = self._extract_native_pdf_page(doc, page_index, file_path, metadata)
                if processed is not None:
                    pages.append(processed)

            if raster_indices:
                pages.extend(
                    self._rasterize_pdf_pages(file_path, raster_indices, metadata)
                )

        pages.sort(key=lambda p: p.page_number)
        return pages

    def _extract_native_pdf_page(
        self,
        doc: fitz.Document,
        page_index: int,
        source_path: Path,
        metadata: dict,
    ) -> Optional[ProcessedPage]:
        page_number = page_index + 1
        try:
            page = doc[page_index]
            native_text = page.get_text("text").strip()

            scale = self._dpi / 72.0
            matrix = fitz.Matrix(scale, scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)

            if pixmap.width == 0 or pixmap.height == 0:
                logger.warning(
                    "Skipping zero-dimension page | file=%s page=%d",
                    source_path.name, page_number,
                )
                return None

            out_path = self._output_path(source_path, page_number)
            pixmap.save(str(out_path))

            logger.debug(
                "Native-text page saved | page=%d size=%dx%d",
                page_number, pixmap.width, pixmap.height,
            )
            return ProcessedPage(
                page_number=page_number,
                image_path=out_path,
                source_type=SourceType.PDF_NATIVE_TEXT,
                native_text=native_text,
                width_px=pixmap.width,
                height_px=pixmap.height,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error(
                "Failed to extract native-text page | file=%s page=%d error=%s",
                source_path.name, page_number, exc,
            )
            return None

    def _rasterize_pdf_pages(
        self,
        file_path: Path,
        page_indices: list[int],
        metadata: dict,
    ) -> list[ProcessedPage]:
        # Fail fast if Poppler is missing before processing any pages
        try:
            pdfinfo_from_path(str(file_path))
        except PDFInfoNotInstalledError as exc:
            raise CorruptFileError(
                "Poppler is not installed or not on PATH. "
                "In Docker: add 'RUN apt-get install -y poppler-utils' to your Dockerfile."
            ) from exc

        pages: list[ProcessedPage] = []

        for page_index in page_indices:
            page_number = page_index + 1
            try:
                pil_images = convert_from_path(
                    str(file_path),
                    dpi=self._dpi,
                    first_page=page_number,
                    last_page=page_number,
                    fmt="png",
                    thread_count=1,
                    use_cropbox=True,
                )

                if not pil_images:
                    logger.warning(
                        "pdf2image returned no image | file=%s page=%d",
                        file_path.name, page_number,
                    )
                    continue

                pil_image = pil_images[0]

                if pil_image.width == 0 or pil_image.height == 0:
                    logger.warning(
                        "Skipping zero-dimension raster page | file=%s page=%d",
                        file_path.name, page_number,
                    )
                    continue

                out_path = self._output_path(file_path, page_number)
                pil_image.save(str(out_path), format=TARGET_FORMAT)

                logger.debug(
                    "Raster page saved | page=%d size=%dx%d",
                    page_number, pil_image.width, pil_image.height,
                )
                pages.append(ProcessedPage(
                    page_number=page_number,
                    image_path=out_path,
                    source_type=SourceType.PDF_RASTER,
                    native_text=None,
                    width_px=pil_image.width,
                    height_px=pil_image.height,
                    metadata=metadata,
                ))

            except (PDFPageCountError, PDFSyntaxError) as exc:
                logger.error(
                    "pdf2image error | file=%s page=%d error=%s",
                    file_path.name, page_number, exc,
                )
            except Exception as exc:
                logger.error(
                    "Unexpected rasterization error | file=%s page=%d error=%s",
                    file_path.name, page_number, exc,
                )

        return pages

    # ------------------------------------------------------------------
    # Image processing
    # ------------------------------------------------------------------

    def _process_image(self, file_path: Path, metadata: dict) -> list[ProcessedPage]:
        try:
            img = Image.open(str(file_path))
            img.verify()
        except UnidentifiedImageError as exc:
            raise CorruptFileError(
                f"Pillow cannot identify image format: '{file_path}'"
            ) from exc
        except Exception as exc:
            raise CorruptFileError(
                f"Image file appears corrupt or unreadable: '{file_path}': {exc}"
            ) from exc

        # Re-open after verify() — PIL invalidates the handle after verify
        try:
            img = Image.open(str(file_path))
        except Exception as exc:
            raise CorruptFileError(
                f"Failed to re-open image after verification: '{file_path}': {exc}"
            ) from exc

        img = self._normalize_image(img, file_path)

        if img.width == 0 or img.height == 0:
            raise EmptyDocumentError(
                f"Image has zero dimensions after normalization: '{file_path}'"
            )

        out_path = self._output_path(file_path, page_number=1)
        img.save(str(out_path), format=TARGET_FORMAT, dpi=(self._dpi, self._dpi))

        logger.debug(
            "Image normalized | size=%dx%d dpi=%d", img.width, img.height, self._dpi
        )

        return [ProcessedPage(
            page_number=1,
            image_path=out_path,
            source_type=SourceType.IMAGE_RASTER,
            native_text=None,
            width_px=img.width,
            height_px=img.height,
            metadata=metadata,
        )]

    def _normalize_image(self, img: Image.Image, source_path: Path) -> Image.Image:
        """Convert to RGB and rescale to target DPI if needed."""
        if img.mode != "RGB":
            logger.debug("Converting %s→RGB | file=%s", img.mode, source_path.name)
            img = img.convert("RGB")

        source_dpi = self._read_dpi(img)
        if source_dpi and source_dpi != self._dpi:
            scale = self._dpi / source_dpi
            new_w = max(1, round(img.width * scale))
            new_h = max(1, round(img.height * scale))
            logger.debug(
                "Rescaling %d→%d DPI | %dx%d → %dx%d | file=%s",
                source_dpi, self._dpi, img.width, img.height,
                new_w, new_h, source_path.name,
            )
            img = img.resize((new_w, new_h), Image.LANCZOS)

        return img

    @staticmethod
    def _read_dpi(img: Image.Image) -> Optional[float]:
        try:
            dpi_info = img.info.get("dpi")
            if dpi_info:
                return float(dpi_info[0])
        except (TypeError, IndexError, ValueError):
            pass
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_path(file_path: Path) -> None:
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: '{file_path}'")
        if not file_path.is_file():
            raise ValueError(f"Input path is not a regular file: '{file_path}'")
        if not os.access(file_path, os.R_OK):
            raise PermissionError(f"Input file is not readable: '{file_path}'")

    def _output_path(self, source_path: Path, page_number: int) -> Path:
        """Format: <output_dir>/<stem>_page<N:04d>.png"""
        filename = f"{source_path.stem}_page{page_number:04d}.png"
        return self._output_dir / filename
