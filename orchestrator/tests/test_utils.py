import numpy as np
import pytest

from orchestrator.utils.geo import (
    calculate_distance_to_coast,
    determine_epicenter_location,
    determine_tsunami_warning,
    format_arrival_time,
)


def test_calculate_distance_to_coast():
    coast_points = np.array([[-70.0, -20.0], [-71.0, -21.0]])
    distance = calculate_distance_to_coast(coast_points, -70.5, -20.5)
    assert isinstance(distance, float)
    assert distance > 0


def test_format_arrival_time():
    formatted_time = format_arrival_time(14.5, "15")
    assert isinstance(formatted_time, str)
    assert ":" in formatted_time

    # Test day rollover
    rollover_time = format_arrival_time(25.5, "15")
    assert rollover_time.split()[0].startswith("01")


@pytest.mark.parametrize(
    "Mw,h,h0,dist_min,expected",
    [
        (7.5, 30, -100, 10, "Probable Tsunami pequeno y local"),
        (8.9, 30, -100, 10, "Genera un Tsunami grande y destructivo"),
        (7.0, 70, -100, 10, "El epicentro esta en el Mar y NO genera Tsunami"),
        (6.5, 30, -100, 10, "El epicentro esta en el Mar y NO genera Tsunami"),
    ],
)
def test_determine_tsunami_warning(Mw, h, h0, dist_min, expected):
    warning = determine_tsunami_warning(Mw, h, h0, dist_min)
    assert warning == expected


@pytest.mark.parametrize(
    "h0,dist_min,expected",
    [
        (100, 60, "tierra"),
        (100, 30, "tierra cerca de costa"),
        (-100, 10, "mar"),
    ],
)
def test_determine_epicenter_location(h0, dist_min, expected):
    location = determine_epicenter_location(h0, dist_min)
    assert location == expected
