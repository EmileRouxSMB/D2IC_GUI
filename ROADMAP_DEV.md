# D2IC_GUI — feuille de route de développement

**État au 17 octobre 2026 :** les deux parcours du GUI, le calcul D2IC, la fusion TH et les exports ParaView sont implémentés et rejoués sur une étude synthétique. Les nouveaux runs utilisent le magasin D2IC par image ; l’archive NPZ globale est facultative. La revue visuelle en navigateur et plusieurs scénarios d’erreur restent à vérifier avant de clôturer tous les jalons.

## Cible et ordre

La première livraison utilisable est **DIC seule** : ouvrir une étude, sélectionner les images VIS, préparer la ROI, lancer D2IC, examiner les champs et ouvrir une série PVD/VTU dans ParaView. La livraison complète ajoute la **thermique** avec correspondance VIS–TH approuvée, synchronisation aux instants VIS, températures nodales et moyennes par élément. Les images sources restent à leur emplacement ; chaque run fige sa configuration et leur chemin absolu.

| Jalon | Dépend de | Résultat utilisable | État |
| --- | --- | --- | --- |
| M0 — Contrats et exemple minimal | — | Un jeu synthétique court, un schéma TOML versionné et les contrats des adaptateurs. | vérifié |
| M1 — Projet et coque web | M0 | Étude ouvrable et sauvegardable ; navigation gauche, vues et panneau redimensionnable. | en cours |
| M2 — Images VIS, ROI et maillage | M1 | Séquence VIS contrôlée, masque final reproductible et maillage prévisualisé. | en cours |
| M3 — Parcours DIC seule | M2 | Calcul, contrôle des champs et export PVD/VTU aux temps VIS. **Premier livrable utilisable.** | en cours |
| M4 — Correspondance et temps TH | M1 et données VIS de M2 | Transformation approuvée et table TH/VIS inspectable, sans calcul de fusion. | en cours |
| M5 — Fusion thermique et export | M3 et M4 | `T`, `ΔT`, moyennes élémentaires et série ParaView couplée. | vérifié |
| M6 — Validation intégrée | M3 et M5 | Deux études rejouables, contrôles de robustesse et documentation de livraison. | en cours |

Les jalons suivent cet ordre par défaut pour limiter les intégrations inachevées. M4 peut être développé après M2 sans attendre la fin de M3 si ses fichiers et tests restent indépendants. Un jalon ne passe à `vérifié` que lorsque ses critères sont constatés dans l'application et notés dans le journal de fin de document.

## M0 — Contrats et exemple minimal

**Objectif :** fixer les petites interfaces entre GUI, D2IC et DICTHFusion avant de construire les vues.

| Ticket | Travail borné | Preuve attendue | État |
| --- | --- | --- | --- |
| M0.1 | Inventorier les points d'appel existants : configuration et pipeline séquentiel D2IC, `paths.mask_path`, lecture des sorties NPZ, export VTU/PVD et JSON de transformation DICTHFusion. | Note courte des entrées/sorties, dimensions, unités et limites, avec chemins des fonctions réelles. | vérifié |
| M0.2 | Définir le schéma versionné de `config.toml`, ses défauts et le catalogue des aides `(i)` pour **chaque** paramètre exposé. Séparer paramètres d'étude et préférences d'affichage. | Exemple TOML relu par `tomllib`, table clé → contrôle → défaut → unité → aide ; valeurs absentes traitées explicitement. | vérifié |
| M0.3 | Construire deux petites séquences synthétiques : VIS avec translation connue et TH avec champ constant puis évolution linéaire. Prévoir une paire VIS/TH de résolutions différentes et des fichiers temporels avec trame manquante. | Générateur ou fixtures légers et résultats attendus documentés ; aucun jeu expérimental massif requis. | vérifié |

**Sortie du jalon :** les conventions `(x, y)` VIS/TH, temps en secondes, unité thermique, masque final, état initial et échelle sont écrites dans les contrats. Les décisions encore ouvertes (par exemple horloges indépendantes ou seuils de qualité DIC) sont consignées sans inventer une règle universelle.

## M1 — Projet et coque web

**Objectif :** disposer d'une étude locale stable et d'une interface navigable avant d'y brancher le calcul.

| Ticket | Travail borné | Preuve attendue | État |
| --- | --- | --- | --- |
| M1.1 | Créer le paquet Python, le serveur local `127.0.0.1`, le chargement des pages et un démarrage documenté. | La page s'ouvre depuis une commande reproductible sur une étude exemple. | vérifié |
| M1.2 | Implémenter ouverture, nouvelle étude, sauvegarde atomique et copie d'étude. La copie conserve les mêmes cibles d'images, copie les petits masques/calibrations, et exclut images et runs. | Réouverture du TOML, chemin absolu des images inchangé, absence de duplication des séquences ; message clair si une source manque. | vérifié |
| M1.3 | Créer barre supérieure, navigation verticale à icônes, zone centrale et panneau droit 70/30 avec poignée de redimensionnement en direct. Préserver zoom/sélection et proposer l'accès aux paramètres sur écran étroit. | Démonstration grand écran et écran étroit ; souris, clavier et toucher quand disponible ; aucun calcul lancé par le redimensionnement. | en cours |
| M1.4 | Générer les contrôles depuis le schéma, avec valeur courante, défaut, unité, aide `(i)`, validation et indicateur de modification non enregistrée. | Toutes les clés du schéma ont un contrôle ; une valeur invalide renvoie au champ et n'altère pas le dernier TOML valide. | en cours |

**Sortie du jalon :** créer, copier, modifier et rouvrir une étude sans perdre ses paramètres. Les vues restent librement accessibles même si certaines entrées scientifiques manquent.

## M2 — Images VIS, ROI et maillage

**Objectif :** rendre l'entrée mécanique visible et vérifiable avant toute résolution DIC.

| Ticket | Travail borné | Preuve attendue | État |
| --- | --- | --- | --- |
| M2.1 | Lire la séquence VIS sans la copier, choisir référence et motif, trier par temps, extraire les numéros du nom ou les horodatages des métadonnées selon le projet. | Table des chemins absolus, dimensions, temps et source des temps ; doublons, manques et ordre non monotone signalés. | vérifié |
| M2.2 | Charger un masque VIS TIFF/PNG depuis un fichier et l’afficher sur la référence VIS avant sauvegarde. | Test sur petit masque connu : dimensions et masque vide contrôlés, aperçu immédiat sur la VIS. | en cours |
| M2.3 | Sur Mailler, enregistrer le masque source sans l’altérer et produire le maillage depuis la copie finale, avec aperçu superposé. | Changer le masque modifie ou invalide le maillage ; aucune ROI périmée ne peut servir au calcul. | en cours |

**Sortie du jalon :** une étude possède une liste VIS exacte, un temps de référence et un maillage cohérent avec la ROI visible. La composition d’aperçu n’altère jamais les images VIS ni le masque source.

## M3 — Parcours DIC seule

**Objectif :** livrer un premier outil scientifique complet, indépendant des données thermiques.

| Ticket | Travail borné | Preuve attendue | État |
| --- | --- | --- | --- |
| M3.1 | Traduire `config.toml` du GUI en configuration D2IC résolue, en pointant vers les images VIS originales et le masque final figé dans le run. | Test d'adaptateur sur l'étude synthétique ; aucun chemin d'image n'est réécrit vers une copie. | vérifié |
| M3.2 | Lancer D2IC dans un processus de travail, suivre progression, journal, erreur et annulation ; figer configuration et manifeste du run. | Run réussi puis rouvert ; un run interrompu n'est pas présenté comme terminé ; double lancement évité. | en cours |
| M3.3 | Afficher déplacements, déformations, résidus et historiques aux **images VIS acquises**. Ajouter l'état de référence `u₀ = 0`, `E₀ = 0` quand nécessaire. | Translation synthétique retrouvée, déformation proche de zéro et unités correctes. | en cours |
| M3.4 | Confirmer l'échelle par facteur ou segment, convertir coordonnées et déplacements ensemble pour l'affichage/export mm ; exporter VTU par instant et PVD daté en secondes VIS. | Avant confirmation, longueur en px ; après confirmation, translation et géométrie cohérentes en mm ; `meshio` relit les champs et le PVD pointe vers les bons VTU. | en cours |

**Porte de revue :** vérifier repère VIS complet après binning/recadrage, compatibilité D2IC, champs nodaux, unités et reprise d'un ancien run. M3 est le **MVP DIC seule** et peut être utilisé pendant le développement thermique.

## M4 — Correspondance VIS–TH et temps commun

**Objectif :** rendre chaque décision de fusion inspectable avant de calculer une température matérielle.

| Ticket | Travail borné | Preuve attendue | État |
| --- | --- | --- | --- |
| M4.1 | Lire les TIFF TH comme températures, sans correction radiométrique, et afficher valeurs/unités et dimensions. Choisir les temps TH par nom ou métadonnées. | Une image TH connue est affichée avec sa température réelle ; cadence usuelle 50 Hz modifiable. | vérifié |
| M4.2 | Reprendre l'ajustement affine/projectif de DICTHFusion depuis des points homologues VIS/TH ; montrer résidus par point, RMS et superposition sur les deux résolutions. | Transformation synthétique connue retrouvée ; points dégénérés refusés ; l'aperçu ne modifie pas les TIFF. | en cours |
| M4.3 | Enregistrer **l'approbation manuelle** liée à la calibration exacte ; invalider cette approbation après changement de points, de modèle, de dimensions ou de fichier. | Fusion bloquée sans approbation ; modification de calibration demande une nouvelle validation, sans seuil RMS universel. | vérifié |
| M4.4 | Construire l'axe commun aux instants VIS entiers, avec horloges déjà communes ou événement repéré dans chaque série ; montrer TH exacte ou deux TH successives, temps et poids. | Table vérifiée sur coïncidence, interpolation, trame TH manquante, temps hors plage et deux horloges non alignées ; aucune extrapolation. | vérifié |

**Porte de revue :** confirmer le sens VIS → TH de `H`, les coordonnées originales malgré résolutions distinctes, la provenance des temps et le choix explicite du décalage entre horloges. L'approbation d'une transformation ne remplace pas la vérification de sa stabilité pendant l'essai.

## M5 — Fusion thermique et export couplé

**Objectif :** associer température et mécanique aux mêmes points matériels et aux temps VIS acquis.

| Ticket | Travail borné | Preuve attendue | État |
| --- | --- | --- | --- |
| M5.1 | Transporter les nœuds `X + uₖ`, projeter VIS → TH, échantillonner bilinéairement la ou les TH et interpoler linéairement **la température seulement** entre deux TH successives. | Champ uniforme conservé ; loi temporelle linéaire retrouvée ; hors champ, non fini, non encadré et trame manquante restent invalides. | vérifié |
| M5.2 | Définir `T_ref` au premier temps VIS, depuis une TH coïncidente ou deux TH encadrantes, puis `ΔT` au même point matériel ; exposer validité et causes d'absence. | `ΔT₀ = 0` là où la référence est valide ; une référence absente n'est pas remplacée par une autre image. | vérifié |
| M5.3 | Calculer la température moyenne par élément sur sa surface **déformée** par quadrature Q4/T3, et sa variation depuis la moyenne élémentaire initiale. | Champ constant reproduit ; un seul point de quadrature invalide rend l'élément invalide ; pas de moyenne partielle silencieuse. | vérifié |
| M5.4 | Ajouter `Temperature`, `Delta_temperature`, validités en `PointData`, moyennes en `CellData`, puis écrire VTU/PVD couplés aux temps VIS valides. | Lecture avec `meshio` des formes/champs/unités ; ParaView ouvre la série ; les images sources ne sont pas ajoutées aux exports. | vérifié |

**Porte de revue :** examiner les équations, la référence temporelle, les deux interpolations, la géométrie courante, la gestion des `NaN` et la cohérence des unités ParaView. Aucun résultat couplé n'est déclaré valide sur un instant VIS dépourvu de TH interpolable.

## M6 — Validation intégrée et livraison

| Ticket | Travail borné | Preuve attendue | État |
| --- | --- | --- | --- |
| M6.1 | Rejouer de zéro une étude DIC seule et une étude DIC + TH à partir de leurs `config.toml` et images externes, puis rouvrir les runs. | Manifeste des chemins absolus, temps, versions, masque et son SHA-256, calibration, poids TH et unités ; résultats identiques à tolérance numérique définie. | vérifié |
| M6.2 | Exercer les flux d'erreur : source manquante ou modifiée, ROI vide, temps non monotone, calibration périmée, disque d'export indisponible, annulation du calcul. | Message avec cause et action ; anciens runs intacts ; pas de résultat partiel présenté comme terminé. | en cours |
| M6.3 | Vérifier navigation gauche, panneau redimensionnable, formulaire complet avec aides `(i)`, clavier, écran étroit et conservation de zoom/sélection. | Parcours manuel documenté ou test navigateur ciblé sur les interactions critiques. | en cours |
| M6.4 | Compléter exemples, commandes d'installation/démarrage, `memory.md`, limites physiques et tableau des fonctions réellement livrées. | Un chercheur peut reprendre les deux exemples et ouvrir les PVD sans deviner un réglage caché. | vérifié |

**Sortie du jalon :** GUI utilisable sur les deux parcours, tests ciblés verts, revue des écarts aux trois spécifications et limites connues consignées. Toute option annoncée mais absente est indiquée explicitement dans la documentation de livraison.

## Règles de suivi et d'économie de tokens

- **États des tickets et jalons :** `à faire`, `en cours`, `vérifié`, `bloqué`. `bloqué` exige une cause précise ; une difficulté ou un test à écrire ne suffit pas. L'orchestrateur ne valide pas un jalon sur la seule déclaration d'un sous-agent.
- **Responsabilités :** `gui_orchestrator` découpe et intègre ; `gui_scout` (Luna bas) répond à une question de lecture ; `gui_builder` (Luna moyen) réalise un ticket simple ; `gui_reviewer` (Sol haut) relit les changements aux portes de revue scientifique, de chemins, de processus ou d'export. Les profils sont dans [`../.codex/agents/`](../.codex/agents/memory.md). Le modèle du fil principal reste celui choisi par l'utilisateur.
- **Contexte transmis :** identifiant du ticket, résultat attendu, fichiers/sections précis, invariant critique et test demandé. Lire la section utile d'une spécification, pas les trois documents en entier. Une tâche courte ou dépendante reste au responsable courant ; ne pas mettre deux agents sur les mêmes fichiers.
- **Vérification :** commencer par le test ciblé et le cas synthétique interprétable. Étendre les tests seulement si un risque concret apparaît. Les changements d'UI se contrôlent sur l'écran concerné ; les calculs sont comparés à une valeur attendue. Noter commande, résultat et limite.
- **Frontières Git :** `D2IC` et `DICTHFusion` sont des dépôts distincts. Un ticket qui les modifie nomme cette frontière, limite la modification à l'API nécessaire et teste l'adaptateur GUI. Ne pas absorber leurs changements indépendants dans une livraison GUI.

## Prochain travail

**Porte M6 restante :** vérifier les interactions ROI, correspondance, panneau redimensionnable et écran étroit dans un navigateur ; exercer annulation/reprise du worker et erreurs disque avec un run réel ; mesurer mémoire et temps sur une séquence expérimentale longue. Les anciens runs NPZ restent lisibles.

## Journal de validation

- **2026-11-06 — ZIP Windows x64 CPU assemblé depuis Linux** : `build_windows.py`, lanceur Windows générable hors Windows, CPython/wheels Windows, OpenCV headless, Gmsh et runtime Microsoft C++ placé près de python.exe. Archive `dist/D2IC_GUI-cpu-windows-amd64.zip` : 253,8 Mio, 768,5 Mio décompressés. Preuves : 10 tests packaging ciblés réussis ; 322 binaires PE x64 et tags de wheels contrôlés, absence de plugins GPU et de bibliothèques Linux, intégrité CRC du ZIP valide, présence des DLL CRT et du helper scientifique vérifiée. Livré : `Verifier_D2IC_GUI.cmd` pour imports/JIT/Gmsh/worker cubique et rapport Windows. Limite explicite : aucun binaire Windows exécuté dans cet environnement Linux ; `validated_on_windows` reste `false` jusqu’à la vérification sur la cible.

- **2026-11-06 — Distribution autonome CPU/headless** : `build_portable.py`, paquet GUI `pyproject.toml`, lanceur `desktop.py`, adaptation du suivi/arrêt des workers Windows/POSIX et guide `PACKAGING.md`. Sources scientifiques copiées temporairement, métadonnées OpenCV remplacées par headless uniquement dans ces copies, CPython 3.12 embarqué, dépendances binaires CPU, nettoyage conservant licences et métadonnées, copie Gmsh native Linux, relocalisation et archivage. Preuves : 72 tests ciblés GUI/packaging/lanceur réussis ; 11 tests packaging/lanceur réexécutés après retrait de terminfo pour les volumes insensibles à la casse. Assemblage réel sous `dist/D2IC_GUI-cpu-linux-x86_64` avec contrôle JAX CPU/JIT, OpenCV sans GUI, Gmsh, worker cubique sur images identiques (déplacement nul), 11 liens symboliques internes, lancement hors dépôt et HTTP 200 des page/schéma/actifs. Taille décompressée mesurée : 1 041,5 Mio. Limite : validation Linux x86_64 seulement ; distributions Windows/macOS et ancienneté minimale de glibc à vérifier sur les cibles.

- **2026-11-06 — Zoom sans lissage** : images centrales et pile ROI rendues en pixels (`image-rendering: pixelated`, puis `crisp-edges` si pris en charge), version CSS actualisée. Les aperçus VIS/TH conservent leur pleine résolution ; aucune modification des données ni de l’interpolation DIC. Vérification : contrôle des URL d’images `full=1`, des actifs HTTP et régression Node du zoom. Limite : rendu graphique à confirmer dans le navigateur utilisateur.

- **2026-11-06 — Zoom commun des vues d’images** : `static/image_zoom.js` apporte zoom par clic/rectangle, Ctrl/Cmd + clic pour dézoomer, indicateur local et Réinitialiser la vue. Raccordement des vues VIS, TH, ROI, Synchro, Échelle, correspondance, réglages DIC et Résultats ; transformations communes aux calques ROI, conversions en pixels natifs pour points/segment/nœuds, centre conservé au redimensionnement. Maj + clic retire désormais un nœud. Preuves : `node --test D2IC_GUI/tests/test_image_zoom.cjs` → 9 tests réussis (maths, événements, chargement tardif, resize et coordonnées) ; syntaxe des deux scripts valide ; `PYTHONPATH=D2IC/src:im_jax:. python -m pytest -q D2IC_GUI/tests/test_project_server.py` → 61 tests réussis ; actifs HTTP 200 et ordre de chargement du module contrôlé. Revue des conversions sans défaut restant identifié. Limite : tests de DOM simulé, inspection visuelle en navigateur restante.

- **2026-11-06 — ROI : réglage et calque photométriques** : déplacement de l’érosion dans ROI / maillage ; calque bleu indépendant sur la VIS, actualisé au changement et à la réinitialisation du rayon sans remaillage. La route de calque réutilise la morphologie, le retrait des îlots, le binning et l’érosion D2IC ; le bouton Mailler conserve la morphologie géométrique enregistrée pour rester cohérent avec l’aperçu. Preuves : `PYTHONPATH=D2IC/src:im_jax:. python -m pytest -q D2IC_GUI/tests/test_project_server.py D2IC/tests/test_correlation_roi.py` → 71 tests réussis, dont 18 comparaisons pixel à pixel avec le masque final enregistré (trous, îlots, morphologie et binning 1/2/3) ; syntaxe JS valide et contrôle Node du routage ROI, des changements/réinitialisation de rayon et de l’absence d’accès au maillage. Limite : validation visuelle navigateur non réalisée.

- **2026-11-06 — Réglage d’érosion photométrique et analyse ergonomique** : ajout de `dic.roi_erosion_px` au schéma GUI, aide visible et transmission au snapshot D2IC ; exemples, schéma et mémoires documentés. Analyse priorisée dans `ERGONOMIE_REVIEW.md`. Preuve : `PYTHONPATH=D2IC/src:im_jax:. python -m pytest -q D2IC_GUI/tests/test_project_server.py D2IC/tests/test_correlation_roi.py` → 53 tests réussis ; `node --check D2IC_GUI/static/app.js` → OK. Le test HTTP conserve exactement masque final et calque maillage après passage à 3 px ; le vrai worker conserve le masque géométrique et écrit le masque photométrique érodé. Revue scientifique ciblée sans défaut relevé. Limite : vérification visuelle navigateur non réalisée ; le calque photométrique reste une proposition.

À chaque ticket terminé, ajouter une ligne courte avec **date, ticket, fichiers livrés, commande ou observation de vérification, résultat et limite restante**. Au moment de clôturer un jalon, l'orchestrateur rassemble ces preuves et met son état à jour dans le tableau d'ordre. M0 et le noyau scientifique M5 sont vérifiés ; les autres jalons restent ouverts pour les preuves ergonomiques ou les flux d’erreur.

- **2026-10-17 — M3/M6, modèle de résultats et reprise** : magasin D2IC versionné par image, checkpoint après exports, NPZ de compatibilité atomique, lecture GUI des champs/historiques, progression et reprise de run, cache des aperçus, relocalisation contrôlée VIS/TH. Preuve : `PYTHONPATH=D2IC/src:. pytest -q D2IC/tests/test_result_store.py D2IC_GUI/tests/test_project_server.py D2IC_GUI/tests/test_integration_studies.py` → 16 tests réussis ; `node --check D2IC_GUI/static/app.js` → OK. Limite : une étude relocalisée peut ouvrir les anciens résultats mais la reprise des anciens calculs exige toujours leurs sources et leur empreinte originales ; les performances sur de longues séquences réelles restent à mesurer.

- **2026-10-17 — modèle D2IC sans archive globale automatique** : `output.export_legacy_npz` vaut `true` par défaut dans D2IC et `false` dans les nouveaux runs GUI. `worker.py` lit `dic_store` pour la provenance, le maillage et la fusion ; l'archive de compatibilité est créée sur demande depuis Export. La ROI importée n'est plus réécrite hors du projet et la calibration approuvée restitue ses points/résidus. Preuve : `PYTHONPATH=D2IC/src:. python -m pytest -q D2IC_GUI/tests D2IC/tests/test_result_store.py D2IC/tests/test_sequence_result_resume.py D2IC/tests/test_sequence_mask_path.py` → 34 tests réussis ; `node --check D2IC_GUI/static/app.js` → OK. Limite : validation visuelle navigateur et longues séquences réelles non réalisées ici.

- **2026-10-17 — M1, explorateur local** : navigation des dossiers et fichiers, filtres VIS/TH/ROI/calibration/études, recherche et pagination ; raccordement aux chemins TOML et aux actions nouvelle/ouvrir/copier/relocaliser. Preuve : PYTHONPATH=D2IC/src:. python -m pytest -q D2IC_GUI/tests/test_project_server.py → 11 tests réussis ; ensemble de régression GUI/D2IC → 35 tests réussis ; node --check D2IC_GUI/static/app.js → OK. Limite : interaction visuelle en navigateur encore à vérifier.

- **2026-10-17 — M2.1, ouverture VIS par étapes** : panneau VIS limité au dossier, à la série et à la référence ; détection des séries par noms, séparation des caméras et sélection de la référence depuis l’image affichée. Les paramètres de temps VIS passent dans DIC et la destination des runs dans Résultats. Preuve : 38 tests de régression réussis pour GUI/D2IC et syntaxe JS validée. Limite : revue visuelle navigateur à faire.\n
- **2026-10-17 — M2.1, formats VIS** : TIFF, BMP, PNG et JPEG (gris/couleur) décodés par le même lecteur que D2IC pour l’inventaire, l’aperçu, la ROI, la calibration, la relocalisation et le run. TIFF TH gardés scalaires. Preuve : six cas de formats et protection TH dans test_project_server.py ; 51 tests de régression GUI/D2IC réussis, syntaxe JS valide.

- **2026-10-17 — M2.1, aperçu VIS immédiat** : lecture de la série selon les valeurs courantes du formulaire, accès image borné au dossier VIS sélectionné avant sauvegarde, navigation dans la table ; avertissement si les temps sont invalides. Preuve : 53 tests GUI/D2IC réussis et syntaxe JS valide. Limite : interaction visuelle en navigateur à vérifier.

- **2026-10-17 — M2.2/M2.3, ROI fichier et Mailler** : panneau ROI limité au fichier et à la taille des éléments ; aperçu composé VIS + masque avant sauvegarde ; bouton Mailler, copie interne du masque, génération Gmsh depuis un thread serveur et affichage VIS + maillage. Preuve : 57 tests GUI/D2IC réussis et syntaxe JS valide ; le changement du masque source invalide l’aperçu du maillage. Limite : revue visuelle en navigateur à effectuer.

- **2026-10-17 — M2.2/M2.3, TIFF ROI gris + alpha** : lecteur de masque partagé avec les conventions D2IC pour l’aperçu, la copie, le maillage et la validation du run ; l’aperçu Gmsh reste sur CPU. Preuve : test synthétique gris + alpha, puis `img/DP600L2/roi.tif` réel : aperçu HTTP 200, sauvegarde 200, maillage 691 nœuds/644 éléments à 35 px et image HTTP 200.

- **2026-10-17 — M1.2, ouverture d’étude** : dossier et `config.toml` sélectionnables, double clic sur le dossier, explorateur ouvert au parent, actualisation immédiate de l’interface et accès au bouton sur écran étroit. Preuve : API de l’étude `nouvelle_etude` ouverte sur le serveur local ; test ciblé dossier/fichier `config.toml` réussi.

- **2026-10-17 — M1.3/M6.3, espace image** : navigation gauche repliée par défaut avec icônes et commande d’ouverture ; suppression du titre/sous-titre central redondant ; marges réduites autour du contenu scientifique. La vue mobile garde le tiroir avec libellés et les commandes Image/Paramètres. Preuve : syntaxe JS et structure statique vérifiées ; inspection visuelle navigateur restante.

- **2026-10-17 — M1.2/M1.3, bandeau Fichier** : barre compacte 46 px ; menu Nouvelle, Ouvrir, Enregistrer, Enregistrer sous, Dupliquer, Relocaliser ; raccourci Ctrl/⌘+S. Enregistrer sous transporte les modifications non enregistrées vers une nouvelle étude sans toucher l’originale. Preuve : test ciblé de copie des réglages courants, structure HTML et syntaxe JS vérifiées.

- **2026-10-17 — Sélection VIS pour le calcul** : cases par image, actions tout activer / 1 sur N / désélection avant ou après I ; exclusions persistées dans `config.toml`, chemins absolus actifs figés dans le manifeste et `dic_config.toml`. Le moteur D2IC accepte une liste explicite sans explorer les images exclues. Vérification : test ciblé de préparation, exécution et refus des listes périmées ou vides.

- **2026-10-17 — Gestion des runs par ligne** : Stop, Redémarrer et Supprimer sur chaque run ; résumé du run sélectionné au-dessus de la liste, avec progression et erreur. La suppression refuse un calcul actif et un lien hors de l’étude. Preuve : test API des trois actions, régression GUI/D2IC et syntaxe JS.

- **2026-10-17 — Identifiants de run** : dossier et `manifest.run_id` au format UTC `YY-MM-DD-001`, incrément quotidien sans collision ; les anciens runs restent inchangés. Preuve : test d’incrément/jour, cohérence manifeste/dossier et calcul synthétique.

- **2026-10-17 — Interpolation cubique au lancement** : le worker source charge `im_jax` local avant D2IC ; un run cubique complet en sous-processus termine sur l’étude synthétique. Le run historique échoué à 0/44 images peut être repris depuis Résultats sans modifier son snapshot.

- **2026-10-17 — Surface image maximisée** : suppression de la trame et des marges de scène ; séquences VIS/TH, ROI, DIC et cartes de résultats occupent la surface centrale. La liste des runs et son en-tête sont compactés ; adaptation à la largeur réelle du conteneur. Vérification : syntaxe JS, parsing CSS et route Résultats ciblée.

- **2026-10-18 — Vue ROI/maillage plein champ** : affichage de la référence VIS entière avec deux calques RGBA indépendants (ROI en filigrane et maillage), ajustés ensemble à la zone centrale ; cases à cocher immédiates. Le maillage enregistré produit un calque dédié, contrôlé par les empreintes du masque et les paramètres scientifiques ; l’ancien aperçu composé reste disponible. Preuve : tests `test_project_server.py` pour alpha, dimensions et péremption du maillage ; 35 tests réussis, `node --check` réussi. La revue visuelle dans un navigateur reste à faire.

- **2026-10-18 — Superposition ROI corrigée** : une capture utilisateur montrait VIS et ROI en colonne malgré les cases cochées. La géométrie des trois images est maintenant imposée aussi lors de la création du DOM ; les URL des actifs statiques ont changé pour forcer leur actualisation par le navigateur. Vérification : `node --check D2IC_GUI/static/app.js` et réponses HTTP 200 des actifs versionnés. Revue visuelle dans le navigateur utilisateur attendue.

- **2026-10-18 — Étalonnage DIC interactif** : deux poignées de segment manipulables en pixels VIS d’origine, loupe pendant le déplacement et ajustement au clavier ; coordonnées, distance et facteur mm/px visibles avant confirmation. Modifier le segment ou sa longueur révoque la confirmation précédente. Preuve : test scientifique `test_segment_scale_uses_original_vis_pixel_distance`, 36 tests `test_project_server.py` réussis, syntaxe JS et CSS valides. Validation visuelle navigateur encore à réaliser.

- **2026-10-19 — Séparation Échelle / Réglages DIC et volet droit** : navigation à règle graduée et engrenage ; `[scale]` isolé des champs `[dic]`, `[time]`, `[runtime]` sans migration de `config.toml`. Le volet droit se replie en rail et retrouve sa largeur ; la loupe reste visible pendant la sélection d’une extrémité. Vérification : syntaxe JS et CSS, tests GUI ciblés. Validation visuelle en navigateur encore à effectuer.

- **2026-10-19 — M3.3, Job Manager et exploration des champs** : deux vues distinctes ; chaque run terminé ouvre Résultats depuis sa ligne. La carte est cadrée sur le maillage et reste entièrement visible. Sélection multi-nœuds par clic/Ctrl-clic, courbes sur les temps VIS avec coupures aux valeurs absentes, bornes cinématiques manuelles ou calculées sur image/séquence. Les historiques multi-nœuds chargent chaque frame et l’archive thermique une seule fois par requête ; la température élémentaire reste constante par cellule et masque les cellules invalides. Preuve : `test_project_server.py` → 37 tests réussis, `test_integration_studies.py` → 1 test réussi avec `PYTHONPATH=/workspaces/08_dic/im_jax`, syntaxe JS et CSS vérifiées. Limite : disposition et interactions à confirmer dans un navigateur graphique.

- **2026-10-19 — Correction d’affichage des résultats** : image de champ positionnée dans toute la zone disponible avec conservation du rapport d’aspect ; clics captés sur le conteneur et convertis via le rectangle réellement visible vers les coordonnées VIS du maillage. Le SVG des nœuds reste un affichage seulement. Sur grand écran, l’historique est latéral pour préserver la hauteur de la carte. Preuve : syntaxe JavaScript et CSS valide ; confirmation visuelle dans le navigateur utilisateur attendue.

- **2026-10-20 — Sélection de la séquence TH** : détection des séries TIFF, aperçu avant sauvegarde, cases par image et commandes Tout activer, 1/N, avant/après I comme en VIS. `thermal.excluded_images` pilote l’inventaire, la synchronisation et le manifeste du run ; seules les images TH actives sont référencées et une trame désactivée ne peut pas être franchie par interpolation. Preuve : 41 tests serveur et 1 test d’intégration réussis ; syntaxe JavaScript et CSS vérifiées. Validation interactive dans un navigateur graphique restante.

- **2026-10-21 — Vue Synchro** : l’ancien onglet Temps devient Synchro, expose les deux cadences et présente les trames VIS/TH et les trois images sources de la correspondance sélectionnée. La première VIS reste marquée comme référence thermique. Preuve : 42 tests serveur réussis, dont une correspondance exacte, interpolée et trois aperçus PNG ; syntaxe JavaScript, Python et CSS vérifiées. Contrôle visuel navigateur restant.

- **2026-11-07 — Dessin de ROI par formes** : Rectangle/Ellipse, ajout/retrait et annulation en pixels VIS natifs, puis création d’un nouveau TIFF binaire avant le workflow habituel Mailler. TIFF marqué premier plan blanc pour préserver les masques presque pleins et leurs trous. Photométrie limitée aux blocs complets de la VIS après binning, géométrie FE conservée. Vérifications : 71 tests serveur/dessin Python, 13 tests JavaScript ; 17 tests D2IC binning/photométrie. Chromium : rectangle avec trou elliptique → TIFF → maillage (137 nœuds, 113 éléments), dessin à zoom ×2 correctement rastérisé. Archive Windows reconstruite ; exécution native Windows restant à vérifier.
