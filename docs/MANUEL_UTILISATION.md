# Manuel d’utilisation

Installation et lancement : [README](../README.md#installation). Exemple prêt à générer : [étude synthétique](../examples/README.md). Le GUI lit des images existantes ; il ne les importe pas dans l’étude.

## 1. Créer ou ouvrir une étude

Au démarrage sans étude, choisir **Créer une étude** ou **Ouvrir une étude** et sélectionner son dossier / `config.toml`. L’espace de travail reste bloqué tant qu’une étude n’est pas créée ou ouverte ; annuler le choix du dossier revient à cet écran. Une étude fournie au lancement s’ouvre directement. Pour changer ensuite d’étude, utiliser **Fichier**. Choisir **DIC seule** ou **DIC + thermique**. Le panneau droit contient les paramètres et leurs aides `(i)` ; **Enregistrer** conserve les réglages dans `config.toml`.

**Enregistrer sous** et **Dupliquer** créent une autre étude avec les petits actifs nécessaires, sans modifier l’originale ni copier les séquences. **Relocaliser les images** met à jour leurs dossiers après vérification ; les anciens runs conservent leurs chemins historiques.

## 2. Choisir les images et leurs temps

| Vue | À renseigner et vérifier |
| --- | --- |
| **VIS** | Dossier, série, référence et images actives. Formats TIFF, BMP, PNG ou JPEG ; la couleur est convertie en niveaux de gris comme dans D2IC. |
| **Réglages DIC / Synchro** | Numéro extrait du nom + cadence, ou horodatage TIFF. Vérifier référence, ordre des acquisitions et temps. |
| **Thermique** | TIFF scalaires déjà exprimés en température, unité, série et acquisitions actives. Aucune correction radiométrique n’est faite ici. |

Les commandes de sélection permettent notamment de retenir une image sur N ou d’exclure avant/après l’image choisie. La référence VIS reste active. Désactiver une TH peut supprimer l’encadrement nécessaire à une interpolation.

L’aperçu peut rester accessible avec un avertissement temporel ; le calcul exige des temps valides. Les images doivent garder les dimensions attendues pour leur caméra.

## 3. Préparer la ROI et le maillage

Dans **ROI / maillage**, importer un masque TIFF/PNG non vide aux dimensions de la VIS, ou dessiner :

1. Choisir **Rectangle** ou **Ellipse**, puis glisser sur la référence.
2. Utiliser **Ajouter** pour combiner les formes et **Retirer** pour créer des trous.
3. Cliquer sur **Créer l’image ROI**, régler la taille des éléments puis **Mailler**.

Changer le masque, la taille de maille ou le binning impose de régénérer le maillage. Un dessin encore actif doit être créé ou abandonné avant préparation du job.

**Érosion photométrique** exclut des observations près des bords et des trous : rayon en pixels VIS d’origine, défaut `0`. Elle ne change pas le maillage. Les calques géométrique vert et photométrique bleu permettent d’inspecter la différence ; leurs cases changent seulement l’affichage.

## 4. Confirmer l’échelle et régler la DIC

Dans **Échelle**, saisir un facteur mm/pixel ou placer deux points de distance connue, renseigner cette distance puis **Confirmer l’échelle**. Les poignées permettent de retoucher le segment ; les flèches déplacent le point sélectionné de 1 px, ou 10 px avec Maj.

Sans confirmation, les longueurs restent en pixels ; une sortie en mm exige une échelle confirmée et l’unité correspondante dans les réglages d’export. Les déformations restent sans dimension.

Dans **Réglages DIC**, adapter les paramètres du solveur à l’essai. Les aides présentent le rôle de chaque champ. Les cartes de résidu sont facultatives et augmentent le volume des résultats.

## 5. Ajouter la thermique

Ce parcours est réservé au mode **DIC + thermique**.

- Dans **Thermique**, placer des points homologues VIS/TH, ajuster le modèle affine ou projectif, examiner les résidus et **approuver** la transformation. Il n’existe pas de seuil RMS universel d’acceptation.
- Dans **Synchro**, vérifier les cadences, l’événement commun ou les horodatages et les images TH associées à chaque instant VIS.
- Réapprouver une calibration modifiée. Un changement de cadrage ou de géométrie relative des caméras nécessite de revoir sa validité.

La température suit les points matériels déplacés. Hors image, sans référence thermique valide ou sans acquisitions TH successives encadrantes, certains champs restent absents (`NaN`) ; aucune extrapolation n’est effectuée. Voir le [contrat scientifique](INTEGRATION_CONTRACTS.md).

## 6. Préparer, lancer et reprendre un calcul

Enregistrer les réglages puis, dans **Job Manager**, cliquer sur **Préparer le job**. Une ligne conserve les sources et réglages figés, avec ses diagnostics :

| Action / état | Effet |
| --- | --- |
| Erreur de préparation | Corriger l’étude puis préparer un **nouveau** job. |
| Avertissement | Examiner sa conséquence ; il ne bloque pas **Lancer**. |
| **Lancer** | Exécuter le job préparé ; un seul calcul est actif à la fois. |
| **Stop** | Interrompre le worker. |
| **Redémarrer** | Reprendre un run échoué/arrêté si les entrées figées restent compatibles. |
| **Supprimer** | Supprimer le run et ses résultats après confirmation ; arrêter d’abord un run actif. Les sources restent intactes. |

Les résultats DIC deviennent consultables à mesure que les frames sont validées. Les champs thermiques apparaissent après la fusion complète. Déplacer ou modifier les sources peut empêcher une reprise.

## 7. Lire les résultats et exporter

Dans **Résultats**, sélectionner le champ et l’instant VIS. Le fond VIS courant, l’opacité et les bornes de couleur servent à l’affichage ; ils ne changent pas les données stockées.

- **Suivi de points** : clic pour ajouter un nœud, **Maj + clic** pour le retirer ; export CSV de la grandeur choisie sur les instants disponibles.
- **Coupe** : deux clics définissent un segment matériel ; choisir le nombre d’échantillons, puis exporter l’image courante ou la séquence. Hors maillage et valeurs absentes restent vides.
- **Zoom** : activer le mode, cliquer ou tracer un rectangle ; Ctrl/Cmd + clic réduit le zoom, **Réinitialiser la vue** rétablit le cadrage. Le désactiver pour placer points ou segments.

Dans **Export**, retrouver les VTU/PVD produits selon les options enregistrées avant le run. Le PVD s’ouvre dans ParaView. Le choix individuel des champs VTU après calcul n’est pas proposé. **Créer une archive NPZ compatible** produit l’archive DIC globale seulement si un autre outil en a besoin. Les détails de formats sont dans [RESULT_MODEL.md](RESULT_MODEL.md).

## En cas de problème

| Symptôme | Vérification |
| --- | --- |
| Maillage absent ou périmé | Recréer la ROI si nécessaire, puis **Mailler** avec les réglages courants. |
| Temps invalides | Vérifier expression des noms, cadence, référence et source des horodatages. |
| Température absente | Examiner synchronisation, trous de trames, champ caméra et référence thermique initiale. |
| Calibration refusée | Inspecter les points, dimensions et fichier, puis ajuster et approuver à nouveau. |
| Source modifiée ou disparue | Restaurer la source ou relocaliser l’étude et préparer un nouveau job. |
| Calcul échoué | Lire le diagnostic et le journal du run avant de redémarrer. |
