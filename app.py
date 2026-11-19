"""Dashboard Dash : accidents et incidents d'aviation civile aux États-Unis (NTSB).

Lancement local :   python app.py      puis   http://127.0.0.1:8050
Déploiement :       gunicorn app:server   (voir render.yaml)

Une seule interaction (un filtre, ou un clic sur un État) met à jour : les 4 indicateurs,
8 graphiques, la carte Folium, le tableau et les phrases de lecture.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
from dash import Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update

import carte
import charts
import db

OPT = db.options_filtres()
D_FIN = str(OPT["derniere_date"])
D_FIN_FR = f"{D_FIN[8:10]}/{D_FIN[5:7]}/{D_FIN[:4]}"
LIBELLES_SEG = {r.code: charts.SEGMENTS.get(r.code, r.libelle) for r in OPT["segments"].itertuples()}
GRAVITES_OPTIONS = [{"label": v, "value": k} for k, v in db.GRAVITES.items()] + [{"label": "Non renseigné", "value": "NR"}]
DEFAUT = {"annees": [OPT["an_min"], OPT["an_max"]], "segments": [], "gravites": [g["value"] for g in GRAVITES_OPTIONS],
          "categories": [], "etats": []}

app = Dash(__name__, title="Aviation civile aux États-Unis · NTSB")
server = app.server  # exposé pour gunicorn


# --- outils d'affichage ---------------------------------------------------------------
def fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def pct(x: float, d: int = 0) -> str:
    return f"{x:.{d}f}".replace(".", ",") + " %"


def partielle(ev: pd.DataFrame) -> bool:
    return (not ev.empty) and str(int(ev["annee"].max())) == D_FIN[:4] and D_FIN[5:] < "12-25"


def sans_partielle(ev: pd.DataFrame) -> pd.DataFrame:
    return ev.iloc[:-1] if partielle(ev) and len(ev) > 1 else ev


# --- phrases du haut de page, calculées sur l'ensemble des données ---------------------
def phrases_hero() -> tuple[str, str]:
    con = db.connexion()
    try:
        db.selection(con, DEFAUT["annees"], (), DEFAUT["gravites"], (), ())
        k, seg, ph = db.kpis(con), db.segments(con), db.phases(con)
    finally:
        con.close()
    titre = "Où et quand les événements d'aviation civile tournent-ils au drame ?"
    lede = ""
    try:
        ag = seg[seg["segment"] == "AG"].iloc[0]
        part_ag = 100 * ag["mortels"] / k["mortels"]
        titre = (f"L'aviation générale concentre {pct(part_ag)} des événements mortels aux États-Unis, "
                 f"et le danger se joue en vol.")
        p = ph[ph["famille"].isin(charts.PHASES_COURTES) & (ph["evenements"] >= 20)].copy()
        p["taux"] = 100 * p["mortels"] / p["evenements"]
        p["nom"] = p["famille"].map(charts.PHASES_COURTES)
        p = p.sort_values("taux", ascending=False)
        a, b = p.iloc[0], p.iloc[1]
        atterr = p[p["nom"] == "Atterrissage"]
        fin = f", contre {pct(atterr.iloc[0]['taux'])} à l'atterrissage" if not atterr.empty else ""
        lede = (f"{a['nom']} ({pct(a['taux'])} de mortels) et {b['nom'].lower()} ({pct(b['taux'])}) sont les phases où "
                f"un événement a le plus de chances d'être mortel{fin}. Moyenne tous événements : {pct(k['taux'], 1)}.")
    except Exception:
        pass
    return titre, lede


HERO_TITRE, HERO_LEDE = phrases_hero()


# --- composants -----------------------------------------------------------------------
def carte_graphique(titre: str, lecture: str, graph_id: str, span: int) -> html.Div:
    return html.Div(className=f"carte span-{span}", children=[
        html.H3(titre), html.P(lecture, className="lecture"),
        dcc.Graph(id=graph_id, config={"displayModeBar": False}),
    ])


def bloc(numero: str, titre: str, insight_id: str, *cartes) -> html.Section:
    return html.Section(className="bloc", children=[
        html.Div(className="bloc-tete", children=[
            html.Span(numero, className="bloc-num"),
            html.Div([html.H2(titre), html.P(id=insight_id, className="insight")]),
        ]),
        html.Div(className="grille", children=list(cartes)),
    ])


def carte_kpi(libelle, valeur, delta, serie, couleur, classe="") -> html.Div:
    return html.Div(className="kpi", children=[
        html.Div(libelle, className="kpi-libelle"),
        html.Div(valeur, className="kpi-valeur " + classe),
        html.Div(delta, className="kpi-delta"),
        dcc.Graph(figure=charts.sparkline(serie, couleur), config={"staticPlot": True, "displayModeBar": False},
                  className="kpi-spark"),
    ])


def delta_txt(serie_complete: pd.Series, annees: pd.Series, points: bool = False) -> str:
    if len(serie_complete) < 2:
        return " "
    a, b = float(serie_complete.iloc[-1]), float(serie_complete.iloc[-2])
    an_a, an_b = int(annees.iloc[-1]), int(annees.iloc[-2])
    if points:
        diff = a - b
        txt = f"{abs(diff):.1f}".replace(".", ",") + " pt"
    else:
        if b == 0:
            return " "
        diff = 100 * (a - b) / b
        txt = pct(abs(diff))
    fleche = "▲" if diff > 0 else "▼" if diff < 0 else "■"
    classe = "hausse" if diff > 0 else "baisse"
    return html.Span([html.Span(f"{fleche} {txt}", className=classe), f"  {an_a} vs {an_b}"])


# --- mise en page ---------------------------------------------------------------------
filtres = html.Div(className="filtres", children=[
    html.Div(className="filtre filtre-annees", children=[
        html.Label("Période"),
        dcc.RangeSlider(id="f-annees", min=OPT["an_min"], max=OPT["an_max"], step=1, value=DEFAUT["annees"],
                        marks={a: str(a) for a in sorted({OPT["an_min"], OPT["an_max"], *range(OPT["an_min"], OPT["an_max"] + 1, 6)})},
                        tooltip={"placement": "bottom", "always_visible": False}, allowCross=False),
    ]),
    html.Div(className="filtre", children=[
        html.Label("Segment d'exploitation"),
        dcc.Dropdown(id="f-segments", multi=True, placeholder="Tous",
                     options=[{"label": LIBELLES_SEG[c], "value": c} for c in LIBELLES_SEG]),
    ]),
    html.Div(className="filtre", children=[
        html.Label("Type d'aéronef"),
        dcc.Dropdown(id="f-categories", multi=True, placeholder="Tous",
                     options=[{"label": c, "value": c} for c in OPT["categories"]]),
    ]),
    html.Div(className="filtre", children=[
        html.Label("État"),
        dcc.Dropdown(id="f-etats", multi=True, placeholder="Tous (ou clic sur le graphique)",
                     options=[{"label": r.nom, "value": r.code} for r in OPT["etats"].itertuples()]),
    ]),
    html.Div(className="filtre filtre-gravite", children=[
        html.Label("Gravité"),
        dcc.Checklist(id="f-gravites", options=GRAVITES_OPTIONS, value=DEFAUT["gravites"], className="cases", inline=True),
    ]),
    html.Button("Réinitialiser", id="f-reset", n_clicks=0, className="bouton"),
])

COLONNES_TABLE = [
    {"name": "Date", "id": "date"}, {"name": "Lieu", "id": "lieu"}, {"name": "Aéronef", "id": "aeronef"},
    {"name": "Segment", "id": "segment"}, {"name": "Gravité", "id": "gravite"},
    {"name": "Décès", "id": "morts", "type": "numeric"}, {"name": "Météo", "id": "meteo"},
]

app.layout = html.Div(className="app", children=[
    html.Header(className="topbar", children=[
        html.Div(className="marque", children=[html.Span(className="marque-point"), "Sécurité aérienne · États-Unis"]),
        html.Div(f"Source NTSB · données au {D_FIN_FR}", className="puce"),
    ]),
    html.Section(className="hero", children=[
        html.P("Pour les responsables sécurité d'aéroclubs, d'écoles de pilotage et d'exploitants d'aviation générale",
               className="kicker"),
        html.H1(HERO_TITRE),
        html.P(HERO_LEDE, className="lede") if HERO_LEDE else None,
    ]),
    filtres,
    html.Section(className="kpis", id="kpis"),

    bloc("01", "Le constat : combien, et qui est concerné", "i-constat",
         carte_graphique("Évolution annuelle", "Volume (haut) et part d'événements mortels (bas), année par année.",
                         "g-evolution", 7),
         carte_graphique("Les segments : combien de morts, et quel risque",
                         "À gauche le nombre d'événements mortels, à droite la part de mortels dans le segment.",
                         "g-segments", 5)),

    bloc("02", "Où surviennent les événements", "i-ou",
         html.Div(className="carte span-8", children=[
             html.H3("Carte des événements"),
             html.P("Chaque point est un événement, les mortels sont au-dessus. Le menu en haut à droite active la densité.",
                    className="lecture"),
             dcc.Loading(type="dot", color="#E6EDF7", children=html.Iframe(id="carte", className="carte-iframe")),
             html.P(id="carte-note", className="note"),
         ]),
         carte_graphique("Les États les plus touchés",
                         "Événements mortels · part de mortels. Un clic sur une barre filtre tout le dashboard sur cet État.",
                         "g-etats", 4)),

    bloc("03", "Quand : phase de vol et saison", "i-quand",
         carte_graphique("Phase de vol : nombre de morts et risque",
                         "Une phase peut être rare mais très meurtrière : lire les deux colonnes ensemble.",
                         "g-phases", 7),
         carte_graphique("Saisonnalité", "Nombre d'événements par mois et par année : le pic d'été est-il stable ?",
                         "g-saison", 5)),

    bloc("04", "Conditions, appareils et causes", "i-causes",
         carte_graphique("Météo et lumière", "Part d'événements mortels selon les conditions de vol.", "g-conditions", 4),
         carte_graphique("Âge de l'aéronef", "Répartition de l'âge, événements mortels contre autres.", "g-ages", 4),
         carte_graphique("Ce que relèvent les enquêteurs", "Constats par famille. Un événement peut en cumuler plusieurs.",
                         "g-causes", 4)),

    html.Section(className="bloc", children=[
        html.Div(className="bloc-tete", children=[
            html.Span("05", className="bloc-num"),
            html.Div([html.H2("Le détail : les événements les plus graves de la sélection"),
                      html.P("Triés par nombre de décès. Cliquer sur un en-tête pour trier autrement.", className="insight")]),
        ]),
        html.Div(className="carte", children=[
            dash_table.DataTable(
                id="tableau", columns=COLONNES_TABLE, data=[], page_size=10, sort_action="native", sort_mode="single",
                style_as_list_view=True,
                style_table={"overflowX": "auto"},
                style_header={"backgroundColor": "#0B1220", "color": "#8FA0BA", "border": "0", "fontWeight": "600",
                              "fontSize": "12px", "textTransform": "uppercase", "letterSpacing": ".04em"},
                style_cell={"backgroundColor": "#121B2E", "color": "#E6EDF7", "border": "0",
                            "borderBottom": "1px solid #26344F", "padding": "10px 12px", "fontFamily": "Inter, Arial, sans-serif",
                            "fontSize": "13px", "textAlign": "left"},
                style_data_conditional=[
                    {"if": {"filter_query": '{gravite} = "Mortel"', "column_id": "gravite"}, "color": "#FF5A4F", "fontWeight": "600"},
                    {"if": {"filter_query": '{gravite} = "Blessés graves"', "column_id": "gravite"}, "color": "#F2B84B"},
                    {"if": {"column_id": "morts"}, "textAlign": "right"},
                ],
            ),
        ]),
    ]),

    html.Footer(className="pied", children=[
        html.P([
            "Source : NTSB, base d'enquêtes sur les accidents et incidents d'aviation civile (avall), événements survenus aux États-Unis, ",
            f"{OPT['an_min']} à {OPT['an_max']} (données jusqu'au {D_FIN_FR}). Un « événement » regroupe accidents et incidents. ",
            "Les événements sans coordonnées n'apparaissent pas sur la carte ; l'âge de l'aéronef et les causes ne sont connus que pour une partie des événements ; "
            "le nombre d'événements ne mesure pas un risque par heure de vol.",
        ]),
    ]),
])


# --- callbacks ------------------------------------------------------------------------
@app.callback(
    Output("f-annees", "value"), Output("f-segments", "value"), Output("f-gravites", "value"),
    Output("f-categories", "value"), Output("f-etats", "value"),
    Input("f-reset", "n_clicks"), Input("g-etats", "clickData"), State("f-etats", "value"),
    prevent_initial_call=True,
)
def reinitialiser_ou_filtrer_etat(_, clic, etats):
    """Bouton « Réinitialiser » ou clic sur un État dans le graphique."""
    if ctx.triggered_id == "g-etats":
        if not clic:
            return (no_update,) * 5
        code = clic["points"][0]["customdata"][1]
        etats = list(etats or [])
        etats = [e for e in etats if e != code] if code in etats else etats + [code]
        return no_update, no_update, no_update, no_update, etats
    return DEFAUT["annees"], DEFAUT["segments"], DEFAUT["gravites"], DEFAUT["categories"], DEFAUT["etats"]


def construire_kpis(k: dict, ev: pd.DataFrame) -> list:
    comp = sans_partielle(ev)
    tendance = {c: comp[c].tolist() for c in ("evenements", "mortels", "morts", "taux")} if not comp.empty else \
        {c: [] for c in ("evenements", "mortels", "morts", "taux")}
    ans = comp["annee"] if not comp.empty else pd.Series(dtype=int)
    return [
        carte_kpi("Événements", fmt(k["n"]), delta_txt(comp["evenements"], ans) if not comp.empty else " ",
                  tendance["evenements"], "#5B8DC9"),
        carte_kpi("Événements mortels", fmt(k["mortels"]), delta_txt(comp["mortels"], ans) if not comp.empty else " ",
                  tendance["mortels"], "#FF5A4F", "rouge"),
        carte_kpi("Personnes décédées", fmt(k["morts"]), delta_txt(comp["morts"], ans) if not comp.empty else " ",
                  tendance["morts"], "#E6EDF7"),
        carte_kpi("Part d'événements mortels", pct(k["taux"], 1),
                  delta_txt(comp["taux"], ans, points=True) if not comp.empty else " ",
                  tendance["taux"], "#FF5A4F", "rouge"),
    ]


def construire_phrases(k, seg, ph, cond, etats_df, causes_df) -> tuple[str, str, str, str]:
    """Une phrase de lecture par bloc, calculée sur la sélection courante."""
    if not k["n"]:
        return ("Aucun événement pour ces filtres.",) * 4
    # 1. constat
    s = seg.copy()
    s["segment"] = s["segment"].map(lambda c: "Autres" if c in charts.AUTRES_SEGMENTS else charts.SEGMENTS.get(c, c))
    s = s.groupby("segment", as_index=False)[["evenements", "mortels"]].sum().sort_values("mortels", ascending=False)
    top = s.iloc[0]
    constat = (f"{top['segment']} : {pct(100 * top['mortels'] / max(k['mortels'], 1))} des événements mortels de la sélection, "
               f"avec {pct(100 * top['mortels'] / top['evenements'])} de mortels dans ce segment (moyenne {pct(k['taux'], 1)}).")
    # 2. où
    ou = "Pas de coordonnées pour cette sélection."
    if not etats_df.empty and k["mortels"]:
        e1 = etats_df.iloc[0]
        cinq = 100 * etats_df.head(5)["mortels"].sum() / k["mortels"]
        ou = (f"{e1['etat']} compte le plus d'événements mortels ({fmt(e1['mortels'])}) ; "
              + (f"les cinq premiers États en rassemblent {pct(cinq)}. " if len(etats_df) > 5 else "")
              + f"{fmt(k['geo'])} événements sont géolocalisés sur {fmt(k['n'])}.")
    # 3. quand
    quand = ""
    p = ph[ph["famille"].isin(charts.PHASES_COURTES) & (ph["evenements"] >= 20)].copy()
    if not p.empty:
        p["taux"] = 100 * p["mortels"] / p["evenements"]
        p["nom"] = p["famille"].map(charts.PHASES_COURTES)
        p = p.sort_values("taux", ascending=False)
        a, z = p.iloc[0], p.iloc[-1]
        quand = (f"{a['nom']} est la phase la plus dangereuse ({pct(a['taux'])} de mortels, {fmt(a['mortels'])} événements mortels) ; "
                 f"{z['nom'].lower()} la moins ({pct(z['taux'])}).")
    # 4. conditions + causes
    morceaux = []
    if not cond.empty:
        t = cond.groupby("meteo")[["evenements", "mortels"]].sum()
        if {"VMC", "IMC"} <= set(t.index) and t.loc["VMC", "evenements"] and t.loc["IMC", "evenements"]:
            morceaux.append(f"Aux instruments (IMC), {pct(100 * t.loc['IMC', 'mortels'] / t.loc['IMC', 'evenements'])} des événements sont mortels, "
                            f"contre {pct(100 * t.loc['VMC', 'mortels'] / t.loc['VMC', 'evenements'])} à vue (VMC).")
    if not causes_df.empty:
        total = causes_df["ev_id"].nunique()
        hum = causes_df[causes_df["niveau1"] == "Personnel issues"]["ev_id"].nunique()
        morceaux.append(f"Un facteur humain est relevé dans {pct(100 * hum / total)} des événements enquêtés.")
    return constat, ou, quand, " ".join(morceaux)


@lru_cache(maxsize=24)
def calculer(annees, segs, gravs, cats, etats):
    """Interroge la base et construit tous les éléments pour un jeu de filtres (mémorisé pour les retours en arrière)."""
    con = db.connexion()
    try:
        db.selection(con, annees, segs, gravs, cats, etats)
        k = db.kpis(con)
        ev, seg, ph, cond = db.evolution(con), db.segments(con), db.phases(con), db.conditions(con)
        etats_df, causes_df = db.etats_top(con), db.causes(con)
        figs = (
            charts.evolution(ev, D_FIN),
            charts.segments(seg, k["taux"]),
            charts.etats(etats_df),
            charts.phases(ph, k["taux"]),
            charts.saison(db.saison(con), D_FIN),
            charts.conditions(cond),
            charts.ages(db.ages(con)),
            charts.causes(causes_df),
        )
        html_carte, affiches = carte.construire_carte(db.points_carte(con))
        t = db.tableau(con)
        phrases = construire_phrases(k, seg, ph, cond, etats_df, causes_df)
    finally:
        con.close()
    note = (f"{fmt(k['geo'])} événements géolocalisés sur {fmt(k['n'])} ; {fmt(affiches)} points dessinés, les plus graves en priorité."
            if k["n"] else "Aucun événement pour ces filtres.")
    t["date"] = t["ev_date"]
    t["lieu"] = (t["ev_city"].fillna("") + ", " + t["code_etat"].fillna("")).str.strip(", ")
    t["aeronef"] = t["categorie"]
    t["segment"] = t["code_segment"].map(lambda c: charts.SEGMENTS.get(c, "Autres"))
    t["gravite"] = t["gravite"].map(lambda g: db.GRAVITES.get(g, "Non renseigné"))
    t["meteo"] = t["meteo"].fillna("n.r.")
    lignes = t[["date", "lieu", "aeronef", "segment", "gravite", "morts", "meteo"]].to_dict("records")
    return (construire_kpis(k, ev), *phrases, *figs, html_carte, note, lignes)


@app.callback(
    Output("kpis", "children"),
    Output("i-constat", "children"), Output("i-ou", "children"), Output("i-quand", "children"), Output("i-causes", "children"),
    Output("g-evolution", "figure"), Output("g-segments", "figure"), Output("g-etats", "figure"), Output("g-phases", "figure"),
    Output("g-saison", "figure"), Output("g-conditions", "figure"), Output("g-ages", "figure"), Output("g-causes", "figure"),
    Output("carte", "srcDoc"), Output("carte-note", "children"), Output("tableau", "data"),
    Input("f-annees", "value"), Input("f-segments", "value"), Input("f-gravites", "value"),
    Input("f-categories", "value"), Input("f-etats", "value"),
)
def mettre_a_jour(annees, segs, gravs, cats, etats):
    """Un seul callback : une interaction met à jour les KPI, les phrases, 8 graphiques, la carte et le tableau."""
    return calculer(tuple(annees), tuple(segs or ()), tuple(gravs or ()), tuple(cats or ()), tuple(etats or ()))


if __name__ == "__main__":
    app.run(debug=False)
