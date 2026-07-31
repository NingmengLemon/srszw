"""Compatibility namespace for legacy project export helpers."""

from .config import Config
from .converter import ConversionError, SRSZWConverter
from .utils import generate_from_string

__version__ = "0.1.0"
__all__ = ["Config", "ConversionError", "SRSZWConverter", "generate_from_string"]
