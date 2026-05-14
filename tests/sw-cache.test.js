const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const swPath = path.join(__dirname, '..', 'sw.js');
const swSource = fs.readFileSync(swPath, 'utf8');

test('service worker precaches playback policy script for PWA shell updates', () => {
  assert.match(swSource, /['"]\/static\/playback-policy\.js['"]/);
});
