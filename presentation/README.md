# Who Disappears presentation

Open `index.html` directly in a current browser. The deck has no server, build step, font download, CDN, or network dependency.

Use the arrow keys, Page Up and Page Down, Home and End, or the discreet arrows at the screen edges. Drag either 3D model to inspect the laser-cut structure. Slide 4 starts its 46-second light cycle when you select **Play**. **Fast preview ×8** shortens review without changing the sequence.

The construction photograph comes from the supplied source PDF. The interactive cover and light cycle use evaluated geometry from `modell/hang_sagami_laser_v1.blend`. `assets/arten.js` contains the 109 source records from `web/src/data/arten.json`, so the model, scatter plot, and light cycle work from a local `file://` URL.

To rebuild the model assets after changing the Blender source:

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b modell/hang_sagami_laser_v1.blend --python presentation/source/export_model.py
web/node_modules/.bin/esbuild presentation/source/model-runtime.js --bundle --format=iife --target=es2020 --outfile=presentation/model-runtime.js --minify
```

Print from the browser to produce one slide per page. On narrow screens the four slides form one vertical document.
