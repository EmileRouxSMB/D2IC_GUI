# Modèle de résultats D2IC utilisé par le GUI

## Source de vérité d'un run

Chaque calcul possède un dossier immuable `runs/<id>/`. Le fichier `config.toml` et le `manifest.json` y figent les choix, les versions logicielles, le SHA-256 du masque final et les chemins absolus des images VIS/TH. Les images originales restent dans leurs dossiers. Le masque final et, pour un parcours couplé, le JSON de correspondance approuvée sont les seuls petits fichiers d'entrée copiés dans le run.

```text
runs/<id>/
  config.toml                 paramètres de l'étude au lancement
  dic_config.toml             paramètres effectivement lus par D2IC
  manifest.json               provenance, unités, temps et exports
  mask_final.tif              ROI binaire figée
  status.json, run.log         état du worker et journal
  results/
    dic_store/
      metadata.json           schéma D2IC, chemins, conventions et temps VIS
      mesh.npz                nodes_xy (N,2), elements (Ne,3|4)
      roi.npz                 roi_mask (H,W)
      frames/frame_NNNN.npz   u_nodal (N,2), strain (N,3), résidu optionnel
      checkpoint.npz          dernier état validé pour la reprise
      progress.json           progression et nombre d'images validées
    thermal_fields.npz        champs TH aux instants VIS, en mode couplé
    *.vtu, *.pvd              exports ParaView selon la configuration
    dic_results.npz           archive globale facultative, créée à la demande
```

Le magasin versionné `dic_store` est la source de vérité des nouveaux runs. Le GUI l'ouvre avec `d2ic.io.result_store.open_result_store`. Les anciens runs ayant seulement `dic_results.npz` restent lisibles par le même lecteur. Un nouveau run ne produit pas d'archive globale automatiquement : l'action **Créer une archive NPZ compatible** l'exporte à la demande. L'option D2IC `output.export_legacy_npz` vaut `true` par défaut pour les autres consommateurs de D2IC ; l'adaptateur GUI la fixe à `false`.

## Dimensions, temps et unités

Les images sont indexées `(y,x)`, les nœuds et déplacements sont `(x,y)` en pixels VIS natifs. `strain (N,3)` contient `[E11,E22,E12]`, avec `E12` tensoriel. Le magasin ne stocke que les images VIS déformées, dans l'ordre temporel. L'état de référence au premier temps VIS est ajouté en lecture : `u₀=0`, `E₀=0`. `metadata.json` reçoit `reference_time_s` et `frame_times_s`; le manifeste associe à chaque instant le chemin absolu d'image utilisé.

`thermal_fields.npz` contient `temperature`, `delta_temperature`, `thermal_valid` de forme `(Nt+1,N)` et les champs élémentaires de forme `(Nt+1,Ne)`. Une température absente est `NaN`, jamais remplacée par une autre image. Le manifeste conserve pour chaque temps VIS les deux chemins TH encadrants, leur temps, le poids d'interpolation et la cause d'invalidité. Les champs thermiques sont consultables même lorsque l'export VTU est désactivé.

Une sortie en mm exige un étalonnage confirmé. D2IC garde le magasin en pixels ; les VTU en mm sont des fichiers distincts des VTU natifs afin de pouvoir reconstruire l'export sans multiplier deux fois les coordonnées. Les déformations restent sans dimension.

## Écriture, reprise et compatibilité

D2IC écrit une frame puis son checkpoint atomiquement. `progress.json` signale les images terminées ; une frame non validée par checkpoint n'est pas exposée. À la reprise, D2IC compare l'empreinte de la configuration, des images et du masque, puis vérifie le maillage avant de réutiliser un déplacement. Le GUI conserve les anciens runs et n'autorise la reprise que pour un état échoué ou annulé. La relocalisation d'une étude ne réécrit pas les chemins historiques des runs.

Les exports PVD sont datés aux temps VIS mesurés. Un PVD couplé omet les instants sans paire TH valide. Le format `dic_results.npz` est conservé comme export de compatibilité et peut être recréé à partir du magasin sans relancer la DIC.


## Courbes et exports CSV

Le suivi de points exporte la grandeur choisie pour tous les nœuds sélectionnés et tous les instants validés, référence comprise (`node,frame,time_s,<champ>_<unité>`). La coupe est un segment matériel défini en pixels VIS de référence ; le clic dans la configuration courante est inversé par interpolation affine des triangles de visualisation. Les champs nodaux sont interpolés sur ce segment, les quadrilatères étant découpés en triangles 012 et 023 comme les cartes. La distance A → B est mesurée dans la configuration de référence et convertie dans l’unité de longueur du run. Les sorties hors maillage ou non finies restent absentes et produisent des cellules CSV vides.

La coupe exporte soit l’image VIS choisie, soit tous les instants validés (`frame,time_s,distance_<unité>,x_ref_px,y_ref_px,<champ>_<unité>`). Les déformations portent l’unité `1`, les températures celle du run. Ces analyses ne couvrent pas les résidus ni la température élémentaire. Le centrage des couleurs sur zéro est une option de visualisation : bornes ±max(|min|, |max|), en partant des bornes explicites si présentes ou du champ courant autrement.
