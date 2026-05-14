const test = require('node:test');
const assert = require('node:assert/strict');
const policy = require('../static/playback-policy.js');

test('manual transcoding enabled chooses transcode first', () => {
  const result = policy.chooseInitialPlaybackRoute({
    manualTranscodeEnabled: true,
    forceDirect: false,
    hasDirectFailCache: false,
    hasTranscodeUrl: true,
  });

  assert.equal(result.route, 'transcode');
});

test('automatic mode without fail cache chooses direct first', () => {
  const result = policy.chooseInitialPlaybackRoute({
    manualTranscodeEnabled: false,
    forceDirect: false,
    hasDirectFailCache: false,
    hasTranscodeUrl: true,
  });

  assert.equal(result.route, 'direct');
});

test('automatic mode with fail cache chooses transcode first', () => {
  const result = policy.chooseInitialPlaybackRoute({
    manualTranscodeEnabled: false,
    forceDirect: false,
    hasDirectFailCache: true,
    hasTranscodeUrl: true,
  });

  assert.equal(result.route, 'transcode');
});

test('direct startup failure falls back to transcode and records cache intent', () => {
  const result = policy.shouldFallbackAfterStartupFailure({
    activeRoute: 'direct',
    playbackStarted: false,
    hasTranscodeUrl: true,
  });

  assert.deepEqual(result, {
    action: 'fallback',
    nextRoute: 'transcode',
    markDirectFailure: true,
  });
});

test('manual transcode startup failure falls back to direct', () => {
  const result = policy.shouldFallbackAfterStartupFailure({
    activeRoute: 'transcode',
    playbackStarted: false,
    hasTranscodeUrl: true,
  });

  assert.deepEqual(result, {
    action: 'fallback',
    nextRoute: 'direct',
    markDirectFailure: false,
  });
});

test('post-playing failures do not trigger route switching', () => {
  const result = policy.shouldFallbackAfterStartupFailure({
    activeRoute: 'direct',
    playbackStarted: true,
    hasTranscodeUrl: true,
  });

  assert.deepEqual(result, { action: 'ignore' });
});

test('direct fail cache key is stable across platforms', () => {
  assert.equal(
    policy.mediaFailKey({ source: 'alist', raw_path: '/video/demo.mkv' }),
    'alist::/video/demo.mkv'
  );
});

test('markDirectFailRecord writes a 30 minute TTL entry', () => {
  const now = 1700000000000;
  const media = { source: 'alist', raw_path: '/video/demo.mkv' };
  const cache = policy.markDirectFailRecord({}, media, now);
  const key = policy.mediaFailKey(media);

  assert.equal(cache[key].ts, now);
  assert.equal(cache[key].until, now + 30 * 60 * 1000);
});

test('shouldUseDirectFailCache respects TTL', () => {
  const now = 1700000000000;
  const media = { source: 'alist', raw_path: '/video/demo.mkv' };
  const key = policy.mediaFailKey(media);
  const cache = {
    [key]: { until: now + 1000, ts: now },
  };

  assert.equal(policy.shouldUseDirectFailCache(cache, media, now), true);
  assert.equal(policy.shouldUseDirectFailCache(cache, media, now + 1001), false);
});

test('prefers media.name for overlay text', () => {
  assert.equal(
    policy.getDisplayMediaName({ name: 'Demo Clip.mp4', raw_path: '/video/fallback.mkv' }),
    'Demo Clip.mp4'
  );
});

test('falls back to basename from raw_path', () => {
  assert.equal(
    policy.getDisplayMediaName({ raw_path: '/video/long-name-demo-file.mkv' }),
    'long-name-demo-file.mkv'
  );
});

test('returns empty text when media name sources are missing', () => {
  assert.equal(policy.getDisplayMediaName({}), '');
  assert.equal(policy.getDisplayMediaName(null), '');
});

test('hides overlay for image media', () => {
  assert.equal(policy.shouldShowMediaName({ type: 'image', name: 'cover.jpg' }), false);
  assert.equal(policy.shouldShowMediaName({ type: 'video', name: 'clip.mp4' }), true);
});
