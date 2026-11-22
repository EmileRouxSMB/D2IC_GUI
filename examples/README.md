# Exemple synthétique VIS + TH

Après l’[installation](../README.md#installation) :

```bash
python -m D2IC_GUI.examples.generate_synthetic_study /tmp/d2ic_gui_synthetic
```

Le lanceur `examples/generate_synthetic_study.py` appelle le même générateur. Celui-ci produit les TIFF VIS/TH et `expected.json` ; ces images servent à la validation, pas à une mesure expérimentale.

| Donnée | Valeur analytique |
| --- | --- |
| VIS | Temps `0`, `0.15`, `0.35`, `0.45` s ; translations `(0,0)`, `(2,1)`, `(4,2)`, `(6,3)` px. |
| TH | Résolution moitié ; champ uniforme `T(t)=20+2t` °C, cadence 10 Hz, trame à `0.3 s` manquante. |
| Correspondance | `x_TH=x_VIS·63/127`, `y_TH=y_VIS·47/95`. |
| Résultats attendus | À `0.15 s`, `20.3 °C` ; à `0.35 s`, température absente à cause de la trame manquante. |

Dans le GUI, choisir `VIS/vis_0000_tick0000.tif`, motif `vis_*.tif`, expression `tick(\d+)` et cadence VIS `100`. Pour TH : dossier `TH/`, expression `th_(\d+)`, cadence `10`. Importer ou dessiner la ROI, mailler, apparier et approuver les points VIS–TH, puis préparer/lancer le job. Le masque du rejeu automatisé couvre `x=28..99`, `y=22..73`.

Les étapes détaillées sont dans le [manuel](../docs/MANUEL_UTILISATION.md). `config_dic.toml` et `config_dic_thermal.toml` donnent des réglages de départ ; adapter les chemins aux images générées.
