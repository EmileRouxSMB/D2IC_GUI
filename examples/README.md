# Exemple synthétique VIS + TH

Depuis la racine du dépôt, exécuter :

```bash
python D2IC_GUI/examples/generate_synthetic_study.py /tmp/d2ic_gui_synthetic
```

Le script écrit deux séquences TIFF et `expected.json` dans le dossier donné. Il
ne modifie aucune image existante. Il ne faut pas interpréter les images de cette
étude comme des données expérimentales.

La séquence VIS mesure une translation rigide connue, exprimée en pixels VIS
d'origine `(x, y)`. L'image est indexée `(y, x)`. Les quatre temps VIS sont en
secondes et commencent par l'état de référence sans déplacement. La séquence TH
a une résolution moitié en chaque direction, avec le même champ de vue. Chaque
image contient une température uniforme en °C suivant `T(t) = 20 + 2 t`. Les
numéros TH suivent une cadence nominale de 10 Hz ; la trame 3 à `0.3 s` manque.
Ainsi, l'instant VIS `0.35 s` se trouve entre les images TH `0.2 s` et `0.4 s`,
avec une trame numérotée manquante dans l'intervalle. L'interpolation linéaire
attendue donne `indisponible (trame TH 3 manquante) °C`.

Les coordonnées couvrent le même champ de vue : `x_th = (W_th - 1)/(W_vis - 1)
* x_vis` et de même pour `y`. Les TIFF TH sont des températures float32 déjà
exprimées en °C ; aucune correction radiométrique n'est appliquée.

## Rejouer dans le GUI

Lancer `python -m D2IC_GUI`, créer une étude et renseigner dans le panneau droit :

- `paths.visible_dir` : `/tmp/d2ic_gui_synthetic/VIS` ; `paths.reference_image` : `vis_0000_tick0000.tif` ; `paths.visible_pattern` : `vis_*.tif`.
- `time.visible_frame_regex` : `tick(\d+)` ; `time.visible_fps` : `100`.
- Dessiner ou importer un masque VIS sur la référence, enregistrer la ROI, puis prévisualiser le maillage. Pour reproduire le test automatisé, le masque est le rectangle intérieur `x=28..99`, `y=22..73`.
- Pour le parcours couplé, choisir **DIC + thermique**, fixer `thermal.image_dir` à `/tmp/d2ic_gui_synthetic/TH`, `thermal.frame_regex` à `th_(\d+)` et `thermal.thermal_fps` à `10`. Apparier au moins trois points VIS–TH non alignés, inspecter les résidus et approuver la correspondance.

Le test de rejeu compare la translation VIS et la température à `0,15 s` ; il vérifie que la trame TH manquante exclut `0,35 s` du PVD couplé. Les chemins absolus des images restent dans le manifeste du run, sans copie des séquences.
