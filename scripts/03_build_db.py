"""Construit la base SQLite data/aviation.db à partir des CSV exportés d'avall.mdb."""
import os
import re
import sqlite3
from pathlib import Path

import pandas as pd

CSV = Path("data/csv")
DB = Path("data/aviation.db")
PAYS = "USA"  # None pour conserver les événements de tous les pays

DDL = """
CREATE TABLE etats (
    code_etat  TEXT PRIMARY KEY,
    nom        TEXT NOT NULL,
    region_faa TEXT
);
CREATE TABLE segments (
    code_segment TEXT PRIMARY KEY,
    libelle      TEXT NOT NULL
);
CREATE TABLE constructeurs (
    id_constructeur INTEGER PRIMARY KEY,
    nom             TEXT NOT NULL UNIQUE
);
CREATE TABLE phases (
    phase_no INTEGER PRIMARY KEY,
    libelle  TEXT NOT NULL,
    famille  TEXT NOT NULL
);
CREATE TABLE events (
    ev_id           TEXT PRIMARY KEY,
    ntsb_no         TEXT,
    ev_type         TEXT,
    ev_date         TEXT,
    ev_year         INTEGER,
    ev_month        INTEGER,
    ev_city         TEXT,
    code_etat       TEXT REFERENCES etats(code_etat),
    ev_country      TEXT,
    latitude        REAL,
    longitude       REAL,
    gravite_max     TEXT,
    morts           INTEGER,
    blesses_graves  INTEGER,
    blesses_legers  INTEGER,
    indemnes        INTEGER,
    total_personnes INTEGER,
    lumiere         TEXT,
    meteo           TEXT
);
CREATE TABLE aircraft (
    ev_id              TEXT NOT NULL REFERENCES events(ev_id),
    aircraft_key       TEXT NOT NULL,
    categorie          TEXT,
    far_part           TEXT,
    code_segment       TEXT REFERENCES segments(code_segment),
    id_constructeur    INTEGER REFERENCES constructeurs(id_constructeur),
    modele             TEXT,
    annee_construction INTEGER,
    nb_moteurs         INTEGER,
    dommages           TEXT,
    type_vol           TEXT,
    PRIMARY KEY (ev_id, aircraft_key)
);
CREATE TABLE findings (
    id_finding   INTEGER PRIMARY KEY AUTOINCREMENT,
    ev_id        TEXT NOT NULL REFERENCES events(ev_id),
    aircraft_key TEXT,
    finding_no   INTEGER,
    finding_code TEXT,
    description  TEXT,
    cause_factor TEXT
);
CREATE TABLE sequences (
    id_sequence   INTEGER PRIMARY KEY AUTOINCREMENT,
    ev_id         TEXT NOT NULL REFERENCES events(ev_id),
    aircraft_key  TEXT,
    occurrence_no INTEGER,
    phase_no      INTEGER REFERENCES phases(phase_no),
    evenement     TEXT,
    description   TEXT,
    evenement_definissant TEXT
);
CREATE TABLE injuries (
    id_injury          INTEGER PRIMARY KEY AUTOINCREMENT,
    ev_id              TEXT NOT NULL REFERENCES events(ev_id),
    aircraft_key       TEXT,
    categorie_personne TEXT,
    niveau             TEXT,
    nombre             INTEGER
);
CREATE INDEX idx_events_year  ON events(ev_year);
CREATE INDEX idx_events_etat  ON events(code_etat);
CREATE INDEX idx_aircraft_ev  ON aircraft(ev_id);
CREATE INDEX idx_aircraft_seg ON aircraft(code_segment);
CREATE INDEX idx_findings_ev  ON findings(ev_id);
CREATE INDEX idx_seq_ev       ON sequences(ev_id);
CREATE INDEX idx_seq_phase    ON sequences(phase_no);
CREATE INDEX idx_inj_ev       ON injuries(ev_id);
"""

SEGMENTS = {
    "AG": "Aviation générale (Part 91, dont 91K)",
    "LIGNE": "Compagnies régulières (Part 121)",
    "TAXI": "Taxi aérien et commuter (Part 135)",
    "TRAVAIL": "Travail aérien (Parts 133 et 137)",
    "ETR": "Exploitants étrangers (Part 129, non-U.S.)",
    "PUB": "Aéronefs publics et militaires",
    "SPEC": "Régimes spéciaux (drones, ultralégers, expérimental)",
    "AUTRE": "Non renseigné",
}
FAR_VERS_SEGMENT = {
    "091": "AG", "091K": "AG",
    "121": "LIGNE", "135": "TAXI",
    "133": "TRAVAIL", "137": "TRAVAIL",
    "129": "ETR", "NUSN": "ETR", "NUSC": "ETR",
    "PUBU": "PUB", "ARMF": "PUB",
    "103": "SPEC", "107": "SPEC", "125": "SPEC", "437": "SPEC",
}
CATEGORIES = {
    "AIR": "Avion", "HELI": "Hélicoptère", "GLI": "Planeur", "BALL": "Ballon",
    "WSFT": "Pendulaire", "GYRO": "Autogire", "PPAR": "Paramoteur",
    "ULTR": "Ultra-léger", "UNK": "Inconnu",
}
REGLES_MARQUES = [
    (r"^BEECH(CRAFT)?\b", "BEECH"), (r"^BELLANCA\b", "BELLANCA"), (r"^BELL\b", "BELL"),
    (r"^ROBINSON\b", "ROBINSON"), (r"^CIRRUS\b", "CIRRUS"),
    (r"^AIR TRACTOR\b", "AIR TRACTOR"), (r"^CESSNA\b", "CESSNA"),
    (r"^PIPER\b", "PIPER"), (r"^BOEING\b", "BOEING"), (r"^AIRBUS\b", "AIRBUS"),
    (r"^MOONEY\b", "MOONEY"), (r"^MAULE\b", "MAULE"), (r"^HUGHES\b", "HUGHES"),
    (r"^EUROCOPTER\b", "EUROCOPTER"), (r"^SCHWEIZER\b", "SCHWEIZER"),
    (r"^MCDONNELL DOUGLAS\b", "MCDONNELL DOUGLAS"), (r"^DASSAULT\b", "DASSAULT"),
    (r"^EMBRAER\b", "EMBRAER"), (r"^BOMBARDIER\b", "BOMBARDIER"),
    (r"^GULFSTREAM\b", "GULFSTREAM"),
]
SUFFIXES = r"\s+(INC|CORP|CORPORATION|CO|COMPANY|LTD|LLC|AIRCRAFT|HELICOPTERS?)\.?$"


def lire(nom, colonnes=None):
    """Lit un CSV en texte (les identifiants mélangent chiffres et lettres)."""
    df = pd.read_csv(CSV / f"{nom}.csv", dtype=str, usecols=colonnes, low_memory=False)
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def entier(serie):
    return pd.to_numeric(serie, errors="coerce").astype("Int64")


def normaliser_marque(marque):
    if pd.isna(marque):
        return "INCONNU"
    m = re.sub(r"[^\w\s/&-]", " ", str(marque).upper())
    m = re.sub(r"\s+", " ", m).strip()
    m = re.sub(r"^THE ", "", m)
    for motif, nom in REGLES_MARQUES:
        if re.match(motif, m):
            return nom
    precedent = None
    while precedent != m:
        precedent = m
        m = re.sub(SUFFIXES, "", m).strip()
    return m or "INCONNU"


def libelle_phase(descriptions):
    """Libellé de phase = début commun (mot à mot) de toutes les descriptions."""
    jetons = [d.split() for d in descriptions]
    commun = jetons[0]
    for j in jetons[1:]:
        n = 0
        for a, b in zip(commun, j):
            if a != b:
                break
            n += 1
        commun = commun[:n]
        if not commun:
            break
    return " ".join(commun)


def famille_phase(no):
    """Regroupe les 48 phases détaillées en 8 familles de vol."""
    if no < 300 or no == 750:
        return "Sol (préparation, roulage)"
    if no < 400:
        return "Décollage et montée initiale"
    if no < 450:
        return "Croisière"
    if no < 500:
        return "Manœuvres"
    if no < 550:
        return "Approche"
    if no < 600:
        return "Atterrissage"
    if no < 700:
        return "Descente d'urgence ou incontrôlée"
    return "Autre ou inconnu"


def main():
    if DB.exists():
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)

    # --- events -----------------------------------------------------------
    ev = lire("events", [
        "ev_id", "ntsb_no", "ev_type", "ev_date", "ev_year", "ev_month", "ev_city",
        "ev_state", "ev_country", "dec_latitude", "dec_longitude",
        "ev_highest_injury", "inj_tot_f", "inj_tot_s", "inj_tot_m", "inj_tot_n",
        "inj_tot_t", "light_cond", "wx_cond_basic",
    ]).drop_duplicates("ev_id")
    total_brut = len(ev)
    if PAYS:
        ev = ev[ev["ev_country"] == PAYS]
    print(f"Événements retenus : {len(ev)} sur {total_brut} (filtre pays : {PAYS})")
    ids = set(ev["ev_id"])

    dates = pd.to_datetime(ev["ev_date"], format="%m/%d/%y %H:%M:%S", errors="coerce")
    if dates.isna().mean() > 0.5:
        dates = pd.to_datetime(ev["ev_date"], errors="coerce")
    ecart = (dates.dt.year != pd.to_numeric(ev["ev_year"], errors="coerce")).sum()
    print(f"Dates illisibles : {dates.isna().sum()} | année différente d'ev_year : {ecart}")

    lat = pd.to_numeric(ev["dec_latitude"], errors="coerce")
    lon = pd.to_numeric(ev["dec_longitude"], errors="coerce")
    valide = lat.between(-90, 90) & lon.between(-180, 180) & ~((lat == 0) & (lon == 0))
    lat, lon = lat.where(valide), lon.where(valide)

    # --- états ------------------------------------------------------------
    st = lire("states")
    etats = pd.DataFrame({
        "code_etat": st["state"], "nom": st["name"].str.title(), "region_faa": st["faa_region"],
    })
    manquants = sorted(set(ev["ev_state"].dropna()) - set(etats["code_etat"]))
    if manquants:
        ajout = pd.DataFrame({
            "code_etat": manquants, "nom": manquants, "region_faa": [None] * len(manquants),
        })
        etats = pd.concat([etats, ajout], ignore_index=True)
    etats.to_sql("etats", con, if_exists="append", index=False)

    # --- segments ---------------------------------------------------------
    pd.DataFrame({
        "code_segment": list(SEGMENTS), "libelle": list(SEGMENTS.values()),
    }).to_sql("segments", con, if_exists="append", index=False)

    # --- aircraft + constructeurs ----------------------------------------
    ac = lire("aircraft", [
        "ev_id", "Aircraft_Key", "far_part", "acft_category", "acft_make", "acft_model",
        "acft_year", "num_eng", "damage", "type_fly",
    ])
    ac = ac[ac["ev_id"].isin(ids)].drop_duplicates(["ev_id", "Aircraft_Key"]).copy()
    table_marques = {m: normaliser_marque(m) for m in ac["acft_make"].unique()}
    ac["marque"] = ac["acft_make"].map(table_marques)
    noms = sorted(set(ac["marque"]))
    constructeurs = pd.DataFrame({"id_constructeur": range(1, len(noms) + 1), "nom": noms})
    constructeurs.to_sql("constructeurs", con, if_exists="append", index=False)
    id_par_nom = dict(zip(constructeurs["nom"], constructeurs["id_constructeur"]))

    def segment(far):
        if pd.isna(far) or far in ("", "UNK"):
            return "AUTRE"
        return FAR_VERS_SEGMENT.get(far, "AUTRE")

    # --- phases (déduites des descriptions de séquences) -----------------
    sq = lire("Events_Sequence", [
        "ev_id", "Aircraft_Key", "Occurrence_No", "Occurrence_Description",
        "phase_no", "Defining_ev",
    ])
    sq = sq[sq["ev_id"].isin(ids)].copy()
    sq["phase_no"] = entier(sq["phase_no"])
    libelles = {}
    avec_texte = sq.dropna(subset=["phase_no", "Occurrence_Description"])
    for no, groupe in avec_texte.groupby("phase_no"):
        libelles[int(no)] = libelle_phase(groupe["Occurrence_Description"].unique())
    for no in sq["phase_no"].dropna().unique():
        libelles.setdefault(int(no), f"Phase {int(no)}")
    phases = pd.DataFrame({"phase_no": list(libelles), "libelle": list(libelles.values())})
    phases["famille"] = phases["phase_no"].map(famille_phase)
    phases.to_sql("phases", con, if_exists="append", index=False)

    # --- insertion des tables principales --------------------------------
    events = pd.DataFrame({
        "ev_id": ev["ev_id"], "ntsb_no": ev["ntsb_no"], "ev_type": ev["ev_type"],
        "ev_date": dates.dt.strftime("%Y-%m-%d"),
        "ev_year": entier(ev["ev_year"]), "ev_month": entier(ev["ev_month"]),
        "ev_city": ev["ev_city"], "code_etat": ev["ev_state"], "ev_country": ev["ev_country"],
        "latitude": lat, "longitude": lon, "gravite_max": ev["ev_highest_injury"],
        "morts": entier(ev["inj_tot_f"]), "blesses_graves": entier(ev["inj_tot_s"]),
        "blesses_legers": entier(ev["inj_tot_m"]), "indemnes": entier(ev["inj_tot_n"]),
        "total_personnes": entier(ev["inj_tot_t"]),
        "lumiere": ev["light_cond"], "meteo": ev["wx_cond_basic"],
    })
    events.to_sql("events", con, if_exists="append", index=False, chunksize=5000)

    aircraft = pd.DataFrame({
        "ev_id": ac["ev_id"], "aircraft_key": ac["Aircraft_Key"],
        "categorie": ac["acft_category"].map(CATEGORIES).fillna("Inconnu"),
        "far_part": ac["far_part"],
        "code_segment": ac["far_part"].map(segment),
        "id_constructeur": ac["marque"].map(id_par_nom),
        "modele": ac["acft_model"], "annee_construction": entier(ac["acft_year"]),
        "nb_moteurs": entier(ac["num_eng"]), "dommages": ac["damage"],
        "type_vol": ac["type_fly"],
    })
    aircraft.to_sql("aircraft", con, if_exists="append", index=False, chunksize=5000)

    fi = lire("Findings", [
        "ev_id", "Aircraft_Key", "finding_no", "finding_code",
        "finding_description", "Cause_Factor",
    ])
    fi = fi[fi["ev_id"].isin(ids)]
    pd.DataFrame({
        "ev_id": fi["ev_id"], "aircraft_key": fi["Aircraft_Key"],
        "finding_no": entier(fi["finding_no"]), "finding_code": fi["finding_code"],
        "description": fi["finding_description"], "cause_factor": fi["Cause_Factor"],
    }).to_sql("findings", con, if_exists="append", index=False, chunksize=5000)

    def evenement(desc, no):
        if pd.isna(desc):
            return None
        lib = libelles.get(int(no)) if pd.notna(no) else None
        if lib and desc.startswith(lib):
            return desc[len(lib):].strip() or desc
        return desc

    sq["evenement"] = [
        evenement(d, n) for d, n in zip(sq["Occurrence_Description"], sq["phase_no"])
    ]
    pd.DataFrame({
        "ev_id": sq["ev_id"], "aircraft_key": sq["Aircraft_Key"],
        "occurrence_no": entier(sq["Occurrence_No"]), "phase_no": sq["phase_no"],
        "evenement": sq["evenement"], "description": sq["Occurrence_Description"],
        "evenement_definissant": sq["Defining_ev"],
    }).to_sql("sequences", con, if_exists="append", index=False, chunksize=5000)

    inj = lire("injury")
    inj = inj[inj["ev_id"].isin(ids)]
    pd.DataFrame({
        "ev_id": inj["ev_id"], "aircraft_key": inj["Aircraft_Key"],
        "categorie_personne": inj["inj_person_category"], "niveau": inj["injury_level"],
        "nombre": entier(inj["inj_person_count"]),
    }).to_sql("injuries", con, if_exists="append", index=False, chunksize=5000)
    con.commit()

    # --- contrôles --------------------------------------------------------
    print("\n=== Lignes par table ===")
    for t in ["etats", "segments", "constructeurs", "phases", "events",
              "aircraft", "findings", "sequences", "injuries"]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t:15s}{n:>9}")
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    print("Violations de clés étrangères :", len(violations))
    n_geo = con.execute("SELECT COUNT(*) FROM events WHERE latitude IS NOT NULL").fetchone()[0]
    print(f"Événements géolocalisés : {n_geo}")

    print("\n=== Accidents par segment ===")
    print(pd.read_sql_query(
        "SELECT s.libelle, COUNT(DISTINCT a.ev_id) AS evenements, "
        "COUNT(DISTINCT CASE WHEN e.gravite_max = 'FATL' THEN a.ev_id END) AS mortels "
        "FROM aircraft a JOIN segments s USING(code_segment) "
        "JOIN events e USING(ev_id) GROUP BY s.libelle ORDER BY evenements DESC",
        con).to_string(index=False))

    print("\n=== Séquences par famille de phase ===")
    print(pd.read_sql_query(
        "SELECT p.famille, COUNT(*) AS lignes FROM sequences s "
        "JOIN phases p USING(phase_no) GROUP BY p.famille ORDER BY lignes DESC",
        con).to_string(index=False))

    print("\n=== Top 10 constructeurs ===")
    print(pd.read_sql_query(
        "SELECT c.nom, COUNT(*) AS aeronefs FROM aircraft a "
        "JOIN constructeurs c USING(id_constructeur) "
        "GROUP BY c.nom ORDER BY aeronefs DESC LIMIT 10", con).to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
