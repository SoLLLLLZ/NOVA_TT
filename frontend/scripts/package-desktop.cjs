// Local macOS bundle using the locked Electron distribution. No credentials embedded.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
if (process.platform !== 'darwin') throw new Error('Build this bundle on macOS');
const frontend = path.resolve(__dirname, '..');
const root = path.resolve(frontend, '..');
const dest = path.join(frontend, 'release/TuneIt.app');
execFileSync(process.execPath, [path.join(frontend, 'node_modules/electron/install.js')], {stdio:'inherit'});
fs.mkdirSync(path.dirname(dest), { recursive: true });
// Replace only generated output owned by this build script.
fs.rmSync(dest, { recursive: true, force: true });
fs.cpSync(path.join(frontend, 'node_modules/electron/dist/Electron.app'), dest, { recursive: true, verbatimSymlinks: true });
const resources = path.join(dest, 'Contents/Resources');
const payload = path.join(resources, 'app');
fs.mkdirSync(payload, { recursive: true });
for (const item of ['dist', 'desktop', 'public/icons']) fs.cpSync(path.join(frontend, item), path.join(payload, item), { recursive: true });
fs.writeFileSync(path.join(payload, 'package.json'), JSON.stringify({name:'tuneit', version:'0.1.0', main:'desktop/main.cjs'}));
fs.writeFileSync(path.join(resources, 'nova-project.json'), JSON.stringify({root}));
const plist = path.join(dest, 'Contents/Info.plist');
for (const [key, value] of Object.entries({ CFBundleName:'TuneIt', CFBundleDisplayName:'TuneIt', CFBundleIdentifier:'com.nova.tuneit', CFBundleExecutable:'TuneIt' })) {
  try { execFileSync('/usr/libexec/PlistBuddy', ['-c', `Set :${key} ${value}`, plist], {stdio:'pipe'}); }
  catch { execFileSync('/usr/libexec/PlistBuddy', ['-c', `Add :${key} string ${value}`, plist]); }
}
execFileSync('/usr/libexec/PlistBuddy', ['-c', 'Add :LSUIElement bool true', plist]);
fs.renameSync(path.join(dest, 'Contents/MacOS/Electron'), path.join(dest, 'Contents/MacOS/TuneIt'));
execFileSync('/usr/bin/codesign', ['--force', '--deep', '--sign', '-', dest], {stdio:'inherit'});
console.log(dest);
