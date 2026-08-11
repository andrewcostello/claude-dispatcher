'use strict';

// main.cjs — the declared signatures of ONE TypeScript file, as a stable JSON
// fingerprint document.
//
// UNIT D4, P3 BODY. The contract this implements is the docstring of
// `TypeScriptSignatureFingerprinter` in `role_protocol.py`, together with
// `TS_SIGNATURE_EDIT_RULINGS`, which is the acceptance criterion. What a
// TypeScript signature IS, and what is deliberately excluded, is stated once,
// there. It is not restated here; two copies of a contract is the defect this
// unit exists to remove. What IS stated here is the RENDERING GRAMMAR — the
// bytes — because that is this file's own invention and nothing else records
// it.
//
// # WHY THE PARSER IS REQUIRED BY ABSOLUTE PATH
//
// `require('typescript')` walks up from this file looking for a
// `node_modules`, and on this machine the only TypeScript that walk can find
// lives inside the repository under judgement. A branch that edits its own
// `node_modules/typescript/lib/typescript.js` to drop a modifier would then be
// choosing the program that decides what its signatures are. The parser is
// therefore addressed as `<__dirname>/typescript.js` and by nothing else. The
// caller scrubs NODE_PATH and NODE_OPTIONS as well; two independent mechanisms
// for one property, because an environment can be got wrong by a caller and an
// absolute path cannot.
//
// # PROTOCOL
//
// One request object on stdin, one response object on stdout, diagnostics on
// stderr, exactly as the Go helper does. Exit 0 means stdout holds a valid
// response document, INCLUDING a document whose `parse_error` is set. Exit
// non-zero means this program could not do its job and the caller reports
// HELPER_FAILED without reading stdout at all.
//
// `node main.cjs --probe` is the second mode: it writes
// `{"node":…,"typescript":…}` and exits 0. The caller uses it once per process
// to refuse a Node or a parser too old for this grammar. It is deliberately
// NOT part of the fingerprint schema — it answers a question about the
// machine, not about a file.
//
// # DETERMINISM IS PART OF THE CONTRACT
//
// Two runs over identical text must produce byte-identical documents. A
// fingerprint is only ever compared for equality against another run of this
// same program, so any nondeterminism — a map iteration order, a timestamp, a
// path, a source offset — reads to the caller as every symbol having been
// rewritten.
//
// # THE RENDERING GRAMMAR, AND WHY EVERY SEPARATOR IS UNFORGEABLE
//
// The Go unit shipped `embedded T` as an embed marker and a struct field
// literally named `embedded` forged it: a marker a name can spell is not a
// marker. TypeScript makes that far easier to hit than Go does, because a
// member name is not required to be an identifier — `{ "a;b": string }`,
// `{ [Symbol.iterator](): void }`, `{ 1: string }` and `#private` are all
// ordinary code — and because decorator arguments, string-literal types and
// template-literal types put arbitrary author-chosen text inside a signature.
//
// Three rules, applied without exception, close the whole class:
//
//   1. TEXT THAT IS NOT PROVABLY AN IDENTIFIER IS JSON-QUOTED. `nameAtom`
//      emits `i:foo` for an identifier and `s:"a;b"` for anything else; string
//      literal types and expressions emit `JSON.stringify(value)`; computed
//      keys emit `c:"[Symbol.iterator]"`. A JSON string is self-delimiting —
//      it starts and ends with `"` and contains no unescaped `"` or `\` — so
//      no author-chosen character can reach a structural position. Bare text
//      is emitted ONLY when the parser has told us it is an identifier, and a
//      TypeScript identifier cannot contain any of `; , : ( ) { } [ ] < > | &
//      = ? ! * @ # ~ + /` or a space, which is the whole separator alphabet.
//
//   2. EVERY OPTIONAL MARKER LIVES IN AN ALWAYS-PRESENT BRACKET SLOT. A member
//      renders as `[kind][modifiers]name…`, and the modifier slot is emitted
//      as `[]` when there are none rather than omitted. That is the precise
//      repair of the Go defect: there, "no marker" was spelled by the absence
//      of a word in a column a name occupies, so the name could spell the
//      word. Here "no marker" is spelled `[]`, and `[` cannot appear in a
//      TypeScript identifier. So a member NAMED `static` renders
//      `[prop][]i:static:number` and a `static` member named `x` renders
//      `[prop][static]i:x:number`; the two can never converge.
//
//   3. STRUCTURE IS DELIMITED BY BALANCED PAIRS. Containers are `{…}`,
//      argument lists `(…)`, type arguments `<…>`, tuples and index signatures
//      `[…]`. With rule 1 guaranteeing that no author text escapes its
//      delimiters, the encoding is unambiguous, which is the property equality
//      comparison actually needs: two different declarations cannot render the
//      same bytes.
//
// The forging case each separator refuses is named at the function that emits
// it. Anything this file cannot render structurally renders as `@unknown(<the
// parser's own kind name>)` and NEVER as source text: `node.getText()` would
// reintroduce the printer's original-source-text dependency that the contract
// measured and rejected, in the one place nobody would look for it.

const path = require('path');

// Absolute, and derived from this file's own location. See the header.
const ts = require(path.join(__dirname, 'typescript.js'));

// Echoed on every response and checked by the caller against TS_HELPER_SCHEMA.
// Bump it whenever the GRAMMAR above changes, not only when a field moves.
const SCHEMA = 'claude-dispatcher/ts-signature-fingerprint/v1';

// The closed tag set, mirroring TS_KEY_TAGS in role_protocol.py.
const KEY_TAGS = new Set(['i', 's', 'c', 'k']);

/** A defect in THIS program: the only route to a non-zero exit. */
class HelperBug extends Error {}

// --------------------------------------------------------------------------
// keys
// --------------------------------------------------------------------------

// symbolKey is the JavaScript half of `ts_symbol_key`, and the two must agree
// byte for byte: the Python side builds documented example keys with its copy
// and the seals compare them. `\` is doubled first and `/` is then escaped, so
// a member named `a/s:b` cannot forge the key of a member `b` of a member `a`.
function symbolKey(segments) {
  if (!segments.length) {
    throw new HelperBug('a symbol key needs at least one segment');
  }
  return segments
    .map(([tag, text]) => {
      if (!KEY_TAGS.has(tag)) throw new HelperBug(`unknown key tag ${tag}`);
      if (!text) throw new HelperBug(`empty text for a ${tag} segment`);
      return `${tag}:${text.replace(/\\/g, '\\\\').replace(/\//g, '\\/')}`;
    })
    .join('/');
}

// --------------------------------------------------------------------------
// atoms
// --------------------------------------------------------------------------

function isIdentifierText(text) {
  return ts.isIdentifierText(text, ts.ScriptTarget.Latest);
}

// nameAtom is rule 1 of the grammar, and it is also the fold's identity: two
// spellings of ONE member must produce ONE atom, or the gate reports a member
// renamed when a body author merely quoted it. `{ foo }` and `{ "foo" }` are
// the same member to TypeScript, so a string-literal name that IS an
// identifier normalises to the identifier tag; `{ 1: x }` and `{ "1": x }`
// likewise, through the numeric literal's already-normalised `text`.
//
// The `s` tag is therefore reached only by text no identifier can spell, which
// is what keeps `i:` and `s:` from ever colliding.
// THE EMPTY NAME, found by the soak and not by reading. `interface I { "":
// number }`, `declare module "" {}` and `export * from ""` are all legal, and
// all three produce an EMPTY segment text — which `ts_symbol_key` refuses,
// correctly, as a helper bug. Before this guard the helper threw and the
// caller reported HELPER_FAILED: the gate switching itself off on ordinary
// compiling code, which is the worse of the two ways to be wrong.
//
// It lands on the `k` tag because that tag's own definition is "a position the
// language has but no identifier names", and the empty name is exactly that.
// It cannot be forged: a member named `empty` is `i:empty`, a string-literal
// member `"empty"` normalises to `i:empty` too, and a string-literal member
// spelled `k:empty` keys as `s:k:empty` — the LEADING tag is what is read.
function segment(tag, text) {
  return text === '' ? ['k', 'empty'] : [tag, text];
}

function nameAtomOf(node) {
  if (node === undefined || node === null) return null;
  switch (node.kind) {
    case ts.SyntaxKind.Identifier:
      return ['i', node.text];
    case ts.SyntaxKind.PrivateIdentifier:
      // `#secret` already carries a character no ordinary identifier has, and
      // the contract puts it under the `i` tag. A string-literal member named
      // "#secret" is a DIFFERENT member and lands on `s`, which is why the
      // normalisation below is guarded by isIdentifierText and `#secret` is
      // not identifier text.
      return ['i', node.text];
    case ts.SyntaxKind.StringLiteral:
    case ts.SyntaxKind.NoSubstitutionTemplateLiteral:
      return isIdentifierText(node.text)
        ? ['i', node.text]
        : segment('s', node.text);
    case ts.SyntaxKind.NumericLiteral:
    case ts.SyntaxKind.BigIntLiteral:
      return segment('s', node.text);
    case ts.SyntaxKind.ComputedPropertyName:
      return ['c', `[${renderExpr(node.expression)}]`];
    default:
      return ['s', `@kind(${ts.SyntaxKind[node.kind]})`];
  }
}

// renderAtom is where rule 1 is actually enforced. Bare text is emitted only
// when the parser has certified it an identifier; everything else is quoted.
function renderAtom(atom) {
  if (atom === null) return 'k:@anonymous';
  const [tag, text] = atom;
  if (tag === 'k') return `k:${text}`;
  if (tag === 'i' && isIdentifierText(text)) return `i:${text}`;
  if (tag === 'i') return `i:${JSON.stringify(text)}`;
  return `${tag}:${JSON.stringify(text)}`;
}

// --------------------------------------------------------------------------
// modifiers
// --------------------------------------------------------------------------

// Canonical ORDER, so that `static readonly x` and `readonly static x` — both
// legal, both the same declaration — render identically. Sorting by this table
// rather than by the source is the same decision the interface-member rule
// makes: where order carries no information a caller can be made wrong by, it
// is spelling and is normalised.
const MODIFIER_WORDS = new Map([
  [ts.SyntaxKind.ExportKeyword, 'export'],
  [ts.SyntaxKind.DefaultKeyword, 'default'],
  [ts.SyntaxKind.DeclareKeyword, 'declare'],
  [ts.SyntaxKind.AbstractKeyword, 'abstract'],
  [ts.SyntaxKind.StaticKeyword, 'static'],
  [ts.SyntaxKind.OverrideKeyword, 'override'],
  [ts.SyntaxKind.PublicKeyword, 'public'],
  [ts.SyntaxKind.ProtectedKeyword, 'protected'],
  [ts.SyntaxKind.PrivateKeyword, 'private'],
  [ts.SyntaxKind.ReadonlyKeyword, 'readonly'],
  [ts.SyntaxKind.AccessorKeyword, 'accessor'],
  [ts.SyntaxKind.AsyncKeyword, 'async'],
  [ts.SyntaxKind.ConstKeyword, 'const'],
  [ts.SyntaxKind.InKeyword, 'in'],
  [ts.SyntaxKind.OutKeyword, 'out'],
]);
const MODIFIER_ORDER = [...MODIFIER_WORDS.values()];

// The always-present slot of rule 2. `[]` when empty, never omitted.
function slot(words) {
  return `[${words.join(',')}]`;
}

function modifierSlot(node, extra = []) {
  const found = new Set(extra);
  const modifiers = ts.canHaveModifiers(node) ? ts.getModifiers(node) : undefined;
  for (const modifier of modifiers || []) {
    const word = MODIFIER_WORDS.get(modifier.kind);
    if (word) found.add(word);
  }
  return slot(MODIFIER_ORDER.filter((word) => found.has(word)).concat(
    [...found].filter((word) => !MODIFIER_ORDER.includes(word)).sort(),
  ));
}

// Decorators are rendered IN FULL, arguments included, because
// `@Column({ name: 'amount' })` renames a database column with no error
// anywhere — the struct-tag row of the rulings table. They lead the member,
// each wrapped in `@(…)`: `@` cannot appear in an identifier and the
// parenthesis is balanced, so a decorator can neither be forged by a name nor
// swallow the member that follows it.
function decoratorPrefix(node) {
  if (!ts.canHaveDecorators(node)) return '';
  const decorators = ts.getDecorators(node) || [];
  return decorators.map((d) => `@(${renderExpr(d.expression)})`).join('');
}

// --------------------------------------------------------------------------
// expressions — decorator arguments, computed keys, enum initialisers
// --------------------------------------------------------------------------

// Function BODIES are excluded everywhere, including inside a decorator
// argument: `@Watch(() => { … })` is a callback whose body is body work by the
// same rule that excludes a method's. The signature is kept and the body is
// the fixed marker `@body`.
function renderExpr(node) {
  if (!node) return '@none';
  switch (node.kind) {
    case ts.SyntaxKind.Identifier:
      return isIdentifierText(node.text) ? node.text : JSON.stringify(node.text);
    case ts.SyntaxKind.PrivateIdentifier:
      return JSON.stringify(node.text);
    case ts.SyntaxKind.StringLiteral:
    case ts.SyntaxKind.NoSubstitutionTemplateLiteral:
      // The requoting normalisation, at its source: `'x'` and `"x"` both have
      // the cooked value `x` and both render `"x"`. `printNode` would have
      // reused the original quotes, which is the measured defect the rulings
      // table has a control row for.
      return JSON.stringify(node.text);
    case ts.SyntaxKind.NumericLiteral:
    case ts.SyntaxKind.BigIntLiteral:
      // `text` is the parser's normalised value: `1_000`, `1000` and `0x3e8`
      // all arrive here as `1000` (measured, 5.9.3).
      return node.text;
    case ts.SyntaxKind.RegularExpressionLiteral:
      return JSON.stringify(node.text);
    case ts.SyntaxKind.TrueKeyword:
      return 'true';
    case ts.SyntaxKind.FalseKeyword:
      return 'false';
    case ts.SyntaxKind.NullKeyword:
      return 'null';
    case ts.SyntaxKind.ThisKeyword:
      return 'this';
    case ts.SyntaxKind.SuperKeyword:
      return 'super';
    case ts.SyntaxKind.ParenthesizedExpression:
      // Redundant parentheses are spelling.
      return renderExpr(node.expression);
    case ts.SyntaxKind.PropertyAccessExpression:
      return `${renderExpr(node.expression)}${node.questionDotToken ? '?.' : '.'}${
        renderAtom(nameAtomOf(node.name))
      }`;
    case ts.SyntaxKind.ElementAccessExpression:
      return `${renderExpr(node.expression)}[${renderExpr(node.argumentExpression)}]`;
    case ts.SyntaxKind.CallExpression:
      return `${renderExpr(node.expression)}${typeArguments(node.typeArguments)}(${
        (node.arguments || []).map(renderExpr).join(',')
      })`;
    case ts.SyntaxKind.NewExpression:
      return `new ${renderExpr(node.expression)}${typeArguments(node.typeArguments)}(${
        (node.arguments || []).map(renderExpr).join(',')
      })`;
    case ts.SyntaxKind.ArrayLiteralExpression:
      return `[${node.elements.map(renderExpr).join(',')}]`;
    case ts.SyntaxKind.ObjectLiteralExpression:
      return `{${node.properties.map(renderObjectMember).join(',')}}`;
    case ts.SyntaxKind.SpreadElement:
    case ts.SyntaxKind.SpreadAssignment:
      return `...${renderExpr(node.expression)}`;
    case ts.SyntaxKind.ArrowFunction:
    case ts.SyntaxKind.FunctionExpression:
      return `${modifierSlot(node)}fn${signature(node)}=>@body`;
    case ts.SyntaxKind.TemplateExpression:
      return `tpl(${JSON.stringify(node.head.text)}${node.templateSpans
        .map((s) => `,${renderExpr(s.expression)},${JSON.stringify(s.literal.text)}`)
        .join('')})`;
    case ts.SyntaxKind.TaggedTemplateExpression:
      return `tag(${renderExpr(node.tag)},${renderExpr(node.template)})`;
    case ts.SyntaxKind.PrefixUnaryExpression:
      return `pre${ts.tokenToString(node.operator)}(${renderExpr(node.operand)})`;
    case ts.SyntaxKind.PostfixUnaryExpression:
      return `post${ts.tokenToString(node.operator)}(${renderExpr(node.operand)})`;
    case ts.SyntaxKind.BinaryExpression:
      return `bin${ts.tokenToString(node.operatorToken.kind)}(${
        renderExpr(node.left)},${renderExpr(node.right)})`;
    case ts.SyntaxKind.ConditionalExpression:
      return `cond(${renderExpr(node.condition)},${renderExpr(node.whenTrue)},${
        renderExpr(node.whenFalse)})`;
    case ts.SyntaxKind.AsExpression:
      return `as(${renderExpr(node.expression)},${renderType(node.type)})`;
    case ts.SyntaxKind.SatisfiesExpression:
      return `satisfies(${renderExpr(node.expression)},${renderType(node.type)})`;
    case ts.SyntaxKind.TypeAssertionExpression:
      return `assert(${renderType(node.type)},${renderExpr(node.expression)})`;
    case ts.SyntaxKind.NonNullExpression:
      return `nonnull(${renderExpr(node.expression)})`;
    case ts.SyntaxKind.AwaitExpression:
      return `await(${renderExpr(node.expression)})`;
    case ts.SyntaxKind.TypeOfExpression:
      return `typeofx(${renderExpr(node.expression)})`;
    case ts.SyntaxKind.VoidExpression:
      return `voidx(${renderExpr(node.expression)})`;
    case ts.SyntaxKind.ClassExpression:
      return `${modifierSlot(node)}class${typeParameters(node.typeParameters)}${
        heritage(node)}{${renderMembers(node.members)}}`;
    case ts.SyntaxKind.OmittedExpression:
      return '@omitted';
    case ts.SyntaxKind.MetaProperty:
      // `import.meta` and `new.target`. Found by the soak, not by reading:
      // three occurrences in the primary target, all inside decorator-free
      // initialisers. `ts.tokenToString` gives the keyword half.
      return `meta(${ts.tokenToString(node.keywordToken)}.${
        renderAtom(nameAtomOf(node.name))})`;
    default:
      // Never source text. See the header's rule 3 note: `getText()` here
      // would reintroduce the printer's original-source-text dependency in the
      // one place nobody would look for it. The soak counts these.
      unknownKinds.add(ts.SyntaxKind[node.kind]);
      return `@unknown(${ts.SyntaxKind[node.kind]})`;
  }
}

function renderObjectMember(node) {
  const atom = renderAtom(nameAtomOf(node.name));
  switch (node.kind) {
    case ts.SyntaxKind.PropertyAssignment:
      return `${atom}:${renderExpr(node.initializer)}`;
    case ts.SyntaxKind.ShorthandPropertyAssignment:
      return `${atom}:@shorthand`;
    case ts.SyntaxKind.SpreadAssignment:
      return `...${renderExpr(node.expression)}`;
    case ts.SyntaxKind.MethodDeclaration:
      return `${modifierSlot(node)}${atom}${signature(node)}=>@body`;
    case ts.SyntaxKind.GetAccessor:
      return `[get]${atom}${signature(node)}=>@body`;
    case ts.SyntaxKind.SetAccessor:
      return `[set]${atom}${signature(node)}=>@body`;
    default:
      unknownKinds.add(ts.SyntaxKind[node.kind]);
      return `@unknown(${ts.SyntaxKind[node.kind]})`;
  }
}

// --------------------------------------------------------------------------
// types
// --------------------------------------------------------------------------

const KEYWORD_TYPES = new Map([
  [ts.SyntaxKind.AnyKeyword, 'any'],
  [ts.SyntaxKind.UnknownKeyword, 'unknown'],
  [ts.SyntaxKind.NumberKeyword, 'number'],
  [ts.SyntaxKind.BigIntKeyword, 'bigint'],
  [ts.SyntaxKind.ObjectKeyword, 'object'],
  [ts.SyntaxKind.BooleanKeyword, 'boolean'],
  [ts.SyntaxKind.StringKeyword, 'string'],
  [ts.SyntaxKind.SymbolKeyword, 'symbol'],
  [ts.SyntaxKind.VoidKeyword, 'void'],
  [ts.SyntaxKind.UndefinedKeyword, 'undefined'],
  [ts.SyntaxKind.NullKeyword, 'null'],
  [ts.SyntaxKind.NeverKeyword, 'never'],
  [ts.SyntaxKind.IntrinsicKeyword, 'intrinsic'],
  [ts.SyntaxKind.ThisType, 'this'],
]);

function renderEntityName(node) {
  if (!node) return '@none';
  if (node.kind === ts.SyntaxKind.QualifiedName) {
    return `${renderEntityName(node.left)}.${renderAtom(nameAtomOf(node.right))}`;
  }
  return renderAtom(nameAtomOf(node));
}

function typeArguments(list) {
  if (!list || !list.length) return '';
  return `<${list.map(renderType).join(',')}>`;
}

// THE TRAP-2 RULE, in code. Every type expression renders its FULL structure
// wherever it appears — there is no `withSignatures` flag and no name-only
// branch — because the Go unit lost signatures in six positions by having one.
// A structural type in a parameter, a return, a type argument, a conditional
// branch or a mapped-type body has no sub-symbol anywhere; if this function
// did not carry the signature, nothing would.
function renderType(node) {
  if (!node) return '@none';
  const keyword = KEYWORD_TYPES.get(node.kind);
  if (keyword) return keyword;
  switch (node.kind) {
    case ts.SyntaxKind.ParenthesizedType:
      // Redundant parentheses are spelling, not contract. The INNER type is
      // still rendered in full, which is what stops "normalise" becoming
      // "delete" here.
      return renderType(node.type);
    case ts.SyntaxKind.TypeReference:
      return `${renderEntityName(node.typeName)}${typeArguments(node.typeArguments)}`;
    case ts.SyntaxKind.ExpressionWithTypeArguments:
      return `${renderExpr(node.expression)}${typeArguments(node.typeArguments)}`;
    case ts.SyntaxKind.ArrayType:
      // `T[]` and `Array<T>` are deliberately NOT normalised together: they
      // differ under `readonly` and this comparator has no checker.
      return `${renderType(node.elementType)}[]`;
    case ts.SyntaxKind.TupleType:
      return `[${node.elements.map(renderType).join(',')}]`;
    case ts.SyntaxKind.NamedTupleMember:
      return `${slot(node.dotDotDotToken ? ['rest'] : [])}${
        renderAtom(nameAtomOf(node.name))}${node.questionToken ? '?' : ''}:${
        renderType(node.type)}`;
    case ts.SyntaxKind.OptionalType:
      return `${renderType(node.type)}?`;
    case ts.SyntaxKind.RestType:
      return `...${renderType(node.type)}`;
    case ts.SyntaxKind.UnionType:
      // Constituents AS WRITTEN, parenthesised so nesting is unambiguous. The
      // contract argues the false positive: sorting a union would be legal and
      // sorting an intersection would not, and no checker is available to tell
      // which is which in every position.
      //
      // A ONE-CONSTITUENT union is the constituent, and the wrapper is
      // dropped. `type A = | string` — the leading-bar spelling every
      // formatter emits for a union it might extend — parses as a UnionType of
      // one, and rendering it `(string)` made it differ from `type A = string`,
      // which is the same type. Found by the reprint soak: 3 fingerprints in
      // 215,104, all of them this.
      return node.types.length === 1
        ? renderType(node.types[0])
        : `(${node.types.map(renderType).join('|')})`;
    case ts.SyntaxKind.IntersectionType:
      return node.types.length === 1
        ? renderType(node.types[0])
        : `(${node.types.map(renderType).join('&')})`;
    case ts.SyntaxKind.FunctionType:
      return `${signature(node)}=>fn`;
    case ts.SyntaxKind.ConstructorType:
      return `${modifierSlot(node)}new${signature(node)}=>fn`;
    case ts.SyntaxKind.TypeLiteral:
      return `{${renderMembers(node.members)}}`;
    case ts.SyntaxKind.MappedType:
      return `mapped(${node.readonlyToken ? readonlyMarker(node.readonlyToken) : ''}${
        renderTypeParameter(node.typeParameter)}${
        node.nameType ? `,as=${renderType(node.nameType)}` : ''}${
        node.questionToken ? optionalMarker(node.questionToken) : ''},${
        renderType(node.type)})`;
    case ts.SyntaxKind.ConditionalType:
      return `cond(${renderType(node.checkType)},${renderType(node.extendsType)},${
        renderType(node.trueType)},${renderType(node.falseType)})`;
    case ts.SyntaxKind.InferType:
      return `infer(${renderTypeParameter(node.typeParameter)})`;
    case ts.SyntaxKind.IndexedAccessType:
      return `idx(${renderType(node.objectType)},${renderType(node.indexType)})`;
    case ts.SyntaxKind.TypeOperator:
      return `${ts.tokenToString(node.operator)}(${renderType(node.type)})`;
    case ts.SyntaxKind.TypeQuery:
      return `typeof(${renderEntityName(node.exprName)})${
        typeArguments(node.typeArguments)}`;
    case ts.SyntaxKind.LiteralType:
      return `lit(${renderExpr(node.literal)})`;
    case ts.SyntaxKind.TemplateLiteralType:
      // The chunks are JSON-quoted, so a template's literal text cannot forge
      // the `,` that separates it from the interpolated types.
      return `tpltype(${JSON.stringify(node.head.text)}${node.templateSpans
        .map((s) => `,${renderType(s.type)},${JSON.stringify(s.literal.text)}`)
        .join('')})`;
    case ts.SyntaxKind.ImportType:
      return `import(${renderType(node.argument)}${
        node.qualifier ? `,${renderEntityName(node.qualifier)}` : ''}${
        node.isTypeOf ? ',typeof' : ''})${typeArguments(node.typeArguments)}`;
    case ts.SyntaxKind.TypePredicate:
      return `pred(${node.assertsModifier ? 'asserts,' : ''}${
        node.parameterName.kind === ts.SyntaxKind.ThisType
          ? 'this'
          : renderAtom(nameAtomOf(node.parameterName))},${renderType(node.type)})`;
    case ts.SyntaxKind.JSDocNullableType:
    case ts.SyntaxKind.JSDocNonNullableType:
    case ts.SyntaxKind.JSDocOptionalType:
    case ts.SyntaxKind.JSDocVariadicType:
      return `jsdoc(${renderType(node.type)})`;
    default:
      unknownKinds.add(ts.SyntaxKind[node.kind]);
      return `@unknown(${ts.SyntaxKind[node.kind]})`;
  }
}

function optionalMarker(token) {
  return token.kind === ts.SyntaxKind.MinusToken ? ',-?' : ',+?';
}

function readonlyMarker(token) {
  return token.kind === ts.SyntaxKind.MinusToken ? '-readonly,' : '+readonly,';
}

// --------------------------------------------------------------------------
// signatures
// --------------------------------------------------------------------------

// Type parameter NAMES are IN, by the parameter-reorder argument one level up
// the type system: `<K, V>` -> `<V, K>` silently inverts every `Map<A, B>`.
// Constraints, defaults and variance annotations are IN too.
function renderTypeParameter(node) {
  return `${modifierSlot(node)}${renderAtom(nameAtomOf(node.name))}${
    node.constraint ? `<:${renderType(node.constraint)}` : ''}${
    node.default ? `=${renderType(node.default)}` : ''}`;
}

function typeParameters(list) {
  if (!list || !list.length) return '';
  return `<${list.map(renderTypeParameter).join(',')}>`;
}

// Parameter NAMES are IN. The contract's reason, transferred from Go intact:
// a syntactic single-file comparison cannot tell `move(src, dst)` ->
// `move(dst, src)` from two renames, and the reorder inverts every call site
// with no compiler check anywhere.
//
// A DESTRUCTURING pattern is the ruled exception and renders as the fixed
// marker `@pattern`: destructuring binds BY NAME, the binding names are
// body-local, and permuting them cannot make a caller wrong. The parameter's
// TYPE is still rendered in full, so retyping it is still caught.
function renderParameter(node) {
  const extra = [];
  if (node.dotDotDotToken) extra.push('rest');
  const name =
    node.name && ts.isIdentifier(node.name)
      ? renderAtom(nameAtomOf(node.name))
      : 'k:@pattern';
  return `${decoratorPrefix(node)}${modifierSlot(node, extra)}${name}${
    node.questionToken ? '?' : ''}:${
    node.type ? renderType(node.type) : '@inferred'}`;
}

function parameters(list) {
  return `(${(list || []).map(renderParameter).join(',')})`;
}

// A return type that is ABSENT renders as `@inferred` rather than as nothing,
// so that adding or removing an annotation is a fingerprint change on a stable
// symbol rather than something invisible. `@` cannot appear in an identifier,
// so no type reference can spell the marker.
function returnType(node) {
  return `:${node.type ? renderType(node.type) : '@inferred'}`;
}

function signature(node) {
  return `${typeParameters(node.typeParameters)}${parameters(node.parameters)}${
    returnType(node)}`;
}

// --------------------------------------------------------------------------
// members of interfaces, type literals and classes
// --------------------------------------------------------------------------

// Returns {key: segment, text} or null for an element that declares nothing.
//
// The `[kind]` slot leads and the `[modifiers]` slot follows, both always
// present. That is rule 2 and it is what refuses the Go forgery: `class C {
// static: number }` is `[prop][]i:static:number` and `class C { static x:
// number }` is `[prop][static]i:x:number`.
function renderMember(node) {
  const decorators = decoratorPrefix(node);
  switch (node.kind) {
    case ts.SyntaxKind.PropertySignature:
    case ts.SyntaxKind.PropertyDeclaration: {
      const atom = nameAtomOf(node.name);
      return {
        key: atom,
        text: `${decorators}[prop]${modifierSlot(node)}${renderAtom(atom)}${
          node.questionToken ? '?' : ''}${node.exclamationToken ? '!' : ''}:${
          node.type ? renderType(node.type) : '@inferred'}`,
      };
    }
    case ts.SyntaxKind.MethodSignature:
    case ts.SyntaxKind.MethodDeclaration: {
      const atom = nameAtomOf(node.name);
      return {
        key: atom,
        text: `${decorators}[method]${modifierSlot(node)}${renderAtom(atom)}${
          node.questionToken ? '?' : ''}${signature(node)}`,
      };
    }
    case ts.SyntaxKind.GetAccessor:
    case ts.SyntaxKind.SetAccessor: {
      // Accessors fold into ONE member key, and the `[get]`/`[set]` markers
      // are what say which half exists — deleting a setter makes a property
      // read-only to every consumer with no error in this file.
      const atom = nameAtomOf(node.name);
      const kind = node.kind === ts.SyntaxKind.GetAccessor ? 'get' : 'set';
      return {
        key: atom,
        text: `${decorators}[${kind}]${modifierSlot(node)}${renderAtom(atom)}${
          signature(node)}`,
      };
    }
    case ts.SyntaxKind.Constructor:
      return {
        key: ['k', 'ctor'],
        text: `${decorators}[ctor]${modifierSlot(node)}${signature(node)}`,
      };
    case ts.SyntaxKind.CallSignature:
      return {
        key: ['k', 'call'],
        text: `[call]${modifierSlot(node)}${signature(node)}`,
      };
    case ts.SyntaxKind.ConstructSignature:
      return {
        key: ['k', 'new'],
        text: `[new]${modifierSlot(node)}${signature(node)}`,
      };
    case ts.SyntaxKind.IndexSignature:
      return {
        key: ['k', 'index'],
        text: `[index]${modifierSlot(node)}${parameters(node.parameters)}${
          returnType(node)}`,
      };
    case ts.SyntaxKind.ClassStaticBlockDeclaration:
    case ts.SyntaxKind.SemicolonClassElement:
      // A static block is a BODY, and a stray `;` declares nothing.
      return null;
    default:
      unknownKinds.add(ts.SyntaxKind[node.kind]);
      return { key: ['k', 'index'], text: `@unknown(${ts.SyntaxKind[node.kind]})` };
  }
}

// Group by key, fold each group in DECLARATION order, then sort the groups.
//
// The fold is what makes overloaded members representable at all: three
// `m(...)` declarations are one member. The SORT is the contract's deliberate
// parity break with Go's struct-field rule — object member order is visible to
// nobody, so ordering it buys no reorder catch and costs a false positive on
// every alphabetise edit — and the ORDER inside a fold is kept, because
// TypeScript resolves an overload set in declaration order.
function memberGroups(members) {
  const groups = new Map();
  for (const member of members || []) {
    const rendered = renderMember(member);
    if (!rendered) continue;
    const key = symbolKey([rendered.key]);
    if (!groups.has(key)) groups.set(key, { key, atom: rendered.key, parts: [] });
    groups.get(key).parts.push(rendered.text);
  }
  return [...groups.values()].sort((a, b) =>
    a.key < b.key ? -1 : a.key > b.key ? 1 : 0,
  );
}

function renderMembers(members) {
  return memberGroups(members)
    .map((group) => group.parts.join('+'))
    .join(';');
}

function heritage(node) {
  let text = '';
  for (const clause of node.heritageClauses || []) {
    const word =
      clause.token === ts.SyntaxKind.ImplementsKeyword ? 'implements' : 'extends';
    text += ` ${word}(${clause.types.map(renderType).join(',')})`;
  }
  return text;
}

// --------------------------------------------------------------------------
// top-level and namespace declarations
// --------------------------------------------------------------------------

// The `no declared type` marker. Rendering it rather than omitting the symbol
// is what keeps the top-level binding rule TOTAL: adding an annotation is then
// a fingerprint change on a stable key, where "symbol appeared" would have
// meant "not a change".
const UNTYPED = '@untyped';

// The declared type of a top-level binding, in the contract's ruled order:
// the annotation, else a `satisfies` operand's type, else an arrow or function
// expression's signature, else the marker. The initialiser's VALUE is never
// fingerprinted.
function bindingType(declaration) {
  if (declaration.type) return renderType(declaration.type);
  const initializer = declaration.initializer;
  if (!initializer) return UNTYPED;
  if (initializer.kind === ts.SyntaxKind.SatisfiesExpression) {
    return renderType(initializer.type);
  }
  if (
    initializer.kind === ts.SyntaxKind.ArrowFunction ||
    initializer.kind === ts.SyntaxKind.FunctionExpression
  ) {
    return `${modifierSlot(initializer)}fn${signature(initializer)}`;
  }
  return UNTYPED;
}

function bindingNames(name, out) {
  if (!name) return;
  if (ts.isIdentifier(name)) {
    out.push(name);
    return;
  }
  for (const element of name.elements || []) {
    if (element.kind === ts.SyntaxKind.OmittedExpression) continue;
    bindingNames(element.name, out);
  }
}

function variableKeyword(statement) {
  const flags = statement.declarationList.flags;
  if (flags & ts.NodeFlags.Const) return 'const';
  if (flags & ts.NodeFlags.Let) return 'let';
  return 'var';
}

// --------------------------------------------------------------------------
// the collector
// --------------------------------------------------------------------------

// Module-scope, reset per request. Only used for reportage in the soak.
let unknownKinds = new Set();

class Collector {
  constructor() {
    this.order = [];
    this.byKey = new Map();
  }

  // ONE KEY PER NAME, and every declaration of that name folds into it. Three
  // TypeScript shapes arrive here at once — function overloads, declaration
  // merging, and a name occupying more than one declaration space — and all
  // three would otherwise be a DUPLICATE KEY, which the caller refuses as
  // HELPER_OUTPUT_INVALID. The gate faulting on ordinary compiling code is a
  // worse failure than a lenient answer, so the fold is not optional.
  add(prefix, segment, kind, text) {
    const segments = prefix.concat([segment]);
    const key = symbolKey(segments);
    if (!this.byKey.has(key)) {
      this.byKey.set(key, { key, kind, parts: [] });
      this.order.push(key);
    }
    this.byKey.get(key).parts.push(text);
  }

  symbols() {
    return this.order.map((key) => {
      const entry = this.byKey.get(key);
      return {
        symbol: entry.key,
        // Contributions joined by `+`, which no identifier can spell and which
        // every rendering above already uses for the same job one level down.
        fingerprint: entry.parts.join('+'),
        kind: entry.kind,
      };
    });
  }
}

function collectStatements(statements, prefix, collector) {
  for (const statement of statements || []) {
    collectStatement(statement, prefix, collector);
  }
}

function collectStatement(node, prefix, collector) {
  switch (node.kind) {
    case ts.SyntaxKind.FunctionDeclaration: {
      const atom = nameAtomOf(node.name);
      if (!atom) {
        // `export default function () {}` — the anonymous default slot, which
        // no identifier can name and therefore no identifier can forge.
        collector.add(prefix, ['k', 'default'], 'function',
          `${modifierSlot(node)}function${signature(node)}${
            node.body ? '@impl' : '@overload'}`);
        return;
      }
      collector.add(prefix, atom, 'function',
        `${modifierSlot(node)}function ${renderAtom(atom)}${signature(node)}${
          node.body ? '@impl' : '@overload'}`);
      return;
    }
    case ts.SyntaxKind.ClassDeclaration: {
      const atom = nameAtomOf(node.name);
      const body = `${decoratorPrefix(node)}${modifierSlot(node)}class${
        atom ? ` ${renderAtom(atom)}` : ''}${typeParameters(node.typeParameters)}${
        heritage(node)}{${renderMembers(node.members)}}`;
      const own = atom || ['k', 'default'];
      collector.add(prefix, own, 'class', body);
      // Class members are ALSO sub-symbols. The class fingerprint above
      // already carries them in full (P4, 2026-08-10), so an edit to `C.m`
      // moves two rows: `i:C` decides the verdict and `i:C/i:m` says which
      // member did it. The redundancy is the accepted price of having no
      // name-only rendering position anywhere in this grammar.
      const memberPrefix = prefix.concat([own]);
      for (const group of memberGroups(node.members)) {
        collector.add(memberPrefix, group.atom, 'member', group.parts.join('+'));
      }
      return;
    }
    case ts.SyntaxKind.InterfaceDeclaration: {
      const atom = nameAtomOf(node.name);
      // NO sub-symbols for interface members: the interface's own fingerprint
      // is the sole storage, which is why adding a member to one is a change.
      collector.add(prefix, atom, 'interface',
        `${modifierSlot(node)}interface ${renderAtom(atom)}${
          typeParameters(node.typeParameters)}${heritage(node)}{${
          renderMembers(node.members)}}`);
      return;
    }
    case ts.SyntaxKind.TypeAliasDeclaration: {
      const atom = nameAtomOf(node.name);
      collector.add(prefix, atom, 'type',
        `${modifierSlot(node)}type ${renderAtom(atom)}${
          typeParameters(node.typeParameters)}=${renderType(node.type)}`);
      return;
    }
    case ts.SyntaxKind.EnumDeclaration: {
      const atom = nameAtomOf(node.name);
      // ORDERED, with explicit initialisers, and NOT sorted: implicit numeric
      // values follow declaration order, and a `const enum`'s values are
      // inlined into every consumer.
      const members = (node.members || [])
        .map((m) => `${renderAtom(nameAtomOf(m.name))}${
          m.initializer ? `=${renderExpr(m.initializer)}` : '=@auto'}`)
        .join(',');
      collector.add(prefix, atom, 'enum',
        `${modifierSlot(node)}enum ${renderAtom(atom)}{${members}}`);
      return;
    }
    case ts.SyntaxKind.ModuleDeclaration: {
      collectModule(node, prefix, collector);
      return;
    }
    case ts.SyntaxKind.VariableStatement: {
      const keyword = variableKeyword(node);
      for (const declaration of node.declarationList.declarations) {
        const type = bindingType(declaration);
        const names = [];
        bindingNames(declaration.name, names);
        for (const name of names) {
          const atom = nameAtomOf(name);
          collector.add(prefix, atom, 'variable',
            `${modifierSlot(node)}${keyword} ${renderAtom(atom)}:${type}`);
        }
      }
      return;
    }
    case ts.SyntaxKind.ExportDeclaration:
      collectExportDeclaration(node, prefix, collector);
      return;
    case ts.SyntaxKind.ExportAssignment:
      // `export default <expr>` and `export = <expr>`. The first lands in the
      // anonymous default slot; the second gets its own keyword slot so the
      // two cannot merge.
      collector.add(
        prefix,
        node.isExportEquals ? ['k', 'export'] : ['k', 'default'],
        'export',
        `${node.isExportEquals ? 'export=' : 'export default '}${
          renderExpr(node.expression)}`,
      );
      return;
    case ts.SyntaxKind.ImportEqualsDeclaration: {
      // `import X = require('y')` is an import and imports are out — EXCEPT
      // when it is exported, which republishes another module's name.
      const modifiers = modifierSlot(node);
      if (!modifiers.includes('export')) return;
      const atom = nameAtomOf(node.name);
      collector.add(prefix.concat([['k', 'export']]), atom, 'export',
        `${modifiers}import= ${renderAtom(atom)}=${
          node.moduleReference.kind === ts.SyntaxKind.ExternalModuleReference
            ? `require(${renderExpr(node.moduleReference.expression)})`
            : renderEntityName(node.moduleReference)}`);
      return;
    }
    default:
      // Imports, expression statements, and every other statement form: not
      // this module's declarations. Bodies are the work the gate exists to
      // permit, and a declaration inside one is a body-local name.
      return;
  }
}

// The export surface, as symbols under `k:export`. An import is what this
// module consumes and is out; an export is what it PROMISES, and
// `export { h as run }` breaks every importer while touching no declaration.
function collectExportDeclaration(node, prefix, collector) {
  const specifier = node.moduleSpecifier ? node.moduleSpecifier.text : null;
  const typeOnly = node.isTypeOnly ? ['type'] : [];
  const exportPrefix = prefix.concat([['k', 'export']]);
  const from = specifier === null ? '' : ` from ${JSON.stringify(specifier)}`;

  if (!node.exportClause) {
    // `export * from './m'`. The specifier is a `s` segment, so its `/`
    // characters are escaped by symbolKey and cannot spell the separator.
    collector.add(
      exportPrefix.concat([['k', 'star']]),
      segment('s', specifier === null ? '@none' : specifier),
      'export',
      `${slot(typeOnly)}export *${from}`,
    );
    return;
  }
  if (node.exportClause.kind === ts.SyntaxKind.NamespaceExport) {
    // `export * as ns from './m'`
    const atom = nameAtomOf(node.exportClause.name);
    collector.add(exportPrefix, atom, 'export',
      `${slot(typeOnly)}export * as ${renderAtom(atom)}${from}`);
    return;
  }
  for (const element of node.exportClause.elements) {
    const exported = nameAtomOf(element.name);
    const local = nameAtomOf(element.propertyName || element.name);
    collector.add(exportPrefix, exported, 'export',
      `${slot(element.isTypeOnly ? typeOnly.concat(['type']) : typeOnly)}export ${
        renderAtom(exported)}<-${renderAtom(local)}${from}`);
  }
}

// A namespace is a declaration SCOPE, not a type expression, and it is
// rendered as its own modifiers and name and NOTHING about its members.
//
// That is a deliberate departure from the class rule, and the reason is that
// the file's top level is the same kind of scope: adding a top-level
// declaration is ruled NOT a change, and a `namespace N { … }` wrapper must
// not make the identical code stricter purely because it is nested. Nothing is
// lost, and no name-only rendering position is created: every member of a
// namespace is a DECLARATION and therefore always has a sub-symbol of its own
// carrying its full signature. Removing one is a removed symbol, which is a
// change; renaming one is a removal plus an addition, which is a change.
function collectModule(node, prefix, collector) {
  let moduleSegment;
  if (node.flags & ts.NodeFlags.GlobalAugmentation) {
    moduleSegment = ['k', 'global'];
  } else if (node.name && node.name.kind === ts.SyntaxKind.StringLiteral) {
    moduleSegment = segment('s', node.name.text);
  } else {
    moduleSegment = nameAtomOf(node.name);
  }
  collector.add(prefix, moduleSegment, 'module',
    `${modifierSlot(node)}namespace ${renderAtom(moduleSegment)}`);

  const inner = prefix.concat([moduleSegment]);
  const body = node.body;
  if (!body) return;
  if (body.kind === ts.SyntaxKind.ModuleDeclaration) {
    // `namespace N.M { … }` — flattened, so the key nests exactly as a nested
    // block would.
    collectModule(body, inner, collector);
    return;
  }
  collectStatements(body.statements, inner, collector);
}

// --------------------------------------------------------------------------
// the entry point
// --------------------------------------------------------------------------

function scriptKindOf(filePath) {
  // THE DIALECT COMES FROM THE PATH, and it is not cosmetic: `const x =
  // <T>(y);` is a type assertion in `.ts` and an unterminated JSX element in
  // `.tsx` (measured). A helper that guessed would mis-read 475 of the primary
  // target's 996 files.
  return filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
}

// Returns {symbols} or {parseError}. Exported for the soak driver, which needs
// the SAME renderer the gate uses rather than a second one.
function fingerprintSource(filePath, source) {
  unknownKinds = new Set();
  const sourceFile = ts.createSourceFile(
    filePath,
    source,
    ts.ScriptTarget.Latest,
    /* setParentNodes */ true,
    scriptKindOf(filePath),
  );

  // The diagnostics channel is LOAD-BEARING: a recovered parse is not a
  // conservative answer, it is a SMALLER one, and if the base revision is the
  // damaged one every declaration it dropped is ADDED at head — which is not a
  // change. A parser build that cannot expose this must fail loudly rather
  // than proceed assuming the parse was clean.
  const diagnostics = sourceFile.parseDiagnostics;
  if (!Array.isArray(diagnostics)) {
    throw new HelperBug(
      'this parser build does not expose sourceFile.parseDiagnostics, so a ' +
        'recovered parse would be indistinguishable from a clean one',
    );
  }
  if (diagnostics.length) {
    const first = diagnostics[0];
    return {
      parseError: `${ts.flattenDiagnosticMessageText(first.messageText, ' ')} (at ${
        first.start}, ${diagnostics.length} diagnostic${
        diagnostics.length === 1 ? '' : 's'})`,
    };
  }

  const collector = new Collector();
  collectStatements(sourceFile.statements, [], collector);
  return { symbols: collector.symbols(), unknownKinds: [...unknownKinds].sort() };
}

function respond(raw) {
  if (!raw.length) {
    throw new HelperBug(`empty request on stdin; expected one ${SCHEMA} object`);
  }
  let request;
  try {
    request = JSON.parse(raw);
  } catch (error) {
    throw new HelperBug(`request is not well-formed JSON: ${error.message}`);
  }
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    throw new HelperBug('request is not a JSON object');
  }
  if (request.schema !== SCHEMA) {
    throw new HelperBug(
      `request schema ${JSON.stringify(request.schema)} is not ${
        JSON.stringify(SCHEMA)}; a helper and a caller that disagree about the ` +
        'grammar would compare fingerprints that mean different things',
    );
  }
  if (typeof request.path !== 'string' || typeof request.source !== 'string') {
    throw new HelperBug('request.path and request.source must both be strings');
  }

  const result = fingerprintSource(request.path, request.source);
  // symbols and parse_error are MUTUALLY EXCLUSIVE; the caller refuses a
  // document carrying both, and correctly.
  return result.parseError !== undefined
    ? { schema: SCHEMA, parse_error: result.parseError }
    : { schema: SCHEMA, symbols: result.symbols };
}

function main(argv) {
  if (argv.includes('--probe')) {
    process.stdout.write(
      `${JSON.stringify({ node: process.versions.node, typescript: ts.version })}\n`,
    );
    return 0;
  }
  let raw;
  try {
    raw = require('fs').readFileSync(0, 'utf8');
  } catch (error) {
    process.stderr.write(`ts_signature_fingerprint: cannot read stdin: ${error}\n`);
    return 1;
  }
  try {
    process.stdout.write(`${JSON.stringify(respond(raw))}\n`);
  } catch (error) {
    process.stderr.write(
      `ts_signature_fingerprint: ${error && error.message ? error.message : error}\n`,
    );
    return 1;
  }
  return 0;
}

module.exports = { SCHEMA, fingerprintSource, symbolKey, respond };

if (require.main === module) {
  process.exitCode = main(process.argv.slice(2));
}
