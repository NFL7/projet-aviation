"""Carte Folium : grille hexagonale (≈ 100 km), couleur = nombre d'événements mortels par cellule.

Pourquoi des hexagones plutôt que des points : avec des dizaines de milliers d'événements, les points se
superposent en une tache. En regroupant, on lit où ça se concentre, avec un nombre exact par cellule
(infobulle : événements, mortels, part de mortels). Les points individuels restent disponibles en option.
Mêmes filtres que les graphiques (la carte est reconstruite à chaque changement de filtre).
"""
from __future__ import annotations

import math

import folium
import numpy as np
import pandas as pd

TAILLE = 0.9          # rayon d'un hexagone en degrés de latitude (≈ 100 km)
LAT0 = 39.0           # latitude de référence pour corriger la longitude
K = math.cos(math.radians(LAT0))
MIN_EVT_TAUX = 15     # une cellule n'est colorée en « part de mortels » qu'au-delà de ce nombre d'événements
MAX_POINTS = 3000
ROUGE = "#FF5A4F"

# dégradé : peu -> beaucoup
STOPS = [(0.0, (59, 33, 71)), (0.35, (140, 50, 76)), (0.7, (230, 80, 72)), (1.0, (255, 209, 201))]

STYLE = """<style>
 html,body{background:#0B1220;margin:0}
 .leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) grayscale(.8) brightness(.72) contrast(.95)}
 .leaflet-container{background:#0B1220;font-family:Inter,Arial,sans-serif}
 .leaflet-control-layers,.leaflet-bar a{background:#121B2E!important;color:#E6EDF7!important;border-color:#26344F!important}
 .leaflet-control-layers-expanded{padding:8px 10px}
 .leaflet-tooltip{background:#0B1220;color:#E6EDF7;border:1px solid #26344F;box-shadow:none;font-size:12px;line-height:1.5}
 .leaflet-control-attribution{background:rgba(11,18,32,.7)!important;color:#8FA0BA!important}
 .leaflet-control-attribution a{color:#8FA0BA!important}
</style>"""


def _couleur(t: float) -> str:
    t = min(max(t, 0.0), 1.0)
    for (a, ca), (b, cb) in zip(STOPS, STOPS[1:]):
        if t <= b:
            u = (t - a) / (b - a)
            return "#%02x%02x%02x" % tuple(round(x + (y - x) * u) for x, y in zip(ca, cb))
    return "#%02x%02x%02x" % STOPS[-1][1]


def _hex_ids(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coordonnées axiales (q, r) de l'hexagone qui contient chaque point (hexagones « pointe en haut »)."""
    x, y = lon * K, lat
    q = (math.sqrt(3) / 3 * x - y / 3) / TAILLE
    r = (2 / 3 * y) / TAILLE
    # arrondi cubique
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    fx = (dx > dy) & (dx > dz)
    fy = ~fx & (dy > dz)
    rx = np.where(fx, -ry - rz, rx)
    rz = np.where(~fx & ~fy, -rx - ry, rz)
    return rx.astype(int), rz.astype(int)


def _sommets(q: int, r: int) -> list[list[float]]:
    cx = TAILLE * math.sqrt(3) * (q + r / 2)
    cy = TAILLE * 1.5 * r
    pts = []
    for i in range(6):
        a = math.radians(60 * i - 30)
        pts.append([cy + TAILLE * math.sin(a), (cx + TAILLE * math.cos(a)) / K])  # [lat, lon]
    return pts


def _legende(titre: str, bas: str, haut: str) -> str:
    degrade = ", ".join(_couleur(t / 10) for t in range(11))
    return f"""
<div style="position:absolute;z-index:9999;left:12px;bottom:24px;background:rgba(11,18,32,.9);padding:10px 14px;
 border:1px solid #26344F;border-radius:8px;font:12px Inter,Arial,sans-serif;color:#E6EDF7;min-width:230px">
 <div style="margin-bottom:6px;font-weight:600">{titre}</div>
 <div style="height:8px;border-radius:4px;background:linear-gradient(90deg,{degrade})"></div>
 <div style="display:flex;justify-content:space-between;margin-top:4px;color:#8FA0BA"><span>{bas}</span><span>{haut}</span></div>
</div>"""


def construire_carte(points: pd.DataFrame) -> tuple[str, int]:
    """Retourne le HTML de la carte et le nombre de cellules dessinées."""
    carte = folium.Map(location=[39.0, -97.0], zoom_start=4, tiles=None, control_scale=False, prefer_canvas=True, min_zoom=3)
    folium.TileLayer(tiles="OpenStreetMap", name="Fond de carte").add_to(carte)
    carte.get_root().header.add_child(folium.Element(STYLE))
    if points.empty:
        return carte.get_root().render(), 0

    d = points.dropna(subset=["latitude", "longitude"]).copy()
    d["q"], d["r"] = _hex_ids(d["latitude"].to_numpy(), d["longitude"].to_numpy())
    d["mortel"] = (d["gravite"] == "FATL").astype(int)
    cel = d.groupby(["q", "r"], as_index=False).agg(n=("mortel", "size"), m=("mortel", "sum"), deces=("morts", "sum"))
    cel["taux"] = 100 * cel["m"] / cel["n"]

    def infobulle(c) -> str:
        return (f"<b>{int(c.m)} événement(s) mortel(s)</b> sur {int(c.n)}<br>"
                f"{c.taux:.0f} % de mortels · {int(c.deces)} décès")

    # couche 1 : nombre d'événements mortels (échelle racine pour que les petites cellules restent visibles)
    g1 = folium.FeatureGroup(name="Nombre d'événements mortels", show=True)
    fat = cel[cel["m"] > 0]
    if not fat.empty:
        vmax = float(fat["m"].max())
        for c in fat.itertuples():
            col = _couleur(math.sqrt(c.m / vmax))
            folium.Polygon(_sommets(c.q, c.r), color="#0B1220", weight=0.6, fill=True, fill_color=col, fill_opacity=0.88,
                           tooltip=infobulle(c)).add_to(g1)
        carte.get_root().html.add_child(folium.Element(_legende(
            "Événements mortels par cellule (≈ 100 km)", "1", f"{int(vmax)}")))
    g1.add_to(carte)

    # couche 2 : part de mortels (cellules assez fournies seulement, sinon le taux ne veut rien dire)
    g2 = folium.FeatureGroup(name=f"Part de mortels (cellules de {MIN_EVT_TAUX}+ événements)", show=False)
    for c in cel[cel["n"] >= MIN_EVT_TAUX].itertuples():
        folium.Polygon(_sommets(c.q, c.r), color="#0B1220", weight=0.6, fill=True, fill_color=_couleur(c.taux / 60),
                       fill_opacity=0.88, tooltip=infobulle(c)).add_to(g2)
    g2.add_to(carte)

    # couche 3 : points individuels des événements mortels, masqués par défaut
    g3 = folium.FeatureGroup(name="Événements mortels (points)", show=False)
    for ligne in d[d["gravite"] == "FATL"].sort_values("ev_date", ascending=False).head(MAX_POINTS).itertuples():
        info = (f"<b>Mortel</b> · {int(ligne.morts)} mort(s)<br>{ligne.ev_date} · {ligne.ev_city or ''} {ligne.code_etat or ''}"
                f"<br>{ligne.categorie}")
        folium.CircleMarker([round(ligne.latitude, 4), round(ligne.longitude, 4)], radius=3, weight=0, fill=True,
                            fill_color=ROUGE, fill_opacity=0.75, tooltip=info).add_to(g3)
    g3.add_to(carte)

    folium.LayerControl(collapsed=False).add_to(carte)
    return carte.get_root().render(), len(fat)
