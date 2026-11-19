# Accidents d'aviation aux États-Unis : dashboard NTSB

Projet final du module Visualisation interactive (MSc2 DATA, EPITA).

**Idée forte :** l'aviation générale concentre neuf accidents mortels sur dix aux États-Unis, et ils se jouent en vol (manœuvres, descentes incontrôlées, croisière) bien plus qu'à l'atterrissage.

**Audience :** responsables sécurité d'aéroclubs, d'écoles de pilotage et d'exploitants d'aviation générale.

**Source :** NTSB, base `avall` (accidents et incidents d'aviation civile), https://data.ntsb.gov/avdata/ . Seuls les événements survenus aux États-Unis sont conservés : 25 510 événements de 2008 à 2026, 25 450 géolocalisés.

## Contenu du dépôt

| Fichier ou dossier | Rôle |
|---|---|
| `app.py` | Application Dash : mise en page, filtres, callback unique qui met à jour KPI, 6 graphiques et carte |
| `db.py` | Connexion SQLite et toutes les requêtes SQL du dashboard |
| `charts.py` | Les 6 graphiques Plotly (un par fonction) |
| `carte.py` | La carte Folium (densité + marqueurs détaillés) |
| `assets/style.css` | Mise en forme (chargé automatiquement par Dash) |
| `data/aviation.db` | Base SQLite relationnelle, 9 tables liées par clés étrangères |
| `scripts/01_explore_mdb.py` | Exporte les tables du fichier NTSB `avall.mdb` en CSV |
| `scripts/02_profil_tables.py` | Contrôle des tables exportées |
| `scripts/03_build_db.py` | **Régénère `data/aviation.db`** à partir des CSV |
| `notebooks/04_graphiques_plotly.ipynb` | Premiers graphiques exploratoires |
| `requirements.txt`, `.python-version`, `render.yaml` | Déploiement sur Render |

## Schéma de la base

```
etats (code_etat PK)          segments (code_segment PK)       constructeurs (id_constructeur PK)
        |                              |                                  |
        |                              |                                  |
     events (ev_id PK) <---------- aircraft (ev_id + aircraft_key PK) ----+
        ^   ^   ^                      (code_segment FK, id_constructeur FK)
        |   |   |
        |   |   +-- injuries   (ev_id FK)
        |   +------ findings   (ev_id FK)      causes et facteurs relevés
        +---------- sequences  (ev_id FK, phase_no FK) ---> phases (phase_no PK)
```

## Lancer le dashboard en local (Mac)

```bash
cd projet-aviation
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Puis ouvrir http://127.0.0.1:8050 dans le navigateur.

## Régénérer la base depuis zéro

Nécessaire seulement si `data/aviation.db` est perdu ou si on veut des données plus récentes.

```bash
brew install mdbtools                      # une seule fois
# 1. télécharger avall.zip sur https://data.ntsb.gov/avdata/ , le dézipper,
#    et placer avall.mdb dans data/raw/
python scripts/01_explore_mdb.py           # exporte les tables en CSV dans data/csv/
python scripts/03_build_db.py              # construit data/aviation.db
```

## Déploiement (Render)

Le dashboard est servi par `gunicorn app:server`. Étapes détaillées dans la conversation de livraison ; en résumé :
dépôt GitHub public, puis « New Web Service » sur render.yaml ou avec la commande de démarrage
`gunicorn app:server --workers 1 --threads 4 --timeout 120`.
L'offre gratuite met le service en veille après 15 minutes sans visite : ouvrir l'URL quelques minutes avant la démonstration.
