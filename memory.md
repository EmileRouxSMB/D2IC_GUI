# Memory — D2IC_GUI

## Rôle du dossier

Définir puis accueillir l'interface graphique scientifique de DIC 2D, avec deux parcours : DIC seule et DIC + thermique.

## Fichiers importants

- `src/D2IC_GUI/roi.py` : préparation commune du masque photométrique (îlots, binning, érosion), expansion native pour affichage et identité des aperçus maillage ; conserve les opérations D2IC et leurs imports différés.
- `src/D2IC_GUI/results.py` : consultation des magasins DIC actuels ou NPZ historiques, champs, historiques nodaux, coupes matérielles et transport du résidu ; indépendant de FastAPI. `src/D2IC_GUI/server.py` garde les routes, la résolution des runs, les réponses et caches d’affichage.

- `src/D2IC_GUI/build_windows.py` : assemble un ZIP Windows x64 depuis un autre OS avec CPython/wheels Windows, DLL Microsoft CRT, audit statique des binaires PE et vérification scientifique à exécuter sur Windows. Ne déclare jamais une validation Windows lors de l’assemblage croisé.

- `src/D2IC_GUI/build_portable.py` : construit les wheels locaux dans des copies temporaires avec OpenCV headless, assemble CPython 3.12 et les dépendances CPU, nettoie, relocalise, vérifie le worker puis archive sous `dist/`.
- `src/D2IC_GUI/desktop.py` : lanceur CPU local, port libre et navigateur ouvert après réponse HTTP ; ne nécessite pas de navigateur embarqué.
- `pyproject.toml` : paquet GUI et inclusion des actifs statiques pour la distribution.
- `docs/PACKAGING.md` : construction, commandes, contenu et limites de portabilité par OS/libc.

- `README.md` : définition scientifique, parcours, équations, traitement de ROI, exports ParaView et critères de validation.
- `docs/SPEC_TECHNIQUE.md` : choix de la première application web, format `config.toml`, API, calculs et étapes de réalisation.
- `docs/SPEC_ERGONOMIE.md` : interface unique avec navigation gauche à icônes, barre d'étude, zone centrale et panneau droit redimensionnables en direct (70/30 initial), aides `(i)` et critères d'acceptation ergonomique.
- `docs/ROADMAP_DEV.md` : jalons d'implémentation, preuves d'acceptation, risques et routage frugal des agents.
- `memory.md` : repères rapides pour les développements futurs.

## Concepts physiques ou numériques

La DIC suit des points matériels dans la séquence VIS et calcule déplacement et déformation sur un maillage issu du masque final. La dilatation et l'érosion modifient le masque binaire avant maillage. Dans le parcours couplé, la VIS est frontale parallèle à la face étudiée et des points homologues établissent la transformation VIS → TH malgré les résolutions différentes. La face reste suffisamment plane. Les points transportés par la DIC sont projetés en TH ; une image TH coïncidente ou deux images TH successives encadrant chaque temps VIS sont échantillonnées bilinéairement, puis interpolées linéairement dans le temps si nécessaire. La température moyenne par élément est une moyenne surfacique sur l'élément déformé, évaluée par quadrature.

## Conventions

Images `(hauteur, largeur)`, coordonnées `(x, y)` aux centres des pixels, déplacement nodal `(Nn, 2)` en pixels VIS d'origine, déformation `(E11, E22, E12)` sans dimension avec cisaillement tensoriel. `scale.mm_per_pixel` vaut `1` par défaut mais doit être confirmé avant toute sortie en mm ; saisie directe ou segment VIS de longueur connue. Les rayons morphologiques sont en pixels VIS, les temps en secondes ; l'unité thermique doit être déclarée. Une valeur TH hors image est absente (`NaN`) ; une moyenne élémentaire est absente si un point de quadrature est invalide. `ΔT` prend pour référence la température exacte ou interpolée au temps de la première image VIS, au même point matériel ; l’état initial a `u₀ = 0`, `E₀ = 0` et `ΔT₀ = 0` aux nœuds valides. Export d'un VTU par instant et d'un PVD pour la séquence.

## Points d’attention

Le paquet autonome utilise son propre interpréteur, les workers restent lancés par `sys.executable -m D2IC_GUI.worker`. Le lanceur force JAX CPU avant import des moteurs. Le suivi Windows passe par Win32, l’arrêt par `taskkill /T`; POSIX utilise les groupes de processus et récolte les enfants terminés via `waitpid` même sans `/proc`. Les dépendances OpenCV sont remplacées uniquement dans les copies de construction ; aucune réécriture des dépôts scientifiques. Linux embarque les dépendances natives Gmsh hors glibc, ce qui exige de tester la version minimale de Linux ciblée. Les licences et métadonnées sont conservées ; seuls caches, tests et éléments de développement CPython sont retirés.

`dic.roi_erosion_px` est réglable dans ROI / maillage : rayon euclidien en pixels VIS d’origine, même avec binning, défaut `0.0`, exemple `3.0`. L’adaptateur `src/D2IC_GUI/dic_run.py:prepare_run` le transmet au snapshot D2IC. Seules les observations du critère photométrique sont érodées autour des bords et des trous ; le masque final, les nœuds, les éléments et l’aperçu de maillage restent inchangés. Le calque bleu représente les pixels photométriques retenus, le vert la ROI géométrique ; le changement de rayon actualise uniquement le bleu. La route `/api/roi/layer-image?kind=photometric` utilise la morphologie courante, le retrait des îlots, `bin_mask` puis `erode_correlation_roi`, avant répétition des pixels vers la taille VIS (sans interpolation). Ne pas confondre avec l’ancienne morphologie `roi.operation` / `roi.radius_px`, qui modifie la géométrie avant maillage. Le magasin D2IC conserve les deux masques dans `roi.npz`. Voir `docs/ERGONOMIE_REVIEW.md` pour les améliorations proposées à partir de la lecture du GUI.

Le paquet Python est dans `src/D2IC_GUI/` ; les spécifications, contrats et guides sont dans `docs/`, les tests dans `tests/`, et les exemples/configurations dans `examples/`. Les profils de sous-agents sont dans `../.codex/agents/`, le routage par défaut dans `../.codex/config.toml` et le routage haut/bas niveau dans `../.agents/skills/research-task-routing/SKILL.md`. `config.toml` est prévu comme source de vérité par projet, avec snapshot résolu à chaque calcul. Les images ne sont pas copiées ; leurs chemins absolus et métadonnées sont tracés dans le manifeste du run. Réutiliser `D2IC` pour les calculs JAX et l'export DIC VTU/PVD, `DICTHFusion` pour la correspondance spatiale VIS → TH. Régénérer le maillage après modification de ROI. Vérifier les effets du binning et du recadrage sur `H`, la stabilité des caméras et la continuité des numéros TH. La cadence TH usuelle est 50 Hz et reste configurable. Numéros ou temps sont lus depuis les noms de fichiers ou les métadonnées, selon une source choisie par caméra. La transformation VIS → TH exige une validation manuelle après inspection des résidus ; aucun seuil RMS universel n'est imposé. Les TIFF sont déjà des températures ; les corrections radiométriques sont faites en amont. L'export VTU/PVD couplé possède `PointData` thermique, `CellData` des moyennes élémentaires et une échelle physique cohérente.

## Résultats persistés et reprise

La fusion TH du worker utilise désormais l’itérateur de `src/D2IC_GUI/thermal.py`, une frame mécanique en cache et des tableaux temporaires mappés sur disque. Le format final `thermal_fields.npz` reste identique ; prévoir de l’espace disque temporaire pour les six tableaux non compressés. Voir `docs/RESULT_MODEL.md` pour la publication et le nettoyage après erreur.

Les nouveaux runs GUI écrivent `results/dic_store/` : `metadata.json` (schéma versionné, conventions, temps VIS), `mesh.npz`, `roi.npz`, une archive par image déformée dans `frames/`, `checkpoint.npz` et `progress.json`. Le déplacement et la déformation de référence sont implicites et n'occupent pas de frame. Le GUI lit ce magasin via `d2ic.io.result_store.open_result_store`; les anciens runs `dic_results.npz` restent lisibles. L'archive globale est exportée seulement à la demande pour les consommateurs scientifiques existants ; le worker GUI lit directement le magasin versionné.

Un run interrompu peut être relancé depuis son dossier figé. D2IC compare l'empreinte des entrées et les paramètres avant de réutiliser les champs déjà validés. Les vues de champs utilisent un cache PNG local pour chaque frame validée, même pendant le calcul. Les VTU en pixels sont gardés comme données sources ; les éventuels VTU en mm sont des sorties distinctes afin que leur régénération soit idempotente.

La commande « Relocaliser » vérifie les noms, tailles et dimensions des images référencées par le dernier run avant de changer les chemins VIS/TH de l'étude. Les manifestes des anciens runs conservent leurs chemins historiques ; la reprise d'un run déplacé reste soumise à l'empreinte de ses sources et peut donc être refusée. Les nouveaux calculs utilisent les nouveaux dossiers.

L’explorateur local lit les chemins absolus par GET /api/filesystem, filtre les fichiers par usage et pagine les grands dossiers. Le choix de la référence VIS renseigne aussi le dossier des sources ; les images ne sont jamais importées dans le projet par cette action.

La vue VIS est limitée au dossier, au motif de série et à la référence. Le détecteur de séries lit seulement les noms et vérifie que chaque motif proposé retrouve exactement ses fichiers ; la validation des pixels et des temps reste dans l’inventaire scientifique.

Les VIS TIFF/BMP/PNG/JPEG passent par le lecteur D2IC, qui produit le même niveau de gris pour aperçu, inventaire et solveur. Les masques et TIFF thermiques restent des tableaux scalaires 2D ; aucune conversion couleur ne modifie les températures.

L’aperçu VIS utilise `GET /api/visible/inspect` sur les valeurs courantes du formulaire, sans modifier `config.toml`. Les images sont servies par `GET /api/image` avec `visible_dir`, limité au dossier VIS sélectionné ; les temps invalides affichent un avertissement mais ne bloquent pas la lecture des images. Le calcul conserve la validation stricte de l’inventaire.

La vue ROI expose un fichier de masque TIFF/PNG et une taille de maille. `GET /api/roi/overlay-image` compose le masque choisi avec la VIS avant sauvegarde ; Mailler sauvegarde une copie interne puis appelle `/api/mesh/preview` et affiche son image composée. Les outils Rectangle/Ellipse créent un nouveau masque TIFF avant de reprendre ce même workflow ; les anciennes clés de morphologie TOML restent lisibles.

Les masques ROI sont décodés par `imaging.read_mask`, qui réutilise `d2ic.io.app_utils.read_roi_mask`. Le TIFF DP600L2 `roi.tif` est gris + alpha `(1200,1920,2)` ; le canal gris est retenu, ce qui garde l’aperçu, la copie interne, le maillage et le run cohérents. Les TIFF TH restent lus comme données scalaires brutes.

L’ouverture d’une étude accepte le dossier et son `config.toml`. L’explorateur marque ce fichier comme configuration d’étude ; la vue Ouvrir démarre dans le dossier parent et actualise immédiatement le projet chargé. Le bouton Ouvrir reste visible sur écran étroit.

L’interface garde la navigation gauche repliée par défaut (icônes seules) et supprime l’en-tête redondant au-dessus de la zone image. Le bouton en haut du volet ouvre les libellés, avec préférence locale ; le panneau des paramètres reste redimensionnable.

`copy_project(..., settings=...)` accepte un état de formulaire validé pour Enregistrer sous/Dupliquer. La source reste inchangée ; les petits actifs sont copiés et les images restent externes. Le bandeau compact place les opérations dans Fichier.

La table VIS conserve les exclusions par noms dans `paths.excluded_images` ; le chemin absolu de chaque image retenue est figé dans `dic_config.toml` (`paths.image_paths`) et `manifest.json`. La référence reste active ; une sélection VIS remet `dic.image_stride` à 1. La vue Synchro et les exports utilisent la liste filtrée. Les images exclues sont éliminées avant le décodage et la validation des temps du run.

La table TH reprend la détection de séries et les commandes de sélection VIS. `thermal.excluded_images` conserve les noms des TIFF désactivés ; l’aperçu du formulaire fonctionne avant sauvegarde, même si les temps restent à corriger. L’inventaire scientifique accepte seulement les TIFF scalaires actifs, refuse une exclusion absente ou une séquence vide, et fige les chemins absolus retenus dans le manifeste du run. Une trame désactivée rompt l’adjacence temporelle : l’interpolation ne traverse pas ce trou. La référence thermique reste définie au premier instant VIS, sous réserve de disponibilité des trames TH actives.

La vue Résultats affiche une ligne par run avec Stop, Redémarrer et Supprimer ; le résumé du run sélectionné reste au-dessus de la liste. `DELETE /api/runs/{id}` refuse un run actif et un lien hors du dossier de runs. La liste légère lit état et progression sans ouvrir les manifestes de chaque run ; les détails du seul run sélectionné restent disponibles par `GET /api/runs/{id}`.

Les nouveaux runs utilisent un identifiant/dossier `YY-MM-DD-Id` daté en UTC (`001`, `002`, etc. chaque jour). `_allocate_run_dir` choisit le plus grand index existant puis crée le dossier avec `exist_ok=False`, en réessayant après collision. Les anciens noms ne sont pas migrés.

Le worker ajoute le projet local `../im_jax` au chemin Python avant d’importer `.dic_run` et D2IC. Sans cela, `import im_jax` peut résoudre le dossier externe comme un espace de noms vide et rendre l’interpolation cubique indisponible lors du JIT. Le test `test_cubic_worker_subprocess_imports_local_im_jax` exécute le vrai worker dans un processus séparé.


Les inventaires des vues VIS/TH lisent seulement les dimensions dans les en-têtes (`inspect_pixels=False`) pour éviter le décodage de toute la séquence à chaque navigation. L’inventaire du run conserve par défaut la lecture complète et la validation des pixels. L’aperçu PNG est conservé dans un cache mémoire borné, identifié par chemin, taille et date de modification ; les images sources ne sont pas copiées. La vue ROI demande directement l’aperçu de maillage enregistré et revient à la composition ROI si cet aperçu est absent ou périmé. Vérifier l’image source lors du lancement du calcul : l’inventaire rapide ne garantit pas que tous les pixels soient décodables.


Dans la vue ROI/maillage, `GET /api/roi/layer-image` fournit un PNG RGBA translucide du masque choisi, aligné avec l’image VIS complète ; `POST /api/mesh/preview` enregistre aussi `roi/mesh_layer.png`, validé par `GET /api/mesh/layer-image` avec les mêmes empreintes que l’aperçu composé historique. La VIS, le masque et le maillage sont trois calques indépendants ; les cases à cocher n’affectent ni le masque scientifique ni le maillage du run. Un ancien aperçu sans calque exige de cliquer à nouveau sur Mailler.

## Exploration des runs

Job Manager suit les runs et présente un résumé par sélection. Résultats charge seulement les runs terminés et les champs à leurs instants VIS. `/api/runs/{id}/mesh` retourne les coordonnées VIS natives et l’étendue de la carte ; `/field-image` crée un PNG sans axes ni barre de couleur, éventuellement avec `vmin/vmax` cinématiques. `/field-range` calcule les extrema finis d’une image ou de la séquence dans les unités affichées. Les courbes de plusieurs nœuds utilisent les temps VIS, chargent les frames et l’archive thermique une seule fois par requête `/histories`, et ne relient pas les données absentes. La température moyenne par élément reste un champ de cellules constant par élément ; les cellules invalides sont masquées. Seuls les PNG automatiques sont mis en cache ; les cartes à bornes manuelles sont renvoyées en mémoire pour éviter l’accumulation de variantes.

La vue Synchro affiche les cadences VIS/TH, les numéros d’acquisition conservés avec chaque correspondance, et les images sources VIS et TH de la ligne choisie. Les images sont lues à leur chemin absolu sans duplication.


## Zoom des images

`static/image_zoom.js` fournit le zoom par clic ou fenêtre rectangulaire, Ctrl/Cmd + clic pour dézoomer et Réinitialiser la vue. Les calques ROI sont transformés ensemble ; les coordonnées natives des mesures, des points homologues et des nœuds sont obtenues avec la géométrie de l’image transformée. Le mode Zoom est désactivé initialement dans les vues interactives afin de conserver le placement des points ; il est activable dans leur barre d’image. Les préférences de zoom sont visuelles et ne modifient ni TOML ni résultats. Le retrait d’un nœud dans Résultats utilise maintenant Maj + clic.


## Préparation avant lancement

`readiness.py` évalue en lecture seule les prérequis du formulaire et renvoie les états par volet, les obligations et les compléments facultatifs. `POST /api/readiness` alimente les icônes et la fenêtre de guidage ; `POST /api/runs` répète les contrôles sur la configuration enregistrée avant de créer un run. Un maillage prévisualisé doit correspondre aux empreintes des masques et aux paramètres courants ; l’échelle est facultative en pixels, obligatoire en mm. Les températures sans encadrement restent absentes et constituent un avertissement. La lecture complète des sources au lancement reste assurée par `prepare_run` ; le suivi ne crée aucun dossier de run. La recherche de paramètres est supprimée des volets.

Le contrôle vérifie aussi que la morphologie courante reproduit le masque final et que l’érosion photométrique conserve des pixels après binning et retrait des îlots. Les événements temporels sont contrôlés sur les acquisitions réellement retenues après stride, avec les mêmes numéros que le manifeste consommé par le worker. Un run actif bloque un nouveau lancement ; les vues Résultats/Export restent grises avant tout résultat terminé.


## Superposition des résultats en configuration déformée

Les routes de résultats acceptent `overlay=current` pour un PNG RGBA et un maillage d’affichage en coordonnées VIS natives sur tout le domaine image. La géométrie est `X + u_k` (déplacement brut en pixels) ; les valeurs colorées gardent les unités du run. `/api/runs/{id}/visible-image?frame=k` sert uniquement la source VIS enregistrée pour cet instant, avec vérification taille/date/dimensions. `/fields` expose `source_shape_hw` et `residual_frames` (clés NPZ consultées sans décompression des champs).

`_transport_reference_raster` sert uniquement à visualiser les résidus sur la configuration déformée : inversion de la transformation affine sur les triangles du maillage déplacé, puis lecture au plus proche voisin de la carte de référence binnée. Le traitement se fait par blocs de lignes pour borner la mémoire. Les trous NaN et le domaine extérieur restent transparents ; le binning utilise les centres des blocs complets. La carte stockée n’est jamais réécrite. Les aperçus de superposition utilisent un cache `v5` distinct de l’ancien cadrage `v3`.


## Catalogue des paramètres

`src/D2IC_GUI/parameters.toml` est la source des définitions des champs (clé, libellé, type explicite, défaut, choix, aide, onglet, navigateur, visibilité). `schema.load_catalog` le lit au démarrage ; `defaults`, `validate` et `/api/schema` réutilisent ces définitions. `config.toml` garde les valeurs par étude. Les règles scientifiques entre champs restent dans `validate`. Ajouter un contrôle standard demande seulement une entrée TOML ; un nouveau comportement de calcul demande son raccordement au moteur. Voir `docs/CONFIG_SCHEMA.md`. Le catalogue est inclus dans les wheels et les copies de construction portables.


## Consultation pendant le calcul

Les routes de champs, maillage, bornes, image VIS et historiques acceptent les runs actifs, arrêtés ou échoués. La borne temporelle est `store.frame_count` (fichiers contigus, progression et checkpoint), jamais le nombre total prévu au manifeste. `/fields` retourne état, nombres validé/total et temps disponibles ; les historiques sont tronqués à ces mêmes temps. Les exports finaux restent réservés aux runs terminés. `inspect_run` fournit le manifeste figé dans tous les états. Le worker publie par remplacement atomique le manifeste final et `thermal_fields.npz`, consultés en parallèle ; les champs thermiques apparaissent après fusion complète.


Le panneau Résultats regroupe Suivi de points / Coupe dans des sous-onglets. `/api/runs/{id}/section` échantillonne un segment matériel en pixels référence, par interpolation linéaire des triangles de visualisation (quadrilatères divisés 012/023), avec distance en unité du run et lacunes nulles. Les routes `section.csv` et `histories.csv` exportent la grandeur sélectionnée, les temps VIS et les unités ; la coupe accepte image/séquence, les points couvrent tous les instants validés. Le slider remplace le choix de frame ; `field-image?center_zero=true` impose des bornes symétriques sans toucher aux données persistées.


Le blocage de lancement après changement de binning indique les anciennes/nouvelles valeurs et demande de cliquer sur Mailler. Job Manager affiche directement les obligations dans son résumé, près du bouton désactivé ; le contrôle de péremption reste strict.


## Jobs préparés

`dic_run.prepare_job` alloue la ligne avant les contrôles. Un rapport `preparation.json` publié atomiquement conserve les erreurs et avertissements. Les états `preparing`, `blocked`, `pending` précèdent le worker. `POST /api/runs/prepare` ne lance aucun calcul ; `POST /api/runs/{id}/start` vérifie les sources externes et les actifs figés avant lancement. Les mêmes paramètres sont utilisés pour readiness et snapshot ; le masque copié doit correspondre à l’aperçu contrôlé. La liste expose `preparation` et `can_start`. Corriger l’étude puis préparer un nouveau job pour remplacer une préparation bloquée. Les jobs préparés restent indépendants des modifications ultérieures de l’étude. Le verrou de démarrage est partagé par lancement, reprise et suppression ; un seul worker actif par étude. La route historique `POST /api/runs` reste disponible pour compatibilité.
