'use strict';

// main.cjs — the STATE_MACHINE declaration and the enum-shaped types of ONE
// TypeScript file, as JSON on stdout.
//
// It DECIDES NOTHING. The rules live once, in Python's
// `state_machine.check_parsed`, so this reader cannot drift into a laxer answer
// than the Python or Go readers give for the same declaration.
//
// # THE PARSER IS REQUIRED BY ABSOLUTE PATH
//
// `require('typescript')` walks up from this file looking for `node_modules`,
// and the only TypeScript that walk can find on a judged checkout lives inside
// the repository under judgement. A branch could then edit its own
// `node_modules/typescript` and choose the program that reads its own state
// machine. So the parser is addressed as an absolute path derived from
// `__dirname` and from nothing else — not the CWD, not NODE_PATH, not an
// ancestor walk. The caller additionally scrubs every NODE_* variable; two
// independent mechanisms for one property, because an environment can be got
// wrong by a caller and an absolute path cannot.
//
// The parser is the one already vendored for `ts_signature_fingerprint` — 9.1 MB
// that must not be duplicated — reached as a sibling of this directory, which
// keeps it an absolute `__dirname`-derived path rather than a search.
//
// `--probe` reports which file Node actually loaded, read back out of the
// loader's own record rather than recomputed from the specifier, because that is
// the only one of the three mechanisms checkable from outside this file.

const path = require('path');
const fs = require('fs');

const PARSER = path.join(__dirname, '..', 'ts_signature_fingerprint', 'typescript.js');

function emit(doc) {
  process.stdout.write(JSON.stringify(doc) + '\n');
}

function fail(why) {
  // A JSON envelope, never a bare message: the caller decodes stdout, and a
  // plain string surfaces as "unparseable helper output", which hides the reason.
  emit({ declaration: null, enums: {}, why: why, parser: null });
  process.exit(1);
}

let ts;
try {
  ts = require(PARSER);
} catch (e) {
  fail('cannot load the vendored parser at ' + PARSER + ': ' + e.message);
}

function loadedParser() {
  const rec = (module.children || []).find((m) => m && m.filename === PARSER);
  return rec ? rec.filename : null;
}

// --- the declaration -------------------------------------------------------
//
// Two accepted spellings, and both are read rather than one imposed:
//   * a string/template literal holding JSON — identical to the Go spelling, so
//     one machine can be moved between languages verbatim;
//   * an object literal, which is what a TypeScript author would actually write.
// The object form is converted here; anything not literal is refused rather than
// evaluated, because evaluating a declaration means running the branch's code.

function literalToJson(node, why) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return { ok: true, value: node.text, isText: true };
  }
  if (ts.isObjectLiteralExpression(node)) {
    const out = {};
    for (const prop of node.properties) {
      if (!ts.isPropertyAssignment(prop) || !prop.name) {
        return { ok: false, why: 'object literal has a non-literal property' };
      }
      const key = ts.isIdentifier(prop.name) || ts.isStringLiteral(prop.name)
        ? prop.name.text : null;
      if (key === null) return { ok: false, why: 'unsupported property key' };
      const v = literalToJson(prop.initializer, why);
      if (!v.ok) return v;
      out[key] = v.isText ? v.value : v.value;
    }
    return { ok: true, value: out };
  }
  if (ts.isArrayLiteralExpression(node)) {
    const arr = [];
    for (const el of node.elements) {
      const v = literalToJson(el, why);
      if (!v.ok) return v;
      arr.push(v.isText ? v.value : v.value);
    }
    return { ok: true, value: arr };
  }
  if (ts.isNumericLiteral(node)) return { ok: true, value: Number(node.text) };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { ok: true, value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { ok: true, value: false };
  if (node.kind === ts.SyntaxKind.NullKeyword) return { ok: true, value: null };
  if (ts.isAsExpression(node) || ts.isParenthesizedExpression(node)) {
    return literalToJson(node.expression, why); // `... as const`
  }
  return { ok: false, why: 'STATE_MACHINE is not a literal' };
}

function findDeclaration(sf) {
  let found = null;
  const visit = (node) => {
    if (ts.isVariableStatement(node)) {
      for (const d of node.declarationList.declarations) {
        if (d.name && ts.isIdentifier(d.name) && d.name.text === 'STATE_MACHINE'
            && d.initializer) {
          found = d.initializer;
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  if (found === null) {
    return { decl: null, why: 'no module-level STATE_MACHINE literal' };
  }
  const lit = literalToJson(found);
  if (!lit.ok) return { decl: null, why: lit.why };
  if (lit.isText) {
    try {
      return { decl: JSON.parse(lit.value), why: '' };
    } catch (e) {
      return { decl: null, why: 'STATE_MACHINE does not hold valid JSON: ' + e.message };
    }
  }
  return { decl: lit.value, why: '' };
}

// --- the enums -------------------------------------------------------------
//
// TypeScript has three shapes that stand in for an enum, and all three are read:
//   enum X { A = 'a' }            -> member NAMES     (A)
//   const enum X { A = 'a' }      -> member NAMES
//   type X = 'a' | 'b'            -> literal VALUES   ('a')
// A declaration references whichever its own code uses; imposing one spelling
// would make the checker refuse idiomatic code rather than check it.

function collectEnums(sf) {
  const out = {};
  const visit = (node) => {
    if (ts.isEnumDeclaration(node) && node.name) {
      out[node.name.text] = node.members
        .map((m) => (m.name && m.name.text ? m.name.text : null))
        .filter((n) => n !== null)
        .sort();
    }
    if (ts.isTypeAliasDeclaration(node) && node.name && node.type) {
      const t = node.type;
      const members = [];
      const takeLiteral = (n) => {
        if (ts.isLiteralTypeNode(n) && n.literal
            && (ts.isStringLiteral(n.literal)
                || ts.isNoSubstitutionTemplateLiteral(n.literal))) {
          members.push(n.literal.text);
        }
      };
      if (ts.isUnionTypeNode(t)) t.types.forEach(takeLiteral);
      else takeLiteral(t);
      if (members.length > 0) out[node.name.text] = members.sort();
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

function main() {
  const args = process.argv.slice(2);
  if (args[0] === '--probe') {
    emit({ declaration: null, enums: {}, why: '', parser: loadedParser() });
    return;
  }
  if (args.length !== 1) fail('usage: main.cjs [--probe] <file.ts>');
  let text;
  try {
    text = fs.readFileSync(args[0], 'utf8');
  } catch (e) {
    fail('cannot read ' + args[0] + ': ' + e.message);
  }
  const sf = ts.createSourceFile(args[0], text, ts.ScriptTarget.Latest, true);
  const { decl, why } = findDeclaration(sf);
  emit({ declaration: decl, enums: collectEnums(sf), why: why,
         parser: loadedParser() });
}

main();
