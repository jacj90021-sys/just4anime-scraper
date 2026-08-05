// Helper: run an otakuhg iframe page's packed jwplayer script and print the
// resolved stream URL (master.txt / m3u8). Usage: node otakuhg_decode.js <file>
const b = require('fs').readFileSync(process.argv[2], 'utf8');
global.jwplayer = function () {
  return {
    key: '',
    setup: function (cfg) {
      let s = cfg && cfg.sources && cfg.sources[0] && cfg.sources[0].file;
      console.log('SETUP_FILE:' + (s || 'NONE'));
    },
  };
};
global.document = { getElementById: function () { return {}; } };
global.$ = function () { return {}; };
global.window = global;
try { eval(b); } catch (e) { console.log('ERR:' + e.message); }
