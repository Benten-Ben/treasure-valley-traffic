"""Small geometry helpers: distances, a grid index, clustering, Esri to GeoJSON."""

import math

M_PER_DEG_LAT = 111_320.0


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


class GridIndex:
    """Bucket points into ~cell_m squares for fast "what's near here" lookups."""

    def __init__(self, cell_m=200.0, ref_lat=43.6):
        self.dlat = cell_m / M_PER_DEG_LAT
        self.dlon = cell_m / (M_PER_DEG_LAT * math.cos(math.radians(ref_lat)))
        self.cells = {}

    def _key(self, lat, lon):
        return int(lat // self.dlat), int(lon // self.dlon)

    def add(self, lat, lon, item):
        self.cells.setdefault(self._key(lat, lon), []).append((lat, lon, item))

    def near(self, lat, lon, radius_m):
        """[(distance_m, item)] within radius, nearest first."""
        ky, kx = self._key(lat, lon)
        r = int(radius_m // (self.dlat * M_PER_DEG_LAT)) + 1
        out = []
        for y in range(ky - r, ky + r + 1):
            for x in range(kx - r, kx + r + 1):
                for plat, plon, item in self.cells.get((y, x), ()):
                    d = haversine_m(lat, lon, plat, plon)
                    if d <= radius_m:
                        out.append((d, item))
        out.sort(key=lambda t: t[0])
        return out


def cluster_points(points, radius_m=60.0):
    """Union points closer than radius_m (transitively).

    points: list of (lat, lon, payload). Returns list of clusters, each a list
    of the original tuples. Used to merge the several OSM signal nodes or ACHD
    signal poles that make up one intersection.
    """
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    index = GridIndex(cell_m=radius_m)
    for i, (lat, lon, _) in enumerate(points):
        for _, j in index.near(lat, lon, radius_m):
            parent[find(i)] = find(j)
        index.add(lat, lon, i)
    groups = {}
    for i, p in enumerate(points):
        groups.setdefault(find(i), []).append(p)
    return list(groups.values())


def esri_to_geojson(geom):
    """Convert an Esri JSON geometry (in WGS84) to GeoJSON."""
    if not geom:
        return None
    if "x" in geom:
        return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    if "paths" in geom:
        return {"type": "MultiLineString", "coordinates": geom["paths"]}
    if "rings" in geom:
        return {"type": "Polygon", "coordinates": geom["rings"]}
    return None


def representative_point(geom):
    """(lat, lon) for a GeoJSON geometry: the point, or a middle vertex."""
    if not geom:
        return None
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return c[1], c[0]
    if t == "LineString":
        lon, lat = c[len(c) // 2][:2]
        return lat, lon
    if t in ("MultiLineString", "Polygon"):
        line = max(c, key=len)
        lon, lat = line[len(line) // 2][:2]
        return lat, lon
    if t == "MultiPoint":
        lon, lat = c[0][:2]
        return lat, lon
    return None


def line_vertices(geom):
    """All (lat, lon) vertices of a (Multi)LineString geometry."""
    if not geom:
        return []
    if geom["type"] == "LineString":
        return [(p[1], p[0]) for p in geom["coordinates"]]
    if geom["type"] == "MultiLineString":
        return [(p[1], p[0]) for line in geom["coordinates"] for p in line]
    return []
