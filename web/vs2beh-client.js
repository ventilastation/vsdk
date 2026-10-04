// Client for the `vs2beh` wire protocol (T11), used by the VS2 behaviors
// inspector panel (T12).
//
// Spec: docs/vs2-behaviors-proposal.md, "## The live-tune loop". T11 (a
// sibling Wave-5 task, apps/micropython/ventilastation/behavior_control.py)
// owns the device-side handler; this module only owns the browser side of
// the documented text protocol, in the same `handle_command(parts, send,
// scene)` shape `povcal`/`povperf`/`hallfilter` already use on the device:
//
//   > vs2beh list
//   {"subjects":[{"name":"enemies","kind":"pool","count":6,
//     "vars":[...], "behaviors":[{"name":"damageable","class":"Damageable",
//     "params":[...], "actions":[...]}]}]}
//
//   > vs2beh set enemies.damageable.hp 2
//   vs2beh_ok enemies.damageable.hp=2
//
// This module never assumes anything about *how* a line reaches the device
// -- that is a Transport, an object with one async method:
//
//   transport.sendLine(text) -> Promise<string>   // the single reply line
//
// A real device's reply may legitimately span framing the caller's own
// transport already unwraps (the same way `comms.send()` on the device
// side already frames a line plus an optional binary payload) -- this
// module only ever deals in the already-unwrapped text.

/**
 * Build the exact text line `vs2beh set <path> <value>` sends over the
 * wire. `value` is JSON-stringified when it is not already a primitive
 * that reads back unambiguously as one token -- matching the protocol
 * sample's `vs2beh set enemies.damageable.hp 2` (a bare number, no
 * quoting). A string value that itself contains whitespace would break
 * the space-split parser `_dispatch_control()` uses on the device
 * (`cmd_line.split()`), so this function rejects that case rather than
 * emit a line the device could never parse correctly.
 */
export function buildSetCommand(path, value) {
  const token = encodeValueToken(value);
  return `vs2beh set ${path} ${token}`;
}

export function buildResetCommand(path) {
  return `vs2beh reset ${path}`;
}

export function buildListCommand() {
  return "vs2beh list";
}

function encodeValueToken(value) {
  let token;
  if (typeof value === "string") {
    token = value;
  } else {
    token = JSON.stringify(value);
  }
  if (/\s/.test(token)) {
    throw new Error(
      `vs2beh set value must not contain whitespace once encoded (got ${JSON.stringify(value)})`
    );
  }
  return token;
}

/**
 * Parse a `vs2beh list` reply (a single line of JSON) into the same shape
 * the wire sends, with no transformation -- kept as its own function so
 * callers (and tests) don't have to know the reply is "just JSON" today
 * versus whatever framing a real device might add tomorrow.
 *
 * @param {string} replyText
 * @returns {{subjects: Array}}
 */
export function parseListReply(replyText) {
  const parsed = JSON.parse(replyText);
  if (!parsed || !Array.isArray(parsed.subjects)) {
    throw new Error("vs2beh list reply missing a subjects array");
  }
  return parsed;
}

const OK_PATTERN = /^vs2beh_ok\s+(\S+)=(\S+)$/;
const ERROR_PATTERN = /^vs2beh_error\s+(.*)$/;

/**
 * Parse a `vs2beh set`/`vs2beh reset` reply line: either
 * `vs2beh_ok <path>=<value>` or `vs2beh_error <message>` (the documented
 * "an unknown path returns an error naming the closest valid one" case).
 *
 * @param {string} replyText
 * @returns {{ok: true, path: string, value: string} | {ok: false, error: string}}
 */
export function parseSetReply(replyText) {
  const okMatch = OK_PATTERN.exec(replyText.trim());
  if (okMatch) {
    return { ok: true, path: okMatch[1], value: okMatch[2] };
  }
  const errorMatch = ERROR_PATTERN.exec(replyText.trim());
  if (errorMatch) {
    return { ok: false, error: errorMatch[1] };
  }
  throw new Error(`unrecognised vs2beh reply: ${JSON.stringify(replyText)}`);
}

// ---------------------------------------------------------------------------
// Two-level tree shape: subjects, then each subject's vars/behaviors, with
// a behavior's params and nested actions as leaves. This is what the panel
// renders -- see buildSubjectTree() in vs2-behavior-panel.js -- kept here
// as a pure transform so it is Node-testable without a DOM.
// ---------------------------------------------------------------------------

/**
 * Flatten a parsed `list` reply into an array of `{path, param}` leaves --
 * every pool/scene/project variable and every behavior parameter, each
 * carrying its fully-qualified `vs2beh set` path. A tree UI groups these
 * back up by subject and behavior for display; this function only needs
 * to get every leaf's path right once.
 *
 * @param {{subjects: Array}} listResult
 * @returns {{subjectName: string, subjectKind: string, groupName: string|null,
 *   groupClass: string|null, kind: "var"|"param"|"action-param",
 *   actionName: string|null, path: string, param: Object}[]}
 */
export function flattenSubjects(listResult) {
  const leaves = [];
  for (const subject of listResult.subjects) {
    for (const v of subject.vars || []) {
      leaves.push({
        subjectName: subject.name,
        subjectKind: subject.kind,
        groupName: null,
        groupClass: null,
        actionName: null,
        kind: "var",
        path: `${subject.name}.${v.name}`,
        param: v,
      });
    }
    for (const behavior of subject.behaviors || []) {
      for (const p of behavior.params || []) {
        leaves.push({
          subjectName: subject.name,
          subjectKind: subject.kind,
          groupName: behavior.name,
          groupClass: behavior.class,
          actionName: null,
          kind: "param",
          path: `${subject.name}.${behavior.name}.${p.name}`,
          param: p,
        });
      }
      for (const action of behavior.actions || []) {
        for (const p of action.params || []) {
          leaves.push({
            subjectName: subject.name,
            subjectKind: subject.kind,
            groupName: behavior.name,
            groupClass: behavior.class,
            actionName: action.name,
            kind: "action-param",
            path: `${subject.name}.${behavior.name}.${action.name}.${p.name}`,
            param: p,
          });
        }
      }
    }
  }
  return leaves;
}

/**
 * The client itself: wraps a Transport and exposes list()/set()/reset() as
 * promises resolving to already-parsed values. Every attribute a game
 * exposes to the panel is addressed the same way, with no per-type
 * handling here either -- this module only ever moves a path and a value.
 */
export class VS2BehClient {
  /**
   * @param {{sendLine: (text: string) => Promise<string>}} transport
   */
  constructor(transport) {
    this.transport = transport;
  }

  async list() {
    const reply = await this.transport.sendLine(buildListCommand());
    return parseListReply(reply);
  }

  async set(path, value) {
    const reply = await this.transport.sendLine(buildSetCommand(path, value));
    const parsed = parseSetReply(reply);
    if (!parsed.ok) {
      throw new Error(`vs2beh set ${path} failed: ${parsed.error}`);
    }
    return parsed;
  }

  async reset(path) {
    const reply = await this.transport.sendLine(buildResetCommand(path));
    const parsed = parseSetReply(reply);
    if (!parsed.ok) {
      throw new Error(`vs2beh reset ${path} failed: ${parsed.error}`);
    }
    return parsed;
  }
}
