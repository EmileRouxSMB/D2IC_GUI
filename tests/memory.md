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


`test_readiness.py` contrôle la préparation du cas et le refus de création d’un run incomplet via l’API. `test_readiness.cjs` exerce les limites de lancement asynchrones : obligations manquantes, lancement direct malgré les compléments facultatifs, échec de vérification/sauvegarde, refus serveur et double clic. Exécuter `node --test D2IC_GUI/tests/test_readiness.cjs` ; ces tests utilisent les fonctions du GUI dans un contexte simulé.

Le test de redimensionnement avec bandeau de 42 px dans `test_image_zoom.cjs` vérifie que le point source au centre du rectangle image reste identique après changement de proportions de la fenêtre.


`test_result_overlay.py` vérifie le fond VIS courant et sa provenance, le maillage déplacé en pixels avec des valeurs exportées en mm, les PNG RGBA, les trous NaN, le transport analytique d’un résidu sous translation, les bords incomplets après binning et la disponibilité de résidus sur des instants tardifs.


`test_parameter_catalog.py` vérifie une extension TOML seule jusqu’aux défauts, à l’API et à la persistance, ainsi que les rejets de catalogue incohérent. `test_parameter_catalog.cjs` vérifie types de contrôles, choix multiples, placement des nouveaux champs et conversion des valeurs.


Le test du contrôleur dans `test_image_zoom.cjs` vérifie aussi le curseur Ctrl/Cmd sans mouvement de souris, le maintien de Ctrl au relâchement de Cmd, la perte de focus, la synchronisation à l’entrée du pointeur et le retrait des écouteurs à la destruction.


Les tests live dans `test_result_overlay.py` simulent une frame sur disque encore non validée, puis sa publication par checkpoint/progression : cartes, maillage déplacé, fond VIS, bornes et courbes restent limités aux temps validés. Les résultats restent consultables après interruption ; les sorties thermiques sont découvertes après fusion et l’initialisation sans maillage renvoie une attente explicite.

`test_result_live.cjs` vérifie l’ajout d’instants validés et de champs thermiques, la conservation du champ et de l’instant choisis, ainsi que l’invalidation des historiques pendant le polling.


`test_result_sections.py` contrôle les coupes affines, les unités px/mm, les valeurs hors maillage, les CSV et les bornes symétriques de couleurs. `test_result_analysis.cjs` vérifie le transport aller-retour référence/courante et la construction des paramètres de coupe. `test_result_live.cjs` vérifie la croissance du slider et la conservation des sélections pendant un run.


La régression binning dans `test_readiness.py` vérifie le refus sans création de run, le diagnostic 1 → 2 et le déblocage après régénération du maillage. `test_readiness.cjs` vérifie que la cause du refus est visible près du bouton désactivé.

`test_roi_mesh.cjs` vérifie la transformation des arêtes en pixels VIS vers le calque SVG écran pour des images paysage/portrait et les zooms ×1, ×2, ×16 et ×64.


`test_readiness.py` couvre aussi le cycle préparer → ligne bloquée/prête → lancement explicite, les avertissements non bloquants, le snapshot inchangé après modification de l’étude, une source modifiée, une erreur de lecture complète, la préparation pendant un calcul, les changements simultanés de configuration/masque et la suppression concurrente au démarrage. `test_readiness.cjs` vérifie les routes séparées, les messages échappés dans chaque ligne et l’activation de Lancer selon `can_start`.


`test_thermal_streaming.py` contrôle la consommation progressive des déplacements, les températures analytiques et invalidités, le format NPZ inchangé, les exports et la conservation d’une archive existante après une erreur de fusion ou de compression. `test_result_analysis.cjs` importe directement `result_analysis.js`, sans découpage textuel de `app.js`.
