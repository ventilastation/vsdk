// Remote physical-workbench adapter. It implements the same frame/input shape
// as the WASM adapter, but its frames arrive from the authenticated gateway.

const MAGIC = "VSRW";
const VERSION = 1;
const HEADER_BYTES = 20;
const TYPES = Object.freeze({
  HELLO: 0x01,
  FRAME_RGB: 0x02,
  HOST_EVENT: 0x03,
  STATUS: 0x04,
  ERROR: 0x05,
  LEASE: 0x06,
  INPUT: 0x10,
  FRAME_ACK: 0x11,
  HEARTBEAT: 0x12,
  LEASE_REQUEST: 0x13,
  OPERATOR_COMMAND: 0x14,
});
const INPUT_EXIT_EDGE = 0x01;
const DEFAULT_GATEWAY = "https://ventilastation-board.protocultura.net";

function gatewayUrl() {
  const configured = window.VENTILASTATION_REMOTE_GATEWAY;
  return String(configured || DEFAULT_GATEWAY).replace(/\/$/u, "");
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

async function inflate(data) {
  if (typeof DecompressionStream !== "function") {
    throw new Error("This browser cannot decode compressed remote frames");
  }
  const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
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
    this.connected = false;
    this.inputTimer = null;
    this.heartbeatTimer = null;
    this.decodeChain = Promise.resolve();
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
    this.sendInput();
  }

  async stopLoop() {
    this.stopTimers();
    this.sendInput(true);
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
  }

  close() {
    this.stopTimers();
    this.sendInput(true);
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
        this.leaseGeneration = status.lease_generation ?? null;
        this.emitStatus(status);
        return;
      }
      if (message.type === TYPES.STATUS || message.type === TYPES.LEASE) {
        const status = decodeJson(message.payload);
        this.leaseGeneration = status.holder && status.holder === this.email
          ? (status.generation ?? null)
          : null;
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
      if (message.type === TYPES.FRAME_RGB) {
        await this.emitFrame(message);
      }
    }).catch((error) => this.emitError(error));
  }

  async emitFrame(message) {
    const view = new DataView(message.payload.buffer, message.payload.byteOffset, message.payload.byteLength);
    if (message.payload.length < 8 || view.getUint16(0, true) !== 256 || view.getUint16(2, true) !== 54 || view.getUint8(4) !== 1) {
      throw new Error("Unsupported physical-board frame format");
    }
    const codec = view.getUint8(5);
    let rgb = message.payload.slice(8);
    if (codec === 1) {
      rgb = await inflate(rgb);
    } else if (codec !== 0) {
      throw new Error("Unsupported physical-board frame codec");
    }
    if (rgb.length !== 256 * 54 * 3) {
      throw new Error("Physical-board frame has an invalid RGB length");
    }
    const frame = {
      frame: message.sequence,
      events: [{ command: "frame_rgb", args: [], data: rgb }],
      sprites: [],
      assets: [],
    };
    for (const listener of this.frameListeners) {
      listener(frame);
    }
    const ack = new Uint8Array(8);
    const ackView = new DataView(ack.buffer);
    ackView.setUint32(0, message.sequence, true);
    ackView.setUint32(4, 0, true);
    this.send(TYPES.FRAME_ACK, ack);
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
});
