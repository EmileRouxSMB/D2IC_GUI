# Repères de l’interface

- `app.js` : état de l’étude, formulaires, vues et requêtes HTTP ; `index.html` et `style.css` : structure et présentation.
- `image_zoom.js` : géométrie d’affichage et gestes ; `roi_shapes.js` : dessin ; `roi_mesh.js` : arêtes vectorielles.
- `result_analysis.js` : transport référence/courant et paramètres de coupe, importable directement par Node.

Les coordonnées scientifiques restent en pixels VIS natifs ; zoom et mise à l’échelle écran ne changent pas les données. Les transformations des calques doivent rester communes. Les réglages d’affichage vont dans `localStorage`, les paramètres d’étude dans `config.toml` via l’API.

Les contrôles standards viennent de `/api/schema` et du catalogue TOML. Les opérations spécialisées ROI, échelle et calibration conservent leurs interactions dédiées. Les requêtes asynchrones de résultats doivent rester liées à l’étude/run sélectionné et aux frames validées.

Exigences visuelles : [SPEC_ERGONOMIE.md](../../../docs/SPEC_ERGONOMIE.md). Parcours et raccourcis : [manuel](../../../docs/MANUEL_UTILISATION.md). Vérifications : [tests](../../../tests/memory.md).
