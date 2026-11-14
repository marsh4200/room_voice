const DOMAINS = ["light", "switch", "fan", "cover", "climate", "scene", "script", "media_player", "input_boolean", "lock", "humidifier", "vacuum"];
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const split = (v) => v.split(",").map((x) => x.trim()).filter(Boolean);

class RoomVoicePanel extends HTMLElement {
  set hass(h) {
    this._hass = h;
    if (!this._started) {
      this._started = true;
      this._start();
    }
  }

  async _start() {
    this.attachShadow({ mode: "open" });
    this._open = new Set();
    this._dirty = false;
    this._msg = "";
    try {
      this._cfg = await this._hass.callWS({ type: "room_voice/get" });
      const res = await this._hass.callWS({ type: "conversation/agent/list" });
      this._agents = (res.agents || []).filter((a) => !/room.?voice/i.test(a.name || ""));
    } catch (e) {
      this._cfg = { fallback: "", rooms: [] };
      this._agents = [];
      this._msg = "Couldn't load settings: " + (e.message || e);
    }
    this._cfg.rooms = this._cfg.rooms || [];
    this.shadowRoot.addEventListener("click", (e) => this._click(e));
    this.shadowRoot.addEventListener("change", (e) => this._change(e));
    this.shadowRoot.addEventListener("input", (e) => this._input(e));
    this._render();
  }

  _used() {
    const s = new Set();
    for (const r of this._cfg.rooms) for (const i of r.items) s.add(i.entity_id);
    return s;
  }

  _render() {
    const c = this._cfg;
    const count = c.rooms.reduce((n, r) => n + r.items.length, 0);
    this.shadowRoot.innerHTML = `
<style>
:host{display:block;padding:16px;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif);font-size:14px}
.wrap{max-width:900px;margin:0 auto}
.top{display:flex;align-items:center;gap:12px;margin-bottom:16px}
h1{font-size:22px;font-weight:500;margin:0}
.grow{flex:1}
.card{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#ddd);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.dim{color:var(--secondary-text-color);font-size:12px}
input,select{height:34px;padding:0 8px;border:1px solid var(--divider-color,#ccc);border-radius:6px;background:var(--card-background-color,#fff);color:inherit;font:inherit;min-width:0;box-sizing:border-box}
button{height:34px;padding:0 12px;border:1px solid var(--divider-color,#ccc);border-radius:6px;background:none;color:inherit;font:inherit;cursor:pointer}
button.primary{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color,#fff)}
button.x{border:0;padding:0 6px;color:var(--secondary-text-color)}
.row{display:flex;gap:8px;align-items:center}
.head{display:flex;gap:8px;align-items:center;cursor:pointer}
.head b{font-size:16px;font-weight:500}
.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,1.1fr) 30px;gap:8px;align-items:center;margin-top:8px}
.grid input{width:100%}
.mono{font-family:monospace;font-size:11px;color:var(--secondary-text-color);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.res{margin-top:6px;max-height:240px;overflow:auto}
.res div{padding:6px 8px;border-radius:6px;cursor:pointer;display:flex;gap:8px;justify-content:space-between}
.res div:hover{background:var(--secondary-background-color,#eee)}
.msg{font-size:13px;color:var(--secondary-text-color)}
</style>
<div class="wrap">
  <div class="top">
    <h1>Room voice</h1>
    <span class="dim">${c.rooms.length} rooms, ${count} items</span>
    <span class="grow"></span>
    <span class="msg">${esc(this._msg)}</span>
    <button class="primary" data-act="save">${this._dirty ? "Save changes" : "Saved"}</button>
  </div>
  <div class="card">
    <div class="dim" style="margin-bottom:6px">If it isn't about one of your rooms or items, pass it to</div>
    <select data-f="fallback" style="width:100%">
      <option value="">Nothing, say it wasn't understood</option>
      ${this._agents.map((a) => `<option value="${esc(a.id)}" ${a.id === c.fallback ? "selected" : ""}>${esc(a.name)}</option>`).join("")}
    </select>
    <div class="dim" style="margin:12px 0 6px">What it says when it's done. Leave empty to have it say what it did.</div>
    <input data-f="reply" style="width:100%" value="${esc(c.reply == null ? "Okay" : c.reply)}" placeholder="Turned off the kitchen downlights">
  </div>
  ${c.rooms.map((r, ri) => this._room(r, ri)).join("")}
  <div class="card row">
    <input class="grow" id="newroom" placeholder="Playroom">
    <button data-act="addroom">Add room</button>
  </div>
</div>`;
  }

  _room(r, ri) {
    const open = this._open.has(ri);
    return `<div class="card">
  <div class="head" data-act="toggle" data-r="${ri}">
    <b>${esc(r.name)}</b><span class="dim">${r.items.length} items</span><span class="grow"></span>
    <button class="x" data-act="delroom" data-r="${ri}" title="Delete room">Delete</button>
  </div>
  ${!open ? "" : `
  <div class="row" style="margin-top:10px">
    <input data-f="rname" data-r="${ri}" value="${esc(r.name)}" title="Room name">
    <input class="grow" data-f="raliases" data-r="${ri}" value="${esc(r.aliases.join(", "))}" placeholder="Other names for this room, comma separated">
  </div>
  ${r.items.length ? `<div class="grid dim"><span>You say</span><span>Or</span><span>Controls</span><span></span></div>` : ""}
  ${r.items.map((it, ii) => `<div class="grid">
    <input data-f="iname" data-r="${ri}" data-i="${ii}" value="${esc(it.name)}">
    <input data-f="ialiases" data-r="${ri}" data-i="${ii}" value="${esc(it.aliases.join(", "))}" placeholder="other names">
    <span class="mono" title="${esc(it.entity_id)}">${esc(it.entity_id)}</span>
    <button class="x" data-act="delitem" data-r="${ri}" data-i="${ii}" title="Remove">✕</button>
  </div>`).join("")}
  <div style="margin-top:12px">
    <input data-f="search" data-r="${ri}" style="width:100%" placeholder="Search your devices to add to ${esc(r.name)}">
    <div class="res" id="res${ri}"></div>
  </div>`}
</div>`;
  }

  _results(ri, q) {
    const box = this.shadowRoot.getElementById("res" + ri);
    if (!box) return;
    q = q.trim().toLowerCase();
    if (!q) { box.innerHTML = ""; return; }
    const used = this._used();
    const hits = Object.values(this._hass.states)
      .filter((s) => DOMAINS.includes(s.entity_id.split(".")[0]) && !used.has(s.entity_id))
      .filter((s) => s.entity_id.toLowerCase().includes(q) || String(s.attributes.friendly_name || "").toLowerCase().includes(q))
      .slice(0, 40);
    box.innerHTML = hits.length
      ? hits.map((s) => `<div data-act="additem" data-r="${ri}" data-e="${esc(s.entity_id)}"><span>${esc(s.attributes.friendly_name || s.entity_id)}</span><span class="mono">${esc(s.entity_id)}</span></div>`).join("")
      : `<span class="dim">No unused devices match.</span>`;
  }

  _touch(msg) { this._dirty = true; this._msg = msg || ""; }

  _input(e) {
    const t = e.target;
    if (t.dataset.f === "search") this._results(Number(t.dataset.r), t.value);
  }

  _change(e) {
    const t = e.target, f = t.dataset.f, c = this._cfg;
    if (!f || f === "search") return;
    const r = c.rooms[Number(t.dataset.r)], it = r && r.items[Number(t.dataset.i)];
    if (f === "fallback") c.fallback = t.value;
    else if (f === "reply") c.reply = t.value.trim();
    else if (f === "rname") r.name = t.value.trim() || r.name;
    else if (f === "raliases") r.aliases = split(t.value);
    else if (f === "iname") it.name = t.value.trim() || it.name;
    else if (f === "ialiases") it.aliases = split(t.value);
    this._touch();
    this._render();
  }

  async _click(e) {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    const act = t.dataset.act, c = this._cfg, ri = Number(t.dataset.r);
    if (act === "toggle") {
      if (e.target.closest("button")) return;
      this._open.has(ri) ? this._open.delete(ri) : this._open.add(ri);
    } else if (act === "addroom") {
      const name = this.shadowRoot.getElementById("newroom").value.trim();
      if (!name) { this._msg = "Enter a room name"; this._render(); return; }
      c.rooms.push({ name, aliases: [], items: [] });
      this._open.add(c.rooms.length - 1);
      this._touch();
    } else if (act === "delroom") {
      if (!confirm(`Delete ${c.rooms[ri].name} and its items?`)) return;
      c.rooms.splice(ri, 1);
      this._open = new Set();
      this._touch();
    } else if (act === "delitem") {
      c.rooms[ri].items.splice(Number(t.dataset.i), 1);
      this._touch();
    } else if (act === "additem") {
      const id = t.dataset.e, s = this._hass.states[id];
      const q = this.shadowRoot.querySelector(`input[data-f="search"][data-r="${ri}"]`).value;
      c.rooms[ri].items.push({ entity_id: id, name: (s && s.attributes.friendly_name) || id, aliases: [] });
      this._touch();
      this._render();
      const box = this.shadowRoot.querySelector(`input[data-f="search"][data-r="${ri}"]`);
      box.value = q;
      this._results(ri, q);
      return;
    } else if (act === "save") {
      try {
        await this._hass.callWS({ type: "room_voice/save", config: c });
        this._dirty = false;
        this._msg = "Saved";
      } catch (err) {
        this._msg = "Couldn't save: " + (err.message || err);
      }
    }
    this._render();
  }
}
customElements.define("room-voice-panel", RoomVoicePanel);
