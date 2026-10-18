import pytest

from planner.domain.geo import Polyline, decode_polyline, haversine_mi, inverse_mercator_y, mercator_y, simplify_indices


def test_decode_polyline_reference_example():
    # Example from Google's encoded polyline documentation (precision 5).
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    assert pts == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_haversine_one_degree_of_latitude():
    assert haversine_mi((40, -100), (41, -100)) == pytest.approx(69.09, abs=0.05)


@pytest.fixture
def line():
    # Due north along a meridian, ~69 mi per segment, 1 hour per segment.
    pl = Polyline([(40.0, -100.0), (41.0, -100.0), (42.0, -100.0)])
    pl.cum_s = [0.0, 3600.0, 7200.0]
    return pl


def test_point_and_time_interpolation(line):
    half = line.length_mi / 2
    lat, lon = line.point_at(half)
    assert lat == pytest.approx(41.0) and lon == pytest.approx(-100.0)
    assert line.drive_seconds_at(half / 2) == pytest.approx(1800)
    assert line.distance_at_drive_seconds(5400) == pytest.approx(line.length_mi * 0.75)
    assert line.point_at(-5) == (40.0, -100.0)
    assert line.point_at(1e9) == (42.0, -100.0)


def test_slice_includes_interior_vertices(line):
    seg = line.slice(line.length_mi * 0.25, line.length_mi * 0.75)
    assert len(seg) == 3
    assert seg[0][0] == pytest.approx(40.5) and seg[1] == (41.0, -100.0) and seg[2][0] == pytest.approx(41.5)


def test_simplify_drops_collinear_points_and_keeps_corners():
    pts = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 3)]
    assert simplify_indices(pts, 0.01) == [0, 3, 4]


def test_mercator_round_trip():
    for lat in (-60, 0, 33.3, 71):
        assert inverse_mercator_y(mercator_y(lat)) == pytest.approx(lat)
