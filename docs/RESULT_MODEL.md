# Modèle des résultats

Cette page est la référence unique pour le stockage, la reprise, les unités et les exports d’un run D2IC_GUI. Les contrats des APIs amont sont dans [INTEGRATION_CONTRACTS.md](INTEGRATION_CONTRACTS.md).

## Run et stockage

Chaque run est conservé dans `runs/<id>/`. Les sources d’images restent à leur emplacement ; le run fige sa configuration, ses chemins absolus, ses versions, les temps, les conventions et l’empreinte SHA-256 du masque. Le masque final et, en mode couplé, la correspondance approuvée sont copiés.

```text
runs/<id>/
  config.toml          réglages de l’étude au lancement
  dic_config.toml      configuration transmise à D2IC
  manifest.json        provenance, temps, unités, exports
  mask_final.tif       ROI figée
  status.json, run.log état et journal
  results/
    dic_store/         metadata.json, mesh.npz, roi.npz
      frames/frame_NNNN.npz   u_nodal (N,2), strain (N,3)
      checkpoint.npz, progress.json
    thermal_fields.npz champs thermiques du parcours couplé
    *.vtu, *.pvd             exports configurés
    dic_results.npz          export global facultatif
```

`dic_store` est la source de vérité des nouveaux runs et s’ouvre avec `d2ic.io.result_store.open_result_store`. Les anciennes archives `dic_results.npz` restent lisibles. Le GUI ne crée un NPZ global que sur demande ; les autres consommateurs de D2IC conservent leurs propres défauts d’export.

## Dimensions, temps et unités

- Images : `(y,x)` ; nœuds et déplacements : `(x,y)` en pixels VIS natifs. `strain (N,3)` suit `[E11,E22,E12]`, où `E12` est tensoriel et les déformations sont sans dimension.
- Le magasin contient les images VIS déformées, dans l’ordre temporel. La lecture ajoute la référence au premier temps VIS : `u₀=0`, `E₀=0`. `metadata.json` conserve `reference_time_s` et `frame_times_s`; le manifeste associe les chemins d’image.
- Une longueur en mm exige une échelle confirmée. Le magasin DIC reste en pixels ; les VTU convertis sont distincts des VTU natifs. Les déformations restent sans dimension.

## Fusion thermique et validité

Les hypothèses et règles de fusion sont définies dans le [contrat scientifique](INTEGRATION_CONTRACTS.md#contrat-scientifique). Le fichier `thermal_fields.npz` stocke `temperature`, `delta_temperature`, `thermal_valid` de forme `(Nt+1,N)` et les moyennes élémentaires `(Nt+1,Ne)`. Une valeur absente vaut `NaN`. Le manifeste conserve, pour chaque temps VIS, les TH encadrantes, leurs temps, le poids d’interpolation et la cause d’invalidité.

Le worker traite les frames une à une. Les six tableaux thermiques sont assemblés dans des NPY temporaires mappés sur disque, puis publiés dans un NPZ après réussite de la fusion, des exports demandés et de la compression. L’espace disque temporaire est proportionnel à ces tableaux ; les mappings sont fermés avant suppression des temporaires, après succès ou erreur.

## Écriture, reprise et exports

D2IC écrit chaque frame et son checkpoint atomiquement. Seules les frames validées par checkpoint sont visibles ; `progress.json` indique l’avancement. Une reprise vérifie empreinte de configuration, images, masque et maillage avant réutilisation des résultats. Le GUI garde les runs précédents et n’autorise la reprise que pour les états échoué ou annulé. Il ne réécrit pas les chemins historiques lors d’une relocalisation d’étude.

Les PVD utilisent les temps VIS mesurés ; une collection couplée omet les instants sans acquisition TH exacte ni encadrement temporel valide. Des nœuds peuvent néanmoins rester invalides dans une frame exportée. La géométrie exportée reste celle de référence ; coordonnées et déplacements partagent l’unité choisie. VTU/PVD sont configurés par run. Le NPZ monolithique est un format de compatibilité recréable depuis le magasin, sans relancer la DIC.

## Courbes et CSV

Le suivi de points exporte, pour chaque nœud sélectionné et temps validé (référence incluse) : `node,frame,time_s,<champ>_<unité>`. Une coupe est un segment matériel défini en pixels VIS de référence ; les champs nodaux sont interpolés sur les triangles de visualisation (Q4 découpé en 012 et 023). La distance A→B est mesurée dans la configuration de référence et exprimée dans l’unité du run. Hors maillage ou valeurs non finies donnent des cellules vides.

La coupe exporte une image ou tous les temps : `frame,time_s,distance_<unité>,x_ref_px,y_ref_px,<champ>_<unité>`. Déformations : unité `1` ; température : unité déclarée. Résidus et températures élémentaires ne sont pas inclus. Le centrage couleur autour de zéro est une option d’affichage, calculée depuis les bornes explicites ou le champ courant.
