# D2IC_GUI — spécification technique de la première application web

**Statut :** proposition d'implémentation. **Référence scientifique :** [README.md](README.md). Cette spécification décrit le comportement attendu ; elle ne présente pas les fonctions à développer comme déjà disponibles.

## 1. Périmètre et architecture

La première version est une **application web locale** : un serveur Python écoute sur `127.0.0.1`, ouvre une page dans le navigateur et accède aux fichiers de l'expérience sur la machine où il tourne. Le calcul reste local, sur CPU ou GPU selon JAX. Python 3.11 ou plus récent est requis pour `tomllib`. Un déploiement réseau ou multiutilisateur nécessitera un modèle d'accès aux fichiers et d'authentification distinct.

| Élément | Choix technique | Rôle |
| --- | --- | --- |
| Serveur HTTP | FastAPI + Uvicorn, un processus web | API, pages et fichiers de prévisualisation |
| Interface | HTML/Jinja2, CSS, JavaScript natif et Canvas 2D | Barre de navigation gauche, panneaux redimensionnables, formulaires, ROI, points, superpositions et historiques ; pas de chaîne de compilation front-end |
| Configuration | `config.toml` par projet, lu avec `tomllib` ; écriture avec `tomli-w` | Source de vérité des paramètres reproductibles |
| Calcul DIC | `run_sequence_from_config` de `D2IC`, dans un processus de travail séparé | Réutiliser le pipeline séquentiel et son export DIC |
| Correspondance VIS–TH | Fonctions numériques de `DICTHFusion` | Ajustement de `H` par points homologues et échantillonnage spatial bilinéaire |
| Aperçu ROI | OpenCV, masque binaire sur CPU | Composition VIS + ROI sans modifier les fichiers sources |
| Export | `d2ic.io.paraview` et `meshio` | VTU par instant, PVD ordonné par temps ; ajout des champs thermiques |

La chaîne VIS accepte TIFF (.tif/.tiff), BMP, PNG et JPEG (.jpg/.jpeg), en niveaux de gris ou en couleur. L’inventaire, les aperçus, la ROI, la calibration et le solveur utilisent le même décodeur D2IC ; les images couleur sont ramenées en niveaux de gris par moyenne des canaux RGB, sans canal alpha. Les TIFF TH doivent rester des images 2D de température et ne subissent aucune conversion couleur. Les horodatages intégrés sont lus actuellement dans les TIFF ; pour BMP, PNG et JPEG, le temps VIS vient des numéros des noms de fichiers.

Le navigateur ne reçoit que des images réduites, tuiles, contours et tableaux destinés à l'affichage. Les TIFF de température et les tableaux JAX restent côté serveur. Les requêtes de prévisualisation et de modification de configuration sont courtes ; une résolution DIC est lancée dans un **processus de travail** pour ne pas bloquer l'interface. Un seul calcul GPU actif est autorisé dans la première version. Le serveur suit l'état du travail par un fichier d'état et des journaux dans le dossier du projet ; le navigateur interroge périodiquement cet état. Un redémarrage du serveur peut ainsi retrouver les résultats terminés et marquer un travail interrompu.

FastAPI sait servir des templates et des fichiers statiques. Sa documentation réserve les tâches d'arrière-plan intégrées aux travaux légers et recommande un autre mécanisme pour les calculs lourds : le processus de travail est donc un **choix d'architecture proposé** pour ce calcul JAX, sans imposer Redis ni base de données au premier lot.

## 2. Projet et fichiers `config.toml`

Chaque projet possède un dossier indépendant :

```text
mon_essai/
├── config.toml              # paramètres éditables du projet
├── roi/
│   ├── mask_initial.tif     # copie du masque chargé depuis un fichier
│   └── mask_final.tif       # masque effectivement maillé
├── calibration/
│   └── visible_thermal.json # format DICTHFusion existant, si parcours couplé
└── runs/
    └── <identifiant>/
        ├── config.toml      # paramètres du projet résolus pour ce calcul
        ├── dic_config.toml  # configuration compatible avec D2IC
        ├── mask_final.tif   # copie du masque utilisé
        ├── status.json      # état, avancement, erreur éventuelle
        ├── results/         # NPZ, VTU, PVD et figures
        └── manifest.json    # chemins absolus des images, temps, unités, versions
```

`config.toml` est la **source de vérité**. L'interface charge ce fichier, valide ses champs, affiche les valeurs puis écrit les changements de manière atomique (fichier temporaire suivi d'un remplacement). `tomllib` ne sait que lire : `tomli-w` sert à écrire une représentation TOML normalisée. La sauvegarde peut reformater le fichier ; les commentaires libres ne sont pas garantis. Les chemins relatifs sont résolus depuis le dossier contenant `config.toml`. Les images sources ne sont **ni copiées ni déplacées** dans le projet ou les runs. Chaque lancement enregistre un `config.toml` résolu et une copie du petit masque final. Les nouveaux dossiers de run sont nommés `YY-MM-DD-Id` en date UTC, par exemple `26-10-17-001` puis `26-10-17-002` ; l’identifiant numérique, sur trois chiffres au minimum, s’incrémente par jour dans l’étude. L’allocation crée le dossier de façon exclusive pour éviter une collision entre lancements. Les anciens dossiers gardent leur nom et restent lisibles. Après le calcul, `manifest.json` recense les images VIS réellement utilisées par D2IC et les images TH réellement utilisées par la fusion. Pour chaque image, le manifeste conserve son chemin absolu, son temps, la source de ce temps (nom de fichier ou métadonnée), sa taille et sa date de modification ; un hachage SHA-256 peut être demandé pour une vérification forte sans duplication. Si un fichier source disparaît ou change, la réouverture du run le signale. Un chemin absolu seul assure la traçabilité de l'emplacement, pas l'immuabilité du contenu.

### Schéma initial

```toml
[project]
version = 1
mode = "dic_thermal" # "dic" ou "dic_thermal"
name = "essai_traction"

[paths]
visible_dir = "../images/VIS"
reference_image = "VIS_000.bmp"
visible_pattern = "VIS_*.bmp"
excluded_images = []
output_dir = "runs"

[roi]
initial_mask = "roi/mask_initial.tif"
final_mask = "roi/mask_final.tif"
operation = "erosion" # "none", "dilation" ou "erosion"
radius_px = 2
kernel = "disk"

[mesh]
element_size_px = 15.0
remove_islands = true
min_island_area_px = 64

[dic]
image_stride = 1
image_binning = 1
max_iters = 400
tol = 0.01
reg_strength = 0.01
regularization = "elastic"
strain_gauge_length = 80.0
interpolation = "cubic"

[scale]
mm_per_pixel = 1.0 # pixels de l’image VIS d’origine
method = "manual" # "manual" ou "segment"
confirmed = false  # passe à true après étalonnage validé
# Méthode segment : segment_xy_px = [[x1, y1], [x2, y2]] ; segment_length_mm = ...

[time]
visible_source = "filename" # "filename" ou "metadata"
visible_frame_regex = 'VIS_(\d+)' # utilisé si visible_source = "filename"
visible_fps = 10.0 # utilisé si visible_source = "filename"
# En mode "metadata", lire un horodatage exploitable dans chaque image VIS.

[output]
export_vtu = true
export_pvd = true
save_npz = true
export_png = false # activable, car les figures par image augmentent le volume
paraview_length_unit = "px" # "px" ou "mm" si scale.confirmed = true

[runtime]
jax_preferred = "gpu"
jax_fallback = "cpu"
jax_enable_x64 = false

# Les tables ci-dessous sont absentes en mode "dic".
[thermal]
image_dir = "../images/TH"
image_pattern = "TH_*.tif"
excluded_images = []
unit = "degC"
time_source = "filename" # "filename" ou "metadata"
frame_regex = 'TH_(\d+)' # utilisé si time_source = "filename"
thermal_fps = 50.0 # utilisé si time_source = "filename"

[registration]
file = "calibration/visible_thermal.json"
approved = false # validation manuelle après inspection des résidus

[synchronization]
method = "event_frames" # ou "timestamps"
visible_event_frame = 10
thermal_event_frame = 50 # même événement, cadences VIS/TH différentes
thermal_interpolation = "linear"
```

Le mode `dic` ignore et n'exige aucune table thermique. Le mode `dic_thermal` exige `[thermal]`, `[registration]` et `[synchronization]` ; le traitement radiométrique est déjà réalisé avant l'import des TIFF. La cadence TH est fixe, généralement 50 Hz, mais configurable. La source temporelle est choisie séparément pour VIS et TH : numéro extrait du nom de fichier par une expression régulière puis converti avec la cadence, ou horodatage lu dans les métadonnées de l'image. La GUI montre un aperçu des valeurs extraites, leur origine, les doublons, les manques et la monotonie avant calcul. Si la source choisie ne fournit pas de temps exploitable, le projet est refusé et l'utilisateur sélectionne l'autre source ou corrige les fichiers. Les deux séries sont ramenées au même axe temporel au moyen d'un événement commun ou d'horloges déjà synchronisées ; le mode `event_frames` de l'exemple exige des numéros de trame pour les deux caméras. Si les métadonnées sont choisies pour l'une des séries, la synchronisation s'appuie sur les horodatages et un éventuel décalage issu d'un événement commun. Les numéros TH manquants sont signalés même si les temps restent monotones. La configuration doit être refusée si la référence VIS, le masque final, les cadences lorsqu'elles servent à reconstruire le temps, les horodatages, les chemins ou les unités nécessaires sont invalides. `scale.mm_per_pixel` doit être positif et fini ; sa valeur initiale `1` reste marquée non étalonnée tant que `scale.confirmed` est faux. Une sortie `paraview_length_unit = "mm"` exige `scale.confirmed = true`. `output.export_pvd = true` exige `output.export_vtu = true`. `paths.excluded_images` contient les noms des fichiers VIS désactivés pour le calcul ; la valeur par défaut est `[]`. La référence est obligatoirement active. La sélection « 1 image sur N » conserve les indices 1, 1+N, etc., dans l’ordre temporel affiché. Le pas DIC historique est remis à 1 quand la sélection VIS est modifiée. Le lancement refuse une exclusion absente de la série ou une séquence sans image déformée active. `thermal.excluded_images` contient les noms des acquisitions TH désactivées pour la fusion ; la valeur par défaut est `[]`. Le serveur refuse une exclusion absente de la série et une séquence sans TH active. La vue TH inspecte le formulaire courant sans écrire le TOML ; la synchronisation et les nouveaux runs utilisent seulement les TH actives. Les temps, numéros et chemins absolus des TH retenues sont figés dans `manifest.thermal_images`. Une exclusion crée un intervalle sans température si elle interrompt deux acquisitions successives ; la référence thermique reste évaluée au temps de la première VIS, sans référence TH indépendante. Le fichier `dic_config.toml` du run transmet à D2IC `paths.image_paths`, liste ordonnée de chemins absolus, qui prime sur le motif et le pas ; le moteur n’explore alors pas les autres images. La liste ordonnée des chemins absolus effectivement utilisés est conservée dans le manifeste du calcul. Lors d'une réouverture, une modification du dossier source ne modifie pas les résultats figés ; un nouveau calcul résout à nouveau le motif de fichiers et affiche la nouvelle liste avant son lancement.

Ce schéma est celui de **D2IC_GUI**. Un adaptateur produit `runs/<id>/dic_config.toml` au format attendu par `D2IC`, avec les chemins absolus du dossier VIS et du masque figé dans le run. Le nouveau champ D2IC `paths.mask_path` accepte ce masque hors du dossier des images et reste compatible avec l'ancien `paths.mask_filename`. L'adaptateur appelle ensuite `run_sequence_from_config` ; il ne recopie pas l'orchestration scientifique de D2IC. La correspondance entre les champs du projet et ceux du TOML D2IC doit être documentée et testée.

## 3. Vues et fonctions

La barre supérieure compacte contient le menu **Fichier** : Nouvelle étude, Ouvrir, Enregistrer, Enregistrer sous, Dupliquer et Relocaliser. Enregistrer sous et Dupliquer transmettent une copie validée des réglages courants à `POST /api/project/copy` ; la source n’est pas réécrite. La copie contient configuration, masque et calibration, sans images sources ni runs. Les fonctions scientifiques sont disponibles par une navigation verticale à gauche, avec icône et libellé pour chaque vue ; une entrée manquante bloque le lancement concerné, pas la navigation.

| Vue de la navigation gauche | Zone centrale et paramètres associés |
| --- | --- |
| VIS | Image de référence et liste des images retenues ; chemins, motif, temps VIS et configuration du projet dans le panneau droit. |
| ROI / maillage | Image VIS avec ROI fichier puis maillage en surimpression ; fichier ROI et taille des éléments. |
| DIC / échelle | Image et maillage ; toutes les options DIC, étalonnage et exécution. |
| Thermique / correspondance | Deux images VIS et TH, superposition, résidus ; import TH, points homologues, modèle affine/projectif et approbation manuelle. Onglet absent en DIC seule. |
| Synchro | Cadences VIS et TH, table des instants avec numéros de trame et images VIS/TH de la ligne choisie ; paramètres de synchronisation. Onglet absent en DIC seule. |
| Résultats | Cartes et historiques ; lancement, progression, journaux, choix du champ et du run. |
| Export | Aperçu des champs et instants ; VTU/PVD, unités, destination et manifeste. |

Le changement de ROI invalide le maillage, les résultats DIC et la fusion de la version de projet en cours. Le changement de points homologues, de modèle, de dimensions d'image ou de transformation VIS–TH annule la validation manuelle de la correspondance. Le changement de transformation VIS–TH ou de synchronisation temporelle invalide seulement la fusion ; un calcul DIC déjà figé peut être réutilisé si ses images et son masque n'ont pas changé. Ces dépendances sont matérialisées par l'état des étapes dans l'interface.

## 4. Ergonomie de l'interface

La [spécification ergonomique](SPEC_ERGONOMIE.md) définit la barre supérieure, la navigation verticale gauche à icônes, la disposition responsive et les contrôles de chaque vue. Sur écran large, la zone centrale réservée aux images, cartes ou tableaux occupe initialement 70 % de l'espace restant après la navigation gauche ; le panneau droit de paramètres occupe 30 %. Une poignée entre ces deux zones permet leur redimensionnement en direct, avec minima de largeur, conservation du zoom et de la sélection, contrôle au clavier et retour au 70/30. Sur écran étroit, navigation et paramètres deviennent accessibles en tiroirs sans cacher de réglage. Une seule présentation donne accès à **tous les paramètres** de la vue dans ce panneau. Chaque contrôle affiche sa valeur courante, sa valeur par défaut et une aide `(i)` avec description et valeur typique si elle existe. La disposition utilise deux colonnes CSS Grid pour l'espace de travail, pilotées par une variable de largeur mise à jour pendant le glissement de la poignée. Un `ResizeObserver` adapte les Canvas sans recréer leur état scientifique ; le facteur de zoom, le centre observé et les coordonnées des points restent inchangés. La séparation accepte souris, toucher et clavier, expose son état aux technologies d'assistance et respecte des minima initiaux de 480 px pour la zone image et 320 px pour le panneau. Lorsque l'espace disponible après la navigation gauche est inférieur à ces minima, l'interface bascule en disposition étroite. La proportion est conservée localement dans le navigateur ; aucune requête de calcul n'est déclenchée par un redimensionnement. L'étalonnage montre `1 mm/pixel` comme valeur initiale **non confirmée**. L'utilisateur peut saisir le facteur directement ou zoomer sur la VIS de référence, cliquer deux points, renseigner leur distance en mm et prévisualiser le facteur calculé avant validation.

La vue ROI compose côté serveur le masque choisi sur la VIS de référence, puis le maillage sur cette même image après un clic sur Mailler. Un changement de fichier ou de taille de maille invalide l’aperçu précédent. La vue VIS–TH permet de zoomer séparément sur les deux résolutions, de corriger numériquement une paire de points et de voir immédiatement le résidu par point, le RMS en pixels TH et la superposition. L'utilisateur confirme la correspondance après inspection ; aucun seuil RMS universel ne décide automatiquement de sa validité. Les couleurs affichées n'altèrent pas les valeurs TH.

Un curseur de temps parcourt uniquement les **images VIS réellement acquises**. Pour chacune, l'écran indique l'image TH exacte ou les deux TH utilisées, leurs temps et le poids d'interpolation. Le premier instant VIS et sa valeur `T_ref` sont visibles. Dans les résultats, un clic sur un nœud ou un élément conserve la sélection matérielle en changeant de temps ou de champ ; l'interface distingue température nodale et moyenne élémentaire. Les valeurs invalides apparaissent comme absentes, avec leur cause explicite.

Avant chaque calcul, un résumé présente la ROI finale, le nombre d'images VIS/TH, leurs cadences, la transformation VIS–TH, les sorties demandées et une estimation du volume exporté. Un changement de paramètre n'efface pas un run terminé : il crée une nouvelle version de calcul.

## 5. Contrats de calcul et données

### ROI

Le fichier ROI TIFF ou PNG est décodé avec les conventions D2IC : un TIFF gris + alpha utilise son canal gris, puis le seuil D2IC produit un masque booléen `(H_VIS, W_VIS)`, non vide et de mêmes dimensions que la VIS de référence. `GET /api/roi/overlay-image` affiche ce masque sur la VIS avec les valeurs courantes du formulaire, sans sauvegarde. Mailler valide la configuration, copie le masque dans `roi/mask_initial.tif` et `roi/mask_final.tif`, puis construit le maillage depuis le masque final. Le masque source et les images VIS restent inchangés. La taille de maille est exprimée en pixels VIS ; Gmsh est appelé sans gestionnaire de signaux pour fonctionner dans le thread HTTP. Les anciens champs morphologiques du TOML restent lisibles mais ne sont pas présentés dans le GUI.

### DIC

Le processus de travail lit `dic_config.toml` et lance le pipeline séquentiel de `D2IC` sur les images VIS originales. Les nouveaux résultats sont lus dans le magasin versionné `results/dic_store/`, décrit dans [RESULT_MODEL.md](RESULT_MODEL.md) ; le NPZ global de compatibilité est produit seulement à la demande. Après le calcul, il vérifie `ref_path` et `def_paths` dans les métadonnées du magasin DIC contre le manifeste figé des images réellement traitées. Les données numériques échangées avec le solveur sont des tableaux de forme `(H, W)` pour les images, `(Nn, 2)` pour les déplacements nodaux et `(Nn, 3)` pour `(E11, E22, E12)`. Le lancement JAX, ses options de précision et le choix CPU/GPU sont fixés avant l'initialisation du processus de travail. `save_npz` reste activé pour le magasin par image, ses champs et les chemins sources ; `export_vtk_images` reste désactivé par défaut pour éviter de recopier les images dans des fichiers VTI. Après le calcul, l'adaptateur reconstruit le PVD des VTU avec les temps VIS réels du manifeste : le pipeline D2IC actuel emploie sinon des indices d'images. L'interface n'effectue pas de calcul scientifique dans le navigateur.

### Échelle physique

`scale.mm_per_pixel` désigne le nombre de millimètres par pixel de l'image VIS **d'origine**. En mode `manual`, il est saisi directement. En mode `segment`, `mm_per_pixel = segment_length_mm / ||p₂ − p₁||_px` ; les deux coordonnées VIS et la longueur connue sont enregistrées dans le TOML. Un segment nul ou une longueur non positive est refusé. D2IC résout et exporte initialement le maillage et le déplacement dans ce repère pixel, y compris lorsque l'image de calcul est binnée. La conversion s'applique uniquement aux coordonnées et déplacements : `X_mm = s_vis X_px` et `u_mm = s_vis u_px` ; les déformations de Green–Lagrange restent sans dimension. En cas de recadrage, l'origine VIS complète est restaurée avant la projection par `H` et avant l'export physique. Les historiques et le manifeste conservent le facteur et le statut `confirmed`. Tant que l'étalonnage n'est pas confirmé, l'interface et ParaView restent en pixels ; la valeur initiale `1` ne certifie aucune longueur physique.

### Fusion

L'axe temporel de sortie est celui des images VIS réelles. Pour chaque temps `tₖ`, on recherche une image TH à `τⱼ = tₖ` ou deux images TH successives telles que `τⱼ < tₖ < τⱼ₊₁`. Dans le second cas, `α = (tₖ − τⱼ)/(τⱼ₊₁ − τⱼ)` et, à une même coordonnée thermique `qₖ`, `T(qₖ,tₖ) = (1−α)Tⱼ(qₖ) + α Tⱼ₊₁(qₖ)`. Chaque lecture spatiale utilise l'interpolation bilinéaire ; les deux échantillons doivent être valides. Aucune image VIS ni aucun déplacement DIC n'est interpolé. Hors de la plage TH ou si les deux images TH encadrantes ne correspondent pas à deux numéros d'acquisition successifs, la température est indisponible ; aucune extrapolation n'est produite. La période nominale est `1/thermal_fps`, soit `0,02 s` à 50 Hz.

La première image VIS définit `t₀` et la référence de `ΔT`. `T_ref` est la valeur TH coïncidente à `t₀`, ou la valeur obtenue par interpolation des deux TH qui encadrent `t₀`. Si aucune température valide n'existe à `t₀`, l'interface signale l'absence de référence et ne calcule pas `ΔT`. Le pipeline D2IC courant exporte les images déformées ; la GUI crée donc explicitement l'état de référence `t₀` avec `u₀ = 0`, `E₀ = 0`, `T_ref` et `ΔT₀ = 0` aux nœuds thermiquement valides, sans relancer le solveur.

La transformation JSON conserve `H` dans le sens VIS → TH et les résidus en pixels TH. Le statut d'approbation manuelle et l'empreinte du fichier de calibration sont enregistrés dans le run ; une modification de la calibration impose une nouvelle approbation. Une géométrie de points dégénérée empêche l'ajustement, indépendamment de cette approbation. La face étudiée reste suffisamment plane pendant l'essai et la caméra VIS lui est frontale parallèle ; la TH peut avoir une résolution et une orientation différentes. Les nœuds matériels de référence `X` sont transportés à `X + uₖ(X)` au temps VIS `tₖ`, puis projetés par `H` vers `qₖ`. Si la DIC est effectuée sur des images binnées ou recadrées, les coordonnées sont d’abord reconverties dans le repère VIS utilisé pour estimer `H`. Le TIFF TH coïncident, ou les deux TIFF TH encadrants, sont échantillonnés à cette même coordonnée `qₖ` avant interpolation temporelle. Un échantillon hors champ ou non fini est enregistré `NaN` avec un masque de validité. `ΔT` est calculé au **même point matériel** à partir de `T_ref` à `t₀` ; si la référence est invalide à un nœud, `ΔT` reste invalide pour ce nœud. La superposition colorée n'intervient pas dans le calcul des températures.

### Température moyenne par élément

Pour chaque élément du maillage de référence, la GUI reconstruit sa forme déformée au temps VIS, évalue la température aux points de quadrature et calcule une moyenne surfacique pondérée par le jacobien de la géométrie **courante**. La première version utilise une règle 2×2 pour les quadrilatères Q4 et une règle à trois points pour les triangles T3 si présents. La même interpolation spatiale VIS → TH et la même interpolation temporelle TH que pour les nœuds sont appliquées à chaque point de quadrature.

`T_mean_element` a la forme `(Ne,)`. `Delta_T_mean_element` est la différence entre les moyennes de l'élément au temps VIS courant et au premier temps VIS. Si un point de quadrature n'a pas de température valide, la moyenne de cet élément est `NaN` et `Thermal_valid_element = 0` ; aucune renormalisation sur les seuls points valides n'est faite. Un champ TH constant doit donner exactement cette constante pour tous les éléments valides, quelle que soit la déformation.

## 6. API locale et exécution

L'API HTTP transmet des paramètres et des aperçus ; elle ne transporte pas les séquences complètes. Une première découpe suffisante est :

| Route | Fonction |
| --- | --- |
| `GET /api/project` | Lire le projet et les états des étapes |
| `PUT /api/project/config` | Valider puis sauvegarder `config.toml` |
| `GET /api/roi/overlay-image` | Afficher le fichier ROI courant sur la VIS avant sauvegarde |
| `POST /api/mesh/preview` | Générer le maillage et son image superposée à la VIS |
| `GET /api/mesh/preview-image` | Relire l’aperçu valide pour le masque et les paramètres courants |
| `POST /api/roi/save` | Copier le masque source dans l’étude et invalider le maillage précédent |
| `POST /api/registration/fit` | Ajuster `H` à partir des correspondances, retourner résidus et superposition |
| `POST /api/registration/approve` | Enregistrer la validation manuelle pour l'empreinte de calibration affichée |
| `GET /api/synchronization` | Retourner les TH encadrantes et les poids pour chaque temps VIS |
| `POST /api/runs` | Figer les entrées et démarrer le processus de calcul |
| `GET /api/runs/{id}` | Lire état, progression, résultats et erreur |
| `POST /api/runs/{id}/cancel` | Arrêter le processus du run actif et le marquer annulé |
| `POST /api/runs/{id}/resume` | Reprendre un run arrêté ou échoué depuis le magasin DIC sauvegardé |
| `DELETE /api/runs/{id}` | Supprimer le seul dossier du run arrêté, après confirmation dans le GUI ; refuser un run actif ou un lien hors du dossier des runs |
| `POST /api/runs/{id}/export` | Produire VTU/PVD et manifeste |

Le processus de travail écrit d'abord les résultats dans un répertoire temporaire du run, puis les rend visibles après succès. Une erreur conserve la configuration, le journal et le diagnostic. L'annulation demande l'arrêt du processus ; les fichiers partiels ne sont pas présentés comme résultats valides. L'état est défini au minimum par `pending`, `running`, `completed`, `failed`, `cancelled`.

Le serveur n'écoute que sur l'interface loopback en première version. Les chemins fournis par le navigateur sont normalisés et les fichiers de projet sont lus/écrits uniquement dans les emplacements sélectionnés explicitement. Les exports sont servis comme téléchargements depuis le dossier du run.

## 7. Export ParaView

Le parcours DIC réutilise `write_dic_vtu` et `write_pvd` de `D2IC`. Les VTU actuels contiennent déjà `Displacement`, `Strain`, `E11`, `E22` et `E12` en données nodales lorsque la déformation est disponible. Une extension ciblée de l'exporteur ajoute des champs élémentaires `CellData` et un facteur d'échelle de longueur sans changer le comportement des appels existants.

Le parcours couplé écrit `Temperature`, `Delta_temperature` et `Thermal_valid` dans `PointData`, puis `Temperature_element`, `Delta_temperature_element` et `Thermal_valid_element` dans `CellData`. Les champs élémentaires sont les moyennes surfaciques calculées sur les éléments déformés. Le PVD utilise les temps VIS et contient l'état initial si sa température est valide. Un instant VIS sans TH coïncidente ou sans couple TH successif encadrant ne crée pas de VTU couplé ; les nœuds ou éléments partiellement hors champ restent invalides dans les VTU produits.

L'unité de longueur choisie s'applique **ensemble** aux coordonnées du maillage, à `Displacement`, à `Deformed_position` et à toute norme de déplacement. En mode `px`, l'export D2IC actuel est conservé. En mode `mm`, autorisé seulement après confirmation de `scale.mm_per_pixel`, tous ces tableaux sont multipliés par le même facteur pour que la déformation visuelle ParaView reste cohérente. `Strain` et les températures ne changent pas. Le manifeste indique l'unité, le facteur, les images TH encadrantes et les poids temporels.

Un test d'intégration ouvre les fichiers avec `meshio` et vérifie nombre de nœuds/éléments, noms, formes et unités des champs, chemins référencés par le PVD et monotonie des temps. Des champs thermiques constants et linéaires vérifient la moyenne par élément ; une translation connue vérifie l'échelle mm. L'ouverture visuelle dans ParaView complète cette vérification sur un petit cas de référence.

## 8. Découpage de réalisation et acceptation

1. **Projet web + TOML** : ouverture, édition et sauvegarde atomique ; parcours DIC visible ; validation du schéma et des chemins.
2. **ROI + DIC** : ROI depuis un fichier, maillage, calcul en processus séparé, suivi, cartes et VTU/PVD DIC.
3. **Thermique** : correspondance VIS–TH par points homologues, interpolation des TH aux temps VIS, fusion nodale, contrôle des valeurs invalides et VTU/PVD couplés.

La version DIC est acceptée quand un projet `config.toml` suffit à reproduire un calcul, qu’un changement de masque ROI invalide le maillage précédent, que l'étalonnage confirmé convertit correctement les déplacements et que la séquence VTU/PVD porte les bons temps VIS. La version couplée est acceptée quand les deux sources de temps prévues (nom de fichier ou métadonnées) sont reconnues selon le jeu d'images, qu'une correspondance VIS–TH non approuvée bloque la fusion, qu'un champ TH uniforme reste uniforme après projection, qu'une loi thermique linéaire est retrouvée exactement aux temps VIS, qu'une transformation VIS–TH connue donne les températures attendues, et que les temps non encadrés ou projections invalides restent absents. Un exemple minimal par parcours et des tests de compatibilité JAX `jit` pour les nouveaux kernels numériques seront fournis avec l'implémentation.

## Sources des choix techniques

- [Configuration actuelle de D2IC](../D2IC/src/d2ic/io/config.py) et [exemple TOML](../D2IC/examples/configs/sequential_dic.toml) : paramètres et conventions existants.
- [Export ParaView actuel](../D2IC/src/d2ic/io/paraview.py) : champs DIC nodaux, VTU et PVD.
- [Documentation FastAPI — templates](https://fastapi.tiangolo.com/advanced/templates/) et [tâches d'arrière-plan](https://fastapi.tiangolo.com/tutorial/background-tasks/) : base du serveur local et séparation du calcul lourd.
- [Documentation Python — `tomllib`](https://docs.python.org/3/library/tomllib.html) : lecture TOML uniquement ; l'écriture demande un outil distinct.
