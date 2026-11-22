# État et prochaines validations

D2IC_GUI fournit les parcours DIC seule et DIC avec fusion thermique, ainsi que
la préparation des jobs, l’exploration des résultats et les exports ParaView.
Les contrats entre modules sont décrits dans
[INTEGRATION_CONTRACTS.md](INTEGRATION_CONTRACTS.md), le stockage dans
[RESULT_MODEL.md](RESULT_MODEL.md), et la configuration dans
[CONFIG_SCHEMA.md](CONFIG_SCHEMA.md).

## État

| Domaine | État consigné | Limite ou preuve restant à établir |
| --- | --- | --- |
| Projet, configuration et interface | Fonctionnalités livrées | Revue visuelle complète, en particulier écran étroit et interactions de panneaux |
| Images, ROI, maillage et DIC | Parcours implémenté | Mesures de performance sur séquences expérimentales longues ; annulation/reprise sur calcul réel |
| Correspondance et fusion thermique | Parcours implémenté et cas synthétiques vérifiés | Robustesse sur acquisitions réelles et cas d’erreur prolongés |
| Résultats et exports | Stockage versionné, reprise et export disponibles | Vérifier les limites de provenance lorsque les sources externes sont modifiées ou absentes |
| Paquets portables | Assemblage Linux x86_64 vérifié ; archive Windows assemblable | Exécution native Windows et macOS ; compatibilité Linux sur distributions cibles |

Les cas synthétiques ne remplacent pas la validation sur des acquisitions
représentatives. Les limites de calcul et de données sont précisées dans les
contrats ; aucun seuil scientifique universel n’est déduit de ces essais.

## Travaux ouverts

1. Effectuer une revue d’interface dans un navigateur graphique sur écran large
   et étroit, notamment pour ROI, correspondance et panneaux redimensionnables.
2. Vérifier arrêt, reprise, erreurs disque et redémarrage du serveur sur un run
   représentatif, sans confondre run partiel et run terminé.
3. Mesurer mémoire et durée sur une séquence expérimentale longue et documenter
   les conditions de mesure.
4. Exécuter les paquets Windows et macOS sur leurs systèmes cibles ; définir les
   versions Linux prises en charge après essais sur ces distributions.
5. Préciser la présentation des zones peu couvertes par les points de contrôle
   VIS–TH, vérifier l’effet du mouvement entre acquisitions TH dans les essais
   rapides, et définir quels critères de qualité DIC bloquent un résultat ou
   produisent un avertissement. Aucun seuil arbitraire ne remplace ces décisions.

Les cas de référence doivent couvrir translation rigide sans déformation,
conversion px/mm, ROI/maillage, lecture ParaView, température uniforme et
évolution linéaire avec transformation connue, moyennes élémentaires et valeurs
absentes. Un cas réel doit documenter erreurs de correspondance, temps et
paramètres DIC.

## Validation consignée

Validation du 22 novembre 2026, migration `0c8f4ec` / documentation `fabaf8a` :
147 tests Python, 29 tests Node et contrôle du wheel importé hors dépôt. Cette
validation appartient à la migration, elle n’a pas été relancée pour cette
édition documentaire. Les distributions portables n’ont pas été reconstruites ;
la validation Windows/macOS, la mesure mémoire sur une longue séquence et la
revue visuelle manuelle restent à faire.

La feuille de route décrit des preuves attendues, pas des promesses de
fonctionnalité. Mettre à jour ce tableau quand une limite est effectivement
levée, avec la date et la commande ou observation correspondante.
