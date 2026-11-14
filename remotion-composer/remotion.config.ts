import {Config} from '@remotion/cli/config';
import fs from 'fs';

// Optional: point Remotion at a system Chromium (e.g. one that trusts a
// proxy CA) instead of its bundled chrome-headless-shell.
const exe = process.env.REMOTION_BROWSER_EXECUTABLE;
if (exe && fs.existsSync(exe)) {
  Config.setBrowserExecutable(exe);
}
