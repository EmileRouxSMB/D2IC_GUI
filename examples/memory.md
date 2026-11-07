# Memory — D2IC_GUI/examples

## Rôle du dossier

Contient des exemples compacts et reproductibles pour vérifier les contrats
scientifiques de l'interface.

## Fichiers importants

- `generate_synthetic_study.py` : écrit une translation VIS connue et une séquence TH uniforme à évolution linéaire, avec résolutions et temps distincts.
- `README.md` : commande de génération et valeurs analytiques attendues.

## Concepts physiques ou numériques

La translation est définie en pixels VIS d'origine `(x, y)`. La température TH
est `20 + 2 t` °C et constante dans l'espace. Le champ de vue commun est mis à
l'échelle des centres de pixels pour la résolution TH inférieure.

## Conventions

Les configurations DIC seule et couplée documentent `dic.roi_erosion_px = 0.0` ; une valeur `3.0` exclut une bande photométrique en pixels VIS d’origine sans modifier le maillage.

Images indexées `(y, x)`, coordonnées en `(x, y)`, translations en pixels VIS,
temps en secondes, température en °C. La trame TH d'index 3, soit `0.3 s` à
10 Hz, est intentionnellement absente.

## Points d’attention

Installer NumPy et tifffile pour exécuter le générateur. Les TIFF thermiques
contiennent des valeurs float32 directement en °C. La génération n'écrit que
dans le dossier de sortie demandé.
