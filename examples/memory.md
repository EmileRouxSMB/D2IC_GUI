# Repères des exemples

Les configurations de ce dossier sont des points de départ à adapter. Le script local est un lanceur ; l’implémentation importable est `src/D2IC_GUI/examples/generate_synthetic_study.py` à la racine du dépôt.

Les grandeurs analytiques et la commande du générateur sont dans le [README des exemples](README.md). `expected.json`, écrit avec les images, conserve les valeurs attendues du jeu généré. Les tests `test_synthetic_study.py` et `test_integration_studies.py` vérifient les images puis les deux parcours ; aucun exemple ne devient une dépendance aux données expérimentales.
