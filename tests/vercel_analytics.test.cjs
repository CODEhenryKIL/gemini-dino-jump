const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../public/js/vercel_analytics.js'), 'utf8');
const context = { URL };
vm.runInNewContext(source.replaceAll('export function ', 'function '), context);

test('Vercel pageviews remove invite codes, query strings, fragments and extra payload', () => {
  const origin = 'https://test.vercel.app';
  for (const url of ['/?invite=secret&email=test@example.com#token', '/invite/opaque_code_123456?private=yes']) {
    const result = context.redactPageview({ type: 'pageview', url, participant: 'private' }, origin);
    assert.equal(JSON.stringify(result), JSON.stringify({ type: 'pageview', url: origin + '/__preview__/home' }));
  }
});

test('Vercel rejects private/unknown routes, offsite URLs and custom events', () => {
  const origin = 'https://test.vercel.app';
  for (const url of ['/admin.html', '/result/private', '/claims/private', '/api/me', 'https://other.example/']) {
    assert.equal(context.redactPageview({ type: 'pageview', url }, origin), null);
  }
  assert.equal(context.redactPageview({ type: 'event', url: '/', name: 'private' }, origin), null);
});
