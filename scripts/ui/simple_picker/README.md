# Simple Anim Picker — Maya 2026

## Installation
1. Copier le dossier `simple_picker` dans `Documents/maya/2026/scripts/`.
2. Dans le Script Editor (Python) ou sur un bouton de shelf :

```python
import simple_picker
simple_picker.show()
```

En développement : `simple_picker.reload_and_show()`.

## Architecture
| Fichier | Rôle |
|---|---|
| `model.py` | Données (`ButtonData`, `BackgroundData`, `PickerData`), sérialisation JSON — pur Python |
| `presets.py` | Charge `config/presets.json` (presets de boutons/bordures, couleurs gauche/droite/centre) |
| `maya_utils.py` | **Maya utilities** : `SelectionUtils`, `SelectionWatcher`, `NamespaceUtils`, `RigAnalyzer`, `ViewportCapture`, `SceneStorage` (network), `JsonStorage` |
| `graphics.py` | **UI** graphique : `PickerView`, `PickerButtonItem`, `BackgroundItem`, `ShapeFactory` |
| `ui.py` | **UI** : `PickerWindow`, `PropertyPanel`, `BackgroundPanel`, `ColorButton` |
| `logic.py` | **UI Logic** : `PickerController` (relie UI, modèle et Maya) |
| `qt.py` | Compatibilité PySide6 / PySide2 |

L'UI n'importe jamais `maya` ; seule `logic.py` appelle `maya_utils.py`.

## Utilisation
**Mode anim**
- Clic = sélectionne les contrôles du bouton.
- Shift+clic = ajouter/retirer. Glisser = sélection rectangle.
- Molette = zoom. Clic milieu ou Alt+clic gauche = pan.
- **F** (ou A) = recentrer.
- La sélection Maya est synchronisée en continu : les boutons s'allument quand leurs contrôles sont sélectionnés.

**Mode édition** (Ctrl+E)
- Glisser pour déplacer. Flèches pour décaler (Shift = x10).
- Suppr pour effacer, Ctrl+D pour dupliquer.
- Clic droit : nouveau bouton, bouton depuis un preset, un bouton par contrôle sélectionné, miroir G/D, grille magnétique.
- Panneau « Bouton » : label, contrôles (assigner/ajouter/retirer depuis la sélection Maya), forme, X/Y, taille, rotation, scale, couleurs, bordure, arrondi, presets.
- Panneau « Fond » : importer une image, opacité, échelle, position.
- Un point rouge signale un bouton sans contrôle.

**Auto-génération**
1. Cadrer le rig dans un viewport.
2. Sélectionner le groupe racine du rig.
3. Cliquer sur « Auto-générer depuis le rig ».

L'outil cadre la sélection et masque les courbes, la grille et le HUD. Il capture ensuite le viewport en fond, puis crée un bouton par contrôleur (nurbsCurve) à sa position écran. Chaque bouton reprend la couleur d'override du contrôleur, ou une couleur déduite du nom (L_/R_).

**Sauvegarde**
- `.json` : image de fond incluse en base64, donc le fichier est autonome.
- Scène : node `network` `<nom>_animPicker_NET` (attributs `pickerName` et `pickerData`). Le menu déroulant liste les pickers de la scène.
- Les noms de contrôles sont stockés sans namespace ; le champ Namespace permet de réutiliser un picker sur un rig référencé.
