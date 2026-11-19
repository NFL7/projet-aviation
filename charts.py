"""Graphiques Plotly du dashboard (une fonction = un graphique).

Code visuel unique, repris par la carte et le CSS :
  - rouge corail  = événements mortels (et jamais autre chose)
  - bleu acier    = autres événements
  - ambre         = blessés graves
  - tout le reste (axes, repères) en gris-bleu discret.
Chaque graphique dit une chose ; le titre et la phrase de lecture sont dans app.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- palette (identique à assets/style.css) ---------------------------------
BG = "#121B2E"
TEXTE = "#E6EDF7"
MUET = "#8FA0BA"
GRILLE = "#26344F"
FATAL = "#FF5A4F"
AUTRE = "#5B8DC9"
AMBRE = "#F2B84B"
POLICE = "Inter, 'Helvetica Neue', Arial, sans-serif"

# échelle séquentielle unique pour toutes les « parts de mortels »
ECHELLE = [[0.0, "#1A2740"], [0.35, "#5A3B58"], [0.7, "#C4443F"], [1.0, FATAL]]
ECHELLE_VOLUME = [[0.0, "#16233A"], [0.5, "#2F5A8F"], [1.0, "#8EC1FF"]]

SEGMENTS = {
    "AG": "Aviation générale", "TRAVAIL": "Travail aérien", "TAXI": "Taxi aérien",
    "LIGNE": "Compagnies régulières", "PUB": "Public et militaire",
}
AUTRES_SEGMENTS = ["ETR", "SPEC", "AUTRE"]
MOIS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]


def _base(fig: go.Figure, hauteur: int = 360, margin: dict | None = None) -> go.Figure:
    fig.update_layout(
        height=hauteur, margin=margin or dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=POLICE, size=12, color=TEXTE),
        hoverlabel=dict(font_family=POLICE, bgcolor="#0B1220", bordercolor=GRILLE, font_color=TEXTE),
        separators=", ", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                                     title_text="", font=dict(color=MUET)),
    )
    fig.update_xaxes(gridcolor=GRILLE, zerolinecolor=GRILLE, linecolor=GRILLE, tickfont=dict(color=MUET),
                     title_font=dict(color=MUET, size=11))
    fig.update_yaxes(gridcolor=GRILLE, zerolinecolor=GRILLE, linecolor=GRILLE, tickfont=dict(color=MUET),
                     title_font=dict(color=MUET, size=11))
    return fig


def _milliers(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def _pct(x: float, d: int = 0) -> str:
    return f"{x:.{d}f}".replace(".", ",") + " %"


def vide(message: str = "Aucun événement pour ces filtres", hauteur: int = 360) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color=MUET))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _base(fig, hauteur)


# --- mini-courbe des cartes KPI ------------------------------------------------
def sparkline(valeurs, couleur: str) -> go.Figure:
    fig = go.Figure(go.Scatter(y=list(valeurs), mode="lines", line=dict(color=couleur, width=2, shape="spline", smoothing=0.6),
                               hoverinfo="skip"))
    if len(valeurs):
        fig.add_scatter(x=[len(valeurs) - 1], y=[valeurs[-1]], mode="markers", marker=dict(color=couleur, size=6),
                        hoverinfo="skip")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, rangemode="tozero")
    fig.update_layout(height=44, margin=dict(l=0, r=4, t=4, b=0), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


# 1. Évolution : volume (barres empilées) puis part de mortels (courbe), axes alignés ----------
def evolution(df: pd.DataFrame, derniere_date: str) -> go.Figure:
    if df.empty:
        return vide(hauteur=400)
    df = df.copy()
    df["non_mortels"] = df["evenements"] - df["mortels"]
    d = str(derniere_date)
    a0, a1 = int(df["annee"].min()), int(df["annee"].max())
    partielle = str(a1) == d[:4] and d[5:] < "12-25"
    opacite = [1.0] * (len(df) - 1) + [0.45 if partielle else 1.0]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.64, 0.36])
    fig.add_bar(x=df["annee"], y=df["non_mortels"], name="Autres événements", marker=dict(color=AUTRE, opacity=opacite),
                hovertemplate="%{x} : %{y:,d} autres<extra></extra>", row=1, col=1)
    fig.add_bar(x=df["annee"], y=df["mortels"], name="Événements mortels", marker=dict(color=FATAL, opacity=opacite),
                hovertemplate="%{x} : %{y:,d} mortels<extra></extra>", row=1, col=1)
    complet = df.iloc[:-1] if partielle and len(df) > 1 else df
    moyenne = 100 * complet["mortels"].sum() / max(complet["evenements"].sum(), 1)
    fig.add_scatter(x=df["annee"], y=df["taux"], mode="lines+markers", name="Part de mortels", showlegend=False,
                    line=dict(color=TEXTE, width=2), marker=dict(size=6, color=TEXTE),
                    hovertemplate="%{x} : %{y:.1f} % d'événements mortels<extra></extra>", row=2, col=1)
    fig.add_hline(y=moyenne, line_dash="dot", line_color=MUET, line_width=1, row=2, col=1)
    fig.add_scatter(x=[None], y=[None], mode="lines", name=f"Part de mortels (moyenne {_pct(moyenne, 1)} en pointillés)",
                    line=dict(color=TEXTE, width=2), row=2, col=1)
    if partielle:
        fig.add_annotation(x=a1, y=float(df["evenements"].iloc[-1]), text="partielle", showarrow=False,
                           yshift=12, xanchor="center", font=dict(size=10, color=MUET), row=1, col=1)
    fig.update_layout(barmode="stack", bargap=0.28)
    fig.update_xaxes(range=[a0 - 0.6, a1 + 0.6], tickmode="array",
                     tickvals=list(range(a0, a1 + 1, 2 if a1 - a0 > 8 else 1)), showgrid=False)
    fig.update_yaxes(title_text="Événements", row=1, col=1)
    fig.update_yaxes(title_text="% mortels", ticksuffix=" %", rangemode="tozero",
                     range=[0, max(25, df["taux"].max() * 1.2)], row=2, col=1)
    return _base(fig, 420)


# 2 et 3. Volume contre risque : barres des mortels + « sucette » du taux, mêmes lignes ---------
def volume_vs_taux(df: pd.DataFrame, colonne: str, taux_global: float, min_n: int = 20, hauteur: int = 360) -> go.Figure:
    if df is None or df.empty:
        return vide(hauteur=hauteur)
    d = df[df["evenements"] >= min_n].copy()
    if d.empty:
        return vide("Pas assez d'événements pour ces filtres", hauteur)
    d["taux"] = 100 * d["mortels"] / d["evenements"]
    d = d.sort_values("taux")  # le plus risqué en haut
    noms = d[colonne].tolist()
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.04, column_widths=[0.5, 0.5],
                        subplot_titles=("Mortels (nombre)", f"Part de mortels · moy. {_pct(taux_global, 1)}"))
    fig.add_bar(y=noms, x=d["mortels"], orientation="h", marker_color=FATAL, text=[_milliers(v) for v in d["mortels"]],
                textposition="outside", textfont=dict(color=TEXTE, size=11), cliponaxis=False, showlegend=False,
                customdata=d["evenements"], hovertemplate="%{y}<br>%{x:,d} événements mortels sur %{customdata:,d}<extra></extra>",
                row=1, col=1)
    # sucette : tige fine + point
    fig.add_bar(y=noms, x=d["taux"], orientation="h", marker_color="rgba(255,90,79,.35)", width=0.1, showlegend=False,
                hoverinfo="skip", row=1, col=2)
    fig.add_scatter(y=noms, x=d["taux"], mode="markers+text", text=[_pct(t) for t in d["taux"]], textposition="middle right",
                    textfont=dict(color=TEXTE, size=12), cliponaxis=False, showlegend=False,
                    marker=dict(size=13, color=d["taux"], colorscale=[[0, AUTRE], [0.5, "#D98A7F"], [1, FATAL]],
                                cmin=0, cmax=max(40, d["taux"].max()), line=dict(width=2, color=BG)),
                    customdata=np.c_[d["mortels"], d["evenements"]],
                    hovertemplate="%{y}<br>%{x:.1f} % mortels (%{customdata[0]:,d} sur %{customdata[1]:,d})<extra></extra>",
                    row=1, col=2)
    fig.add_vline(x=taux_global, line_dash="dot", line_color=MUET, line_width=1, row=1, col=2)
    fig.update_xaxes(range=[0, float(d["mortels"].max()) * 1.3], showgrid=False, showticklabels=False, row=1, col=1)
    fig.update_xaxes(range=[0, max(float(d["taux"].max()) * 1.3, taux_global * 1.3)], ticksuffix=" %", row=1, col=2)
    fig.update_yaxes(tickfont=dict(color=TEXTE, size=12), gridcolor="rgba(0,0,0,0)")
    for a in fig.layout.annotations[:2]:
        a.update(font=dict(size=11, color=MUET))
    return _base(fig, hauteur, margin=dict(l=8, r=28, t=28, b=24))


def segments(df: pd.DataFrame, taux_global: float) -> go.Figure:
    if df.empty:
        return vide()
    d = df.copy()
    d["segment"] = d["segment"].map(lambda c: "Autres" if c in AUTRES_SEGMENTS else SEGMENTS.get(c, c))
    d = d.groupby("segment", as_index=False)[["evenements", "mortels"]].sum()
    return volume_vs_taux(d, "segment", taux_global, min_n=1, hauteur=400)


PHASES_COURTES = {
    "Sol (préparation, roulage)": "Sol", "Décollage et montée initiale": "Décollage",
    "Croisière": "Croisière", "Manœuvres": "Manœuvres", "Approche": "Approche",
    "Atterrissage": "Atterrissage", "Descente d'urgence ou incontrôlée": "Descente incontrôlée",
}


def phases(df: pd.DataFrame, taux_global: float) -> go.Figure:
    d = df[df["famille"].isin(PHASES_COURTES)].copy() if not df.empty else df
    if d is None or d.empty:
        return vide()
    d["phase"] = d["famille"].map(PHASES_COURTES)
    return volume_vs_taux(d, "phase", taux_global, min_n=20, hauteur=380)


# 4. États : où se concentrent les événements mortels ------------------------------------------
def etats(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vide(hauteur=400)
    d = df.sort_values("mortels").copy()
    d["taux"] = 100 * d["mortels"] / d["evenements"]
    fig = go.Figure(go.Bar(
        y=d["etat"], x=d["mortels"], orientation="h", marker_color=FATAL,
        text=[f"{_milliers(m)}  ·  {_pct(t)}" for m, t in zip(d["mortels"], d["taux"])],
        textposition="outside", textfont=dict(color=TEXTE, size=11), cliponaxis=False,
        customdata=np.c_[d["evenements"], d["code"]],
        hovertemplate="%{y}<br>%{x:,d} événements mortels sur %{customdata[0]:,d}<br><i>Cliquer pour filtrer</i><extra></extra>"))
    fig.update_xaxes(range=[0, float(d["mortels"].max()) * 1.4], showgrid=False, showticklabels=False)
    fig.update_yaxes(tickfont=dict(color=TEXTE, size=12), gridcolor="rgba(0,0,0,0)")
    fig.update_layout(bargap=0.3)
    return _base(fig, 545, margin=dict(l=8, r=8, t=4, b=4))


# 5. Saison : année × mois ----------------------------------------------------------------------
def saison(df: pd.DataFrame, derniere_date: str) -> go.Figure:
    if df.empty:
        return vide(hauteur=400)
    z = df.pivot_table(index="annee", columns="mois", values="evenements", aggfunc="sum").reindex(columns=range(1, 13))
    d = str(derniere_date)
    an_fin, mois_fin = int(d[:4]), int(d[5:7])
    for an in z.index:
        if an == an_fin:
            z.loc[an, [m for m in z.columns if m > mois_fin]] = np.nan
    fig = go.Figure(go.Heatmap(
        z=z.values, x=MOIS, y=z.index.astype(str), colorscale=ECHELLE_VOLUME, xgap=2, ygap=2, hoverongaps=False,
        colorbar=dict(thickness=8, len=0.8, tickfont=dict(color=MUET, size=10), outlinewidth=0, title=dict(text="")),
        hovertemplate="%{y}, %{x}<br>%{z:,d} événements<extra></extra>"))
    fig.update_yaxes(autorange="reversed", type="category", gridcolor="rgba(0,0,0,0)")
    fig.update_xaxes(side="top", gridcolor="rgba(0,0,0,0)")
    return _base(fig, 400, margin=dict(l=8, r=8, t=24, b=4))


# 6. Conditions de vol : lumière × météo -----------------------------------------------------
def conditions(df: pd.DataFrame, seuil: int = 30) -> go.Figure:
    if df.empty:
        return vide(hauteur=340)
    lignes = [l for l in ["Jour", "Aube ou crépuscule", "Nuit"] if l in set(df["lumiere"])]
    cols = [("VMC", "À vue (VMC)"), ("IMC", "Aux instruments (IMC)")]
    n = df.pivot_table(index="lumiere", columns="meteo", values="evenements", aggfunc="sum").reindex(index=lignes, columns=["VMC", "IMC"])
    f = df.pivot_table(index="lumiere", columns="meteo", values="mortels", aggfunc="sum").reindex(index=lignes, columns=["VMC", "IMC"])
    taux = (100 * f / n).where(n >= seuil)
    fig = go.Figure(go.Heatmap(z=taux.values, x=[c[1] for c in cols], y=lignes, colorscale=ECHELLE, zmin=0, zmax=70,
                               xgap=4, ygap=4, showscale=False, hoverongaps=False,
                               hovertemplate="%{y}, %{x}<br>%{z:.1f} % mortels<extra></extra>"))
    for i, ligne in enumerate(lignes):
        for j, (_, nom) in enumerate(cols):
            v = taux.iloc[i, j]
            if pd.isna(v):
                continue
            fig.add_annotation(x=nom, y=ligne, text=f"<b>{v:.0f} %</b>", showarrow=False, yshift=10, font=dict(size=22, color="white"))
            fig.add_annotation(x=nom, y=ligne, text=f"{_milliers(n.iloc[i, j])} événements", showarrow=False, yshift=-14,
                               font=dict(size=11, color="rgba(255,255,255,.75)"))
    fig.update_xaxes(side="top", gridcolor="rgba(0,0,0,0)", tickfont=dict(color=TEXTE, size=12))
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", tickfont=dict(color=TEXTE, size=12))
    fig.add_annotation(xref="paper", yref="paper", x=0, y=-0.13, xanchor="left", showarrow=False,
                       text=f"Cases vides : moins de {seuil} événements", font=dict(size=10, color=MUET))
    return _base(fig, 340, margin=dict(l=8, r=8, t=28, b=38))


# 7. Âge de l'aéronef : mortels contre non mortels (distribution en %) ---------------------
def ages(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return vide(hauteur=340)
    mort = df[df["gravite"] == "FATL"]["age"]
    reste = df[df["gravite"] != "FATL"]["age"]
    if len(mort) < 30 or len(reste) < 30:
        return vide("Pas assez de données d'âge pour ces filtres", 340)
    fig = go.Figure()
    for serie, nom, c in ((reste, "Autres événements", AUTRE), (mort, "Événements mortels", FATAL)):
        fig.add_histogram(x=serie, name=nom, histnorm="percent", xbins=dict(start=0, end=100, size=5),
                          marker=dict(color=c, line=dict(width=0)), opacity=0.7,
                          hovertemplate="%{x} ans : %{y:.1f} % des événements<extra>" + nom + "</extra>")
    fig.update_layout(barmode="overlay", bargap=0.06)
    fig.add_vline(x=float(mort.median()), line_dash="dot", line_color=FATAL, line_width=1,
                  annotation_text=f"médiane mortels : {mort.median():.0f} ans", annotation_font=dict(size=10, color=FATAL),
                  annotation_position="top right")
    fig.update_xaxes(title_text="Âge de l'aéronef (années)", range=[0, 80], showgrid=False)
    fig.update_yaxes(title_text="% des événements du groupe", ticksuffix=" %")
    return _base(fig, 340, margin=dict(l=8, r=8, t=28, b=8))


# 8. Causes : famille > sous-famille (constats des enquêteurs) --------------------------------
TRAD_N1 = {"Personnel issues": "Facteur humain", "Aircraft": "Aéronef", "Environmental issues": "Environnement",
           "Organizational issues": "Organisation"}
TRAD_N2 = {
    "Task performance": "Exécution de la tâche", "Action/decision": "Action et décision",
    "Aircraft oper/perf/capability": "Pilotage et performance", "Physical environment": "Environnement physique",
    "Conditions/weather/phenomena": "Météo et phénomènes", "Aircraft systems": "Systèmes",
    "Aircraft power plant": "Moteur", "Psychological": "Psychologie", "Fluids/misc hardware": "Fluides et équipements",
    "Experience/knowledge": "Expérience", "Physical": "État physique", "Aircraft structures": "Structures",
    "Aircraft propeller/rotor": "Hélice et rotor", "Aircraft handling/service": "Entretien",
    "Operating environment": "Exploitation", "Support/oversight/monitoring": "Supervision", "Management": "Management",
    "Development": "Conception", "Task environment": "Environnement de travail", "Miscellaneous": "Divers",
}
COULEURS_N1 = {"Facteur humain": "#3E6FB0", "Aéronef": "#7A64B8", "Environnement": "#3A9A8B", "Organisation": "#B8A06A"}


def causes(df: pd.DataFrame, par_famille: int = 4) -> go.Figure:
    if df.empty:
        return vide(hauteur=340)
    d = df[df["niveau1"].isin(["Personnel issues", "Aircraft", "Environmental issues"])].copy()
    d["niveau2"] = d["niveau2"].fillna("Divers")
    d = d.groupby(["niveau1", "niveau2"])["ev_id"].nunique().reset_index(name="constats")
    if d.empty:
        return vide(hauteur=340)
    morceaux = []
    for n1, g in d.groupby("niveau1"):
        g = g.sort_values("constats", ascending=False)
        total = g["constats"].sum()
        gros = g[g["constats"] >= 0.06 * total].head(par_famille)
        reste = g["constats"].sum() - gros["constats"].sum()
        morceaux.append(gros)
        if reste >= 0.06 * total:
            morceaux.append(pd.DataFrame([{"niveau1": n1, "niveau2": "Autres", "constats": reste}]))
    d = pd.concat(morceaux, ignore_index=True)
    d["Famille"] = d["niveau1"].map(TRAD_N1)
    d["Sous-famille"] = d["niveau2"].map(lambda v: TRAD_N2.get(v, v))
    fam = d.groupby("Famille")["constats"].sum()
    ids = ["tout"] + list(fam.index) + [f"{a}|{b}" for a, b in zip(d["Famille"], d["Sous-famille"])]
    labels = ["Constats"] + list(fam.index) + list(d["Sous-famille"])
    parents = [""] + ["tout"] * len(fam) + list(d["Famille"])
    values = [0] + list(fam.values) + list(d["constats"])
    couleurs = ["rgba(0,0,0,0)"] + [COULEURS_N1[f] for f in fam.index] + [COULEURS_N1[f] for f in d["Famille"]]
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="remainder", marker=dict(colors=couleurs, line=dict(width=2, color=BG)),
        texttemplate="<b>%{label}</b><br>%{value:,d}", textfont=dict(family=POLICE, size=13, color="white"),
        textposition="top left", pathbar=dict(visible=False), root_color="rgba(0,0,0,0)",
        hovertemplate="%{label}<br>%{value:,d} constats<extra></extra>"))
    return _base(fig, 340, margin=dict(l=0, r=0, t=0, b=0))
