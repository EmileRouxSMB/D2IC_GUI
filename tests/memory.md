# Memory — D2IC_GUI/tests

## Rôle du dossier

Vérifier les contrats scientifiques et les interactions du GUI local.

## Fichiers importants

- `test_build_windows.py` : rejette les wheels Linux, binaires non x64 et plugins GPU ; vérifie le placement des DLL Microsoft CRT et le lanceur Windows écrit depuis Linux.

- `test_build_portable.py` : sources de construction sans modification des originaux, dépendances headless, actifs inclus, nettoyage conservant licences et métadonnées.
- `test_desktop.py` : forçage CPU avant imports, socket loopback, ouverture du navigateur après disponibilité HTTP et suivi/arrêt des workers multiplateforme.

- `test_project_server.py` : configurations, API, ROI, maillage, snapshots et worker DIC.
- `test_thermal.py` : correspondance temporelle et échantillonnage thermique.
- `test_synthetic_study.py` : génération des séquences analytiques.
- `test_integration_studies.py` : parcours des études DIC et couplées.
- `test_image_zoom.cjs` : géométrie du zoom, transformations et interception des gestes, avec Node sans dépendance npm.

## Concepts physiques ou numériques

Les déplacements et coordonnées sont en pixels VIS d’origine ; la température est transportée aux mêmes points matériels. Le zoom ne change que la vue et conserve les coordonnées natives.

## Conventions

Depuis la racine : `PYTHONPATH=D2IC/src:im_jax:. python -m pytest -q D2IC_GUI/tests`.
Pour le zoom : `node --test D2IC_GUI/tests/test_image_zoom.cjs`.

## Points d’attention

Les tests Python utilisent des images synthétiques et des dossiers temporaires. Les tests Node utilisent un DOM simulé pour les gestes et la géométrie ; ils ne remplacent pas une inspection visuelle en navigateur.


`test_roi_shapes.py` vérifie la rastérisation native rectangle/ellipse, les trous, la photométrie avec binning, les fichiers TIFF sans écrasement et la conservation des masques presque pleins au rechargement. `test_roi_shapes.cjs` vérifie la conversion écran vers pixels natifs après zoom et les glissements inversés.
