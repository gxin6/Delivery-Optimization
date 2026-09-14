import gurobipy as gp
import numpy as np
import pandas as pd
import folium
from folium.plugins import BeautifyIcon

_PALETTE = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue", "darkgreen", "brown", "magenta", "darkblue", "pink"]

def reconstruct_route(solved_path: dict[tuple[int, int, int], gp.Var],
                      node_count: int,
                      vehicle: int) -> list[int]:
    result_route = [0]
    current = 0
    while True:
        next_node = None
        for j in range(node_count):
            if j != current and solved_path[current, j, vehicle].X > 0.5:
                next_node = j
                break
        if next_node is None or next_node == 0:
            result_route.append(0)
            break
        result_route.append(next_node)
        current = next_node
    return result_route

def format_time(minutes: float) -> str:
  total = int(round(minutes))
  # Assuming the starting time is 10:00 AM
  h = 10 + total // 60
  m = total % 60
  return f"{h:02d}:{m:02d}"

def vehicle_type_label(vehicle_profile: dict[str, int]) -> str:
    return "van" if vehicle_profile["type"] == 1 else "bike"

def print_routes(arc_traveled_var: dict[tuple[int, int, int], gp.Var],
                 dispatch_var: dict[int, gp.Var],
                 arrival_var: dict[int, gp.Var],
                 fleet: list[dict[str, int | float]],
                 total_nodes: int,
                 distance_matrix: pd.DataFrame,
                 service_times: list[float],
                 order_weights: np.ndarray,
                 order_assignments: np.ndarray,
                 time_windows_mapping: list[str],
                 working_time: float) -> None:
    for v in range(len(fleet)):
        if dispatch_var[v].X < 0.5:
            continue
        route = reconstruct_route(arc_traveled_var, total_nodes, v)
        load = sum(order_weights[c] for c in route[1:-1])
        total_dist = sum(distance_matrix.iat[route[k], route[k + 1]] for k in range(len(route) - 1))
        drive_time = sum(distance_matrix.iat[route[k], route[k + 1]] / fleet[v]["speed_kmh"] * 60 for k in range(len(route) - 1))
        service_time = sum(service_times[c] for c in route[1:-1])
        total_time = drive_time + service_time
        vtype = vehicle_type_label(fleet[v])
        print(f"Vehicle {v} ({vtype}) | stops: {len(route) - 2} | load: {load:.1f} kg | total distance: {total_dist:.2f} km | total time: {total_time:.1f} min | utilization {total_time / working_time * 100:.2f}%")
        print(f"  Route: {' -> '.join(map(str, route))}")
        for k in range(1, len(route) - 1):
            prev, c = route[k - 1], route[k]
            win = time_windows_mapping[int(order_assignments[c])]
            arr = arrival_var[c].X
            d = distance_matrix.iat[prev, c]
            tt = d / fleet[v]["speed_kmh"] * 60
            prev_label = "dep" if prev == 0 else f"C{prev}"
            print(f"    Customer {c:>2} | window {win} | arrival {format_time(arr)} | from {prev_label:<3} {d:5.2f} km | time traveled{tt:5.1f} min | weight {order_weights[c]:.1f} kg")
        last = route[-2]
        return_d = distance_matrix.iat[last, 0]
        return_tt = return_d / fleet[v]["speed_kmh"] * 60
        print(f"    Return to depot from C{last}:{return_d:5.2f} km | time traveled:{return_tt:5.1f} min")

def _init_route_map(coordinates: list[tuple[float, float]]) -> folium.Map:
    route_map = folium.Map(location=coordinates[0], zoom_start=14, tiles="cartodbpositron")
    # Removes the radio button for cartodbpositron, this is for simplicity to avoid writing something completely custom
    # noinspection PyProtectedMember
    for child in route_map._children.values():
        if isinstance(child, folium.raster_layers.TileLayer):
            child.control = False
    folium.Marker(
        coordinates[0],
        popup="Store (Depot)",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(route_map)
    return route_map

def _build_polyline_points(route: list[int],
                           coordinates: list[tuple[float, float]],
                           route_geometries: dict[int, dict[int, list[list[float]]]]) -> list[tuple[float, float]]:
    polyline_points: list[tuple[float, float]] = []
    for k in range(len(route) - 1):
        geom = route_geometries[route[k]][route[k + 1]]
        leg = [(lat, lon) for lon, lat in geom] if geom else [coordinates[route[k]], coordinates[route[k + 1]]]
        polyline_points.extend(leg if not polyline_points else leg[1:])
    return polyline_points

def _add_customer_marker(layer: folium.FeatureGroup,
                         c: int,
                         color: str,
                         coordinates: list[tuple[float, float]]) -> None:
    # noinspection PyTypeChecker
    folium.Marker(
        coordinates[c],
        icon=BeautifyIcon(
            number=c,
            background_color=color,
            border_color=color,
            text_color="#fff",
            icon_shape="circle",
            border_width=2,
        ),
    ).add_to(layer)

def display_route_map(arc_traveled_var: dict[tuple[int, int, int], gp.Var],
                      dispatch_var: dict[int, gp.Var],
                      fleet: list[dict[str, int | float]],
                      total_nodes: int,
                      coordinates: list[tuple[float, float]],
                      route_geometries: dict[int, dict[int, list[list[float]]]]) -> folium.Map:
    route_map = _init_route_map(coordinates)
    for v in range(len(fleet)):
        if dispatch_var[v].X < 0.5:
            continue
        color = _PALETTE[v % len(_PALETTE)]
        route = reconstruct_route(arc_traveled_var, total_nodes, v)
        vtype = vehicle_type_label(fleet[v])
        layer = folium.FeatureGroup(name=f"Vehicle {v} ({vtype})").add_to(route_map)
        folium.PolyLine(_build_polyline_points(route, coordinates, route_geometries),
                        color=color, weight=4, opacity=0.75).add_to(layer)
        for c in route[1:-1]:
            _add_customer_marker(layer, c, color, coordinates)
    folium.LayerControl(collapsed=False).add_to(route_map)
    return route_map

def display_mixed_route_map(available_routes: list[dict],
                            lambda_var: gp.tupledict,
                            ebike_dispatch_var: gp.tupledict,
                            ebike_serves_var: gp.tupledict,
                            number_of_ebikes: int,
                            customers: range,
                            coordinates: list[tuple[float, float]],
                            route_geometries: dict[int, dict[int, list[list[float]]]]) -> folium.Map:
    route_map = _init_route_map(coordinates)

    van_index = 0
    for r in range(len(available_routes)):
        if lambda_var[r].X < 0.5:
            continue
        route = available_routes[r]["path"]
        color = _PALETTE[van_index % len(_PALETTE)]
        layer = folium.FeatureGroup(name=f"Van {van_index}").add_to(route_map)
        folium.PolyLine(_build_polyline_points(route, coordinates, route_geometries),
                        color=color, weight=4, opacity=0.75).add_to(layer)
        for c in route[1:-1]:
            _add_customer_marker(layer, c, color, coordinates)
        van_index += 1

    for b in range(number_of_ebikes):
        if ebike_dispatch_var[b].X < 0.5:
            continue
        served = [c for c in customers if ebike_serves_var[b, c].X > 0.5]
        if not served:
            continue
        color = _PALETTE[(van_index + b) % len(_PALETTE)]
        layer = folium.FeatureGroup(name=f"Ebike {b}").add_to(route_map)
        for c in served:
            for src, dst in [(0, c), (c, 0)]:
                folium.PolyLine(_build_polyline_points([src, dst], coordinates, route_geometries),
                                color=color, weight=3, opacity=0.85, dash_array="8, 8").add_to(layer)
            _add_customer_marker(layer, c, color, coordinates)

    folium.LayerControl(collapsed=False).add_to(route_map)
    return route_map
