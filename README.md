# D2IC_GUI — définition scientifique

## Objet

`D2IC_GUI` est le projet d'une interface graphique de calcul scientifique pour analyser des séquences d'images d'un essai mécanique. Deux parcours sont proposés dès l'ouverture : **DIC seule**, à partir des images visibles, et **DIC + thermique**, qui associe les champs cinématiques et thermiques aux mêmes points matériels et aux mêmes instants.

L'interface prépare les données, pilote les calculs, contrôle leur qualité, visualise les champs et organise les exports. Elle doit réutiliser `D2IC` pour la DIC 2D par éléments finis avec JAX et `DICTHFusion` pour la correspondance VIS → TH et l'interpolation spatiale bilinéaire. L'interpolation temporelle TH est réalisée dans le GUI aux instants VIS. Le GUI local est implémenté avec un magasin de résultats D2IC par image, décrit dans [RESULT_MODEL.md](docs/RESULT_MODEL.md). La [spécification technique](docs/SPEC_TECHNIQUE.md) fixe les choix de la première application web et son format `config.toml`. La [spécification ergonomique](docs/SPEC_ERGONOMIE.md) décrit la navigation gauche à icônes, repliée par défaut, la zone centrale d’images sans titre redondant et le panneau droit redimensionnable, avec les paramètres et leurs aides `(i)`.

## Dessiner une ROI

Dans **ROI / maillage**, choisir **Rectangle** ou **Ellipse**, puis glisser sur la référence VIS. **Ajouter** combine les formes ; **Retirer** crée des trous. Cliquer sur **Créer l’image ROI**, puis **Mailler**. Le masque est une image TIFF binaire (blanc = ROI, noir = extérieur), aux dimensions originales de la VIS, enregistrée dans `roi/drawn_roi_NNN.tif`. Elle peut être rechargée par le sélecteur de fichier comme les masques importés. Chaque création utilise un nouveau nom.

## Installation et démarrage

Pour créer une **distribution autonome CPU avec OpenCV headless** et Python
embarqué, voir [PACKAGING.md](docs/PACKAGING.md). Depuis la racine :
installer `uv` et le paquet GUI en mode éditable, puis lancer
`python -m D2IC_GUI.build_portable`.
Le script produit un dossier et une archive sous `dist/`, pour le système
sur lequel il est exécuté.

Depuis la racine du workspace parent contenant `im_jax`, `D2IC`,
`DICTHFusion` et `D2IC_GUI`, avec Python 3.12 :

```bash
python -m pip install -e ./im_jax -e ./D2IC -e ./DICTHFusion -e ./D2IC_GUI
python -m D2IC_GUI
```

Cette commande installe les quatre paquets en mode éditable. Les dépendances du GUI sont déclarées dans
`D2IC_GUI/pyproject.toml`.

Ouvrir `http://127.0.0.1:8765` dans le navigateur. Pour rouvrir directement une étude, lancer `python -m D2IC_GUI /chemin/vers/etude`. Le menu **Fichier** regroupe **Nouvelle étude**, **Ouvrir**, **Enregistrer**, **Enregistrer sous**, **Dupliquer l’étude** et **Relocaliser les images**. Pour ouvrir une étude, sélectionner son dossier ou son fichier `config.toml` dans l’explorateur ; un double clic sur le dossier l’ouvre aussi. La zone centrale est sans trame décorative ni marge inutile ; images VIS/TH, ROI et cartes de résultats utilisent au maximum la surface disponible. Le bandeau supérieur est compact ; le nom de l’étude, son état et le parcours restent visibles. **Enregistrer sous** crée une nouvelle étude à partir des réglages courants sans modifier l’originale ; **Dupliquer** crée aussi une copie avec un nom proposé. Dans VIS, chaque image de la séquence peut être activée ou désactivée pour l’analyse. Les commandes permettent de tout activer, de retenir une image sur N, ou de désélectionner les images avant ou après l’image I (index affiché dans la table). La référence reste active. Les exclusions sont enregistrées dans `config.toml` ; chaque run fige les chemins absolus des images effectivement analysées, sans copie des sources. Tous les paramètres scientifiques sont dans le panneau droit et sont sauvegardés dans `config.toml` ; les images VIS et TH restent à leur emplacement. Les exemples de configuration et un générateur de petites séquences sont dans [examples](examples/README.md).

Le GUI affiche la progression de D2IC dans Job Manager, puis les cartes et historiques dans Résultats. La carte est entièrement visible ; plusieurs nœuds peuvent être ajoutés par clic et retirés par Maj + clic. Les champs cinématiques acceptent des bornes de couleur manuelles ou calculées sur l’image courante ou toute la séquence. Les moyennes thermiques élémentaires sont affichées par cellule, avec les cellules invalides masquées. Les chemins des exports ParaView restent accessibles dans Export. L'onglet **Export** permet de créer une archive NPZ globale seulement si elle est nécessaire à un autre outil. Les nouveaux runs utilisent le [magasin de résultats par image](docs/RESULT_MODEL.md), avec reprise après interruption. Pour les conventions et limites physiques, lire les sections ci-dessous.

Les images VIS, TH, ROI, Synchro, Échelle, correspondance et Résultats proposent un zoom par rectangle : activer **Zoom**, puis cliquer pour agrandir autour du pointeur, ou maintenir le clic gauche et tracer la fenêtre souhaitée. **Ctrl + clic** (ou Cmd + clic) dézoome autour du pointeur ; **Réinitialiser la vue** retrouve le cadrage complet. Dans les vues de mesure et de résultats, désactiver **Zoom** pour placer les points ou sélectionner les nœuds. Le grossissement affiché dans chaque cadre est relatif à son cadrage initial. Le zoom reste un réglage d’affichage : les coordonnées physiques et les calques ROI, photométrie et maillage restent alignés. Le retrait d’un nœud sélectionné se fait par **Maj + clic**.

## État de la livraison et limites connues

Le zoom affiche les pixels sources sans lissage du navigateur, y compris les calques ROI, photométrie et maillage. Les images VIS/TH sont chargées à leur résolution native. Ce mode d’affichage ne change pas le choix d’interpolation du solveur DIC.

Dans **ROI / maillage**, **Érosion photométrique** (`dic.roi_erosion_px`) exclut une bande autour des bords et des trous du masque pour le seul critère photométrique. Le rayon est exprimé en pixels VIS d’origine, même avec binning. Saisir `3.0` reproduit le réglage d’`IdentVirual/sequential_dic.toml` ; `0.0`, le défaut, désactive l’érosion. Enregistrer avant de lancer un nouveau run. Le masque géométrique, les nœuds et les éléments restent inchangés ; aucun remaillage n’est nécessaire pour modifier ce rayon. L’aperçu superpose la ROI géométrique en vert et les pixels photométriques retenus en bleu : la bande exclue reste visible entre leurs contours. Les cases ROI, Photométrie et Maillage commandent chaque calque séparément. Modifier le rayon actualise le calque bleu avant sauvegarde, sans régénérer le maillage. Les propositions d’ergonomie générale sont dans [l’analyse ergonomique](docs/ERGONOMIE_REVIEW.md).

L’interface comprend un explorateur local pour choisir les dossiers VIS et TH, l’image de référence, les masques ROI, la calibration et le dossier des runs. Il sert aussi à créer, ouvrir, copier ou relocaliser une étude. La recherche porte sur le dossier affiché et les listes volumineuses sont paginées. Les chemins choisis sont enregistrés dans config.toml après validation ; choisir une référence VIS renseigne aussi son dossier. Les images sources restent à leur emplacement.

Les images VIS peuvent être des TIFF (.tif/.tiff), BMP, PNG ou JPEG (.jpg/.jpeg), en niveaux de gris ou en couleur. Les images couleur sont converties en niveaux de gris par le même lecteur que le calcul D2IC ; les TIFF thermiques restent des températures scalaires sans conversion. Pour BMP, PNG et JPEG, les temps VIS sont extraits des noms de fichiers ; la lecture des horodatages intégrés est actuellement réservée aux TIFF.

Dans **Thermique**, les séries TIFF sont détectées par leurs noms et chaque image peut être activée pour la fusion. Les mêmes commandes de sélection groupée que dans VIS sont disponibles. Les exclusions restent dans `config.toml` ; le run ne fige que les chemins absolus des TH actives, sans copier les fichiers. Une trame désactivée ne peut plus servir de borne temporelle et peut rendre une interpolation indisponible. `T_ref` reste calculée au temps de la première VIS.

Dans l’onglet VIS, seuls le dossier des images, la série et la référence sont configurés. Les séries et une expression de numéro de trame sont proposées depuis les noms des fichiers ; en présence de plusieurs séries, l’utilisateur choisit celle à analyser. L’image affichée dans la table peut être définie comme référence. L’aperçu s’actualise dès le choix de la série, sans enregistrer l’étude ; si les temps sont invalides, les images lisibles restent visibles avec un avertissement. Seul le calcul exige des temps valides.

Chaque nouveau run reçoit un identifiant et un dossier `YY-MM-DD-Id` (date UTC, par exemple `26-10-17-001`), incrémentés dans la journée. Les anciens runs restent accessibles sous leur ancien nom. Dans **Job Manager**, **Préparer le job** crée une ligne avec les erreurs et avertissements détectés. **Lancer** est disponible sur cette ligne dès que la préparation ne comporte aucune erreur ; les avertissements ne bloquent pas. Le job conserve les réglages et sources figés lors de sa préparation. Après correction d’une erreur dans l’étude, préparer un nouveau job. Les commandes **Lancer**, **Stop**, **Redémarrer**, **Supprimer** et **Résultats** sont regroupées sur la ligne ; les résultats deviennent accessibles pendant le calcul dès qu’ils sont disponibles. Sélectionner une ligne affiche son état et sa progression en haut. La suppression demande une confirmation et ne concerne que le dossier de ce run ; les images sources restent en place. Les parcours DIC seule et DIC + thermique sont opérationnels sur les séquences synthétiques fournies : configuration TOML, ROI et maillage, correspondance manuellement approuvée, calcul D2IC, cartes et historiques, exports VTU/PVD. Les fichiers ParaView sont produits pendant le run selon `[output]` ; l'onglet Export affiche leurs chemins et peut créer le NPZ global de compatibilité. La sélection individuelle des champs VTU après un run n'est pas encore proposée. Les cartes de résidu photométrique sont facultatives (`output.compute_residual_map=false` par défaut) car elles augmentent le volume du magasin.

Les tests couvrent le rejeu numérique des deux parcours et les principales frontières de données. Une validation visuelle en navigateur sur écran étroit, les scénarios d'annulation/erreur disque en situation réelle et la mesure de performance sur une longue séquence expérimentale restent à effectuer ; ils figurent dans [ROADMAP_DEV.md](docs/ROADMAP_DEV.md).

## Modèle et grandeurs

- **Entrées communes** : image visible de référence `I₀`, images déformées `Iₖ`, masque de région d'intérêt (ROI), temps d'acquisition `tₖ`, facteur `s_vis` en mm par pixel VIS et paramètres du solveur.
- **Entrées du parcours couplé** : images thermiques `Tⱼ` déjà converties en température, temps d'acquisition `τⱼ` et transformation spatiale `H` estimée entre VIS et TH à partir de points homologues.
- **Sorties DIC** : déplacement nodal `uₖ` en pixels VIS, déplacement en mm si l'échelle est confirmée, déformation de Green–Lagrange `Eₖ`, résidus et indicateurs de qualité.
- **Sorties couplées** : sorties DIC, température `T` et variation `ΔT` aux nœuds, températures moyennes par élément, indices des images TH utilisées et validité de l'interpolation temporelle.

Sur le domaine de référence `Ω₀`, la DIC estime le déplacement `uₖ(X)` par conservation des niveaux de gris :

```text
Iₖ(X + uₖ(X)) ≈ I₀(X),     X ∈ Ω₀.
Fₖ = I + ∇_X uₖ,           Eₖ = ½(FₖᵀFₖ − I).
```

Le déplacement est interpolé sur un maillage de la ROI. Le solveur global minimise un écart photométrique pixel à pixel, avec régularisation optionnelle. La déformation est exprimée dans la configuration visible de référence ; ses composantes suivent `(E11, E22, E12)`, avec `E12` cisaillement tensoriel.

L'étalonnage spatial est un scalaire `s_vis` en mm/pixel de l'image VIS d'origine : `u_mm = s_vis u_px`. Sa valeur initiale est `1`, avec le statut **non étalonné** jusqu'à validation explicite par l'utilisateur. L'étalonnage peut être saisi directement ou calculé en cliquant deux points sur l'image VIS de référence et en donnant leur distance connue en mm : `s_vis = L_mm / ||p₂−p₁||_px`. La DIC conserve ses calculs en pixels ; `E` est sans dimension et ne change pas avec cette conversion uniforme. Aucune valeur en mm ne doit être présentée comme mesurée tant que l'étalonnage n'est pas confirmé.

Dans le parcours couplé, un point matériel `X` occupe la position visible `xₖ = X + uₖ(X)` au temps VIS `tₖ`. La caméra VIS observe la face étudiée de manière frontale parallèle. La face étudiée reste suffisamment plane pendant l'essai. La caméra TH peut avoir une autre résolution et un autre point de vue : des points homologues permettent d'estimer une transformation `H` entre les coordonnées VIS et TH sur cette même surface. Pour chaque image VIS entière :

```text
qₖ = H(xₖ)
si τⱼ = tₖ : T_mat(X,tₖ) = Tⱼ(qₖ)
si τⱼ < tₖ < τⱼ₊₁ : α = (tₖ−τⱼ)/(τⱼ₊₁−τⱼ)
                    T_mat(X,tₖ) = (1−α)Tⱼ(qₖ) + α Tⱼ₊₁(qₖ)
```

Chaque image TH est échantillonnée bilinéairement à `qₖ`, puis les deux températures sont interpolées linéairement dans le temps. Les images TH sont généralement acquises à cadence fixe, autour de 50 Hz ; cette cadence reste un paramètre de l'essai. Les numéros ou temps d'acquisition peuvent être déduits des noms de fichiers ou des métadonnées des images, selon le jeu de données. Les temps de sortie sont toujours ceux des images VIS mesurées ; les images VIS et leurs champs DIC ne sont jamais interpolés temporellement. `ΔT` prend comme référence `T_mat(X,t₀)` au temps de la première image VIS : valeur TH coïncidente ou interpolée entre deux images TH encadrantes. Cet état de référence a `u₀ = 0`, `E₀ = 0` et `ΔT₀ = 0` aux nœuds où `T_mat(X,t₀)` est valide. Les TIFF contiennent déjà des températures ; aucune correction d'émissivité ou de réflexion n'est effectuée dans le logiciel.

La température moyenne d'un élément matériel `e` est la moyenne surfacique de la température interpolée sur sa **surface déformée** au temps VIS considéré :

```text
T̄_e(tₖ) = [∫_{Ω_e(tₖ)} T(x,tₖ) dA] / [∫_{Ω_e(tₖ)} dA]
ΔT̄_e(tₖ) = T̄_e(tₖ) − T̄_e(t₀)
```

Elle est évaluée par quadrature sur le maillage DIC, en transportant chaque point d'intégration avant projection VIS → TH. Un élément dont un point d'intégration thermique est invalide reçoit une moyenne absente (`NaN`), sans moyenne partielle silencieuse.

## Préparation commune : région d'intérêt

L’utilisateur charge un masque binaire TIFF ou PNG défini dans les pixels de l’image VIS de référence. La vue ROI affiche immédiatement ce masque en surimpression sur la VIS, même avant l’enregistrement de l’étude. Le masque doit avoir les mêmes dimensions que la VIS et contenir au moins un pixel actif.

Le panneau droit expose le fichier ROI et la taille d’élément en pixels VIS. Le bouton **Mailler** enregistre une copie du masque dans l’étude, génère le maillage DIC à partir de ce masque puis montre ses éléments sur l’image VIS. Les TIFF gris avec canal alpha sont acceptés : le canal gris définit le masque, comme dans D2IC. Le fichier source n’est pas modifié. Un changement de fichier ROI ou de taille de maille impose de générer à nouveau le maillage. Les outils Rectangle/Ellipse permettent aussi de créer un nouveau masque, selon [Dessiner une ROI](#dessiner-une-roi). Les anciens paramètres morphologiques des fichiers `config.toml` restent lus et appliqués pour compatibilité ; ils ne constituent pas des outils d’édition supplémentaires dans le panneau courant.

## Parcours 1 — DIC seule

1. **Créer un projet DIC** : choisir l'image VIS de référence, la séquence déformée, les temps ou la cadence et le dossier de résultats ; contrôler dimensions et ordre des images.
2. **Préparer la ROI** : charger un masque TIFF/PNG ou créer un masque avec les outils Rectangle/Ellipse, le contrôler sur la VIS, choisir la taille des éléments puis cliquer sur Mailler.
3. **Configurer** : régler taille des éléments, initialisation, solveur, régularisation, critères d'arrêt et étalonnage pixel→mm par saisie ou segment de longueur connue ; visualiser le maillage sur l'image de référence.
4. **Calculer et contrôler** : lancer la DIC séquentielle ; examiner convergence, résidus photométriques, déplacements, déformations et zones non corrélées.
5. **Explorer et exporter** : consulter cartes et historiques de `u` et `E`, puis exporter les données et la séquence ParaView.

Ce parcours fonctionne sans image thermique, transformation VIS → TH ni synchronisation entre caméras.

## Parcours 2 — DIC + thermique

1. **Préparer la DIC** : effectuer les étapes communes du parcours DIC seule, avec la même ROI et le même maillage de référence.
2. **Importer la thermique** : charger les TIFF de température, leurs temps ou leur cadence et leur unité ; contrôler dimensions et ordre des images.
3. **Établir la correspondance VIS–TH** : définir des points homologues ou charger une transformation ; choisir le modèle affine ou projectif adapté à la géométrie observée ; examiner superposition, résidus par point et erreur RMS en pixels TH, puis **valider manuellement** la transformation avant fusion. Aucun seuil RMS universel ne décide à la place de l'utilisateur. Les différences de résolution sont prises en compte par `H`.
4. **Construire le temps commun** : prendre chaque image VIS entière comme instant de sortie ; extraire les numéros ou horodatages des noms de fichiers ou des métadonnées, afficher la source retenue, puis utiliser les temps ou un événement commun pour placer les images TH sur le même axe temporel. Afficher pour chaque instant VIS les images TH encadrantes et leur écart.
5. **Fusionner et contrôler** : interpoler linéairement les images TH dans le temps aux instants VIS, puis échantillonner `T` aux points matériels transportés par `u`. Calculer `ΔT` ; signaler les instants non encadrés, les numéros TH manquants, les points hors image TH ou occultés. Les images VIS et leurs champs DIC ne sont jamais interpolés dans le temps.
6. **Explorer et exporter** : afficher `u`, `E`, `T` et `ΔT`, tracer leurs historiques en un point, un élément ou une zone, puis exporter les champs couplés et leurs métadonnées.

## Exports numériques et ParaView

Les deux parcours proposent une exportation **VTU/PVD** directement ouvrable dans ParaView. Un fichier `VTU` contient le maillage et les champs d'un instant ; un fichier `PVD` référence la série ordonnée de VTU avec leurs temps en secondes. L'utilisateur choisit le dossier, le nom de la série et les champs exportés.

| Parcours | Champs proposés dans les VTU | Collection PVD |
| --- | --- | --- |
| DIC seule | Déplacement `u`, `E11`, `E22`, `E12` et indicateurs DIC disponibles ; coordonnées et déplacements en mm si l'étalonnage est confirmé et cette unité choisie | Série DIC aux temps VIS |
| DIC + thermique | Champs DIC ; `T`, `ΔT` et validité aux nœuds ; moyennes `T̄_e` et `ΔT̄_e` en données élémentaires | Série couplée aux temps VIS disposant d'une température valide |

La géométrie exportée reste dans le repère visible de référence pour comparer les champs matériels ; ses coordonnées et le déplacement sont exprimés ensemble en pixels ou en mm après étalonnage confirmé, pour que la déformation affichée dans ParaView reste cohérente. Les données nodales et élémentaires sont identifiées explicitement. Les températures nodales sont associées aux mêmes points matériels que les champs DIC ; les moyennes sont associées aux éléments matériels. Les temps VIS, les images TH encadrantes, les poids d'interpolation, les unités, les conventions de coordonnées et le masque final sont enregistrés dans des métadonnées accompagnant les VTU/PVD. Un instant VIS sans température interpolable ne produit pas de VTU couplé.

Le GUI écrit les champs thermiques dans les VTU couplés et construit leur série PVD aux temps VIS valides. Les résultats DIC sont conservés par image ; une archive NPZ globale peut être créée à la demande.

## Conventions et limites physiques

- Images indexées `(y, x)` ; coordonnées géométriques `(x, y)` aux centres des pixels, origine en haut à gauche.
- Déplacement nodal de forme `(Nn, 2)` en pixels VIS d'origine ; facteur `s_vis` en mm/pixel, initialement `1` mais non confirmé ; déformation `(E11, E22, E12)` sans dimension ; temps en secondes.
- Un binning, recadrage ou redimensionnement impose d'adapter la ROI, le maillage et la transformation `H`.
- La VIS est frontale parallèle à la face étudiée ; la TH peut avoir une résolution et une orientation différentes. `H` est déterminée par correspondances sur cette face et suppose sa géométrie relative stable. La face est supposée suffisamment plane pendant l'essai ; une sortie de ce cadre, une occlusion ou un changement de cadrage invalide la correspondance.
- Chaque résultat couplé est daté par une image VIS réelle. Une température n'est disponible que si une image TH coïncide avec cet instant ou si deux images TH successives l'encadrent. La cadence TH nominale est généralement de 50 Hz ; les numéros d'images manquants doivent être détectés. Il n'y a pas d'extrapolation temporelle ; les valeurs hors image TH sont absentes (`NaN`).
- Les TIFF contiennent directement des températures ; corrections d'émissivité, de réflexion et autres traitements radiométriques sont effectués en amont. L'unité du fichier, notamment °C, doit être déclarée et vérifiée.
- Une contrainte mécanique ou une source thermique ne se déduit pas de la seule juxtaposition de `u`, `E` et `T` sans modèle physique supplémentaire.

## Points scientifiques à affiner

Les hypothèses fixées sont : face suffisamment plane pendant l'essai, VIS frontale parallèle à cette face, transformation VIS–TH par points homologues, TH à cadence fixe généralement 50 Hz, interpolation **des températures TH seulement** entre deux images successives aux temps VIS, TIFF déjà exprimés en température et référence `ΔT` au premier temps VIS.

| Sujet | Proposition pour la première version | Décision restante |
| --- | --- | --- |
| Correspondance spatiale | Essayer affine et projectif, afficher les résidus par point et le RMS ; l'utilisateur valide la transformation après inspection. | Comment présenter clairement les zones où les points de contrôle sont peu représentatifs ? |
| Mouvement entre deux TH | Interpoler les températures à la même coordonnée caméra `qₖ` calculée au temps VIS. | Le mouvement à 50 Hz est-il négligeable à l'échelle d'un pixel TH, y compris dans les essais rapides ? |
| Qualité des mesures | Afficher séparément résidu DIC, erreur de correspondance VIS–TH et validité des températures. | Quels critères DIC doivent bloquer un résultat et lesquels ne produisent qu'un avertissement ? |

## Critères de validation

Le parcours DIC seul doit retrouver une translation rigide connue sans déformation parasite et convertir correctement un déplacement avec un étalonnage mm/pixel connu. Un masque fichier de dimensions VIS connues doit produire le maillage attendu et son aperçu superposé. Les VTU/PVD doivent être lisibles dans ParaView avec les bons champs et temps. Le parcours couplé doit retrouver une température synthétique via une transformation VIS → TH connue et une évolution thermique linéaire interpolée aux temps VIS ; il doit conserver un champ uniforme, retrouver sa moyenne par élément et marquer comme absents les temps non encadrés ou les points TH invalides. Un cas expérimental doit documenter les erreurs de correspondance spatiale, les intervalles TH et les paramètres DIC.

## Modules existants à intégrer

- `../D2IC/` : maillage, solveurs JAX, pipeline DIC séquentiel et export ParaView DIC.
- `../DICTHFusion/` : ajustement VIS → TH à partir de correspondances, interpolation bilinéaire, transformation JSON et interface existante.
- `../img/DP600L2/` : scripts et données expérimentales pouvant servir de validation, sans devenir une dépendance obligatoire.

## Développement du GUI

La [feuille de route](docs/ROADMAP_DEV.md) suit les jalons et leurs preuves de validation. Le [routage des tâches de recherche](../.agents/skills/research-task-routing/SKILL.md) distingue implémentation locale et décision scientifique ou architecturale. Les rôles disponibles sont définis dans [`../.codex/agents/`](../.codex/agents/) ; leur configuration fait autorité pour les modèles employés.

Le worker charge le paquet local `im_jax` avant D2IC quand le dépôt source est utilisé : l’interpolation VIS cubique par défaut reste disponible même si le paquet n’est pas installé en mode éditable. Un run échoué pour cette raison peut être relancé avec **Redémarrer** depuis Job Manager ; sa configuration figée est conservée.


Les paramètres et les contrôles du panneau sont définis dans [`parameters.toml`](src/D2IC_GUI/parameters.toml). Voir [`CONFIG_SCHEMA.md`](docs/CONFIG_SCHEMA.md) pour ajouter une entrée (nom, clé, type, défaut, choix, aide, onglet), puis redémarrer le GUI. Les valeurs propres à chaque étude restent dans son `config.toml`.

## Structure du module

```text
D2IC_GUI/
├── src/D2IC_GUI/       paquet Python et actifs de l’interface
│   ├── examples/       générateur d’étude synthétique importable
│   └── static/         HTML, CSS et JavaScript
├── docs/               définition scientifique, spécifications et contrats
├── tests/              tests Python et JavaScript
├── examples/           configurations et générateur de compatibilité
├── pyproject.toml
└── README.md
```

Les commandes de construction sont des modules du paquet :
`python -m D2IC_GUI.build_portable` ou `python -m D2IC_GUI.build_windows`.
