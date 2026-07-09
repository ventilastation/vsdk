// Browser audio host: plays the sound/music/notes commands the MicroPython
// runtime emits (split out of app.js).

import {
  resolveFirstAvailableUrl,
} from "./app-support.js?v=20260709a";


class BrowserAudioHost {
  constructor(options = {}) {
    this.enabled = false;
    this.musicPlayer = null;
    this.soundCache = new Map();
    this.pendingMusic = null;
    this.readProjectFile = typeof options.readProjectFile === "function"
      ? options.readProjectFile
      : null;
  }

  enable() {
    this.enabled = true;
    if (this.pendingMusic !== null) {
      const { name, loop } = this.pendingMusic;
      this.pendingMusic = null;
      this.playMusic(name, loop);
    }
  }

  buildCandidatePaths(name) {
    const normalized = String(name).replace(/^\/+/, "");
    const slashIndex = normalized.indexOf("/");
    const slug = slashIndex === -1 ? normalized : normalized.slice(0, slashIndex);
    const rest = slashIndex === -1 ? "" : normalized.slice(slashIndex + 1);
    const slugPath = slug.replace(/\./g, "/");
    return [
      ...(rest ? [
        `games/${slugPath}/sounds/${rest}.mp3`,
        `games/${slugPath}/sounds/${rest}.mp3.wav`,
        `games/${slugPath}/sounds/${rest}.wav`,
        `games/${slugPath}/sounds/${rest}.ogg`,
        `system/shared/${slugPath}/sounds/${rest}.mp3`,
        `system/shared/${slugPath}/sounds/${rest}.mp3.wav`,
        `system/shared/${slugPath}/sounds/${rest}.wav`,
        `system/shared/${slugPath}/sounds/${rest}.ogg`,
        `system/${slugPath}/sounds/${rest}.mp3`,
        `system/${slugPath}/sounds/${rest}.mp3.wav`,
        `system/${slugPath}/sounds/${rest}.wav`,
        `system/${slugPath}/sounds/${rest}.ogg`,
      ] : []),
    ];
  }

  guessMimeType(path) {
    if (path.endsWith(".ogg")) {
      return "audio/ogg";
    }
    if (path.endsWith(".wav")) {
      return "audio/wav";
    }
    return "audio/mpeg";
  }

  decodeBase64Bytes(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  async resolveWorkspaceUrl(normalized, candidates) {
    if (!this.readProjectFile) {
      return null;
    }
    for (const path of candidates) {
      try {
        const file = await this.readProjectFile(path, "base64");
        if (!file || typeof file.content !== "string") {
          continue;
        }
        const bytes = this.decodeBase64Bytes(file.content);
        const blob = new Blob([bytes], { type: this.guessMimeType(path) });
        return URL.createObjectURL(blob);
      } catch (_error) {
        // Try the next candidate path.
      }
    }
    return null;
  }

  async resolveUrl(name) {
    const normalized = String(name).replace(/^\/+/, "");
    if (this.soundCache.has(normalized)) {
      return this.soundCache.get(normalized);
    }
    const candidates = this.buildCandidatePaths(normalized);
    const workspaceUrl = await this.resolveWorkspaceUrl(normalized, candidates);
    if (workspaceUrl) {
      this.soundCache.set(normalized, workspaceUrl);
      return workspaceUrl;
    }
    const resolved = await resolveFirstAvailableUrl(candidates, { method: "HEAD" });
    if (resolved) {
      this.soundCache.set(normalized, resolved);
      return resolved;
    }
    this.soundCache.set(normalized, null);
    return null;
  }

  resetCache() {
    for (const url of this.soundCache.values()) {
      if (typeof url === "string" && url.startsWith("blob:")) {
        URL.revokeObjectURL(url);
      }
    }
    this.soundCache.clear();
  }

  async playSound(name) {
    if (!this.enabled) {
      return;
    }
    const url = await this.resolveUrl(name);
    if (!url) {
      return;
    }
    const audio = new Audio(url);
    audio.preload = "auto";
    try {
      await audio.play();
    } catch (_error) {
      return;
    }
  }

  async playMusic(name, loop = false) {
    if (name === "off") {
      this.stopMusic();
      return;
    }
    if (!this.enabled) {
      this.pendingMusic = { name, loop };
      return;
    }
    const url = await this.resolveUrl(name);
    if (!url) {
      return;
    }
    this.stopMusic();
    const audio = new Audio(url);
    audio.preload = "auto";
    // Looping requested by the "music <track> loop" wire command (e.g. Voom).
    audio.loop = Boolean(loop);
    this.musicPlayer = audio;
    try {
      await audio.play();
    } catch (_error) {
      if (this.musicPlayer === audio) {
        this.pendingMusic = { name, loop };
      }
    }
  }

  async playNotes(folder, notes) {
    if (!this.enabled) {
      return;
    }
    for (const note of notes.split(";")) {
      if (!note) {
        continue;
      }
      this.playSound(`${folder}/${note}`);
    }
  }

  stopMusic() {
    this.pendingMusic = null;
    if (!this.musicPlayer) {
      return;
    }
    this.musicPlayer.pause();
    this.musicPlayer.currentTime = 0;
    this.musicPlayer = null;
  }
}

export { BrowserAudioHost };
