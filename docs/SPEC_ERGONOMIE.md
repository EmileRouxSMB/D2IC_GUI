# Principes ergonomiques

Cette note fixe les règles d’interface qui aident à interpréter les données et
à éviter les actions implicites. Le [manuel](MANUEL_UTILISATION.md) décrit les gestes et parcours
utilisateur ; les conventions de calcul figurent dans
[INTEGRATION_CONTRACTS.md](INTEGRATION_CONTRACTS.md).

## Navigation et disposition

L’application présente une barre supérieure pour les actions d’étude, une
navigation verticale à gauche et une zone de travail avec panneau de paramètres
à droite. La navigation donne accès directement aux vues pertinentes : VIS,
ROI/maillage, échelle, DIC, thermique/correspondance, synchronisation, jobs,
résultats et exports. Les vues thermiques sont inactives en DIC seule. Les
prérequis peuvent signaler une étape incomplète sans empêcher la consultation
des autres vues.

Sur grand écran, l’espace restant après la navigation est initialement réparti
à 70 % pour le contenu scientifique et 30 % pour les paramètres. Une poignée
redimensionne les panneaux ; elle est utilisable au clavier et préserve zoom,
centre et coordonnées d’image. Sur écran étroit, navigation et paramètres
restent accessibles dans des tiroirs. Le redimensionnement ne lance pas de
calcul.

## Images, pixels et sélection

Les images, ROI, maillages et champs superposés partagent le repère de l’image
VIS d’origine. Le zoom et le redimensionnement ne changent ni les coordonnées
scientifiques, ni les points sélectionnés. Les contrôles d’image doivent
permettre de retrouver la vue entière et de distinguer clairement les calques.

L’affichage des pixels ne les lisse pas ; ce choix est indépendant de
l’interpolation utilisée par le solveur.

Les points VIS–TH sont manipulés dans le repère natif de chaque image. L’aperçu
montre les résidus et la transformation ; l’approbation reste une action
explicite. Le segment d’échelle affiche ses extrémités, sa longueur et le facteur
calculé avant confirmation. L’échelle initiale n’est jamais présentée comme
étalonnée.

Les vues temporelles parcourent les images VIS acquises. Elles indiquent l’image
TH exacte ou les acquisitions qui encadrent l’instant, avec les temps et le
poids d’interpolation. Une valeur invalide apparaît comme absente, avec sa
cause ; une couleur ne doit jamais faire passer une absence pour une mesure.

## Contrôles, accessibilité et erreurs

Chaque paramètre affiche sa valeur, son unité si applicable, son défaut et une
aide concise. Une valeur typique aide au réglage mais ne constitue pas un
critère scientifique de validité. Les réglages expérimentaux restent
modifiables dans une présentation unique, sans mode « avancé » caché.

Les formulaires, menus, tableaux et validations sont utilisables au clavier.
Canvas et outils de points doivent offrir une alternative numérique lorsque la
précision l’exige. Les états ne reposent pas uniquement sur la couleur ; les
messages d’erreur nomment la donnée concernée, la conséquence et l’action
possible. Les avertissements sont distincts des erreurs bloquantes.

La préparation expose les prérequis qui empêchent un lancement. Une modification
signale les aperçus ou calculs devenus périmés sans altérer les runs déjà
terminés. Les actions longues montrent état, progression et journal ; les
résultats partiels sont identifiés comme tels.
