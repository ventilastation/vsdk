import { LedRingWebGLRenderer } from "../../web/led-ring-renderers.js?v=macroblock-v4";

const CODED_WIDTH = 176;

const video = document.querySelector("#video");
const decoded = document.querySelector("#decoded");
const ring = document.querySelector("#ring");
const resultNode = document.querySelector("#result");

function waitForFrame() {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("decoded frame timeout")), 10000);
    video.requestVideoFrameCallback((_now, metadata) => {
      clearTimeout(timeout);
      resolve(metadata);
    });
  });
}

function waitForIce(peer) {
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => peer.addEventListener("icegatheringstatechange", () => {
    if (peer.iceGatheringState === "complete") resolve();
  }));
}

function planeError(data, firstPlane, secondPlane) {
  let total = 0;
  let maximum = 0;
  for (let y = 0; y < 256; y += 1) {
    for (let x = 0; x < 54; x += 1) {
      const first = data[(y * CODED_WIDTH + firstPlane * 56 + x) * 4];
      const second = data[(y * CODED_WIDTH + secondPlane * 56 + x) * 4];
      const difference = Math.abs(first - second);
      total += difference;
      maximum = Math.max(maximum, difference);
    }
  }
  return { mean: total / (256 * 54), maximum };
}

function renderedChromaError(data) {
  let lit = 0;
  let total = 0;
  let maximum = 0;
  for (let index = 0; index < data.length; index += 4) {
    const red = data[index];
    const green = data[index + 1];
    const blue = data[index + 2];
    if (Math.max(red, green, blue) < 30) continue;
    const difference = Math.max(red, green, blue) - Math.min(red, green, blue);
    lit += 1;
    total += difference;
    maximum = Math.max(maximum, difference);
  }
  return { mean: lit ? total / lit : null, maximum, lit };
}

async function run() {
  const peer = new RTCPeerConnection({ iceServers: [] });
  const transceiver = peer.addTransceiver("video", { direction: "recvonly" });
  const h264 = RTCRtpReceiver.getCapabilities("video").codecs.filter(
    (codec) => codec.mimeType.toLowerCase() === "video/h264",
  );
  transceiver.setCodecPreferences(h264);
  const track = new Promise((resolve) => peer.addEventListener(
    "track", (event) => resolve(event.track), { once: true },
  ));
  await peer.setLocalDescription(await peer.createOffer());
  await waitForIce(peer);
  const socket = new WebSocket("ws://127.0.0.1:8770");
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.send(JSON.stringify(peer.localDescription));
  const answer = await new Promise((resolve) => socket.addEventListener(
    "message", (event) => resolve(JSON.parse(event.data)), { once: true },
  ));
  await peer.setRemoteDescription(answer);
  video.srcObject = new MediaStream([await track]);
  await video.play();
  await waitForFrame();
  await waitForFrame();
  const context = decoded.getContext("2d", { willReadFrequently: true });
  context.drawImage(video, 0, 0, CODED_WIDTH, 256);
  const pixels = context.getImageData(0, 0, CODED_WIDTH, 256).data;
  const redGreen = planeError(pixels, 0, 1);
  const redBlue = planeError(pixels, 0, 2);
  const renderer = new LedRingWebGLRenderer(ring);
  renderer.setDisplaySize(600, 600);
  if (!renderer.renderVideoFrame(video)) {
    throw new Error("LED-ring WebGL renderer rejected the decoded frame");
  }
  renderer.finish();
  const ringPixels = new Uint8Array(ring.width * ring.height * 4);
  renderer.gl.readPixels(
    0, 0, ring.width, ring.height,
    renderer.gl.RGBA, renderer.gl.UNSIGNED_BYTE,
    ringPixels,
  );
  const ringChroma = renderedChromaError(ringPixels);
  const result = {
    ok: redGreen.mean < 8 && redBlue.mean < 8
      && ringChroma.lit > 100 && ringChroma.mean < 8,
    videoSize: [video.videoWidth, video.videoHeight],
    packing: answer.packing,
    redGreen,
    redBlue,
    ringChroma,
  };
  resultNode.textContent = JSON.stringify(result, null, 2);
  document.documentElement.dataset.smoke = result.ok ? "passed" : "failed";
  window.smokeResult = result;
  window.smokePeer = peer;
  window.smokeSocket = socket;
}

run().catch((error) => {
  resultNode.textContent = error.stack || String(error);
  document.documentElement.dataset.smoke = "failed";
});
