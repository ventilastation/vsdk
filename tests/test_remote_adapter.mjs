// Binary framing checks for the browser remote-workbench adapter.

globalThis.window = { location: { search: "", hash: "", pathname: "/", href: "https://example.test/" } };
globalThis.history = { replaceState() {} };
globalThis.sessionStorage = { getItem() { return null; }, removeItem() {} };

const { REMOTE_PROTOCOL } = await import(new URL("../web/remote-adapter.js", import.meta.url));

function assert(value, message = "assertion failed") {
  if (!value) {
    throw new Error(message);
  }
}

function testRoundTrip() {
  const input = new Uint8Array([1, 2, 3]);
  const message = REMOTE_PROTOCOL.decodeMessage(REMOTE_PROTOCOL.encodeMessage(REMOTE_PROTOCOL.TYPES.INPUT, 42, input));
  assert(message.type === REMOTE_PROTOCOL.TYPES.INPUT);
  assert(message.sequence === 42);
  assert(message.payload.length === 3 && message.payload[2] === 3);
}

function testRejectsCorruptLength() {
  const encoded = new Uint8Array(REMOTE_PROTOCOL.encodeMessage(REMOTE_PROTOCOL.TYPES.HELLO, 1, new Uint8Array([9])));
  encoded[16] = 99;
  let threw = false;
  try {
    REMOTE_PROTOCOL.decodeMessage(encoded.buffer);
  } catch (_error) {
    threw = true;
  }
  assert(threw, "corrupt declared length must be rejected");
}

for (const test of [testRoundTrip, testRejectsCorruptLength]) {
  test();
  console.log("ok", test.name);
}
