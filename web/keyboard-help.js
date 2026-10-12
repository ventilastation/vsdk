import { keyboardInputForCode } from "./app-support.js?v=20260717b";

export class KeyboardHelp {
  constructor(dialog, button, resetKeyboard) {
    this.dialog = dialog;
    this.button = button;
    this.resetKeyboard = resetKeyboard;
    this.held = new Set();
    this.blocked = new Set();
    this.keycaps = new Map();
    button.addEventListener("click", () => this.toggle());
    dialog.querySelector("[data-close-help]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("cancel", event => { event.preventDefault(); dialog.close(); });
    dialog.addEventListener("close", () => {
      for (const code of this.held) this.blocked.add(code);
      this.held.clear();
      this.resetKeyboard();
      button.setAttribute("aria-expanded", "false");
      document.querySelector("#frame-canvas-gl:not([hidden]), #frame-canvas-2d:not([hidden])")?.focus({preventScroll: true});
    });
  }

  async load() {
    const response = await fetch(new URL("./keyboard-layout.json?v=source", import.meta.url));
    if (!response.ok) throw new Error("Keyboard layout could not be loaded.");
    const layout = await response.json();
    for (const player of [1, 2]) {
      const board = this.dialog.querySelector(`[data-keyboard-player="${player}"]`);
      board.style.aspectRatio = `${layout.width} / ${layout.height}`;
      for (const entry of [...layout.context, ...layout.keys].filter(key => key.player === player)) {
        const cap = document.createElement("span");
        cap.className = `keyboard-key${entry.code ? "" : " keyboard-key-context"}${entry.key.length > 3 ? " keyboard-key-long" : ""}`;
        cap.style.left = `${entry.x / layout.width * 100}%`;
        cap.style.top = `${entry.y / layout.height * 100}%`;
        cap.style.width = `${(entry.w || 1) / layout.width * 100}%`;
        cap.style.height = `${(entry.h || 1) / layout.height * 100}%`;
        const key = document.createElement("kbd");
        key.textContent = entry.key;
        cap.append(key);
        if (entry.code) {
          const control = document.createElement("span");
          control.textContent = entry.control;
          cap.append(control);
          cap.dataset.code = entry.code;
          this.keycaps.set(entry.code, cap);
        } else {
          cap.setAttribute("aria-hidden", "true");
        }
        board.append(cap);
      }
    }
    this.dialog.querySelector(".keyboard-help-status").hidden = true;
  }

  toggle() {
    if (this.dialog.open) {
      this.dialog.close();
      return;
    }
    for (const code of this.resetKeyboard() || []) this.blocked.add(code);
    for (const cap of this.keycaps.values()) cap.classList.remove("is-held");
    this.dialog.showModal();
    this.button.setAttribute("aria-expanded", "true");
    if (!this.loading) {
      this.loading = this.load().catch(error => {
        this.dialog.querySelector(".keyboard-help-status").textContent = error.message;
      });
    }
  }

  keydown(event) {
    if (event.code === "F1") {
      event.preventDefault();
      if (!event.repeat) this.toggle();
      return true;
    }
    if (this.blocked.has(event.code)) { event.preventDefault(); return true; }
    if (!this.dialog.open) return false;
    if (event.code === "Escape") {
      event.preventDefault();
      this.blocked.add(event.code);
      this.dialog.close();
    } else if (keyboardInputForCode(event.code)) {
      event.preventDefault();
      this.held.add(event.code);
      this.keycaps.get(event.code)?.classList.add("is-held");
    }
    return true;
  }

  keyup(event) {
    const blocked = this.blocked.delete(event.code);
    this.held.delete(event.code);
    this.keycaps.get(event.code)?.classList.remove("is-held");
    return blocked || this.dialog.open;
  }

  releaseAll() {
    this.held.clear();
    this.blocked.clear();
    for (const cap of this.keycaps.values()) cap.classList.remove("is-held");
  }
}
