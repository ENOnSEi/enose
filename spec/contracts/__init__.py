from .processor import SignalProcessorProtocol
from .extractor import HandcraftedExtractorProtocol, SignalExtractorProtocol
from .classifier import ClassifierProtocol

__all__ = [
    "SignalProcessorProtocol",
    "HandcraftedExtractorProtocol",
    "SignalExtractorProtocol",
    "ClassifierProtocol",
]
