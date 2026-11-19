"""Profil des tables utiles : colonnes, répartitions principales, cohérence des jointures."""
from pathlib import Path

import pandas as pd

CSV = Path("data/csv")


def charger(nom):
    return pd.read_csv(CSV / f"{nom}.csv", low_memory=False)


events = charger("events")
aircraft = charger("aircraft")
findings = charger("Findings")
seq = charger("Events_Sequence")
injury = charger("injury")
tables = [
    ("aircraft", aircraft),
    ("Findings", findings),
    ("Events_Sequence", seq),
    ("injury", injury),
]

for nom, df in tables:
    print(f"\n=== {nom} ({len(df)} lignes) ===")
    print(", ".join(df.columns))

print("\n=== Répartitions dans events ===")
for c in ["ev_type", "ev_highest_injury"]:
    print(f"\n{c} :")
    print(events[c].value_counts(dropna=False).head(10))

print("\n=== Aéronefs ===")
for c in ["acft_category", "far_part", "damage"]:
    if c in aircraft.columns:
        print(f"\n{c} :")
        print(aircraft[c].value_counts(dropna=False).head(10))

if "acft_make" in aircraft.columns:
    marque = aircraft["acft_make"].astype(str).str.upper()
    print("\nTop 15 constructeurs :")
    print(marque.value_counts().head(15))
    dassault = aircraft[marque.str.contains("DASSAULT|FALCON", na=False)]
    print(f"\nDassault / Falcon : {len(dassault)} aéronefs")
    if "acft_model" in aircraft.columns and len(dassault):
        print(dassault["acft_model"].value_counts().head(10))

print("\n=== Jointures sur ev_id ===")
ids = set(events["ev_id"])
for nom, df in tables:
    if "ev_id" in df.columns:
        part = df["ev_id"].isin(ids).mean()
        print(f"{nom} : {part:.0%} des lignes rattachées à un événement")
