# Vendored occt-import-js

This directory contains the browser build used by the 3D viewer:

- `occt-import-js.min.js`
- `occt-import-js.wasm`
- `LICENSE.md` (LGPL-2.1)

Version: `0.0.23`
Source: https://github.com/kovacsv/occt-import-js
CDN files: https://cdn.jsdelivr.net/npm/occt-import-js@0.0.23/dist/

The viewer serves these files locally so STEP/CAD gripper loading does not
depend on Internet access or the jsDelivr CDN. Keep the `.wasm` file next to the
JavaScript file; the loader resolves it relative to the script URL.
