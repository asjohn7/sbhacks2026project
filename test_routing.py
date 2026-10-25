from app.demo_data import build_demo_graph
from app.routing import calculate_routes, edge_cost


def test_alpha_zero_is_distance_only_cost():
    assert edge_cost({"length_m": 100, "light_score": 0.0, "confidence": 1.0}, 0) == 100


def test_light_preference_costs_less_for_bright_edges():
    alpha = 2.0
    bright = edge_cost({"length_m": 100, "light_score": 0.9, "confidence": 1}, alpha)
    dim = edge_cost({"length_m": 100, "light_score": 0.2, "confidence": 1}, alpha)
    assert bright < dim


def test_routes_have_geojson_and_metrics():
    graph, _ = build_demo_graph()
    result = calculate_routes(graph, 40.9144, -73.1270, 40.9144, -73.1180, alpha=2.5)
    for key in ("fastest", "brightest"):
        route = result[key]
        assert route["distance_m"] > 0
        assert 0 <= route["pct_well_lit"] <= 1
        assert route["geometry"]["type"] == "FeatureCollection"
        assert route["geometry"]["features"]


def test_detour_is_limited():
    graph, _ = build_demo_graph()
    result = calculate_routes(graph, 40.9128, -73.1290, 40.9160, -73.1165, alpha=3.0)
    assert result["brightest"]["distance_m"] <= result["fastest"]["distance_m"] * 1.61
