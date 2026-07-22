// Remote physical-workbench adapter. It implements the same frame/input shape
// as the WASM adapter, but its frames arrive from the authenticated gateway.

const MAGIC = "VSRW";
const VERSION = 1;
const HEADER_BYTES = 20;
const TYPES = Object.freeze({
  HELLO: 0x01,
  HOST_EVENT: 0x03,
  STATUS: 0x04,
  ERROR: 0x05,
  LEASE: 0x06,
  INPUT: 0x10,
  HEARTBEAT: 0x12,
  LEASE_REQUEST: 0x13,
  OPERATOR_COMMAND: 0x14,
  VIDEO_OFFER: 0x20,
  VIDEO_ANSWER: 0x21,
  VIDEO_STATUS: 0x22,
  VIDEO_STOP: 0x23,
});
const INPUT_EXIT_EDGE = 0x01;
const VIDEO_WIDTH = 162;
const VIDEO_HEIGHT = 256;
const VIDEO_LOGICAL_WIDTH = 54;
const VIDEO_LOGICAL_HEIGHT = 256;
// This version is deliberately included in signaling. A stale gateway or tab
// must reject the stream rather than render a different packing as RGB.
const VIDEO_PACKING = "rgb-luma-planes-v2";
// The stable gateway terminates Google OAuth and forwards signaling over FRP.
// Operators may override it before loading the emulator for a staged endpoint.
const DEFAULT_GATEWAY = "https://ventilastation-board.protocultura.net";

function gatewayUrl() {
  const queryGateway = new URLSearchParams(window.location.search).get("gateway");
  const configured = queryGateway || window.VENTILASTATION_REMOTE_GATEWAY || DEFAULT_GATEWAY;
  let parsed;
  try {
    parsed = new URL(String(configured));
  } catch (_error) {
    throw new Error("The remote gateway URL is invalid");
  }
  const localHttp = parsed.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
  const unsafe = parsed.username || parsed.password || parsed.search || parsed.hash;
  if (unsafe || (parsed.protocol !== "https:" && !localHttp)) {
    throw new Error("The remote gateway must be an HTTPS origin");
  }
  return parsed.origin;
}

function socketUrl(base) {
  return base.replace(/^http/u, "ws") + "/ws";
}

function encodeMessage(type, sequence, payload = new Uint8Array(), flags = 0) {
  const data = payload instanceof Uint8Array ? payload : new Uint8Array(payload);
  const out = new Uint8Array(HEADER_BYTES + data.length);
  const view = new DataView(out.buffer);
  out.set([...MAGIC].map((value) => value.charCodeAt(0)), 0);
  view.setUint8(4, VERSION);
  view.setUint8(5, type);
  view.setUint16(6, flags, true);
  view.setUint32(8, sequence >>> 0, true);
  view.setUint32(12, Math.floor(performance.now()) >>> 0, true);
  view.setUint32(16, data.length, true);
  out.set(data, HEADER_BYTES);
  return out.buffer;
}

function decodeMessage(buffer) {
  const data = new Uint8Array(buffer);
  if (data.length < HEADER_BYTES) {
    throw new Error("Remote message is shorter than its header");
  }
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const magic = String.fromCharCode(...data.slice(0, 4));
  const version = view.getUint8(4);
  const length = view.getUint32(16, true);
  if (magic !== MAGIC || version !== VERSION || length !== data.length - HEADER_BYTES) {
    throw new Error("Invalid remote message");
  }
  return {
    type: view.getUint8(5),
    flags: view.getUint16(6, true),
    sequence: view.getUint32(8, true),
    timestampMs: view.getUint32(12, true),
    payload: data.slice(HEADER_BYTES),
  };
}

function jsonPayload(value) {
  return new TextEncoder().encode(JSON.stringify(value));
}

function decodeJson(data) {
  return JSON.parse(new TextDecoder().decode(data));
}

function h264CodecPreferences() {
  const capabilities = globalThis.RTCRtpReceiver?.getCapabilities?.("video");
  return (capabilities?.codecs || []).filter((codec) => (
    String(codec.mimeType || "").toLowerCase() === "video/h264"
  ));
}

function waitForIceGatheringComplete(peer, timeoutMs = 10000) {
  if (peer.iceGatheringState === "complete") {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      peer.removeEventListener("icegatheringstatechange", changed);
      reject(new Error("Timed out gathering WebRTC candidates"));
    }, timeoutMs);
    const changed = () => {
      if (peer.iceGatheringState !== "complete") {
        return;
      }
      window.clearTimeout(timeout);
      peer.removeEventListener("icegatheringstatechange", changed);
      resolve();
    };
    peer.addEventListener("icegatheringstatechange", changed);
  });
}

function takeTicketFromLocation() {
  const saved = sessionStorage.getItem("ventilastation.remote.ticket");
  if (saved) {
    sessionStorage.removeItem("ventilastation.remote.ticket");
    return saved;
  }
  const params = new URLSearchParams(window.location.hash.slice(1));
  const ticket = params.get("remote_ticket");
  if (ticket) {
    history.replaceState(null, "", `${location.pathname}${location.search}`);
  }
  return ticket;
}

export class RemoteWorkbenchAdapter {
  static async requestTicket() {
    const base = gatewayUrl();
    const expectedOrigin = new URL(base).origin;
    const popup = window.open(`${base}/auth/start`, "ventilastation-remote-auth", "popup,width=520,height=680");
    if (!popup) {
      throw new Error("Your browser blocked the sign-in popup");
    }
    const ticket = await new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        window.removeEventListener("message", receive);
        reject(new Error("Timed out waiting for Google sign-in"));
      }, 65000);
      const receive = (event) => {
        if (event.origin !== expectedOrigin || event.data?.type !== "ventilastation-remote-ticket" || typeof event.data.ticket !== "string") {
          return;
        }
        window.clearTimeout(timeout);
        window.removeEventListener("message", receive);
        resolve(event.data.ticket);
      };
      window.addEventListener("message", receive);
    });
    sessionStorage.setItem("ventilastation.remote.ticket", ticket);
    return ticket;
  }

  constructor(ticket = takeTicketFromLocation()) {
    this.name = "Physical workbench";
    this.usesWorkerFrameStream = true;
    this.ticket = ticket;
    this.socket = null;
    this.frameListeners = new Set();
    this.hostEventListeners = new Set();
    this.errorListeners = new Set();
    this.statusListeners = new Set();
    this.sequence = 0;
    this.input = { joy1: 0, joy2: 0, extra: 0, exit: false };
    this.leaseGeneration = null;
    this.role = null;
    this.email = null;
    this.boardConnected = null;
    this.connected = false;
    this.inputTimer = null;
    this.heartbeatTimer = null;
    this.decodeChain = Promise.resolve();
    this.videoConfig = null;
    this.videoPeer = null;
    this.videoTransceiver = null;
    this.videoElement = null;
    this.videoTrack = null;
    this.videoState = "stopped";
    this.videoFrameCallbackId = null;
    this.videoFrameSequence = 0;
    this.lastVideoTime = -1;
    this.videoStats = null;
    this.videoStatsTimer = null;
  }

  async init() {
    if (!this.ticket) {
      throw new Error("Choose Connect physical board first");
    }
    await this.connect();
    return this;
  }

  connect() {
    if (this.socket?.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    const url = `${socketUrl(gatewayUrl())}?ticket=${encodeURIComponent(this.ticket)}`;
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(url);
      socket.binaryType = "arraybuffer";
      let opened = false;
      socket.addEventListener("open", () => {
        opened = true;
        this.socket = socket;
        this.connected = true;
        this.ticket = null;
        this.emitStatus({ state: "connected" });
        resolve();
      }, { once: true });
      socket.addEventListener("message", (event) => this.receive(event.data));
      socket.addEventListener("close", () => {
        this.connected = false;
        this.leaseGeneration = null;
        this.stopTimers();
        this.stopVideo(false);
        this.emitStatus({ state: "disconnected" });
        if (!opened) {
          reject(new Error("Physical board connection was rejected"));
        }
      });
      socket.addEventListener("error", () => {
        if (!opened) {
          reject(new Error("Could not connect to the physical board"));
        }
      });
    });
  }

  async startLoop() {
    this.stopTimers();
    this.inputTimer = window.setInterval(() => this.sendInput(), 1000 / 30);
    this.heartbeatTimer = window.setInterval(() => this.sendHeartbeat(), 5000);
    this.videoStatsTimer = window.setInterval(() => void this.collectVideoStats(), 5000);
    this.sendInput();
    if (this.videoConfig && !this.videoPeer) {
      try {
        await this.startVideo(this.videoConfig);
      } catch (error) {
        this.emitError(error);
      }
    }
  }

  async stopLoop() {
    this.stopTimers();
    this.sendInput(true);
    this.stopVideo(true);
  }

  stopTimers() {
    if (this.inputTimer !== null) {
      window.clearInterval(this.inputTimer);
      this.inputTimer = null;
    }
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.videoStatsTimer !== null) {
      window.clearInterval(this.videoStatsTimer);
      this.videoStatsTimer = null;
    }
  }

  close() {
    this.stopTimers();
    this.sendInput(true);
    this.stopVideo(true);
    this.socket?.close();
  }

  setInput(joy1, joy2 = 0, extra = 0, exit = false) {
    this.input = { joy1: joy1 & 0x7F, joy2: joy2 & 0x7F, extra: extra & 0x7F, exit: Boolean(exit) };
    this.sendInput();
  }

  requestControl() {
    this.send(TYPES.LEASE_REQUEST, jsonPayload({ action: "request" }));
  }

  releaseControl() {
    this.send(TYPES.LEASE_REQUEST, jsonPayload({ action: "release" }));
  }

  resetBoard() {
    this.operatorCommand({ action: "reset" });
  }

  setRpm(rpm) {
    this.operatorCommand({ action: "rpm", rpm: Number(rpm) });
  }

  operatorCommand(command) {
    if (this.leaseGeneration === null) {
      return;
    }
    this.send(TYPES.OPERATOR_COMMAND, jsonPayload({ ...command, lease_generation: this.leaseGeneration }));
  }

  onFrame(listener) {
    this.frameListeners.add(listener);
    return () => this.frameListeners.delete(listener);
  }

  onRuntimeError(listener) {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  onHostEvent(listener) {
    this.hostEventListeners.add(listener);
    return () => this.hostEventListeners.delete(listener);
  }

  onStatus(listener) {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  ensureVideoElement() {
    if (this.videoElement) {
      return this.videoElement;
    }
    const video = document.createElement("video");
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;
    video.setAttribute("aria-hidden", "true");
    video.style.position = "fixed";
    video.style.left = "-10000px";
    video.style.top = "0";
    video.style.width = `${VIDEO_WIDTH}px`;
    video.style.height = "256px";
    video.style.pointerEvents = "none";
    document.body.append(video);
    this.videoElement = video;
    return video;
  }

  async startVideo(config = this.videoConfig) {
    if (!config || this.videoPeer || !this.connected) {
      return;
    }
    if (config.transport !== "webrtc" || String(config.codec).toUpperCase() !== "H264") {
      throw new Error("The remote gateway did not offer H.264 WebRTC video");
    }
    if (
      Number(config.width) !== VIDEO_WIDTH
      || Number(config.height) !== VIDEO_HEIGHT
      || Number(config.logicalWidth) !== VIDEO_LOGICAL_WIDTH
      || Number(config.logicalHeight) !== VIDEO_LOGICAL_HEIGHT
      || config.packing !== VIDEO_PACKING
    ) {
      throw new Error(
        `Remote video packing ${config.packing || "missing"} does not match ${VIDEO_PACKING}; reload the emulator and restart the gateway`,
      );
    }
    if (typeof RTCPeerConnection !== "function") {
      throw new Error("This browser does not support WebRTC video");
    }
    const h264 = h264CodecPreferences();
    if (!h264.length) {
      throw new Error("This browser has no H.264 WebRTC decoder");
    }
    this.videoConfig = config;
    const peer = new RTCPeerConnection({ iceServers: config.iceServers || [] });
    this.videoPeer = peer;
    this.videoState = "signaling";
    const transceiver = peer.addTransceiver("video", { direction: "recvonly" });
    transceiver.setCodecPreferences(h264);
    this.videoTransceiver = transceiver;
    peer.addEventListener("track", (event) => {
      void this.attachVideoTrack(event.track).catch((error) => this.emitError(error));
    }, { once: true });
    peer.addEventListener("connectionstatechange", () => {
      if (this.videoPeer !== peer) {
        return;
      }
      this.videoState = peer.connectionState;
      this.emitStatus({ state: "video", video_state: this.videoState, video_codec: "H264" });
      if (["failed", "closed"].includes(peer.connectionState)) {
        this.stopVideo(false);
      }
    });
    try {
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      await waitForIceGatheringComplete(peer);
      this.send(TYPES.VIDEO_OFFER, jsonPayload({
        type: peer.localDescription.type,
        sdp: peer.localDescription.sdp,
      }));
    } catch (error) {
      this.stopVideo(false);
      throw error;
    }
  }

  async finishVideo(answer) {
    const peer = this.videoPeer;
    if (!peer || answer?.type !== "answer" || typeof answer.sdp !== "string") {
      throw new Error("Invalid WebRTC video answer");
    }
    if (
      String(answer.codec).toUpperCase() !== "H264"
      || Number(answer.width) !== VIDEO_WIDTH
      || Number(answer.height) !== VIDEO_HEIGHT
      || Number(answer.logicalWidth) !== VIDEO_LOGICAL_WIDTH
      || Number(answer.logicalHeight) !== VIDEO_LOGICAL_HEIGHT
      || answer.packing !== VIDEO_PACKING
    ) {
      throw new Error(
        `Negotiated video packing ${answer?.packing || "missing"} does not match ${VIDEO_PACKING}; reload the emulator and restart the gateway`,
      );
    }
    await peer.setRemoteDescription({ type: answer.type, sdp: answer.sdp });
  }

  async attachVideoTrack(track) {
    if (track.kind !== "video" || !this.videoPeer) {
      return;
    }
    this.videoTrack = track;
    const video = this.ensureVideoElement();
    video.srcObject = new MediaStream([track]);
    await video.play();
    this.scheduleVideoFrame();
  }

  scheduleVideoFrame() {
    const video = this.videoElement;
    if (!video || !this.videoPeer || this.videoFrameCallbackId !== null) {
      return;
    }
    const emit = (_now, metadata = {}) => {
      this.videoFrameCallbackId = null;
      if (!this.videoPeer || !this.videoElement || this.videoElement.readyState < 2) {
        return;
      }
      this.videoFrameSequence = (this.videoFrameSequence + 1) >>> 0;
      const frame = {
        frame: Number(metadata.presentedFrames) || this.videoFrameSequence,
        povVideoFrame: this.videoElement,
        videoMetadata: {
          codec: "H264",
          packing: this.videoConfig?.packing || VIDEO_PACKING,
          width: Number(metadata.width) || this.videoElement.videoWidth,
          height: Number(metadata.height) || this.videoElement.videoHeight,
          mediaTime: Number(metadata.mediaTime) || this.videoElement.currentTime,
          processingDuration: Number(metadata.processingDuration) || 0,
        },
        events: [],
        sprites: [],
        assets: [],
      };
      for (const listener of this.frameListeners) {
        listener(frame);
      }
      this.scheduleVideoFrame();
    };
    if (typeof video.requestVideoFrameCallback === "function") {
      this.videoFrameCallbackId = video.requestVideoFrameCallback(emit);
      return;
    }
    this.videoFrameCallbackId = window.requestAnimationFrame((now) => {
      if (video.currentTime === this.lastVideoTime) {
        this.videoFrameCallbackId = null;
        this.scheduleVideoFrame();
        return;
      }
      this.lastVideoTime = video.currentTime;
      emit(now);
    });
  }

  stopVideo(signalGateway = false) {
    if (signalGateway) {
      this.send(TYPES.VIDEO_STOP, new Uint8Array());
    }
    const video = this.videoElement;
    if (video && this.videoFrameCallbackId !== null) {
      if (typeof video.cancelVideoFrameCallback === "function") {
        video.cancelVideoFrameCallback(this.videoFrameCallbackId);
      } else {
        window.cancelAnimationFrame(this.videoFrameCallbackId);
      }
    }
    this.videoFrameCallbackId = null;
    this.videoTrack = null;
    if (video) {
      video.pause();
      video.srcObject = null;
    }
    const peer = this.videoPeer;
    this.videoPeer = null;
    this.videoTransceiver = null;
    peer?.close();
    this.videoState = "stopped";
    this.videoStats = null;
  }

  async collectVideoStats() {
    const peer = this.videoPeer;
    if (!peer) {
      return;
    }
    let report;
    try {
      report = await peer.getStats();
    } catch (error) {
      if (this.videoPeer === peer) {
        this.emitError(error);
      }
      return;
    }
    const stats = { codec: "H264", state: peer.connectionState };
    for (const item of report.values()) {
      if (item.type === "inbound-rtp" && item.kind === "video") {
        Object.assign(stats, {
          bytesReceived: Number(item.bytesReceived) || 0,
          packetsReceived: Number(item.packetsReceived) || 0,
          packetsLost: Number(item.packetsLost) || 0,
          framesDecoded: Number(item.framesDecoded) || 0,
          framesDropped: Number(item.framesDropped) || 0,
          framesPerSecond: Number(item.framesPerSecond) || 0,
          jitter: Number(item.jitter) || 0,
        });
      }
    }
    this.videoStats = stats;
    this.emitStatus({ state: "video", video_state: this.videoState, video_stats: stats });
  }

  sendInput(forceNeutral = false) {
    if (this.leaseGeneration === null) {
      return;
    }
    const input = forceNeutral ? { joy1: 0, joy2: 0, extra: 0, exit: false } : this.input;
    const payload = new Uint8Array(8);
    const view = new DataView(payload.buffer);
    payload[0] = input.joy1;
    payload[1] = input.joy2;
    payload[2] = input.extra;
    payload[3] = input.exit ? INPUT_EXIT_EDGE : 0;
    view.setUint32(4, this.leaseGeneration, true);
    this.send(TYPES.INPUT, payload);
  }

  sendHeartbeat() {
    if (this.leaseGeneration === null) {
      return;
    }
    const payload = new Uint8Array(8);
    new DataView(payload.buffer).setUint32(0, this.leaseGeneration, true);
    this.send(TYPES.HEARTBEAT, payload);
  }

  send(type, payload) {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      return;
    }
    this.sequence = (this.sequence + 1) >>> 0;
    this.socket.send(encodeMessage(type, this.sequence, payload));
  }

  receive(buffer) {
    this.decodeChain = this.decodeChain.then(async () => {
      const message = decodeMessage(buffer);
      if (message.type === TYPES.HELLO) {
        const status = decodeJson(message.payload);
        this.role = status.role || null;
        this.email = status.email || null;
        this.boardConnected = status.board_connected ?? this.boardConnected;
        this.leaseGeneration = status.lease_generation ?? null;
        this.videoConfig = status.video || null;
        this.emitStatus(status);
        await this.startVideo(this.videoConfig);
        return;
      }
      if (message.type === TYPES.STATUS || message.type === TYPES.LEASE) {
        const status = decodeJson(message.payload);
        this.boardConnected = status.board_connected ?? this.boardConnected;
        if (message.type === TYPES.LEASE || Object.hasOwn(status, "holder")) {
          this.leaseGeneration = status.holder && status.holder === this.email
            ? (status.generation ?? null)
            : null;
        }
        this.emitStatus(status);
        return;
      }
      if (message.type === TYPES.ERROR) {
        const error = decodeJson(message.payload);
        this.emitError(new Error(error.message || error.code || "Remote gateway error"));
        return;
      }
      if (message.type === TYPES.HOST_EVENT) {
        this.emitHostEvent(message);
        return;
      }
      if (message.type === TYPES.VIDEO_ANSWER) {
        await this.finishVideo(decodeJson(message.payload));
        return;
      }
      if (message.type === TYPES.VIDEO_STATUS) {
        const status = decodeJson(message.payload);
        this.videoState = status.state || this.videoState;
        this.emitStatus({
          state: "video",
          video_state: this.videoState,
          video_codec: status.codec || "H264",
          video_packing: status.packing || this.videoConfig?.packing || null,
          video_stats: status.stats || null,
        });
        return;
      }
    }).catch((error) => this.emitError(error));
  }

  emitHostEvent(message) {
    const view = new DataView(message.payload.buffer, message.payload.byteOffset, message.payload.byteLength);
    if (message.payload.length < 7) {
      throw new Error("Invalid remote host event");
    }
    const nameLength = view.getUint8(0);
    const argsLength = view.getUint16(1, true);
    const dataLength = view.getUint32(3, true);
    if (message.payload.length !== 7 + nameLength + argsLength + dataLength) {
      throw new Error("Remote host event length mismatch");
    }
    const nameStart = 7;
    const argsStart = nameStart + nameLength;
    const dataStart = argsStart + argsLength;
    const command = new TextDecoder().decode(message.payload.slice(nameStart, argsStart));
    const args = decodeJson(message.payload.slice(argsStart, dataStart));
    const data = message.payload.slice(dataStart);
    const event = { command, args, data };
    for (const listener of this.hostEventListeners) {
      listener(event);
    }
  }

  emitStatus(status) {
    for (const listener of this.statusListeners) {
      listener(status);
    }
  }

  emitError(error) {
    for (const listener of this.errorListeners) {
      listener(error);
    }
  }
}

export function isRemoteMode() {
  return new URLSearchParams(window.location.search).get("remote") === "1";
}

export const REMOTE_PROTOCOL = Object.freeze({
  TYPES,
  encodeMessage,
  decodeMessage,
  gatewayUrl,
  h264CodecPreferences,
  VIDEO_PACKING,
});
