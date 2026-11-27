# Guide simple de D2IC GUI

Ce guide suit le parcours **DIC seule** : créer une étude, charger les images, dessiner la région d’intérêt (ROI), mailler, lancer un calcul et analyser les résultats.

## 1. Démarrer et créer une étude

1. Sous Windows, extraire entièrement l’archive du GUI, puis lancer `D2IC_GUI.cmd`.
2. Garder la console ouverte : le GUI s’affiche dans le navigateur.
3. Sur l’écran de démarrage, cliquer sur **Créer une étude** et choisir le dossier où enregistrer le projet. Pour reprendre un travail, choisir **Ouvrir une étude** et sélectionner son dossier ou son fichier `config.toml`.
4. Choisir le parcours **DIC seule**.

Une étude doit être ouverte avant de travailler. Choisir un dossier utilisateur accessible en écriture, de préférence hors du dossier de l’application. Enregistrer régulièrement avec **Fichier → Enregistrer** ou **Ctrl + S**.

## 2. Charger les images VIS

1. Ouvrir la vue **VIS**.
2. Dans les paramètres à droite, sélectionner le dossier contenant les images avec **Parcourir…**.
3. Choisir la série dans **Séries détectées** si plusieurs séries sont proposées.
4. Vérifier l’**image de référence** : c’est l’état initial auquel les autres images seront comparées. La première image est proposée automatiquement ; la changer si nécessaire.
5. Vérifier les images actives : conserver la référence et au moins une image déformée acquise après elle.
6. Vérifier les temps d’acquisition et, si les temps proviennent des numéros de fichiers, renseigner la cadence réelle dans les réglages.

Les formats VIS acceptés sont TIFF, BMP, PNG et JPEG. Les images sources restent dans leur dossier : elles ne sont pas copiées dans l’étude.

## 3. Dessiner la ROI avec un rectangle ou une ellipse

La ROI est la zone de l’image sur laquelle le calcul sera effectué.

1. Ouvrir **ROI / maillage** : l’image de référence s’affiche.
2. Cliquer sur **Rectangle** ou **Ellipse**.
3. Avec l’action **Ajouter**, cliquer-glisser sur l’image pour dessiner la zone à conserver.
4. Ajouter d’autres formes si nécessaire. Pour exclure une partie ou créer un trou, choisir **Retirer**, puis dessiner une forme dans cette zone.
5. Utiliser **Annuler la dernière forme** pour corriger le dessin, ou **Nouveau dessin** pour recommencer.
6. Cliquer sur **Créer l’image ROI** pour enregistrer le masque TIFF. Ce masque est ensuite sélectionné dans **Fichier ROI**.

**Le dessin seul ne suffit pas : il faut cliquer sur Créer l’image ROI avant de mailler.**

Le calque vert représente la ROI géométrique ; le bleu représente les pixels retenus pour la corrélation après les réglages photométriques. On peut aussi sélectionner un masque TIFF ou PNG existant, de mêmes dimensions que la référence VIS.

## 4. Générer le maillage

1. Dans **ROI / maillage**, régler **Taille de maille** dans les paramètres.
2. Cliquer sur **Mailler**.
3. Vérifier que les arêtes du maillage couvrent la zone souhaitée et respectent les exclusions.

Après une modification du masque, de la taille de maille ou du binning, cliquer à nouveau sur **Mailler**.

Pour obtenir des longueurs en millimètres, passer par **Échelle**, définir le facteur mm/pixel ou mesurer un segment de longueur connue, puis cliquer sur **Confirmer l’échelle**. Cette étape est facultative pour travailler en pixels.

## 5. Préparer et lancer le job

1. Vérifier les paramètres dans **Réglages DIC**, puis enregistrer l’étude.
2. Ouvrir **Job Manager** et cliquer sur **Préparer le job**.
3. Lire les diagnostics. Si une erreur bloque la préparation, corriger l’étude puis préparer un nouveau job.
4. Cliquer sur **Lancer** dans la ligne du job préparé.
5. Suivre son état dans **Job Manager**. **Stop** permet d’interrompre le calcul.

Les réglages d’un job sont figés lors de sa préparation. Pour calculer avec d’autres réglages, préparer un nouveau job. Garder la console de l’application ouverte pendant le calcul.

## 6. Analyser les résultats

Depuis la ligne du job, cliquer sur **Résultats**.

### Afficher une carte

- Choisir la grandeur dans **Champ** : déplacement ou déformation, selon les champs disponibles.
- Déplacer le curseur **Instant VIS** pour parcourir la séquence.
- Choisir **Fond VIS → VIS de l’instant choisi** et ajuster l’opacité pour comparer le champ à l’image.
- Ajuster les bornes de couleur pour faciliter la lecture. Ces réglages changent uniquement l’affichage.

### Suivre des points

1. Ouvrir **Suivi de points** et choisir la **Grandeur**.
2. Cliquer sur la carte pour sélectionner un nœud du maillage. **Maj + clic** permet de le retirer.
3. Lire l’évolution temporelle de la grandeur sélectionnée.
4. Cliquer sur **Exporter CSV · toutes les images** pour récupérer les valeurs.

### Tracer une coupe

1. Ouvrir **Coupe**.
2. Cliquer deux fois sur le maillage pour définir les extrémités du segment.
3. Choisir la grandeur et le nombre d’échantillons.
4. Exporter en CSV pour l’image courante ou toutes les images.

Désactiver le mode zoom pour sélectionner des points ou placer une coupe. Pour poursuivre l’analyse dans ParaView, retrouver les fichiers VTU/PVD dans **Export** et ouvrir le PVD.

## Si une étape bloque

- **Aperçu ROI impossible** : vérifier qu’une étude est ouverte et qu’une référence VIS est choisie.
- **ROI vide** : dessiner au moins une forme avec **Ajouter**, puis créer l’image ROI.
- **Maillage absent ou périmé** : cliquer à nouveau sur **Mailler** avec les réglages courants.
- **Job impossible à lancer** : lire les erreurs de préparation dans **Job Manager** et corriger les étapes indiquées.

Pour aller plus loin : [manuel d’utilisation](MANUEL_UTILISATION.md).
