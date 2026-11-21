# D2IC_GUI — spécification ergonomique de l'application web locale

**Statut :** spécification de conception, GUI non implémentée. Ce document définit l'expérience utilisateur. La [définition scientifique](README.md) fixe les grandeurs et hypothèses ; la [spécification technique](SPEC_TECHNIQUE.md) fixe l'architecture et le format `config.toml`. En cas de divergence sur un calcul, la définition scientifique fait foi.

## 1. Objectif et utilisateurs

Une personne qui découvre la DIC doit pouvoir préparer un essai et comprendre chaque paramètre grâce à une aide courte, sans connaître le format TOML. Une personne expérimentée doit pouvoir régler **toutes les options prévues par la configuration**, inspecter les données intermédiaires, reprendre un calcul et exporter les champs sans quitter l'interface.

Il existe **une seule présentation**, avec tous les paramètres disponibles dans le panneau droit. Chaque contrôle montre sa valeur courante et sa valeur par défaut ; son icône `(i)` ouvre une brève description, l'unité, l'effet du réglage et une valeur ou plage typique lorsqu'elle a un sens. Une valeur typique est un repère de départ, jamais un critère de validité scientifique. Aucune correction automatique de données expérimentales ne doit rester implicite.

### Principes d'interaction

- **Laisser naviguer librement** : les entrées de la navigation gauche ouvrent directement les vues scientifiques ; le calcul seul vérifie que ses entrées obligatoires sont prêtes.
- **Montrer la preuve** : aperçus des images, ROI finale, maillage, temps extraits, résidus de correspondance et unités avant lancement.
- **Séparer préparation et résultat figé** : les modifications courantes ne changent jamais un run terminé ; un nouveau lancement crée un nouveau run.
- **Montrer tous les paramètres** : chaque vue affiche tous ses réglages dans le panneau droit, regroupés par sujet sans catégorie « avancée » ni mode d'accès distinct. Le panneau affiche directement les paramètres, sans outil de recherche.
- **Expliquer les blocages** : chaque erreur indique le fichier, la valeur ou la vue concernée, sa conséquence et l'action possible. Les avertissements restent distincts des erreurs bloquantes.
- **Préserver les données** : afficher le chemin absolu des images retenues dans le récapitulatif et le manifeste ; les images ne sont pas dupliquées dans le projet.

### Explorateur de fichiers intégré

Les champs qui désignent un dossier ou un fichier ont un bouton **Parcourir…** et restent saisissables au clavier. L’explorateur local affiche le chemin absolu courant, permet de remonter ou de saisir un chemin, de rechercher dans le dossier courant et de charger les entrées par pages. Les dossiers sont toujours navigables ; les fichiers affichés sont filtrés selon l’usage (image VIS/TH, masque TIFF/PNG, calibration JSON, étude avec config.toml). La sélection d’une image de référence renseigne son nom et le dossier VIS correspondant. Les chemins choisis ne sont appliqués au calcul qu’après enregistrement du projet. La création et la copie d’étude demandent un dossier parent et un nom de dossier ; l’explorateur ne duplique pas les images.

## 2. Structure générale et disposition

L’application s’ouvre sur une étude ou une page d’accueil compacte. Le bandeau supérieur, d’environ 46 px de haut, montre l’identité D2IC, un menu **Fichier**, le nom et l’état de l’étude, le parcours DIC/DIC + thermique et les runs récents. Il laisse autant de hauteur que possible à l’image.

Le menu **Fichier** contient **Nouvelle étude**, **Ouvrir**, **Enregistrer**, **Enregistrer sous**, **Dupliquer l’étude** et **Relocaliser les images**. Il se ferme après une action, au clic extérieur ou avec Échap. `Ctrl+S`/`⌘S` enregistre l’étude active. **Enregistrer sous** copie les réglages courants, y compris les modifications non encore enregistrées, vers un nouveau dossier puis l’ouvre sans modifier l’étude source. **Dupliquer** suit le même mécanisme avec un nom de copie proposé. La copie conserve les chemins absolus des images sources et les petits masques/calibrations nécessaires, sans copier les séquences d’images ni les anciens runs.


Une **barre de navigation verticale à gauche**, inspirée par la simplicité de la barre latérale de ChatGPT, donne accès directement à : **VIS**, **ROI / maillage**, **Échelle**, **Réglages DIC**, **Thermique / correspondance**, **Synchro**, **Job Manager**, **Résultats**, **Export**. Chaque entrée associe une icône représentative et un libellé toujours lisible en mode développé. La navigation est repliée par défaut pour laisser plus de largeur aux images : seules les icônes sont visibles. Le bouton placé en haut du volet la développe ou la replie ; ce choix est mémorisé localement. Chaque icône possède une infobulle et un nom accessible au clavier et aux lecteurs d’écran. Les icônes proposées sont : image pour VIS, contour de sélection pour ROI, règle graduée pour Échelle, engrenage pour Réglages DIC, thermomètre pour Thermique, horloge pour Synchro, commandes de calcul pour Job Manager, courbe pour Résultats et flèche de sortie pour Export. L'icône ne constitue jamais seule l'information d'état.

Les entrées Thermique et Synchro sont absentes en parcours DIC seule ; changer de parcours est un contrôle permanent près du nom de l'étude. Toutes les autres vues sont accessibles à tout moment, même si une entrée manque. Aucun bouton « Précédent / Continuer » ni assistant pas à pas n'est prévu. Chaque entrée affiche son état : prêt, incomplet, avertissement, erreur ou résultat périmé. Cliquer sur l'état ouvre la cause et le contrôle concerné ; seule l'action **Lancer** exige que les entrées requises soient valides. La navigation gauche peut être développée ou repliée sans changer la vue active ni les paramètres.

### Espace de travail

Sur écran large, la largeur **restante après la navigation gauche** est partagée **initialement à 70 % pour la zone centrale** et **30 % pour le panneau de paramètres à droite**. La zone centrale commence directement par l’image ou le contenu scientifique, sans répéter le nom de la vue au-dessus ; ce nom figure déjà dans la navigation et le panneau droit. Elle accueille une ou plusieurs images, une superposition, une frise temporelle, une carte de résultat ou un tableau scientifique selon la vue. Le panneau droit affiche en permanence les paramètres et actions de cette vue, avec défilement indépendant.

Une **poignée visible entre la zone centrale et le panneau droit** permet de modifier les largeurs **en direct par glisser-déposer**, sans relâcher la souris pour voir le résultat. Les images, superpositions, légendes, tableaux et formulaires se réorganisent pendant le déplacement ; les coordonnées des pixels, les points posés, la sélection matérielle, le niveau de zoom et le centre observé restent stables. Le panneau ne peut pas rétrécir au point de rendre ses champs illisibles ; la zone centrale conserve assez d'espace pour manipuler une image. Si la fenêtre devient trop étroite pour ces deux minima, la disposition passe au mode étroit décrit ci-dessous. Un double clic sur la poignée restaure 70/30 ; des touches fléchées la déplacent par pas réguliers quand elle a le focus. La proportion choisie est mémorisée localement, par navigateur, sans entrer dans le `config.toml` scientifique ni dans les runs. Le redimensionnement ne relance aucun calcul scientifique.

Le panneau droit regroupe les réglages sous des titres courts. **Chaque paramètre**, y compris les chemins et les cases à cocher, présente son libellé, sa valeur courante, son unité si applicable, et sa **valeur par défaut** ; l'icône `(i)` révèle en quelques phrases sa fonction, sa valeur ou plage typique si pertinente, et sa clé TOML. Si aucune valeur typique générale n'existe (chemin de fichier, choix dépendant de l'appareil), l'aide le dit explicitement. Une action **Réinitialiser ce paramètre** revient au défaut indiqué ; les réglages restent modifiables sans changer de mode. Les défauts proviennent du schéma versionné de D2IC_GUI : ils ne sont ni les valeurs du dernier projet ouvert, ni celles d'un ancien run. Pour un champ obligatoire sans valeur universelle, tel que le dossier d'images, le défaut affiché est « à renseigner » et la réinitialisation efface la valeur. Les options inapplicables au parcours ou à la méthode courante restent visibles mais désactivées avec une explication, sauf les sections thermiques entièrement absentes en DIC seule.

Sur écran étroit, la navigation gauche devient un tiroir ouvert par un bouton, avec les libellés visibles ; le panneau de paramètres devient un tiroir occupant la largeur disponible, ouvrable sans perdre la vue ni les modifications. La poignée centrale est remplacée par les commandes **Afficher l'image** / **Afficher les paramètres** si les deux zones ne peuvent plus coexister lisiblement. Aucun contrôle n'est masqué à cause de la taille de l'écran. Sur écran tactile assez large, la poignée accepte aussi le glissement au doigt ; Les proportions 70/30 sont donc une disposition initiale du seul espace de travail sur écran large, pas une contrainte rigide sur tous les écrans.

`config.toml` reste la source de vérité reproductible : le panneau charge ses valeurs, les valide et les enregistre de manière atomique. L'utilisateur peut ouvrir le fichier ou afficher la clé TOML associée à chaque champ, mais la GUI ne propose pas un second mode d'édition qui aurait des règles différentes. Une clé non reconnue dans un TOML ouvert est signalée, jamais écartée silencieusement. L'interface annonce que la réécriture peut reformater le TOML et ne garantit pas la conservation des commentaires libres.

### Direction visuelle et fluidité

L'esthétique prend **ChatGPT comme référence d'ambiance** : interface calme et lisible, surfaces claires ou sombres cohérentes, contrastes mesurés, séparateurs discrets, espacements réguliers, typographie sobre, icônes simples et commandes facilement repérables. Les cartes et cadres ne doivent pas concurrencer les images scientifiques. Cette référence guide la hiérarchie visuelle ; D2IC_GUI garde son identité et ses contraintes de mesure. La palette scientifique des cartes de température ou de déformation reste indépendante du thème d'interface et dispose d'une légende avec unités.

Les changements de vue et l'ouverture des panneaux sont réactifs et conservent les états de travail : zoom, image courante, sélection, saisies non enregistrées et position de défilement du panneau droit. Les prévisualisations légères sont actualisées sans rechargement complet de la page ; les opérations longues affichent un état visible. Les transitions visuelles sont brèves et peuvent être désactivées par la préférence système de réduction des animations. La fluidité perçue ne doit pas masquer un calcul en cours, une erreur ou une valeur devenue périmée.

Les vues d’images disposent d’une commande **Zoom** : un clic gauche agrandit autour du pointeur et un glisser du bouton gauche définit la fenêtre à agrandir. **Ctrl + clic** (Cmd + clic sur macOS) dézoome autour du pointeur ; **Réinitialiser la vue** affiche l’image entière. Dans les vues avec points ou nœuds, le mode Zoom doit être activé pour tracer une fenêtre, puis désactivé pour utiliser les outils scientifiques. Le zoom ne change pas les coordonnées sources et conserve l’alignement des calques.

## 3. Contenu des vues de la navigation gauche

### 3.1 VIS

La vue VIS sert uniquement à ouvrir et vérifier les images visibles. Les formats VIS acceptés sont TIFF, BMP, PNG et JPEG (niveaux de gris ou couleur) ; une image couleur est convertie en niveaux de gris selon le lecteur D2IC. Son panneau droit présente le dossier VIS, la série retenue (motif de fichiers) et l’image de référence. Après choix du dossier, le GUI détecte les séries à partir des noms, affiche pour chacune son nombre d’images et une référence proposée. Une seule série est présélectionnée ; plusieurs séries demandent un choix explicite. Si les noms contiennent plusieurs nombres, le numéro d’acquisition est proposé à partir de la dernière composante numérique variable ; l’expression reste modifiable dans DIC. Le motif reste éditable et la référence peut être choisie dans l’explorateur ou en affichant une image de la table centrale.

La surface centrale est entièrement dédiée aux données : aucun quadrillage décoratif, cadre translucide ou marge interne de scène. Les vues VIS et thermique donnent la plus grande largeur à l’image et gardent la liste dans une colonne étroite ; quand cette surface devient trop étroite, la liste passe sous l’image sans la masquer. ROI et DIC occupent la hauteur disponible ; les champs d’un run terminé restent entièrement visibles dans la hauteur disponible, avec les courbes sous la carte. La zone centrale montre l’image sélectionnée, la référence choisie et la liste exacte des fichiers de la série. Chaque ligne porte une case « Analyse » ; la référence est toujours active. Un compteur indique le nombre d’images actives. Les actions groupées sont « Tout activer », « 1 image sur N » (à partir de la première image), « Désélectionner avant I » et « Désélectionner après I ». I est l’index à partir de 1 dans la table et sa ligne reste inchangée ; cliquer une ligne renseigne I. Les actions avant/après conservent les exclusions existantes. Les images désactivées restent visibles et prévisualisables, mais ne sont pas calculées. La sélection est sauvée dans `config.toml` et figée dans chaque run. Le choix d’une série ou d’une référence actualise l’aperçu immédiatement ; l’enregistrement le conserve dans l’étude. Les images originales restent à leur emplacement. Le parcours DIC/DIC + thermique se choisit dans la barre supérieure. Le nom de l’étude et le dossier des runs sont accessibles dans Job Manager ; la cadence VIS est dans Synchro ; l’origine des temps et l’expression des numéros VIS sont dans Réglages DIC.

### 3.2 ROI / maillage

Les outils **Rectangle** et **Ellipse** tracent un nouveau masque sur la référence VIS, avec **Ajouter** et **Retirer** pour combiner les formes ou creuser des trous. **Annuler la dernière forme** et **Nouveau dessin** corrigent le brouillon. **Créer l’image ROI** écrit un nouveau `roi/drawn_roi_NNN.tif` binaire à la résolution VIS et renseigne le champ Fichier ROI. Le fichier est ensuite traité comme un masque importé ; **Mailler** poursuit le workflow habituel. Le dessin respecte le zoom et ne remplace jamais un fichier existant.

Le panneau droit contient le chemin du fichier ROI TIFF/PNG, la taille des éléments en pixels VIS et l’érosion photométrique, chacun avec sa valeur et son aide `(i)`. L’explorateur permet de choisir le masque. La zone centrale affiche immédiatement le masque sur la VIS de référence, même si le formulaire n’est pas encore enregistré.

Le bouton **Mailler** enregistre la configuration, copie le masque dans l’étude sans modifier le fichier source, construit le maillage DIC et remplace l’aperçu central par sa surimpression sur l’image VIS. Le nombre de nœuds, d’éléments et la taille retenue sont affichés. Une ROI vide, illisible ou de dimensions différentes de la VIS donne une erreur explicite. Modifier le fichier ou la taille rend le maillage précédent périmé et nécessite un nouveau clic sur **Mailler**.

Le champ **Érosion photométrique** (`dic.roi_erosion_px`, défaut `0.0`) règle le rayon d’exclusion des observations aux bords et aux trous, en pixels VIS d’origine même avec binning. Sa note visible précise que le maillage reste inchangé et donne `3.0` comme exemple. Ce réglage est distinct de la morphologie géométrique de la ROI et ne nécessite pas de remaillage. Le calque bleu matérialise les pixels conservés après érosion sur la VIS, au-dessus de la ROI géométrique verte. Les calques ROI, Photométrie et Maillage sont commandés séparément. Le rayon actualise l’aperçu avant sauvegarde sans remailler.

### 3.3 Échelle et Réglages DIC

L'onglet **Échelle** affiche l'image VIS de référence et l'outil de segment ; son panneau droit contient uniquement les paramètres `[scale]`. L'onglet **Réglages DIC** affiche la référence VIS et regroupe dans son panneau droit les paramètres du solveur `[dic]` (hors érosion photométrique, placée dans ROI), du temps VIS `[time]` et du calcul JAX `[runtime]`, séparés en sections. Le masque et la taille de maille restent dans ROI / maillage.

Chaque paramètre est initialisé à sa valeur par défaut documentée ; les aides `(i)` décrivent notamment l'effet de la taille des éléments, de la régularisation et de la qualité des images. Un aperçu du maillage donne nombre de nœuds/éléments et taille approximative en pixels. Tous les réglages du solveur sont présents dans le panneau droit.

L'échelle physique a deux méthodes : **Saisir mm/pixel** ou **Mesurer un segment connu** sur l'image VIS de référence. Pour le segment, les deux points, la longueur connue en mm et le facteur calculé sont visibles avant confirmation. Les deux extrémités se placent par clic puis se retouchent par glisser-déposer ; une loupe montre les pixels VIS d'origine pendant le déplacement. La poignée sélectionnée peut aussi être ajustée au clavier par pas de 1 px (10 px avec Maj). Tout déplacement invalide la confirmation précédente et recalcule l'aperçu mm/px. La valeur initiale `1 mm/pixel` porte toujours l'étiquette **non étalonné** ; tant que l'utilisateur ne confirme pas l'étalonnage, les cartes et exports de longueur restent en pixels. La déformation est affichée comme sans dimension.

**Paramètres du panneau droit :** stride et binning des images, itérations maximales, tolérance, type et force de régularisation, longueur de jauge de déformation, interpolation et calcul CPU/GPU/précision. Chaque contrôle affiche unité, valeur par défaut, valeur du projet et clé TOML. Les paramètres effectivement transmis à D2IC sont consultables avant le lancement.

### 3.4 Thermique / correspondance

**Visible uniquement en parcours DIC + thermique.** La zone centrale place VIS et TH côte à côte ; le panneau droit contient import TH, paires de points, modèle de transformation et résidus.

L'utilisateur choisit le dossier TIFF TH. Les séries sont détectées automatiquement par leurs noms ; s'il y en a plusieurs, il choisit la série à utiliser. Une table affiche chaque acquisition, son aperçu, ses dimensions, son temps et sa case **Fusion**. Comme dans VIS, les commandes permettent de tout activer, de retenir une image sur N, ou de désélectionner avant/après l'image I. Le nombre d'images actives est visible ; les exclusions sont enregistrées dans `config.toml` et figées dans le manifeste du run. Le choix du dossier ou de la série actualise l'aperçu avant l'enregistrement. Une TH désactivée ne peut plus servir à l'interpolation ; si deux trames retenues ne sont pas successives, l'intervalle ne fournit pas de température. La référence `T_ref` reste déterminée au temps de la première VIS, sans image TH de référence choisie indépendamment. L'unité déclarée est affichée ; le texte d'aide rappelle que les TIFF contiennent déjà les températures et que le logiciel n'applique pas de correction d'émissivité.

Deux images côte à côte permettent de créer, déplacer, corriger numériquement ou supprimer des paires de points homologues. Chaque vue garde son zoom ; les coordonnées restent dans les pixels **originaux** de sa caméra. Le modèle affine ou projectif est choisi explicitement. La GUI affiche les résidus **par point en pixels TH**, le RMS et une superposition VIS–TH réglable en opacité. Une zone témoin éloignée des points de calage peut être inspectée avec la même superposition. Un ajustement géométriquement impossible est bloqué et expliqué. Pour un ajustement possible, la **validation manuelle** se fait avec **Valider cette correspondance** après examen : aucun seuil RMS universel ne valide automatiquement la fusion. Une modification des points, du modèle, des dimensions ou du fichier de calibration annule cette validation et l'indique immédiatement.

**Paramètres du panneau droit :** coordonnées des points en table éditable, chargement/enregistrement du JSON de transformation, matrice `H` et empreinte de la calibration approuvée. La GUI rappelle que la VIS est frontale parallèle à une face suffisamment plane ; elle montre la différence de résolution entre VIS et TH sans prétendre les rendre identiques.

### 3.5 Synchro

**Visible uniquement en parcours DIC + thermique.** La zone centrale montre les images VIS et TH de la correspondance sélectionnée, ainsi que la table des correspondances ; le panneau droit contient les cadences VIS et TH, et les paramètres de synchronisation.

L'utilisateur choisit séparément pour VIS et TH la source temporelle : noms de fichiers ou métadonnées. Les temps extraits, leur origine et leurs unités sont prévisualisés. Selon les données, il sélectionne des horloges déjà synchronisées ou repère un événement commun dans les deux séquences. La méthode choisie et le décalage obtenu restent visibles. La table détaille pour chaque instant VIS son numéro d’acquisition, l’image TH exacte ou les **deux images TH successives** utilisées, leurs numéros, leurs temps et le poids d’interpolation. Sélectionner une ligne affiche ces images côte à côte.

La première ligne VIS est marquée **référence thermique `T_ref`**. Les lignes sans TH encadrantes, avec trame TH manquante dans l'intervalle, ou hors plage TH portent une cause explicite. Aucune image VIS n'est créée ni interpolée. Les aperçus lisent les images à leur emplacement d’origine, sans copier les séquences dans le projet.

**Paramètres du panneau droit :** cadences VIS et TH, paramètres d’événement, d’interpolation et de décalage. L’extraction des numéros reste dans les vues de la série concernée. L'interface ne suppose pas qu'un horodatage de deux caméras différentes constitue à lui seul une horloge commune.

### 3.6 Résultats

Avant **Lancer**, un récapitulatif présente : parcours, images VIS réellement sélectionnées, ROI finale et maillage, étalonnage et unité, paramètres DIC, liste TH et couverture des temps VIS, calibration approuvée, champs demandés et estimation du nombre et du volume des fichiers de sortie. Les avertissements demandent une lecture explicite mais ne sont pas transformés en validation scientifique automatique. Les erreurs bloquantes sont regroupées avec liens vers leurs vues.

Pendant le calcul : état, image VIS en cours, progression connue, temps écoulé, journal repliable et action **Annuler**. Le statut ne promet pas un temps restant si l'estimation est instable. Après succès, l'utilisateur choisit un champ, un instant VIS acquis et un run. La carte affiche unité, plage de couleurs, légende et part de données valides. Les champs cinématiques disposent de bornes min/max saisissables, et de raccourcis pour les extrema de l’image courante ou de toute la séquence. Les valeurs absentes portent une trame distincte ; cliquer dessus explique la cause disponible. Une sélection de nœud ou d'élément reste attachée au même point matériel au fil du temps. Les courbes distinguent `T` nodale, température **moyenne de l'élément**, `ΔT`, déplacement et déformation ; elles indiquent les manques sans relier artificiellement les points séparés par des données invalides.

Les nouveaux runs sont affichés sous l’identifiant de leur dossier `YY-MM-DD-Id` (date UTC, index quotidien à partir de 001) ; les runs plus anciens conservent leur nom actuel. Dans Job Manager, chaque run occupe une ligne sélectionnable avec les commandes **Stop**, **Redémarrer** et **Supprimer**. Un bouton **Résultats** ouvre les champs disponibles pendant le calcul, après interruption et à la fin. Les nouveaux instants et historiques sont actualisés sans réinitialiser la sélection ; l’état et la progression restent visibles. Stop est disponible pendant le calcul ; Redémarrer reprend un run arrêté ou échoué depuis son état sauvegardé ; Supprimer retire le dossier du run après confirmation et est indisponible pendant le calcul. La sélection d’une ligne affiche en haut un résumé : identifiant, état, nombre d’images terminées, progression, dernière mise à jour et erreur éventuelle. La vue Résultats affiche le champ sélectionné en entier, sans tableau des valeurs au nœud. Un clic sur la carte ajoute le nœud le plus proche à la sélection ; Maj + clic retire un nœud sélectionné. Les courbes de plusieurs nœuds sont superposées et identifiées par une légende ; les instants invalides coupent la courbe. La liste se rafraîchit tant qu’un calcul est actif, sans empiler de commandes ni réinitialiser le champ choisi. La liste des runs affiche date, parcours, statut, images retenues, unités et configuration figée. Ouvrir un ancien run ne remplace pas les paramètres du projet courant. Une comparaison de deux runs peut juxtaposer leurs paramètres et résultats, avec avertissement si les maillages ou temps ne sont pas comparables.

### 3.7 Export

La zone centrale prévisualise les instants et champs exportés ; le panneau droit contient le choix des champs, unités et destination. L'utilisateur choisit les champs, la série, le dossier et l'unité de longueur. Le formulaire explique **VTU = un instant** et **PVD = série chronologique ouvrable dans ParaView**. En mode couplé, il distingue champs nodaux et moyennes par élément. Le mode millimètre n'est proposé que si l'étalonnage est confirmé ; la géométrie et les déplacements adoptent alors ensemble cette unité. Une prévisualisation donne nombre de VTU, temps VIS inclus, instants couplés exclus faute de TH valide et volume estimé. Les images sources ne sont jamais ajoutées par défaut aux exports.

Après export, la page donne le chemin du PVD, le dossier des VTU, les champs/unités et le manifeste. Une erreur de disque ou de fichier est reliée à l'export concerné ; le run et ses résultats déjà calculés restent consultables.

## 4. Règles transversales de clarté et de contrôle

| Situation | Présentation et action attendues |
| --- | --- |
| Paramètre modifié | Marque « modifications non enregistrées », action Enregistrer et liste des résultats ou vues rendus périmés. |
| ROI modifiée | Aperçu du nouveau masque ; maillage, DIC et fusion courante marqués à recalculer. Les anciens runs restent figés. |
| Correspondance VIS–TH modifiée | Approbation annulée ; nouvelle inspection des résidus requise avant fusion. |
| Temps VIS/TH modifiés | Table de synchronisation recalculée ; fusion courante marquée périmée ; DIC réutilisable si ses entrées sont identiques. |
| Source inaccessible | Chemin absolu, dernière observation et action pour retrouver le fichier ; ne pas remplacer automatiquement par un fichier homonyme. |
| Température invalide | Valeur absente, raison disponible (hors champ, non finie, hors plage temporelle, trame manquante) ; aucune couleur ne doit suggérer une mesure. |
| Unité non confirmée | Mention « pixels VIS » pour les longueurs ; ne pas afficher `1 mm/pixel` comme un étalonnage validé. |
| Action longue | Progression et journal consultables ; double lancement empêché tant que le travail est actif. |

L'icône `(i)` de chaque paramètre ouvre une aide courte, avec une valeur typique lorsqu'elle est pertinente et, si utile, une explication illustrée par la donnée affichée : par exemple, le sens de la taille de maille ou du poids d’interpolation TH. Les termes scientifiques sont conservés, mais définis dans cette aide. Les valeurs numériques s'accompagnent d'unités ; les décimales et séparateurs ne changent pas les données du TOML.

Le navigateur doit être utilisable au clavier pour les formulaires, menus, tables et validations ; les outils Canvas proposent aussi une table de coordonnées éditable pour les points homologues et le segment d'étalonnage. Les états ne sont jamais communiqués uniquement par couleur. Les vues image conservent les coordonnées et valeurs scientifiques lors du zoom, du panoramique et du changement de palette. Une largeur d'écran réduite empile les panneaux sans cacher les paramètres ni les messages d'erreur.

## 5. Couverture des paramètres

La GUI expose les paramètres utiles dans la vue concernée. Les clés historiques conservées pour compatibilité restent dans `config.toml` sans commande visible. La table ci-dessous fixe la couverture du panneau droit.

| Vue | Sections TOML et options à exposer |
| --- | --- |
| VIS | `[project]` mode, nom ; `[paths]` dossier, référence, motif, sortie ; `[time]` source et expression régulière VIS. |
| ROI / maillage | `[roi]` fichier du masque initial ; `[mesh]` taille des éléments. Les autres clés restent dans le TOML pour compatibilité mais ne sont pas des options de cette vue. |
| Échelle | `[scale]` méthode, facteur, segment, longueur, confirmation. |
| Réglages DIC | `[dic]` options du solveur ; `[time]` source et extraction du temps VIS ; `[runtime]` dispositif préféré, repli, précision. |
| Thermique / correspondance | `[thermal]` dossier, motif, unité, source de temps, expression régulière ; `[registration]` fichier et approbation. |
| Synchro | `[time]` cadence VIS, `[thermal]` cadence TH et `[synchronization]` méthode, événements, interpolation TH et décalage. |
| Export | `[output]` VTU, PVD, NPZ, PNG, unité de longueur ; nom de série et destination du run. |

Une option qui dépend du parcours ou d'une méthode choisie peut être désactivée avec une explication. Chaque clé dispose d'un défaut explicite et d'une aide `(i)` ; une valeur typique n'est indiquée que si elle a un sens. Le défaut est défini dans le schéma de D2IC_GUI et doit correspondre à la valeur utilisée pour une nouvelle étude.

| Exemple d'aide `(i)` | Description courte | Défaut affiché | Indication typique |
| --- | --- | --- | --- |
| Taille des éléments | Fixe l'échelle spatiale du maillage DIC en pixels VIS. | Valeur du modèle de nouvelle étude ; unité px. | À choisir selon texture et gradients ; vérifier l'aperçu du maillage. |
| Facteur mm/pixel | Convertit coordonnées et déplacements après confirmation. | `1`, statut « non étalonné ». | Mesurer sur l'image VIS ou saisir un étalonnage connu. |
| Cadence TH | Reconstruit les temps depuis les numéros TH quand cette source est sélectionnée. | Valeur du modèle de nouvelle étude ; unité Hz. | Souvent 50 Hz pour les essais visés, à vérifier dans l'acquisition. |
| Dossier VIS | Désigne les fichiers sources, conservés à leur emplacement. | « à renseigner ». | Aucun chemin typique. |

Une nouvelle clé ajoutée au schéma doit être rattachée à une vue, à un défaut et à une aide courte avant livraison de la fonction correspondante.

## 6. Critères d'acceptation ergonomique

1. Un utilisateur peut créer ou copier une étude depuis la barre supérieure, ouvrir librement les vues depuis la navigation gauche, vérifier les images retenues, charger un fichier ROI puis générer le maillage, lancer le calcul, lire les unités et ouvrir un PVD, sans éditer le TOML.
2. Le même projet peut passer au parcours couplé : l'utilisateur voit les deux résolutions, ajuste et approuve la correspondance, contrôle la table des temps TH et retrouve `T_ref`, `T`, `ΔT` et la moyenne par élément.
3. Chaque paramètre exposé par sa vue possède une valeur courante, un défaut et une aide `(i)` ; les paramètres de compatibilité masqués restent dans le TOML. Après modification, le `config.toml` sauvegardé et le snapshot du run permettent de reproduire le calcul.
4. Une calibration non approuvée, une ROI vide, une source temporelle inexploitable ou une sortie en mm non étalonnée sont refusées avec une cause et une action explicites. Une donnée TH partiellement invalide reste visible comme telle dans les résultats.
5. Modifier la ROI, la correspondance ou la synchronisation marque exactement les résultats concernés comme périmés, sans altérer les runs terminés ni dupliquer les images sources.
6. Sur écran large, la zone centrale et le panneau droit occupent initialement 70 % et 30 % de l'espace restant après la navigation gauche. La poignée les redimensionne en direct, respecte des tailles minimales, se commande au clavier et revient à 70/30 par double clic ; l'image garde ses coordonnées et le calcul ne redémarre pas. Sur écran étroit, navigation et paramètres restent accessibles en tiroirs.
7. La barre latérale gauche associe une icône et un libellé à chaque vue scientifique ; l'entrée active et son état restent identifiables en mode développé ou replié. Les principales tâches restent possibles au clavier ; les états et les valeurs invalides restent compréhensibles sans interpréter uniquement une couleur.

Le volet droit des paramètres est repliable sur ordinateur : une bande de 44 px garde un bouton visible pour le rouvrir. Le réglage de largeur précédent est restauré à l’ouverture et mémorisé localement. Sur écran étroit, le panneau conserve son comportement de volet superposé et le bouton de fermeture existant.


## Suivi de la préparation et autorisation de lancement

Les icônes des volets portent les états suivants : gris pour une étape inactive, rouge pour un prérequis bloquant manquant, vert pour une étape complétée. L’état est décrit dans le titre accessible de chaque icône et reste visible avec la navigation repliée. Les volets thermiques restent gris en DIC seule.

Job Manager présente la préparation et une commande « Étapes à compléter ». Sa fenêtre, ouverte à la demande, affiche seulement les obligations ; chaque entrée permet d’ouvrir le volet concerné. Le lancement reste désactivé tant que les obligations ne sont pas remplies ou que le contrôle échoue. Le clic sur Lancer démarre directement après contrôle et sauvegarde lorsque les obligations sont remplies, sans fenêtre de confirmation ni rappel facultatif. Les contrôles sont répétés côté serveur avant de créer un run.

Une ROI finale non vide, de dimensions VIS cohérentes, et un aperçu de maillage à jour sont obligatoires. La calibration d’échelle reste facultative en pixels et devient obligatoire pour les sorties en mm. En couplage, les sources TH et la correspondance approuvée pour le fichier courant sont obligatoires ; les instants sans couverture TH sont signalés comme avertissements, conformément à la convention des températures absentes. Un dessin ROI non converti en image est signalé comme bloquant dans le formulaire.


Dans ROI / maillage, les limites de la ROI et de la région photométrique ainsi que les arêtes du maillage sont affichées sous forme de tracés vectoriels aux dimensions natives de la VIS. Les arêtes de maillage utilisent une largeur de trait de 0,2 pixel VIS, et les trois calques restent alignés à l’image lors du redimensionnement et du zoom.


Résultats propose le fond « VIS de l’instant choisi » et un curseur d’opacité du champ (0 à 100 %). La carte est affichée en configuration déformée au même instant, avec toutes les couches alignées pendant le zoom ; Sans image conserve cette géométrie. « Carte de résidu » apparaît parmi les champs uniquement si elle est enregistrée et seuls ses instants disponibles sont sélectionnables. Le résidu est transporté vers la configuration déformée pour conserver la correspondance avec le fond courant.


### Préparer puis lancer un job

Dans Job Manager, le bouton global **Préparer le job** crée une ligne même si des prérequis scientifiques manquent. Les erreurs et avertissements sont affichés directement sur cette ligne. Le bouton **Lancer** est sur la même ligne que **Stop**, **Redémarrer**, **Supprimer** et **Résultats** ; il est actif si la préparation ne contient aucune erreur bloquante. Les avertissements ne demandent pas de confirmation. Après correction dans l’étude, une nouvelle préparation crée un nouveau job ; les réglages d’un job déjà préparé restent figés.
