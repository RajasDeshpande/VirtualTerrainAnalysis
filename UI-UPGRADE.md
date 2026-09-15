# Terrain inspector upgrade

The existing terrain, Blender analysis, immutable asset manifest, coordinate transformation and VR locomotion are retained.

The viewer uses a location header, grouped display/navigation controls, a scrollable inspector, a compact slope legend and expandable details. Small screens use a lower inspection panel that can be collapsed. The world-space legend appears only in immersive VR.

`terrain.js` emits selected-point measurements. `inspector.js` displays coordinates, elevation, slope and classification and handles the inspector toggle. No Google Maps integration or API configuration is required.

Validation: `node tests/test_viewer.cjs` checks real GLB material switching, full/overview scales, raycasting, inverse UTM coordinates, measurements and download paths. Quest hardware validation remains pending.
