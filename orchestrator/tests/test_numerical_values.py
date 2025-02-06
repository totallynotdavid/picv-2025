import pytest

from orchestrator.core.calculator import TsunamiCalculator
from orchestrator.models.schemas import EarthquakeInput


@pytest.fixture(scope="module")
def calculator():
    return TsunamiCalculator()


@pytest.fixture(scope="module")
def input_data():
    # todo: 'dia' is a string in our schema
    return EarthquakeInput(
        Mw=9.0, h=12.0, lat0=56.0, lon0=-156.0, hhmm="0000", dia="23"
    )


expected_basic = {
    "length": 575.439937,  # L (km)
    "width": 144.543977,  # W (km)
    "seismic_moment": 3.981072e22,  # M0 (N*m)
    "dislocation": 10.636224,  # D (m)
    "azimuth": 247.0,  # Focal mechanism strike (deg)
    "dip": 18.0,  # Dip (deg)
    "distance_to_coast": 10439.472791,  # (km)
}

expected_rect_params = {
    "L1": 575439.937337,  # in m
    "W1": 137469.491288,  # in m
    "beta": 13.435833,  # in degrees
    "alfa": -23.0,  # in degrees
    "h1": 591632.472501,  # in m
    "a1": -49.150481,  # in km
    "b1": 291.704432,  # in km
    "xo": -153.348142,  # longitude
    "yo": 56.446823,  # latitude
}

expected_corners = [
    (-153.348142, 56.446823),
    (-158.112445, 54.424496),
    (-158.595568, 55.562662),
    (-153.831264, 57.584989),
    (-153.348142, 56.446823),
]


@pytest.fixture(scope="module")
def calc_result(calculator, input_data):
    return calculator.calculate_earthquake_parameters(input_data)


@pytest.mark.parametrize("param,expected", list(expected_basic.items()))
def test_basic_parameters(calc_result, param, expected):
    value = getattr(calc_result, param)
    assert value == pytest.approx(expected, rel=1e-6), f"Mismatch in {param}"


@pytest.mark.parametrize("param,expected", list(expected_rect_params.items()))
def test_rectangle_parameters(calc_result, param, expected):
    rect_params = calc_result.rectangle_parameters
    assert rect_params[param] == pytest.approx(expected, rel=1e-6), (
        f"Mismatch in rectangle parameter: {param}"
    )


@pytest.mark.parametrize("idx,expected_corner", list(enumerate(expected_corners)))
def test_rectangle_corners(calc_result, idx, expected_corner):
    computed_corner = calc_result.rectangle_corners[idx]
    assert computed_corner["lon"] == pytest.approx(expected_corner[0], rel=1e-6), (
        f"Corner {idx} longitude mismatch"
    )
    assert computed_corner["lat"] == pytest.approx(expected_corner[1], rel=1e-6), (
        f"Corner {idx} latitude mismatch"
    )


def test_focal_mechanism(calc_result):
    # Focal mechanism values are already tested in basic_parameters,
    # but added one more here for completeness
    assert calc_result.azimuth == pytest.approx(expected_basic["azimuth"], rel=1e-6)
    assert calc_result.dip == pytest.approx(expected_basic["dip"], rel=1e-6)


if __name__ == "__main__":
    pytest.main([__file__])
