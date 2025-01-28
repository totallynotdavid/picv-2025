from dataclasses import dataclass


@dataclass
class SourceParameters:
    """Earthquake source parameters."""

    length: float
    width: float
    moment: float
    displacement: float


@dataclass
class TsunamiAnalysis:
    """Results of tsunami analysis."""

    source_params: SourceParameters
    latitude: float
    longitude: float
    plot_url: str
    title: str
    coast_distance: float
    epicenter_depth: float
