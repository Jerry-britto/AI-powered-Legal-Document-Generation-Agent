"""
Document Parser utilities using LlamaParse (llama_cloud SDK) with robust fallback mechanisms.
"""

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple
from dotenv import load_dotenv
import pypdf
from llama_cloud import LlamaCloud

load_dotenv()
logger = logging.getLogger(__name__)


ARTIFACTS_DIR = Path("artifacts")


def _parse_path(file_path: Path, use_llama_parse: bool = True) -> Tuple[str, str]:
    """
    Parses a legal document (PDF, TXT, MD) into markdown/text.
    Uses LlamaParse (via llama_cloud SDK) if available, with robust fallbacks.
    """
    path = file_path

    # If it's already a text/markdown file, read directly
    if path.suffix.lower() in [".txt", ".md"]:
        return path.read_text(encoding="utf-8"), "text"

    # If PDF and LlamaParse requested
    llama_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if use_llama_parse and llama_key and path.suffix.lower() == ".pdf":
        try:
            logger.info("Attempting document parsing via LlamaParse (llama_cloud)...")

            client = LlamaCloud(api_key=llama_key)
            with open(path, "rb") as f:
                uploaded_file = client.files.create(file=f, purpose="parse")
            
            result = client.parsing.parse(
                file_id=uploaded_file.id,
                tier="agentic",
                version="latest",
                expand=["markdown"]
            )
            
            if result.markdown and result.markdown.pages:
                extracted_pages = [page.markdown for page in result.markdown.pages]
                full_md = "\n\n".join(extracted_pages)
                if len(full_md.strip()) > 50:
                    logger.info("Successfully parsed document via LlamaParse.")
                    return full_md, "llama_parse"
        except Exception as e:
            logger.warning(f"LlamaParse parsing encountered issue ({e}). Falling back to local parser...")

    # Fallback 1: Local PDF reader (pypdf or pdfplumber if available)
    try:
        reader = pypdf.PdfReader(file_path)
        extracted = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                extracted.append(page_text)
        combined = "\n\n".join(extracted)
        if len(combined.strip()) > 50:
            return combined, "pypdf"
    except Exception as exc:
        logger.warning("Local PDF parsing failed for %s: %s", path, exc)

    raise RuntimeError(f"Unable to parse document at {path}")


def parse_case_document(file_path: str, use_llama_parse: bool = True) -> str:
    """Parse a document from disk without applying the cache."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document file not found at: {file_path}")
    text, _ = _parse_path(path, use_llama_parse=use_llama_parse)
    return text


def ingest_case_document(
    content: bytes,
    source_name: str,
    use_llama_parse: bool = True,
    artifacts_dir: Path = ARTIFACTS_DIR,
) -> Tuple[str, Dict[str, Any]]:
    """Parse and cache the complete source document by content hash."""
    if not content:
        raise ValueError("The uploaded document is empty.")

    digest = hashlib.sha256(content).hexdigest()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    cache_path = artifacts_dir / f"parsed_{digest}.md"
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8").strip()
        return text, {
            "source_name": source_name,
            "source_hash": digest,
            "cache_hit": True,
            "cache_path": str(cache_path),
            "parser": "cache",
            "character_count": len(text),
        }

    suffix = Path(source_name).suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix) as temp_file:
        temp_file.write(content)
        temp_file.flush()
        text, parser_name = _parse_path(Path(temp_file.name), use_llama_parse=use_llama_parse)

    text = text.strip()
    if not text:
        raise RuntimeError(f"Unable to extract text from uploaded document '{source_name}'.")
    cache_path.write_text(text + "\n", encoding="utf-8")
    return text, {
        "source_name": source_name,
        "source_hash": digest,
        "cache_hit": False,
        "cache_path": str(cache_path),
        "parser": parser_name,
        "character_count": len(text),
    }
