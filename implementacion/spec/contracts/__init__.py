from .processor import SignalProcessorProtocol
from .extractor import HandcraftedExtractorProtocol, SignalExtractorProtocol
from .classifier import ClassifierProtocol
from .reporter import ReportGeneratorProtocol

__all__ = [
    "SignalProcessorProtocol",
    "HandcraftedExtractorProtocol",
    "SignalExtractorProtocol",
    "ClassifierProtocol",
    "ReportGeneratorProtocol",
]
