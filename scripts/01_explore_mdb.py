"""Exporte les tables du fichier NTSB (avall.mdb) en CSV et affiche un état des lieux."""
import subprocess
from pathlib import Path

import pandas as pd

MDB = Path("data/raw/avall.mdb")
OUT = Path("data/csv")
OUT.mkdir(parents=True, exist_ok=True)


def lister_tables():
    res = subprocess.run(
        ["mdb-tables", "-1", str(MDB)], capture_output=True, text=True, check=True
    )
    return [t.strip() for t in res.stdout.splitlines() if t.strip()]


def main():
    print(f"{'table':28s}{'lignes':>10}{'colonnes':>10}")
    print("-" * 48)
    frames = {}
    for table in lister_tables():
        dest = OUT / f"{table}.csv"
        with open(dest, "w") as f:
            subprocess.run(["mdb-export", str(MDB), table], stdout=f, check=True)
        df = pd.read_csv(dest, low_memory=False)
        frames[table] = df
        print(f"{table:28s}{len(df):>10}{df.shape[1]:>10}")

    # Zoom sur la table des événements
    nom = next((t for t in frames if t.lower() == "events"), None)
    if nom is None:
        print("\nPas de table 'events' trouvée : envoie-moi la liste ci-dessus.")
        return
    ev = frames[nom]
    print(f"\n--- Table {nom} ---")
    print("Colonnes :", ", ".join(ev.columns))
    col_annee = next((c for c in ev.columns if c.lower() == "ev_year"), None)
    if col_annee:
        print(f"Années couvertes : {int(ev[col_annee].min())} à {int(ev[col_annee].max())}")
    for c in ev.columns:
        if "lat" in c.lower() or "lon" in c.lower():
            print(f"{c}: {ev[c].notna().mean():.0%} renseigné")


if __name__ == "__main__":
    main()