# Catalogue des paramètres

La source d’autorité est [`src/D2IC_GUI/parameters.toml`](../src/D2IC_GUI/parameters.toml). Elle définit noms, types, valeurs par défaut et aides. Le serveur la lit au démarrage, `/api/schema` la transmet au navigateur et les contrôles de la vue active sont générés depuis ces métadonnées.

Une étude conserve ses valeurs dans son `config.toml`. Les clés absentes reçoivent les défauts du catalogue ; les réglages visuels du navigateur restent locaux. Les études existantes conservent leurs valeurs et la compatibilité de leurs clés.

## Ajouter un paramètre

Ajouter une entrée à `parameters.toml`, redémarrer le serveur et recharger le GUI :

```toml
[[parameters]]
key = "dic.nouveau_seuil"
label = "Nouveau seuil"
type = "float"
default = 0.05
minimum = 0.0
view = "Réglages DIC"
group = "Solveur DIC"
help = "Décrire son rôle et les hypothèses numériques."
```

Le catalogue fournit le formulaire, la validation, la sauvegarde et un défaut pour les anciennes études. Il ne raccorde pas le paramètre à l’algorithme : ce changement requiert une implémentation explicite dans le code concerné.

## Métadonnées et validation

Champs requis : `key`, `label`, `type`, `default`, `view`, `help`. `key` est une clé TOML unique à deux niveaux. `choices` limite les chaînes autorisées ; `unit`, `minimum`, `group` et `order` précisent l’affichage. `view_dic` peut changer l’onglet en DIC seule ; `hidden` masque un paramètre ; `readonly` interdit sa saisie ; `picker` filtre les sélecteurs (`directory`, `image`, `mask`, `registration`, `file`). Les champs numériques sont typés et validés ; `array` est saisi en JSON, ou par sélection multiple avec `choices`.

Types : `string`, `integer`, `float`, `boolean`, `directory`, `file`, `array`. Des `choices` sur une chaîne créent une liste ; sur un tableau, une sélection multiple.

Onglets connus : `VIS`, `ROI`, `Échelle`, `Réglages DIC`, `Thermique`, `Synchro`, `Job Manager`, `Résultats`, `Export`. `Global` désigne les paramètres de barre d’étude masqués du panneau. Un nouvel onglet central implique aussi une modification de navigation.

`thermal_sections` réserve certaines tables au parcours couplé. Les exclusions de séquences, morphologies historiques, masque final et interactions ROI/échelle/calibration sont gérés ailleurs. Les clés dupliquées, onglets inconnus, types/défauts incohérents sont rejetés au chargement. Les contraintes entre champs (par exemple échelle confirmée pour mm ou VTU requis par PVD) restent dans `schema.validate`.
