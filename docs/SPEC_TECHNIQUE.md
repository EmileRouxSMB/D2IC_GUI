# Spécification technique

Cette note résume l’architecture et les invariants d’exécution de D2IC_GUI. Les
conventions scientifiques partagées avec D2IC et DICTHFusion sont définies dans
[INTEGRATION_CONTRACTS.md](INTEGRATION_CONTRACTS.md), le stockage des résultats
dans [RESULT_MODEL.md](RESULT_MODEL.md), et les clés de configuration dans
[CONFIG_SCHEMA.md](CONFIG_SCHEMA.md). L’état de livraison figure dans
[ROADMAP_DEV.md](ROADMAP_DEV.md).

## Architecture

D2IC_GUI est une application web locale : le serveur Python écoute sur
`127.0.0.1`, sert l’interface et lit les données sur la machine de l’utilisateur.
Le navigateur affiche des aperçus et des champs ; les séquences complètes et les
calculs restent côté serveur. L’application n’est pas un service réseau ou
multiutilisateur.

Le paquet Python est dans `src/D2IC_GUI/`. Les principaux modules sont :

- `server.py` : routes HTTP, vues, inventaire et orchestration des opérations ;
- `project.py`, `schema.py`, `parameters.toml`, `readiness.py` : projets,
  configuration, validation et prérequis ;
- `imaging.py`, `roi.py`, `thermal.py`, `results.py` : aperçus et traitements
  d’images, ROI, données thermiques et résultats ;
- `worker.py`, `dic_run.py` : exécution et adaptation du pipeline D2IC ;
- `static/` : HTML, CSS et JavaScript natif, sans compilation front-end.

D2IC fournit le solveur séquentiel et DICTHFusion les outils de correspondance
VIS–TH. FastAPI/Uvicorn servent l’application ; JAX exécute DIC sur CPU (ou sur
un accélérateur disponible et configuré). OpenCV est requis sans interface
graphique dans les distributions portables.

## Étude, configuration et exécution

Chaque étude contient un `config.toml`, les petits fichiers propres au projet
(masque ROI, calibration éventuelle) et un dossier `runs/`. Les images sources
restent à leur emplacement. Les chemins relatifs sont résolus depuis le fichier
de configuration ; les chemins et paramètres effectivement utilisés sont
figés dans chaque run.

La GUI valide les changements et remplace atomiquement le TOML sauvegardé. Sa
réécriture peut normaliser le format et ne garantit pas la conservation des
commentaires libres. Chaque run conserve une configuration résolue, les
références de ses entrées, son état et ses résultats. Le manifeste enregistre
les chemins, temps, unités et provenance utiles ; un chemin seul ne garantit pas
que le contenu du fichier source n’a pas changé.

Les calculs DIC s’exécutent dans un processus de travail séparé afin de ne pas
bloquer le serveur. Un run préparé fige ses entrées ; les contrôles sont répétés
au lancement. Un seul worker est actif à la fois. État, progression, journaux,
arrêt et reprise sont associés au run. Les résultats ne sont publiés comme
terminés qu’après leur écriture validée. Les détails du format persistant sont
dans [RESULT_MODEL.md](RESULT_MODEL.md).

## Invariants de données et de calcul

- Les images VIS sont traitées par D2IC ; les TIFF thermiques restent des
  images 2D de température, sans conversion couleur ni correction radiométrique
  dans la GUI.
- Les temps de sortie sont ceux des acquisitions VIS retenues. Une image VIS ou
  un déplacement DIC n’est pas interpolé. Les détails de synchronisation et de
  fusion sont définis dans [INTEGRATION_CONTRACTS.md](INTEGRATION_CONTRACTS.md).
- Les coordonnées d’étalonnage sont exprimées dans les pixels VIS d’origine.
  La valeur initiale `1 mm/pixel` n’est pas un étalonnage confirmé. Les
  longueurs en millimètres ne sont disponibles qu’après confirmation ; les
  déformations restent sans dimension.
- Une ROI doit être non vide et cohérente avec l’image de référence. Le masque
  source reste intact ; le masque et le maillage utilisés sont figés dans le
  projet ou le run. Un changement d’entrée invalide les aperçus dérivés.
- Une calibration VIS–TH exige une approbation manuelle liée aux données
  examinées. Aucun seuil universel de résidu ne décide seul de sa validité.
  Valeurs thermiques hors champ ou non valides restent manquantes avec leur
  statut ; elles ne sont pas remplacées par une interpolation implicite.

## API et limites de plateforme

L’API locale transmet configuration, états, tableaux de synthèse et aperçus ;
elle ne transporte pas les séquences brutes complètes. Les interfaces sont
consommées par le GUI et les scripts locaux. Toute modification de contrat doit
être répercutée dans les tests d’intégration et les documents de contrat.

Les outils de construction créent des distributions CPU propres à un système et
une architecture. La construction d’un paquet Windows depuis Linux vérifie
l’archive et ses composants, mais ne valide pas son exécution native. Voir
[PACKAGING.md](PACKAGING.md) pour les commandes et les limites de validation.
