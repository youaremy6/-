/**
 * Static checks for the WeChat mini program that do not need 微信开发者工具.
 *
 * - every JS file parses (vm.Script, so no child process is spawned)
 * - every page declared in app.json has js/json/wxml/wxss
 * - every bind and catch handler used in WXML exists in that page's JS
 * - every local phrase audio path exists in the package
 * - the state machine rejects an illegal transition and follows the happy path
 *
 * Usage: node scripts/check_miniprogram.mjs
 */

import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { createRequire } from 'node:module';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const MP = join(ROOT, 'miniprogram');
const require = createRequire(import.meta.url);

let failures = 0;
const problems = [];

function fail(message) {
  failures += 1;
  problems.push(message);
}

function checkJs(file) {
  const source = readFileSync(file, 'utf8');
  try {
    new vm.Script(source, { filename: file });
  } catch (error) {
    fail(`${file}: ${error.message}`);
  }
  return source;
}

function checkJson(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch (error) {
    fail(`${file}: invalid JSON (${error.message})`);
    return {};
  }
}

const appJson = checkJson(join(MP, 'app.json'));
const pages = appJson.pages || [];
if (pages.length < 3) fail(`app.json: expected 3 pages, got ${pages.length}`);

for (const page of pages) {
  const base = join(MP, page);
  for (const ext of ['js', 'json', 'wxml', 'wxss']) {
    if (!existsSync(`${base}.${ext}`)) fail(`${page}: missing .${ext}`);
  }
  const jsSource = checkJs(`${base}.js`);
  const wxml = readFileSync(`${base}.wxml`, 'utf8');
  const handlers = new Set();
  for (const match of wxml.matchAll(/(?:bind|catch)[a-zA-Z]+="([^"]+)"/g)) {
    handlers.add(match[1]);
  }
  for (const handler of handlers) {
    const defined =
      new RegExp(`\\b${handler}\\s*\\(`).test(jsSource) ||
      new RegExp(`\\b${handler}\\s*:`).test(jsSource);
    if (!defined) fail(`${page}.wxml uses handler "${handler}" not defined in ${page}.js`);
  }
  checkJson(`${base}.json`);
}

for (const file of ['app.js', 'config.js']) checkJs(join(MP, file));
for (const file of ['utils/api.js', 'utils/audio.js', 'utils/format.js', 'utils/recorder.js', 'utils/settings.js', 'utils/state.js', 'data/phrases.js']) {
  checkJs(join(MP, file));
}

// Phrase pack and bundled audio.
const pack = require(join(MP, 'data/phrases.js'));
if (!pack.phrases || pack.phrases.length !== 27) fail(`phrases.js: expected 27 phrases, got ${pack.phrases ? pack.phrases.length : 0}`);
const scenarios = new Set();
let placeholderAudio = 0;
for (const phrase of pack.phrases) {
  scenarios.add(phrase.scenario);
  if (phrase.reviewStatus !== 'draft') fail(`${phrase.id}: expected draft review status`);
  for (const language of ['mandarin', 'lanzhou']) {
    const meta = phrase[`${language}Audio`];
    if (!meta || !meta.file) {
      fail(`${phrase.id}:${language}: missing audio file reference`);
      continue;
    }
    const local = join(MP, 'assets', 'phrases', meta.file);
    if (!existsSync(local)) fail(`${phrase.id}:${language}: bundled audio missing (${meta.file})`);
    if (meta.kind === 'placeholder') placeholderAudio += 1;
  }
}
if (scenarios.size !== 4) fail(`expected 4 scenarios, got ${[...scenarios].join(',')}`);

// State machine behaviour.
const stateModule = require(join(MP, 'utils/state.js'));
const machine = new stateModule.StateMachine(() => {});
const happy = ['recording', 'uploading', 'recognizing', 'translating', 'synthesizing', 'ready', 'playing', 'ready', 'idle'];
for (const next of happy) {
  if (!machine.to(next)) fail(`state machine rejected happy-path transition to ${next}`);
}
const illegal = new stateModule.StateMachine(() => {});
const originalWarn = console.warn;
console.warn = () => {};
illegal.to('recording');
illegal.to('ready');
console.warn = originalWarn;
if (illegal.state !== 'recording') fail(`illegal transition recording -> ready was not rejected (state=${illegal.state})`);

const totalAudio = pack.phrases.length * 2;
console.log(`pages=${pages.length} handlers_ok=true phrases=${pack.phrases.length} audio=${totalAudio} placeholder=${placeholderAudio}`);
if (problems.length) {
  console.error('\nFAILURES:');
  for (const problem of problems) console.error(' - ' + problem);
  process.exit(1);
}
console.log('MINIPROGRAM STATIC CHECK OK');
