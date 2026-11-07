# Memory — static

## Rôle du dossier

Contient la coque front-end locale de D2IC : structure de page, styles responsives et interactions des vues scientifiques.

## Fichiers importants

- `index.html` : barre supérieure, navigation scientifique, espace de travail et panneau de configuration.
- `style.css` : thème clair, navigation repliée par défaut, mise en page 70/30, séparateur, tables et dispositions étroites.
- `image_zoom.js` : contrôles communs de zoom par clic ou rectangle, dézoom Ctrl/Cmd + clic et réinitialisation ; géométrie de l’image après transformation.
- `app.js` : chargement des métadonnées et du projet, formulaires, aperçus de séquences, import de ROI, aperçu du maillage, appariement VIS–TH, exploration des champs et suivi de runs, ainsi que l’explorateur local de fichiers.

## Concepts physiques ou numériques

Les vues VIS et thermique affichent les fichiers réels disponibles via l’API. Les VIS TIFF/BMP/PNG/JPEG sont décodées par le lecteur D2IC pour partager la même conversion couleur → niveaux de gris ; les TIFF TH restent strictement scalaires. Le masque ROI TIFF/PNG, y compris gris + alpha, est rendu en calque transparent sur la VIS ; le bouton Mailler crée un calque maillage séparé ainsi qu’une image composée de compatibilité et copie le masque sans toucher à la source ; les points homologues VIS–TH sont transmis en pixels natifs de chaque caméra. Les tableaux affichent les temps en secondes et les TH encadrantes/poids/causes de synchronisation. Les cartes d’un run combinent champ, instant VIS, unité, et provenance/validité thermique. L’onglet Export affiche les PVD du run et peut demander l’archive NPZ globale de compatibilité. Le navigateur ne réalise aucun calcul scientifique.

## Conventions

- Le panneau droit affiche uniquement les clés de la vue active. VIS contient dossier, motif de série et référence ; le parcours global est dans la barre supérieure.
- Les séries VIS sont proposées par GET /api/visible/series depuis les noms des fichiers, sans charger les pixels. La référence proposée est le premier nom par ordre numérique ; la dernière composante numérique variable suggère l’expression temporelle. Une sélection explicite reste possible. GET /api/visible/inspect lit le formulaire courant pour afficher immédiatement les images, avant sauvegarde ; les lignes de la table changent l’aperçu via GET /api/image avec le dossier VIS sélectionné.
- Les champs TOML sont construits depuis les métadonnées `GET /api/schema` et affichent valeur, défaut, unité et aide.
- Le projet est chargé par `GET /api/project` et sauvegardé par `PUT /api/project/config`.
- L’explorateur lit GET /api/filesystem : chemins absolus, filtres par usage, recherche locale et pages de 200 entrées au plus. La sélection des sources ne modifie que le formulaire ; config.toml est écrit par l’action Enregistrer. Pour ouvrir une étude, le dossier ou son `config.toml` est accepté, avec double clic sur le dossier. Le bouton Ouvrir reste accessible en écran étroit.
- Les actions de projet utilisent POST `/api/project/new`, `/open` et `/copy`.
- Les opérations ROI, correspondance, synchronisation et calcul utilisent les routes documentées dans `app.js`.
- La proportion de séparation est une préférence locale (`localStorage`), jamais une donnée scientifique ; le partage initial est 70 % image et 30 % paramètres.

## Points d’attention

- Les images centrales et la pile ROI utilisent `image-rendering: pixelated` puis `crisp-edges` lorsque pris en charge : le zoom montre les pixels sources sans lissage du navigateur. Les aperçus VIS/TH sont demandés en pleine résolution (`full=1`) ; ce réglage d’affichage est indépendant de l’interpolation du solveur DIC. La version de la feuille CSS est changée pour éviter un ancien rendu en cache.

- ROI / maillage expose `dic.roi_erosion_px` depuis le schéma, avec une note visible précisant l’exclusion photométrique aux bords/trous et le maillage inchangé. Le défaut est zéro ; `3.0` est une valeur d’exemple. L’aperçu conserve la ROI géométrique verte et superpose un calque photométrique bleu indépendant, aligné sur les pixels VIS. Le rayon et sa réinitialisation actualisent seulement le calque bleu sans toucher au maillage ; les trois cases commandent ROI, photométrie et maillage. Le calcul du calque utilise les valeurs courantes du formulaire avant sauvegarde.

- La VIS, le calque ROI et le calque maillage ont les mêmes dimensions en pixels ; `object-fit: contain` les ajuste ensemble à toute la zone centrale sans déformer leurs coordonnées. Les cases ROI/maillage modifient seulement la visibilité des calques.
- En écran étroit, paramètres et navigation deviennent accessibles par panneaux superposés.
- La forme du JSON des routes séquence tolère plusieurs clés de liste ; toute modification des corps attendus doit rester alignée avec l’API serveur.

La navigation gauche démarre en mode icônes, avec libellés accessibles par `title` et `aria-label`, et un bouton de développement en haut du volet. Sa préférence est locale au navigateur. La zone centrale n’affiche plus un titre/sous-titre de vue redondant et gagne de la largeur et de la hauteur ; les commandes Image/Paramètres restent visibles en écran étroit.

Le bandeau supérieur est limité à 46 px. Le menu Fichier regroupe les opérations d’étude ; le projet, son état et le parcours restent visibles. Le menu se ferme après une action, au clic extérieur ou avec Échap ; Ctrl/⌘+S appelle Enregistrer. Enregistrer sous et Dupliquer envoient le formulaire courant à `POST /api/project/copy` pour créer une nouvelle étude sans sauvegarder l’originale.

La table VIS expose les cases Analyse et les actions 1/N, avant I, après I. Les exclusions vont dans `paths.excluded_images` (noms simples), et les changements marquent l’étude non enregistrée. La référence ne peut pas être désactivée.

Job Manager rend les actions dans chaque ligne et garde le résumé du run sélectionné en haut. Un run terminé ouvre Résultats via son bouton dédié. La sélection est mémorisée par étude ; Supprimer exige une confirmation et Stop précède la suppression d’un run actif. Résultats utilise `/fields`, `/mesh`, `/field-image`, `/field-range` et `/history` pour une carte cadrée sur le maillage, les bornes cinématiques et les courbes de plusieurs nœuds. Les nœuds sont sélectionnés sur la carte avec clic et Maj + clic ; les historiques sont mis en cache dans la page, sans tableau numérique.

La scène centrale n’a plus de `stage-grid` ni de cadre translucide. Les vues s’étendent jusqu’aux bords de la zone image ; la liste VIS/TH est étroite à grande largeur et passe sous l’image en conteneur étroit. Le pied de scène reste dans le DOM pour les mises à jour historiques mais est masqué. La vue Résultats sépare la carte entière et les courbes dans la hauteur disponible ; Job Manager possède sa propre liste de runs.


Le conteneur ROI applique aussi par JavaScript `position: relative` et trois images `position: absolute; inset: 0; width/height: 100%; object-fit: contain`. Cette géométrie évite que les calques se placent en colonne si une ancienne feuille CSS est encore en cache. Les URL de `style.css` et `app.js` dans `index.html` portent une version lors des changements de rendu.


Les espacements verticaux des vues séquence et du panneau des paramètres sont resserrés : en-tête, recherche, sections, champs, cartes de séries et lignes de table. Les champs et cases gardent leur taille de commande. La version des actifs statiques dans `index.html` est incrémentée lors d’un changement CSS visible pour invalider le cache du navigateur.


La vue DIC/échelle superpose un canevas de tracé à la VIS de référence pleine résolution. Les deux points de `scale.segment_xy_px` sont exprimés en pixels VIS d’origine ; les événements pointeur convertissent les coordonnées d’écran via le rectangle de l’image. Les extrémités sont déplaçables ; une loupe dessine un extrait de l’image d’origine près du point actif. Flèches = 1 px, Maj + flèches = 10 px. Chaque modification remet `scale.confirmed` à `false` ; le facteur `segment_length_mm / distance_px` reste un aperçu jusqu’au clic de confirmation.


La navigation distingue désormais `Échelle` (icône règle, section `[scale]`, segment interactif) et `Réglages DIC` (icône engrenage, sections `[dic]`, `[time]`, `[runtime]`). La loupe reste affichée après le relâchement du pointeur tant que la poignée conserve le focus ; elle disparaît à la désélection ou à la sortie de la vue. Le volet des paramètres se replie en rail de 44 px sur ordinateur, avec état mémorisé dans `localStorage` (`d2ic-settings-expanded`) ; la largeur réglée par le séparateur est conservée.

La carte Résultats place le PNG en position absolue dans sa zone avec `object-fit: contain` : elle ne crée plus de piste Grid à hauteur intrinsèque qui rogne le bas du maillage. La géométrie du clic est calculée depuis la boîte réellement rendue de l’image ; le clic est reçu par `.run-field-frame`, puis converti vers l’étendue du maillage. Le SVG des nœuds est uniquement un calque visuel et ne capte pas les événements.

Dans Résultats, la carte et l’historique occupent deux colonnes quand la zone centrale est large ; l’historique passe sous la carte quand le conteneur est étroit. Cela maximise la hauteur disponible pour les maillages allongés.

La vue TH réutilise la disposition VIS : détection des séries TIFF, aperçu de l’image sélectionnée, table de cases Fusion et commandes tout activer / 1 sur N / avant-après I. Les exclusions sont `thermal.excluded_images` et seules les acquisitions actives alimentent la synchronisation et les nouveaux runs. L’aperçu utilise le formulaire courant sans sauvegarder l’étude ; `T_ref` reste associé au premier temps VIS.

La vue Synchro place les cadences VIS et TH dans le panneau droit et présente les numéros de trame VIS/TH dans la table. Choisir une ligne affiche sa VIS et les TH gauche/droite dans trois cadres ; si les deux TH désignent le même fichier, le troisième cadre indique cette identité sans deuxième chargement. La première VIS est identifiée comme référence thermique. La table est issue de la configuration enregistrée ; une modification non enregistrée est signalée avant recalcul.


Les vues d’images sont raccordées automatiquement à `D2ICImageZoom.attach` lors des changements du DOM central. Les contrôleurs des conteneurs supprimés sont détruits. La pile ROI complète est transformée ensemble ; les images des vues de mesure sont transformées tandis que les canvas/SVG de points sont recalculés à l’événement `imageviewchange`. `fieldImageGeometry` fournit le rectangle effectif des pixels après object-fit et zoom pour la sélection des nœuds et les points homologues. L’étalonnage utilise le rectangle de l’image transformée pour placer son canvas en pixels natifs. Ctrl/Cmd + clic est réservé au dézoom ; Maj + clic retire un nœud sélectionné. Les aperçus des séquences utilisent la pleine résolution pour conserver les détails au zoom.


`roi_shapes.js` gère les rectangles et ellipses en coordonnées VIS natives, y compris après zoom. Un brouillon contient une liste ordonnée de formes Ajouter/Retirer ; sa rastérisation et les calques ROI/photométrie passent par `/api/roi/shapes/preview`. `/api/roi/shapes/save` produit uniquement un nouveau TIFF 0/255 ; le formulaire pointe ensuite sur ce fichier et Mailler reprend les routes existantes. Le brouillon bloque le maillage tant que l’image ROI n’est pas créée. Aucun polygone n’est stocké dans le TOML.
