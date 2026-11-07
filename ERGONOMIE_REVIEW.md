# Analyse ergonomique — 6 novembre 2026

Analyse fondée sur `static/app.js`, `static/index.html`, `schema.py`,
`server.py` et `SPEC_ERGONOMIE.md`. Les recommandations ci-dessous viennent
de la lecture du code ; leur présentation visuelle et leur utilité doivent
être confirmées en navigateur avec une étude expérimentale.

L’interface possède une base adaptée au travail scientifique : séquences VIS
et TH sélectionnables, référence explicite, calques ROI et maillage séparés,
volet redimensionnable, étalonnage interactif et snapshots de calcul.
L’amélioration principale concerne la lisibilité de l’état scientifique de
l’étude et de l’effet des paramètres.

| Priorité | Constat et point du code | Amélioration proposée | Vérification attendue |
| --- | --- | --- | --- |
| Haute | La navigation ne synthétise pas les dépendances scientifiques (`app.js`, `selectView`, `loadROI`). | Afficher pour chaque étape « incomplet », « prêt », « périmé » ou « erreur », avec la cause et un lien vers le réglage à corriger. Garder la navigation libre. | Changer de référence ou de ROI indique les étapes à revoir avant lancement. |
| Haute | Le panneau ROI affiche un masque géométrique ; la photométrie utilise désormais un second masque (`loadROI`, `dic_run.prepare_run`). | Ajouter un calque photométrique distinct avec légende : zone maillée, pixels retenus et bande exclue ; afficher le nombre de pixels conservés. Utiliser le même opérateur D2IC et les mêmes unités après binning. | À 3 px, la bande change et les nœuds/éléments restent identiques. Un masque photométrique vide est signalé avant calcul. |
| Haute | Corrigé : le bouton Mailler conserve désormais les anciennes clés de morphologie (`loadROI`) pour rester cohérent avec l’aperçu. | Clarifier le contrat « masque importé exact » dans la documentation et signaler toute ancienne morphologie enregistrée. Distinguer ce traitement de l’érosion photométrique. | Ouvrir une étude avec `roi.operation = "erosion"` rend explicite ce qui sera maillé. |
| Haute | Plusieurs actions dépendent de la configuration enregistrée ; certains aperçus utilisent le formulaire courant (`renderFields`, `loadSynchronization`, `prepare_run`). | Avant lancement, présenter un résumé des entrées et réglages qui seront figés : référence, nombre d’images, ROI, taille de maille, érosion photométrique, binning, unités et dispositif. Rendre les modifications non enregistrées explicites. | Le résumé correspond au snapshot du run, y compris après modification du formulaire. |
| Moyenne | Réglages DIC regroupe sélection, résolution, solveur, déformation et dispositif dans des sections assez denses (`renderFields`). | Séparer « observations photométriques », « solveur », « déformations » et « calcul JAX ». Relier binning et interpolation au réglage d’érosion placé dans ROI ; réserver les options avancées à un groupe dépliable. | Les réglages usuels sont trouvés sans parcourir les options techniques. |
| Moyenne | Une progression sans total connu peut être présentée à 0 % (`renderRunSummary`). | Afficher une phase nommée et une progression indéterminée pendant compilation/maillage ; afficher n/N seulement quand disponible. Associer l’erreur à une action de correction. | La préparation JAX n’est plus confondue avec un calcul bloqué à 0 %. |
| Moyenne | La navigation démarre en icônes et les aides sont surtout contextuelles (`index.html`, `renderFields`). | Proposer les libellés lors de la première ouverture ; vérifier focus clavier, aides au focus, panneau étroit et conservation de la sélection des résultats. | Parcours complet au clavier et contrôle à largeur réduite. |

Livré dans cette intervention : réglage « Érosion photométrique » dans
ROI / maillage, aide toujours visible, validation du rayon, sauvegarde et
transmission au moteur. Le défaut reste `0.0` pour les études existantes ;
saisir `3.0` reproduit le paramètre d’`IdentVirual/sequential_dic.toml`.
Le calque photométrique bleu est maintenant livré dans ROI, avec actualisation du rayon avant sauvegarde et visibilité indépendante de la ROI verte et du maillage. L’aperçu tient compte de la morphologie courante, du retrait des îlots et du binning. Le compteur de pixels et le résumé avant calcul restent des propositions.
