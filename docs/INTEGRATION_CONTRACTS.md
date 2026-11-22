# Contrats d’intégration

Cette page fixe les conventions entre le GUI, D2IC et DICTHFusion. Les chemins `D2IC/` et `DICTHFusion/` partent du workspace parent ; les chemins d’étude partent du dossier de configuration. Pour le stockage et les exports, voir [RESULT_MODEL.md](RESULT_MODEL.md), qui en est la référence.

## Contrat scientifique

La DIC par éléments finis estime le déplacement `uₖ(X)` par conservation de luminosité : `Iₖ(X+uₖ(X)) ≈ I₀(X)`. Avec `Fₖ=I+∇_X uₖ`, la déformation de Green–Lagrange est `Eₖ=½(FₖᵀFₖ−I)` dans la configuration VIS de référence. Les champs suivent `[E11,E22,E12]`, où `E12` est tensoriel. Coordonnées et déplacements sont en pixels VIS ; le temps est en secondes. L’échelle `s_vis=L_mm/||p₂−p₁||_px` convertit pixels en mm uniquement après confirmation explicite ; sinon les résultats restent en pixels.

La caméra VIS observe frontalement la face étudiée, supposée suffisamment plane durant l’essai. La correspondance `H` projette VIS vers TH ; elle suppose que la géométrie relative des caméras reste stable. Pour un point matériel `X` à un temps VIS réel `tₖ`, `xₖ=X+uₖ(X)`, puis `qₖ=H(xₖ)`. `qₖ` reste fixe pour échantillonner bilinéairement chaque image TH encadrante ; les températures sont ensuite interpolées linéairement dans le temps. Les images VIS et les champs DIC ne sont jamais interpolés. Il n’y a ni extrapolation ni interpolation à travers une acquisition TH manquante/non successive. `ΔT` prend pour référence la température au premier temps VIS, exacte ou interpolée, au même point matériel. Les températures sont moyennées sur la surface déformée de chaque élément par quadrature ; si un point d’intégration est invalide, la moyenne entière vaut `NaN`, sans moyenne partielle. Les TIFF TH doivent être calibrés et corrigés radiométriquement en amont ; leur unité doit être déclarée. Déduire des contraintes mécaniques ou des sources thermiques exige un modèle physique supplémentaire. Un changement de cadrage, une occlusion ou une face hors plan remet en cause la correspondance.

## Interopérabilité

| Module / API | Rôle et limites utiles |
| --- | --- |
| `d2ic.io.config.load_sequence_config` | Lit le TOML D2IC (`[paths]`, `[mesh]`, `[dic]`, `[output]`, `[runtime]`). Les chemins relatifs partent du TOML. `mask_path` prévaut sur `mask_filename`. |
| `d2ic.pipelines.sequence_platehole.run_sequence_from_config` | Exécute le calcul et écrit les résultats sur disque. Le GUI fournit les chemins absolus des images actives et ordonnées, avec `image_stride=1`. Le masque niveaux de gris devient booléen ; Gmsh est requis. |
| `d2ic.io.result_store.open_result_store` | Ouvre le magasin versionné des nouveaux runs ; format, reprise et compatibilité sont décrits dans [RESULT_MODEL.md](RESULT_MODEL.md). |
| `d2ic.io.paraview.write_dic_vtu`, `write_pvd`, `write_image_vti` | Exporte maillage, champs et images. D2IC écrit en pixels ; le GUI réalise les exports mm séparés après confirmation. Le pipeline séquentiel ne déduit pas les temps VIS : le GUI date le PVD depuis le manifeste. |
| `DICTHFusion.registration.fit_registration`, `transform_points`, `sample_temperature`, `temperature_at_visible_points` | Ajuste/projette `H` VIS→TH et échantillonne la TH par interpolation bilinéaire. Coordonnées `(x,y)` aux centres des pixels, origine en haut à gauche. Hors domaine `[0,W−1]×[0,H−1]` : `NaN`. |
| `DICTHFusion.registration.save_registration`, `load_registration` | Sérialise le JSON version 1 (direction, repère, dimensions, matrice et diagnostics). Le lecteur vérifie version, direction et matrice finie `(3,3)`, pas l’approbation GUI ni toutes les métadonnées. |

`fit_registration` accepte les modèles affine (3 paires non colinéaires minimum) et projectif (4 paires en position générale minimum). Il renvoie `H (3,3)` float64 et des résidus en pixels TH ; RMS et résidus sont des diagnostics, sans seuil universel. La calibration n’est approuvée que par l’utilisateur après inspection. La fonction active `jax_enable_x64` à l’import ; le worker doit tenir compte de cet effet sur la configuration JAX.

D2IC renvoie `u_nodal (Nt,Nn,2)` en pixels et `strain (Nt,Nn,3)` sans dimension ; `Nt` exclut la référence. Le GUI ajoute l’état de référence. `paths.mask_path` peut être hors de `img_dir`. Les opérations morphologiques et le masque final relèvent du GUI ; l’érosion photométrique ne change pas le maillage D2IC.

DICTHFusion ne gère ni temps, ni synchronisation/interpolation temporelle, ni approbation manuelle. La fusion, la référence `ΔT` et les invalidités sont la responsabilité du GUI selon le contrat scientifique ci-dessus. Pour les parcours opérateur, voir le [manuel](MANUEL_UTILISATION.md) ; pour l’architecture, la [spécification technique](SPEC_TECHNIQUE.md).
