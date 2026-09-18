/**
 * tests/unit/test_viewer_canvas_api.mjs
 *
 * Regression test for CanvasRenderingContext2D path calls in robot-3d-viewer.
 * Enforces that all ctx.lineTo and ctx.moveTo calls have exactly 2 valid arguments.
 */

import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '../..');
const viewerDir = path.resolve(repoRoot, 'robot-3d-viewer');

console.log('Running Viewer Canvas API Safety Tests...');

function parseFunctionCalls(content, fnName) {
  const regex = new RegExp('\\b' + fnName + '\\s*\\(', 'g');
  let match;
  const calls = [];
  while ((match = regex.exec(content)) !== null) {
    const start = match.index + match[0].length;
    let depth = 1;
    let i = start;
    while (i < content.length && depth > 0) {
      if (content[i] === '(') depth++;
      else if (content[i] === ')') depth--;
      i++;
    }
    const argStr = content.slice(start, i - 1);
    calls.push({ raw: match[0] + argStr + ')', args: argStr, index: match.index });
  }
  return calls;
}

const files = fs.readdirSync(viewerDir).filter((f) => f.endsWith('.mjs'));
let totalCallsChecked = 0;

for (const file of files) {
  const content = fs.readFileSync(path.join(viewerDir, file), 'utf8');
  for (const fn of ['lineTo', 'moveTo']) {
    const calls = parseFunctionCalls(content, fn);
    for (const call of calls) {
      let depth = 0;
      const args = [];
      let current = '';
      for (const char of call.args) {
        if (char === '(') depth++;
        else if (char === ')') depth--;
        if (char === ',' && depth === 0) {
          args.push(current.trim());
          current = '';
        } else {
          current += char;
        }
      }
      if (current.trim()) args.push(current.trim());

      assert.strictEqual(
        args.length,
        2,
        'Malformed ' + fn + ' in ' + file + ': expected 2 arguments, got ' + args.length + ' in ' + call.raw
      );
      assert.ok(
        args[0].length > 0 && args[1].length > 0,
        'Empty coordinate argument in ' + fn + ' in ' + file + ': ' + call.raw
      );
      totalCallsChecked++;
    }
  }
}

console.log('  [PASS] Verified ' + totalCallsChecked + ' Canvas lineTo/moveTo calls across all viewer modules.');
console.log('ALL VIEWER CANVAS API SAFETY TESTS PASSED!');
