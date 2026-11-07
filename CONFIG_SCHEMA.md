# D2IC_GUI — schéma `config.toml` version 1

`config.toml` est lu par `tomllib`. Les clés absentes prennent le défaut ci-dessous. Une étude DIC nouvelle omet les tables TH, mais les conserve si elle revient temporairement du parcours couplé. Les préférences visuelles (largeur du panneau, vue active, zoom) restent dans le navigateur et n’entrent pas dans ce fichier.

Les séries VIS peuvent utiliser TIFF (.tif/.tiff), BMP, PNG ou JPEG (.jpg/.jpeg). La conversion des couleurs en niveaux de gris suit exactement le lecteur D2IC ; les TIFF thermiques restent des températures 2D.

| Clé | Vue | Défaut | Unité | Aide |
| --- | --- | --- | --- | --- |
| `project.version` | Système | `1` | — | Version du format de l'étude ; fixée à 1. |
| `project.mode` | Global | `"dic"` | — | DIC seule ou DIC avec température. Choix : dic, dic_thermal. |
| `project.name` | Résultats | `"Nouvelle étude"` | — | Nom lisible de l'étude. |
| `paths.visible_dir` | VIS | `""` | — | Dossier des images VIS TIFF, BMP, PNG ou JPEG ; elles restent sur place. |
| `paths.reference_image` | VIS | `""` | — | Nom ou chemin de l'image de référence. |
| `paths.visible_pattern` | VIS | `"*.tif"` | — | Motif de la série VIS ; la référence est exclue du calcul DIC. |
| `paths.output_dir` | Résultats | `"runs"` | — | Destination des calculs figés. |
| `roi.initial_mask` | ROI | `"roi/mask_initial.tif"` | — | Masque binaire VIS avant morphologie. |
| `roi.final_mask` | ROI | `"roi/mask_final.tif"` | — | Masque binaire effectivement utilisé pour le maillage. |
| `roi.operation` | ROI | `"none"` | — | Dilate ou érode le masque initial avant maillage. Choix : none, dilation, erosion. |
| `roi.radius_px` | ROI | `0` | px VIS | Rayon du disque morphologique ; zéro conserve le masque. |
| `roi.kernel` | ROI | `"disk"` | — | Forme de l'élément structurant ; disque discret. Choix : disk. |
| `mesh.element_size_px` | ROI | `15.0` | px VIS | Échelle du maillage à inspecter sur la texture VIS. |
| `mesh.remove_islands` | ROI | `true` | — | Écarte les petites composantes séparées du masque. |
| `mesh.min_island_area_px` | ROI | `64` | px² VIS | Aire sous laquelle une composante est écartée. |
| `dic.image_stride` | DIC | `1` | — | Retient une image VIS sur ce nombre ; les temps restent ceux des acquisitions retenues. |
| `dic.image_binning` | DIC | `1` | — | Réduit la résolution du calcul ; les résultats reviennent aux pixels VIS d'origine. |
| `dic.roi_erosion_px` | ROI | `0.0` | px VIS d’origine | Rayon d’érosion euclidienne des observations photométriques aux bords et aux trous. Zéro désactive l’érosion ; `3.0` reproduit le réglage d’IdentVirual. Aucun changement du masque de maillage, des nœuds ou des éléments. |
| `dic.max_iters` | DIC | `400` | — | Limite des itérations du solveur DIC. |
| `dic.tol` | DIC | `0.01` | — | Critère d'arrêt du solveur DIC. |
| `dic.reg_strength` | DIC | `0.01` | — | Poids de la régularisation ; dépend du cas étudié. |
| `dic.regularization` | DIC | `"elastic"` | — | Type de régularisation du champ de déplacement. Choix : elastic, spring. |
| `dic.strain_gauge_length` | DIC | `80.0` | px VIS | Échelle spatiale d'estimation des déformations. |
| `dic.interpolation` | DIC | `"cubic"` | — | Interpolation des niveaux de gris aux positions déformées. Choix : cubic, linear. |
| `scale.mm_per_pixel` | DIC | `1.0` | mm/px | Millimètres par pixel VIS d'origine ; confirmé explicitement avant sortie en mm. |
| `scale.method` | DIC | `"manual"` | — | Saisie directe ou segment mesuré sur la référence VIS. Choix : manual, segment. |
| `scale.confirmed` | DIC | `false` | — | Confirme que la mesure d'échelle a été vérifiée. |
| `scale.segment_xy_px` | DIC | `[]` | px VIS | Deux points [x,y] dans la VIS d'origine. |
| `scale.segment_length_mm` | DIC | `0.0` | mm | Longueur physique connue entre les deux points. |
| `time.visible_source` | DIC | `"filename"` | — | Numéros du nom de fichier ou horodatages des métadonnées. Choix : filename, metadata. |
| `time.visible_frame_regex` | DIC | `"(\\d+)"` | — | Capture le numéro d'acquisition dans le nom de fichier. |
| `time.visible_fps` | DIC | `10.0` | Hz | Convertit les numéros d'image en secondes. |
| `output.export_vtu` | Export | `true` | — | Un fichier de champs par temps VIS. |
| `output.export_pvd` | Export | `true` | — | Série ParaView datée par les temps VIS ; exige VTU. |
| `output.save_npz` | Export | `true` | — | Conserve le magasin DIC par image et ses chemins sources pour la reprise ; archive globale sur demande. |
| `output.export_png` | Export | `false` | — | Figures par image, qui augmentent le volume du run. |
| `output.compute_residual_map` | Export | `false` | — | Carte de résidu photométrique par image VIS ; augmente le volume du magasin DIC. |
| `output.paraview_length_unit` | Export | `"px"` | — | mm exige une échelle confirmée ; coordonnées et déplacements changent ensemble. Choix : px, mm. |
| `output.series_name` | Export | `"dic"` | — | Nom de base des fichiers VTU/PVD. |
| `runtime.jax_preferred` | DIC | `"gpu"` | — | Dispositif JAX demandé pour le processus de calcul. Choix : gpu, cpu. |
| `runtime.jax_fallback` | DIC | `"cpu"` | — | Utilisé si le dispositif préféré est indisponible. Choix : cpu, gpu. |
| `runtime.jax_enable_x64` | DIC | `false` | — | Active les flottants 64 bits avant l'initialisation JAX. |
| `thermal.image_dir` | Thermique | `""` | — | Dossier des TIFF contenant déjà des températures. |
| `thermal.image_pattern` | Thermique | `"*.tif"` | — | Motif des acquisitions thermiques. |
| `thermal.unit` | Thermique | `"degC"` | — | Unité physique des valeurs TIFF ; aucune correction radiométrique. |
| `thermal.time_source` | Thermique | `"filename"` | — | Numéros du nom ou horodatages des métadonnées. Choix : filename, metadata. |
| `thermal.frame_regex` | Thermique | `"(\\d+)"` | — | Capture le numéro d'acquisition thermique. |
| `thermal.thermal_fps` | Thermique | `50.0` | Hz | Convertit les numéros TH en secondes ; souvent 50 Hz. |
| `registration.file` | Thermique | `"calibration/visible_thermal.json"` | — | Transformation VIS vers TH issue de points homologues. |
| `registration.approved` | Thermique | `false` | — | Validation manuelle liée au fichier exact et à ses dimensions. |
| `synchronization.method` | Temps | `"timestamps"` | — | Horodatages communs ou événement vu par les deux caméras. Choix : timestamps, event_frames. |
| `synchronization.visible_event_frame` | Temps | `0` | — | Numéro de trame VIS de l'événement commun. |
| `synchronization.thermal_event_frame` | Temps | `0` | — | Numéro de trame TH du même événement. |
| `synchronization.thermal_interpolation` | Temps | `"linear"` | — | Interpolation linéaire des températures seulement. Choix : linear. |
| `synchronization.thermal_offset_s` | Temps | `0.0` | s | Décalage explicite de l'horloge TH vers les temps VIS. |

## Validation

- Les chemins d’images et de masque restent éditables dans une étude incomplète, mais leur existence est vérifiée avant calcul.
- `output.save_npz` active le magasin par image, obligatoire pour la reprise du calcul ; `output.export_pvd` exige `export_vtu`.
- La sortie en mm exige une échelle confirmée. En méthode segment, le facteur est calculé depuis deux points VIS natifs et leur longueur connue.
- Les tables TH n’entrent pas dans un run DIC seule. Une correspondance couplée exige une approbation liée au SHA-256 du JSON et aux dimensions VIS/TH.
