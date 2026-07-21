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

function testSelectsOnlyH264VideoCodecs() {
  globalThis.RTCRtpReceiver = {
    getCapabilities() {
      return {
        codecs: [
          { mimeType: "video/VP8" },
          { mimeType: "video/H264", sdpFmtpLine: "profile-level-id=42e01f" },
          { mimeType: "video/rtx" },
        ],
      };
    },
  };
  const codecs = REMOTE_PROTOCOL.h264CodecPreferences();
  assert(codecs.length === 1);
  assert(codecs[0].mimeType === "video/H264");
}

function testSelectsGatewayFromQuery() {
  window.location.search = "?remote=1&gateway=https%3A%2F%2Ffresh-tunnel.example";
  assert(REMOTE_PROTOCOL.gatewayUrl() === "https://fresh-tunnel.example");
  window.location.search = "";
}

function testRejectsUnsafeGateway() {
  window.location.search = "?gateway=http%3A%2F%2Fpublic.example";
  let threw = false;
  try {
    REMOTE_PROTOCOL.gatewayUrl();
  } catch (_error) {
    threw = true;
  }
  assert(threw, "a public plaintext gateway must be rejected");
  window.location.search = "";
}

for (const test of [
  testRoundTrip,
  testRejectsCorruptLength,
  testSelectsOnlyH264VideoCodecs,
  testSelectsGatewayFromQuery,
  testRejectsUnsafeGateway,
]) {
  test();
  console.log("ok", test.name);
}
