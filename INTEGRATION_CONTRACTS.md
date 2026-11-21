# D2IC_GUI — contrats d’intégration

Cette note décrit les échanges entre le GUI, D2IC et DICTHFusion. Les chemins de sources préfixés par `D2IC/` ou `DICTHFusion/` partent de l’espace de travail parent contenant les dépôts voisins, et non de la racine Git de `D2IC_GUI`. Les chemins d’une étude restent résolus depuis son dossier de configuration.

## Références et fonctionnement courant

- [README.md](README.md) : hypothèses et conventions scientifiques.
- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) : catalogue des paramètres du GUI ; [SPEC_TECHNIQUE.md](SPEC_TECHNIQUE.md) : architecture et traduction vers D2IC.
- [RESULT_MODEL.md](RESULT_MODEL.md) : source de référence pour le stockage courant, les dimensions, les unités, la reprise et les analyses des résultats.

Les nouveaux runs utilisent le magasin versionné `results/dic_store/`, lu avec `d2ic.io.result_store.open_result_store`. L’adaptateur `dic_run.prepare_run` fixe `save_npz=true`, `keep_results=false` et `export_legacy_npz=false` : les champs DIC sont persistés par image, sans accumulation de l’historique DIC dans le pipeline. Le worker annote le magasin avec les temps VIS et les conventions physiques. L’archive DIC globale n’est créée qu’à la demande pour compatibilité ; l’archive thermique `thermal_fields.npz` fait partie du format courant du parcours couplé.

Les interfaces historiques du NPZ monolithique sont regroupées dans une section dédiée ci-dessous ; elles ne définissent pas le stockage des nouveaux runs.

## D2IC : config et exécution séquentielle

- `D2IC/src/d2ic/io/config.py::load_sequence_config(cfg_path) -> SequenceConfig` lit un TOML. Tables obligatoires : `[paths]`, `[mesh]`, `[dic]`, `[output]`, `[runtime]`. Les chemins `img_dir` et `out_dir` relatifs sont résolus depuis le TOML. Si `paths.mask_path` existe, il est prioritaire et relatif au TOML ; sinon `mask_filename` est recherché dans `img_dir`. Il faut donc générer un `dic_config.toml` adapté, avec les chemins absolus du run et `mask_path` vers le masque final figé.
- `D2IC/src/d2ic/pipelines/sequence_platehole.py::run_sequence_from_config(cfg_path, *, output_dir=None, output_prefix=None, collection_dir=None) -> None` charge cette config et exécute le calcul ; les résultats sont écrits sur disque, pas retournés. Il vérifie la référence et le masque. Le GUI lui transmet la liste absolue des images actives et échantillonnées dans `paths.image_paths`, avec `image_stride=1` dans la configuration D2IC ; le manifeste conserve cet ordre et les temps correspondants. Les autres consommateurs D2IC peuvent utiliser la découverte par `image_pattern` et les options d’échantillonnage du pipeline. Il faut au moins une image déformée. Le masque est lu en niveaux de gris puis converti en ROI booléenne ; le maillage est généré par Gmsh, requis sans repli.
- Les images calculées sont `(H, W)` après `image_binning`. Les coordonnées de maillage sont `(Nn, 2)` `(x, y)` et les éléments sont des triangles ou Q4 ; les coordonnées et déplacements DIC sont en pixels de l’image VIS selon la convention du projet. `u_nodal` a forme `(Nt, Nn, 2)`, `strain` `(Nt, Nn, 3)` dans l’ordre `[E11, E22, E12]`, sans dimension, avec `E12` tensoriel. `Nt` compte les images déformées, sans état de référence initial. D2IC ne prend pas en charge l’échelle mm dans cette interface ; le GUI l’applique à l’affichage/export après confirmation.
- `runtime.jax_preferred`, `jax_fallback`, `jax_enable_x64` et `jax_matmul_precision` règlent JAX au lancement du pipeline. Le processus de travail doit fixer la configuration de plateforme/précision avant l’initialisation JAX, comme le recommande `SPEC_TECHNIQUE.md`.

## Masque et sélection des observations

- `paths.mask_path` est défini et résolu dans `D2IC/src/d2ic/io/config.py`; `sequence_platehole.py` le vérifie, le lit et transmet le masque à la génération du maillage. Il peut être hors du dossier d’images. `mask_filename` reste accepté pour compatibilité, relatif à `img_dir`. Les opérations morphologiques et le choix du masque final relèvent du GUI ; D2IC ne les orchestre pas.
- Dans le GUI, la morphologie géométrique héritée reste appliquée avant maillage ; l’érosion photométrique `dic.roi_erosion_px` modifie seulement les observations. Le module `roi.py` partage la préparation photométrique et l’identité des aperçus entre routes et contrôles de préparation. Les opérations numériques D2IC restent déléguées à D2IC.

## Compatibilité historique : NPZ DIC monolithique

Les anciens runs contenant uniquement `dic_results.npz` restent lisibles avec `open_result_store`. Le GUI consulte ce lecteur commun plutôt que de choisir un autre modèle scientifique selon le stockage.

L’ancien pipeline avec accumulation (`keep_results=true`) produisait notamment `nodes_xy (Nn,2)`, `elements (Ne,3|4)`, `u_nodal (Nt,Nn,2)`, `strain (Nt,Nn,3)`, les chemins des images et les conventions de déformation. Ces archives ne fournissent pas nécessairement les temps mesurés : le manifeste du run reste nécessaire pour les associer aux acquisitions. Les contraintes historiques de production du NPZ ne doivent pas être appliquées au magasin par image.

`D2IC/src/d2ic/io/mechanical_npz.py::load_dic_history_npz(path, prepend_reference=True)` est un lecteur mécanique spécialisé Q4, pas le lecteur général du GUI. Il n’importe pas tous les champs et métadonnées. Pour consulter les résultats du GUI, utiliser les fonctions de `results.py`, qui ouvrent le lecteur D2IC commun et ajoutent explicitement l’état de référence lorsque requis.

## Export ParaView DIC

- `D2IC/src/d2ic/io/paraview.py::write_dic_vtu(path, mesh, result) -> Path` écrit un état DIC VTU avec coordonnées `mesh.nodes_xy (Nn,2)` complétées en z=0, connectivité triangle/Q4, déplacement nodal et champs. `Displacement` et `Deformed_position` sont vectoriels 3D ; `Displacement_magnitude`, `E11`, `E22`, `E12` sont scalaires. `Strain` est tenseur 3D symétrique construit depuis `[E11,E22,E12]`, avec termes hors-plan nuls. Les unités restent celles d’entrée (pixels pour longueur/déplacement, déformation adimensionnelle) : l’exporteur ne convertit pas en mm.
- `write_pvd(path, datasets)` prend des tuples `(time, path)` ou `(time, path, part)` et écrit une collection dont les temps sont ceux fournis. `write_image_vti` exporte séparément une image 2D en coordonnées pixels.
- Le pilote `D2IC/src/d2ic/batch/mesh_based.py` sait transmettre `BatchConfig.frame_times`; leur longueur doit correspondre au nombre d’images déformées. En l’absence de ces temps, il date les sorties par indice `k`. Le pipeline TOML séquentiel ne déduit généralement pas l’axe VIS ; le GUI doit fournir les temps réels et peut appeler `write_pvd` pour reconstruire la collection datée. Le worker reconstruit la collection DIC avec les temps VIS réels, y compris la référence. La fusion et les exports couplés sont implémentés dans `worker._fuse_thermal` et `thermal.py` ; ils ajoutent les champs thermiques nodaux et élémentaires et la provenance définis dans [RESULT_MODEL.md](RESULT_MODEL.md).

## DICTHFusion : recalage et température

API publique réexportée dans `DICTHFusion/__init__.py`, implémentée dans `DICTHFusion/registration.py` :

- `fit_registration(visible_points, thermal_points, visible_shape, thermal_shape, model="affine")` reçoit deux tableaux appariés `(n,2)` de coordonnées pixel `(x,y)` aux centres des pixels, et les formes `(hauteur, largeur)`. Retourne `(H, residuals)` : matrice `H (3,3)` float64 VIS→TH et résidus euclidiens par paire en pixels TH. Modèle affine : au moins 3 paires non colinéaires ; projectif : au moins 4 paires en position générale. Refuse formes incompatibles, valeurs non finies et système de rang déficient. Les résidus/RMS sont diagnostics ; aucune validation manuelle ni tolérance universelle n’est imposée par la fonction.
- `transform_points(matrix, xy_visible)` mappe des coordonnées `(...,2)` VIS en coordonnées `(...,2)` TH par coordonnées homogènes. Les images peuvent avoir des résolutions différentes ; coordonnées `(x,y)`, origine coin supérieur gauche, centres de pixels.
- `sample_temperature(thermal_image, thermal_xy)` échantillonne bilinéairement une image `(H_TH,W_TH)` aux coordonnées `(...,2)` et retourne les températures de même forme spatiale. Hors domaine des centres de pixels `[0,W-1] × [0,H-1]`, résultat `NaN`. Les valeurs de pixels sont utilisées sans conversion d’unité ; les TIFF sont supposés déjà calibrés (souvent °C).
- `temperature_at_visible_points(image, H, xy_visible)` compose projection VIS→TH et échantillonnage ; les tableaux de sortie sont JAX. `registration.py` active `jax_enable_x64` à l’import ; tenir compte de cet effet de configuration dans le processus de travail.
- `save_registration(path, matrix, model, pairs, visible_path, thermal_path, visible_shape, thermal_shape, residuals)` écrit JSON version 1 avec direction `visible_to_thermal`, convention de coordonnées, chemins absolus, dimensions `(H,W)`, matrice, paires et résidus, RMS en pixels TH. `load_registration(path) -> (data, H)` vérifie la version/direction et que `matrix` est finie de forme `(3,3)` ; ce n’est pas une validation complète des métadonnées ou de l’approbation GUI.

DICTHFusion ne gère ni le temps ni la synchronisation/interpolation temporelle TH, ni l’approbation manuelle persistée par le projet. Il suppose que la calibration est réutilisée avec le même cadrage et la géométrie relative inchangée. L’interpolation temporelle, les invalidités de trames et la référence `ΔT` restent des responsabilités du GUI, selon `README.md` et `SPEC_TECHNIQUE.md`.
