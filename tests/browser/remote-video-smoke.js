import { LedRingWebGLRenderer } from "../../web/led-ring-renderers.js?v=remote-video-smoke";

const CODED_WIDTH = 162;
const CODED_HEIGHT = 256;
const LOGICAL_WIDTH = 54;

function stage(value) {
  document.querySelector("#result").textContent = value;
}

function paintPackedFrame(canvas) {
  const context = canvas.getContext("2d", { alpha: false });
  const image = context.createImageData(CODED_WIDTH, CODED_HEIGHT);
  const colors = [
    [255, 0, 0],
    [0, 255, 0],
    [0, 0, 255],
    [255, 255, 0],
    [255, 0, 255],
    [0, 255, 255],
  ];
  for (let y = 0; y < CODED_HEIGHT; y += 1) {
    for (let logicalX = 0; logicalX < LOGICAL_WIDTH; logicalX += 1) {
      const rgb = colors[(logicalX + Math.floor(y / 32)) % colors.length];
      for (let component = 0; component < 3; component += 1) {
        const value = rgb[component];
        const offset = (y * CODED_WIDTH + logicalX * 3 + component) * 4;
        image.data[offset] = value;
        image.data[offset + 1] = value;
        image.data[offset + 2] = value;
        image.data[offset + 3] = 255;
      }
    }
  }
  context.putImageData(image, 0, 0);
}

function waitForDecodedFrame(video) {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("decoded frame timeout")), 10000);
    const done = (_now, metadata) => {
      window.clearTimeout(timeout);
      resolve(metadata);
    };
    if (typeof video.requestVideoFrameCallback === "function") {
      video.requestVideoFrameCallback(done);
    } else {
      video.addEventListener("loadeddata", () => done(0, {}), { once: true });
    }
  });
}

function waitForIceGathering(peer) {
  if (peer.iceGatheringState === "complete") {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("ICE gathering timeout")), 10000);
    peer.addEventListener("icegatheringstatechange", () => {
      if (peer.iceGatheringState === "complete") {
        window.clearTimeout(timeout);
        resolve();
      }
    });
  });
}

async function negotiatedCodec(peer) {
  const report = await peer.getStats();
  for (const item of report.values()) {
    if (item.type !== "inbound-rtp" || item.kind !== "video") {
      continue;
    }
    return report.get(item.codecId)?.mimeType || "unknown";
  }
  return "missing";
}

async function run() {
  stage("creating packed source");
  const source = document.createElement("canvas");
  source.width = CODED_WIDTH;
  source.height = CODED_HEIGHT;
  paintPackedFrame(source);
  const stream = source.captureStream(30);
  const sender = new RTCPeerConnection({ iceServers: [] });
  const receiver = new RTCPeerConnection({ iceServers: [] });
  window.smokeDebug = { sender, receiver };
  const video = document.createElement("video");
  window.smokeDebug.video = video;
  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;
  const trackPromise = new Promise((resolve) => {
    receiver.addEventListener("track", (event) => resolve(event.track), { once: true });
  });
  const transceiver = sender.addTransceiver(stream.getVideoTracks()[0], { direction: "sendonly" });
  const h264 = RTCRtpSender.getCapabilities("video").codecs.filter(
    (codec) => codec.mimeType.toLowerCase() === "video/h264",
  );
  if (!h264.length) {
    throw new Error("browser has no H.264 encoder");
  }
  transceiver.setCodecPreferences(h264);
  stage("gathering sender ICE");
  await sender.setLocalDescription(await sender.createOffer());
  await waitForIceGathering(sender);
  stage("creating H.264 answer");
  await receiver.setRemoteDescription(sender.localDescription);
  const receiverTransceiver = receiver.getTransceivers()[0];
  const receiverH264 = RTCRtpReceiver.getCapabilities("video").codecs.filter(
    (codec) => codec.mimeType.toLowerCase() === "video/h264",
  );
  receiverTransceiver.setCodecPreferences(receiverH264);
  const answer = await receiver.createAnswer();
  await receiver.setLocalDescription(answer);
  stage("gathering receiver ICE");
  await waitForIceGathering(receiver);
  await sender.setRemoteDescription(receiver.localDescription);
  stage("waiting for decoded H.264 frame");
  video.srcObject = new MediaStream([await trackPromise]);
  const sourceTrack = stream.getVideoTracks()[0];
  const frameTimer = window.setInterval(() => {
    paintPackedFrame(source);
    sourceTrack.requestFrame?.();
  }, 33);
  await Promise.race([
    video.play(),
    new Promise((_resolve, reject) => {
      window.setTimeout(() => reject(new Error("video play timeout")), 10000);
    }),
  ]);
  const metadata = await waitForDecodedFrame(video);
  window.clearInterval(frameTimer);
  const ring = document.querySelector("#ring");
  const renderer = new LedRingWebGLRenderer(ring);
  renderer.setDisplaySize(640, 640);
  const rendered = renderer.renderVideoFrame(video);
  const glError = renderer.gl.getError();
  const result = {
    ok: rendered && glError === renderer.gl.NO_ERROR,
    codec: await negotiatedCodec(receiver),
    videoWidth: video.videoWidth,
    videoHeight: video.videoHeight,
    presentedFrames: Number(metadata.presentedFrames) || null,
    renderProfile: renderer.lastProfile,
    glError,
  };
  document.querySelector("#result").textContent = JSON.stringify(result, null, 2);
  document.documentElement.dataset.smoke = result.ok ? "passed" : "failed";
  stream.getTracks().forEach((track) => track.stop());
  sender.close();
  receiver.close();
}

run().catch(async (error) => {
  const debug = window.smokeDebug || {};
  const detail = {
    error: error.stack || String(error),
    senderConnection: debug.sender?.connectionState,
    senderIce: debug.sender?.iceConnectionState,
    receiverConnection: debug.receiver?.connectionState,
    receiverIce: debug.receiver?.iceConnectionState,
    videoReadyState: debug.video?.readyState,
    videoSize: debug.video ? [debug.video.videoWidth, debug.video.videoHeight] : null,
  };
  document.querySelector("#result").textContent = JSON.stringify(detail, null, 2);
  document.documentElement.dataset.smoke = "failed";
});
