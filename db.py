"""Accès à la base SQLite et requêtes du dashboard.

Toutes les données affichées viennent de data/aviation.db. À chaque interaction,
on crée une table temporaire `sel` qui contient les événements correspondant aux
filtres choisis (années, segments, gravité, catégorie d'aéronef) ; les requêtes
des graphiques s'appuient ensuite sur cette sélection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "data" / "aviation.db"

GRAVITES = {
    "FATL": "Mortel",
    "SERS": "Blessés graves",
    "MINR": "Blessés légers",
    "NONE": "Aucun blessé",
}

# Vue « un événement = une ligne » : on rattache l'aéronef principal
# (le premier aéronef de l'événement) pour connaître segment, catégorie et âge.
VUE_EVENEMENTS = """
CREATE TEMP VIEW v_evt AS
SELECT e.ev_id, e.ev_date, e.ev_year, e.ev_month, e.ev_city, e.code_etat,
       e.latitude, e.longitude, COALESCE(e.gravite_max, 'NR') AS gravite,
       COALESCE(e.morts, 0) AS morts, e.meteo, e.lumiere,
       COALESCE(a.code_segment, 'AUTRE') AS code_segment,
       COALESCE(a.categorie, 'Inconnu') AS categorie,
       a.id_constructeur, a.modele, a.annee_construction
FROM events e
LEFT JOIN aircraft a
  ON a.ev_id = e.ev_id
 AND a.aircraft_key = (SELECT MIN(x.aircraft_key) FROM aircraft x WHERE x.ev_id = e.ev_id)
"""


def connexion() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute(VUE_EVENEMENTS)
    return con


def _in(colonne: str, valeurs: list) -> tuple[str, list]:
    marques = ",".join("?" * len(valeurs))
    return f"{colonne} IN ({marques})", list(valeurs)


def selection(con: sqlite3.Connection, annees, segments, gravites, categories, etats=()) -> int:
    """Remplit la table temporaire `sel` avec les événements filtrés."""
    conds, params = ["ev_year BETWEEN ? AND ?"], [int(annees[0]), int(annees[1])]
    # Segments et catégories : rien de choisi = pas de filtre.
    # Gravité : cases toutes décochées = aucun résultat.
    for colonne, valeurs, si_vide in (
        ("code_segment", segments, "tout"), ("gravite", gravites, "rien"),
        ("categorie", categories, "tout"), ("code_etat", etats, "tout"),
    ):
        if valeurs:
            c, p = _in(colonne, valeurs)
            conds.append(c)
            params += p
        elif si_vide == "rien":
            conds.append("0")
    con.execute("DROP TABLE IF EXISTS sel")
    con.execute(f"CREATE TEMP TABLE sel AS SELECT * FROM v_evt WHERE {' AND '.join(conds)}", params)
    con.execute("CREATE INDEX temp.idx_sel ON sel(ev_id)")
    return con.execute("SELECT COUNT(*) FROM sel").fetchone()[0]


def q(con: sqlite3.Connection, sql: str, params: list | None = None) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params or [])


# --- listes pour les filtres -------------------------------------------------
def options_filtres() -> dict:
    con = connexion()
    try:
        annees = q(con, "SELECT MIN(ev_year) AS a, MAX(ev_year) AS b, MAX(ev_date) AS d FROM events").iloc[0]
        segments = q(con, """SELECT s.code_segment AS code, s.libelle FROM segments s
                             WHERE s.code_segment IN (SELECT DISTINCT code_segment FROM aircraft)""")
        categories = q(con, """SELECT categorie, COUNT(*) n FROM aircraft
                               GROUP BY categorie ORDER BY n DESC""")["categorie"].tolist()
        etats = q(con, """SELECT DISTINCT e.code_etat AS code, COALESCE(s.nom, e.code_etat) AS nom
                          FROM events e LEFT JOIN etats s ON s.code_etat = e.code_etat
                          WHERE e.code_etat IS NOT NULL ORDER BY nom""")
    finally:
        con.close()
    return {
        "an_min": int(annees["a"]), "an_max": int(annees["b"]), "derniere_date": annees["d"],
        "segments": segments, "categories": categories, "etats": etats,
    }


# --- requêtes des visualisations --------------------------------------------
def kpis(con) -> dict:
    r = q(con, """SELECT COUNT(*) AS n, SUM(gravite = 'FATL') AS mortels,
                         SUM(morts) AS morts, SUM(latitude IS NOT NULL) AS geo FROM sel""").iloc[0]
    n = int(r["n"] or 0)
    mortels = int(r["mortels"] or 0)
    return {"n": n, "mortels": mortels, "morts": int(r["morts"] or 0),
            "taux": (100 * mortels / n) if n else 0.0, "geo": int(r["geo"] or 0)}


def evolution(con) -> pd.DataFrame:
    df = q(con, """SELECT ev_year AS annee, COUNT(*) AS evenements,
                          SUM(gravite = 'FATL') AS mortels, SUM(morts) AS morts
                          FROM sel GROUP BY ev_year ORDER BY ev_year""")
    df["taux"] = 100 * df["mortels"] / df["evenements"]
    return df


def segments(con) -> pd.DataFrame:
    return q(con, """SELECT sel.code_segment AS segment, COUNT(*) AS evenements,
                            SUM(sel.gravite = 'FATL') AS mortels
                     FROM sel GROUP BY sel.code_segment""")


def phases(con) -> pd.DataFrame:
    """Un événement compte une fois par famille de phase où il a une séquence."""
    return q(con, """
        SELECT p.famille, COUNT(*) AS evenements, SUM(sel.gravite = 'FATL') AS mortels
        FROM (SELECT DISTINCT s.ev_id, p2.famille
              FROM sequences s JOIN phases p2 ON p2.phase_no = s.phase_no) p
        JOIN sel ON sel.ev_id = p.ev_id
        GROUP BY p.famille""")


def conditions(con) -> pd.DataFrame:
    """Part de mortels selon la lumière (jour, aube ou crépuscule, nuit) et la météo (VMC, IMC)."""
    return q(con, """
        SELECT CASE WHEN lumiere = 'DAYL' THEN 'Jour'
                    WHEN lumiere IN ('DAWN', 'DUSK') THEN 'Aube ou crépuscule'
                    WHEN lumiere IN ('NITE', 'NDRK', 'NBRT') THEN 'Nuit' END AS lumiere,
               meteo, COUNT(*) AS evenements, SUM(gravite = 'FATL') AS mortels
        FROM sel WHERE meteo IN ('VMC', 'IMC') AND lumiere IN ('DAYL', 'DAWN', 'DUSK', 'NITE', 'NDRK', 'NBRT')
        GROUP BY 1, 2""")


def ages(con) -> pd.DataFrame:
    return q(con, """SELECT sel.code_segment AS segment, sel.gravite, sel.ev_year - sel.annee_construction AS age
                     FROM sel
                     WHERE sel.annee_construction IS NOT NULL
                       AND sel.ev_year - sel.annee_construction BETWEEN 0 AND 100""")


def causes(con) -> pd.DataFrame:
    """Causes et facteurs (table findings) : 2 premiers niveaux de la hiérarchie NTSB."""
    df = q(con, """SELECT DISTINCT f.ev_id, f.description FROM findings f
                   JOIN sel ON sel.ev_id = f.ev_id WHERE f.description IS NOT NULL""")
    if df.empty:
        return df.assign(niveau1=[], niveau2=[])
    parts = df["description"].str.split("-", n=2, expand=True)
    df["niveau1"] = parts[0].str.strip()
    df["niveau2"] = parts[1].str.strip() if parts.shape[1] > 1 else None
    return df[["ev_id", "niveau1", "niveau2"]].drop_duplicates()


def etats_top(con, n: int = 12) -> pd.DataFrame:
    return q(con, """SELECT sel.code_etat AS code, COALESCE(et.nom, sel.code_etat) AS etat,
                            COUNT(*) AS evenements, SUM(sel.gravite = 'FATL') AS mortels
                     FROM sel LEFT JOIN etats et ON et.code_etat = sel.code_etat
                     WHERE sel.code_etat IS NOT NULL
                     GROUP BY sel.code_etat ORDER BY mortels DESC, evenements DESC LIMIT ?""", [n])


def saison(con) -> pd.DataFrame:
    return q(con, """SELECT ev_year AS annee, ev_month AS mois, COUNT(*) AS evenements, SUM(gravite = 'FATL') AS mortels
                     FROM sel WHERE ev_month BETWEEN 1 AND 12 GROUP BY ev_year, ev_month""")


def tableau(con, n: int = 400) -> pd.DataFrame:
    """Les événements les plus graves de la sélection (décès, puis date récente)."""
    return q(con, """SELECT ev_date, ev_city, code_etat, categorie, code_segment, gravite, morts, meteo
                     FROM sel ORDER BY morts DESC, ev_date DESC LIMIT ?""", [n])


def points_carte(con) -> pd.DataFrame:
    return q(con, """SELECT ev_id, ev_date, ev_city, code_etat, latitude, longitude,
                            gravite, morts, meteo, categorie
                     FROM sel WHERE latitude IS NOT NULL AND longitude IS NOT NULL""")
