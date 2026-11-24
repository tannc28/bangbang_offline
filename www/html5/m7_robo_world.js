import {visualPosition, visualXY, cooldownView} from './combat_state.js';
import {aiNpcTemplate, actorLifeBarVisible} from './tank_appearance.js';
import {createRoboFloat, sampleRoboFloat} from './m7_robo_floats.js';
import {resourceSequence} from './battle_effects.js';
import {vietnameseNpcName} from './m81331_locale.js';

const UI = 'zh_CN/gui_summer/controls/gameplay/';
const clamp = (number, min, max) => Math.max(min, Math.min(max, number));
const BUBBLE_MS = 5000, BUBBLE_MAX_WIDTH = 200, BUBBLE_LIFT = 58, BUBBLE_SELF_LIFT = 82;
const QUAN_VU_TANK_ID = 10000056;
const QUAN_VU_HINT_BUFF = 990056;
const MISSING_HP_FINISHERS = new Set([10000102, 10000070, 10000048, 10000082, 10000107]);

/** Original Robo presentation drawn at its native world coordinates.
 * Health, life epochs, visibility and identities are read from native packets.
 * Actor labels are submitted within the actor layer, before foreground props.
 */
export class RoboWorld {
  constructor(view) {
    this.view = view; this.catalog = null;
    this.textures = new Map(); this.bubbleKeys = []; this.measureCtx = null;
    this.hpTrails = new Map();
    this.selfLife = null; this.selfStartedAt = 0;
    this.floats = []; this.floatMutex = ''; this.floatMutexAt = 0; this.floatHistory = [];
    this.speakers = [];
    this.drawn = {airMarker: false, selfMarker: false, spawnArrow: false, minimap: false};
  }

  setCatalog(catalog) { this.catalog = catalog; }

  clear() {
    for (const image of this.textures.values()) this.view.surface.releaseTexture(image);
    this.textures.clear(); this.bubbleKeys = []; this.hpTrails.clear();
    this.selfLife = null; this.selfStartedAt = 0; this.speakers = [];
    this.floats = []; this.floatMutex = ''; this.floatMutexAt = 0; this.floatHistory = [];
    this.drawn = {airMarker: false, selfMarker: false, spawnArrow: false, minimap: false};
  }

  asset(logical) { return this.catalog?.assets?.[logical] || null; }

  image(asset) {
    if (!asset) return null;
    const image = this.view.store.image(asset);
    if (!image) this.view.store.requestImage(asset);
    return image;
  }

  drawImage(asset, x, y, {center = false, alpha = 1} = {}) {
    if (!asset) return false;
    return this.view.drawFrame(asset, {sx: 0, sy: 0, w: asset.width, h: asset.height,
      offsetX: center ? -asset.width / 2 : 0, offsetY: center ? -asset.height / 2 : 0}, x, y, 0, alpha);
  }

  drawCanvas(image, x, y, alpha = 1) {
    const pos = this.view.screenPoint(x + image.width / 2, y + image.height / 2);
    const zoom = this.view.camera.zoom;
    this.view.surface.draw(image, {sw: image.width, sh: image.height,
      x: pos.x, y: pos.y, width: image.width * zoom, height: image.height * zoom, alpha});
  }

  /** Speech bubble texture: word-wrapped text in a rounded box with a tail, border by camp. */
  bubbleTexture(text, border) {
    const key = `bubble:${border}:${text}`;
    if (this.textures.has(key)) return this.textures.get(key);
    const font = 'bold 14px Tahoma, Arial, sans-serif', pad = 7, line = 18, tail = 8;
    const measure = (this.measureCtx ??= document.createElement('canvas').getContext('2d'));
    measure.font = font;
    const lines = [];
    for (const word of text.split(/\s+/).filter(Boolean)) {
      const last = lines.length ? lines[lines.length - 1] : null;
      if (last != null && measure.measureText(`${last} ${word}`).width <= BUBBLE_MAX_WIDTH) lines[lines.length - 1] = `${last} ${word}`;
      else lines.push(word);
    }
    if (!lines.length) return null;
    const width = Math.ceil(Math.min(BUBBLE_MAX_WIDTH, Math.max(...lines.map(row => measure.measureText(row).width))) + pad * 2);
    const height = lines.length * line + pad * 2;
    const image = document.createElement('canvas'), c = image.getContext('2d');
    image.width = width + 4; image.height = height + tail + 4;
    c.translate(2, 2);
    c.beginPath(); c.roundRect(0, 0, width, height, 8);
    c.moveTo(width / 2 - 7, height); c.lineTo(width / 2, height + tail); c.lineTo(width / 2 + 7, height);
    c.fillStyle = 'rgba(255,255,255,.93)'; c.fill();
    c.lineWidth = 2; c.strokeStyle = border; c.stroke();
    c.fillStyle = 'rgba(255,255,255,.93)'; c.fillRect(width / 2 - 6, height - 2, 12, 3);
    c.font = font; c.textBaseline = 'top'; c.fillStyle = '#151515';
    lines.forEach((row, index) => c.fillText(row, pad, pad + index * line, BUBBLE_MAX_WIDTH));
    this.textures.set(key, image);
    this.bubbleKeys.push(key);
    if (this.bubbleKeys.length > 48) {
      const oldKey = this.bubbleKeys.shift();
      const oldImg = this.textures.get(oldKey);
      if (oldImg) { this.view.surface.releaseTexture(oldImg); this.textures.delete(oldKey); }
    }
    return image;
  }

  /** Latest chat line of each tank drawn this frame, above its tank, on top of the actor layer. */
  drawChatBubbles(state, now) {
    const speakers = this.speakers; this.speakers = [];
    const chat = state.chat || [];
    if (!chat.length) return;
    const ownCamp = state.actors[String(state.selfObjectId)]?.camp;
    for (const {actor, position} of speakers) {
      let row = null;
      for (const item of chat) if (item.speakerId === actor.objectId && now - item.receivedAt < BUBBLE_MS) row = item;
      if (!row) continue;
      const self = actor.objectId === state.selfObjectId;
      const border = self ? '#2fae25' : actor.camp === ownCamp ? '#1f8fd0' : '#d8332a';
      const image = this.bubbleTexture(row.text, border);
      if (!image) continue;
      const age = now - row.receivedAt, alpha = age > BUBBLE_MS - 600 ? (BUBBLE_MS - age) / 600 : 1;
      this.drawCanvas(image, position.x - image.width / 2, position.y - (self ? BUBBLE_SELF_LIFT : BUBBLE_LIFT) - image.height, alpha);
    }
  }

  effect(name, now, start = this.view.animationStart, {loop = true} = {}) {
    const sequence = this.catalog?.effects?.[name];
    if (!sequence?.frames?.length) return null;
    const index = Math.floor(Math.max(0, now - start) / sequence.frameMs);
    if (!loop && index >= sequence.frames.length) return null;
    return {sequence, index: loop ? index % sequence.frames.length : index};
  }

  drawAirMarker() {
    const map = this.catalog?.maps?.[String(this.view.prepared?.map?.mapId)];
    this.drawn.airMarker = false;
    for (const point of map?.airPoints || []) {
      this.drawn.airMarker = this.drawImage(map.airMarker, point.x, point.y, {center: true}) || this.drawn.airMarker;
    }
  }

  grid(maxHp, execRatio = 0, bonusRatio = 0) {
    const key = `life-grid:${maxHp}:${execRatio}:${bonusRatio}`;
    if (!this.textures.has(key)) {
      const image = document.createElement('canvas'); image.width = 72; image.height = 14;
      const c = image.getContext('2d');
      if (maxHp > 0) {
        // MOBA Minor & Major HP segmentation so high-HP Lv5/Lv6 tanks stay readable.
        const minorUnit = maxHp <= 9000 ? 500 : maxHp <= 18000 ? 1000 : 2500;
        const majorUnit = maxHp <= 9000 ? 1000 : maxHp <= 18000 ? 2000 : 5000;
        for (let hpMark = minorUnit; hpMark < maxHp; hpMark += minorUnit) {
          const x = Math.round(70 * hpMark / maxHp);
          if (x <= 1 || x >= 69) continue;
          const major = hpMark % majorUnit === 0;
          c.strokeStyle = major ? 'rgba(0, 0, 0, 0.95)' : 'rgba(0, 0, 0, 0.68)';
          c.lineWidth = 1;
          c.beginPath();
          c.moveTo(x + .5, 2);
          c.lineTo(x + .5, major ? 8.5 : 5.5);
          c.stroke();
        }
        if (bonusRatio > 0 && bonusRatio < 1) {
          const bx = clamp(Math.round(70 * bonusRatio), 2, 68);
          c.fillStyle = '#ffb703';
          c.fillRect(bx, 1, 1.5, 9);
        }
        if (execRatio > 0 && execRatio < 1) {
          const ex = clamp(Math.round(70 * execRatio), 2, 68);
          c.fillStyle = '#120408';
          c.fillRect(ex - 1, 0, 3, 11);
          c.fillStyle = '#ffd166';
          c.fillRect(ex, 0, 1.5, 11);
          c.fillStyle = '#ff2e4c';
          c.fillRect(ex - 1, 0, 3, 2);
        }
      }
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  trailTexture(widthPx) {
    const w = clamp(Math.round(widthPx), 2, 70);
    const key = `hp-trail:${w}`;
    if (!this.textures.has(key)) {
      const image = document.createElement('canvas'); image.width = w; image.height = 6;
      const c = image.getContext('2d');
      const grad = c.createLinearGradient(0, 0, 0, 6);
      grad.addColorStop(0, '#ffffff');
      grad.addColorStop(0.55, '#ffe8a3');
      grad.addColorStop(1, '#ff9f1c');
      c.fillStyle = grad;
      c.fillRect(0, 0, w, 6);
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  sampleDamageTrail(actor, now) {
    if (!(actor.maxHp > 0)) return null;
    const cur = clamp(actor.hp / actor.maxHp, 0, 1);
    const id = actor.objectId;
    let rec = this.hpTrails.get(id);
    if (!rec || rec.lifeEpoch !== actor.lifeEpoch || cur > rec.prevRatio) {
      rec = {lifeEpoch: actor.lifeEpoch, prevRatio: cur, trailRatio: cur, hitAt: now};
      this.hpTrails.set(id, rec);
      return null;
    }
    if (cur < rec.prevRatio - 0.004) {
      if (rec.trailRatio < rec.prevRatio) rec.trailRatio = rec.prevRatio;
      rec.prevRatio = cur;
      rec.hitAt = now;
    }
    const elapsed = Math.max(0, now - rec.hitAt);
    if (elapsed > 90) {
      const decay = Math.min(1, (elapsed - 90) / 340);
      rec.trailRatio = cur + (rec.trailRatio - cur) * (1 - decay * 0.32);
      if (elapsed >= 430 || rec.trailRatio - cur < 0.015) rec.trailRatio = cur;
    }
    const curPx = Math.trunc(cur * 70), trailPx = Math.trunc(rec.trailRatio * 70);
    return trailPx - curPx >= 2 ? {startPx: curPx, widthPx: trailPx - curPx} : null;
  }

  executeMarkerTexture(inRange) {
    const key = `exec-marker-v2:${inRange ? 'ready' : 'near'}`;
    if (!this.textures.has(key)) {
      const image = document.createElement('canvas'); image.width = 148; image.height = 86;
      const c = image.getContext('2d');
      const cx = 74;
      const borderCol = inRange ? '#ffe566' : '#ff9e80';
      c.save();
      c.shadowColor = inRange ? 'rgba(255, 23, 68, 0.95)' : 'rgba(220, 38, 38, 0.8)';
      c.shadowBlur = inRange ? 12 : 8;

      // Top royal crimson-gold banner
      const bgGrad = c.createLinearGradient(0, 6, 0, 36);
      if (inRange) {
        bgGrad.addColorStop(0, '#ff1744');
        bgGrad.addColorStop(0.55, '#b7092b');
        bgGrad.addColorStop(1, '#590416');
      } else {
        bgGrad.addColorStop(0, 'rgba(153, 27, 27, 0.94)');
        bgGrad.addColorStop(1, 'rgba(48, 8, 18, 0.94)');
      }
      c.fillStyle = bgGrad;
      c.strokeStyle = borderCol;
      c.lineWidth = inRange ? 2.6 : 2.0;
      c.beginPath();
      c.roundRect(10, 6, 128, 30, 8);
      c.fill();
      c.stroke();

      // Dramatic downward crescent-halberd execution blade-arrow
      const bladeGrad = c.createLinearGradient(0, 36, 0, 80);
      bladeGrad.addColorStop(0, inRange ? '#ffe566' : '#ffb4a2');
      bladeGrad.addColorStop(0.35, inRange ? '#ff1744' : '#e63946');
      bladeGrad.addColorStop(1, '#7f0019');
      c.fillStyle = bladeGrad;
      c.strokeStyle = borderCol;
      c.lineWidth = 2.2;
      c.beginPath();
      c.moveTo(cx - 24, 38);
      c.lineTo(cx - 9, 44);
      c.lineTo(cx - 14, 54);
      c.lineTo(cx, 80);
      c.lineTo(cx + 14, 54);
      c.lineTo(cx + 9, 44);
      c.lineTo(cx + 24, 38);
      c.closePath();
      c.fill();
      c.stroke();
      c.restore();

      // Glowing white-gold center spine along the execution blade
      c.strokeStyle = inRange ? '#fffbeb' : '#ffe4e6';
      c.lineWidth = 2.2;
      c.beginPath();
      c.moveTo(cx, 40);
      c.lineTo(cx, 73);
      c.stroke();

      // High-contrast large banner text
      c.font = inRange ? '900 15.5px Tahoma, Arial, sans-serif' : 'bold 13.5px Tahoma, Arial, sans-serif';
      c.textAlign = 'center';
      c.textBaseline = 'middle';
      c.lineJoin = 'round';
      c.strokeStyle = '#240008';
      c.lineWidth = 4;
      const label = inRange ? '🗡 TRẢM NGAY!' : '⚔ ĐỦ 30% TRẢM';
      c.strokeText(label, cx, 21.5);
      c.fillStyle = inRange ? '#fff7bd' : '#ffe4e6';
      c.fillText(label, cx, 21.5);

      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  executeRingTexture() {
    const key = 'exec-lock-ring-v2';
    if (!this.textures.has(key)) {
      const image = document.createElement('canvas'); image.width = 126; image.height = 126;
      const c = image.getContext('2d');
      const cx = 63, cy = 63;
      c.save();
      c.shadowColor = 'rgba(255, 23, 68, 0.9)';
      c.shadowBlur = 8;
      // Outer dashed crimson-gold lock circle
      c.beginPath();
      c.arc(cx, cy, 48, 0, Math.PI * 2);
      c.strokeStyle = 'rgba(255, 229, 102, 0.92)';
      c.lineWidth = 2.6;
      c.setLineDash([14, 8]);
      c.stroke();
      c.setLineDash([]);
      c.beginPath();
      c.arc(cx, cy, 43, 0, Math.PI * 2);
      c.strokeStyle = 'rgba(255, 23, 68, 0.78)';
      c.lineWidth = 1.8;
      c.stroke();
      // 4 diagonal Pyke-X inward execution blades
      for (let i = 0; i < 4; i += 1) {
        c.save();
        c.translate(cx, cy);
        c.rotate(Math.PI / 4 + i * (Math.PI / 2));
        c.beginPath();
        c.moveTo(57, -6);
        c.lineTo(35, 0);
        c.lineTo(57, 6);
        c.lineTo(52, 0);
        c.closePath();
        c.fillStyle = '#ff1744';
        c.strokeStyle = '#ffe566';
        c.lineWidth = 1.6;
        c.fill();
        c.stroke();
        c.restore();
      }
      c.restore();
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  executeBarGlowTexture(inRange) {
    const key = `exec-bar-glow:${inRange ? 'ready' : 'near'}`;
    if (!this.textures.has(key)) {
      const image = document.createElement('canvas'); image.width = 80; image.height = 19;
      const c = image.getContext('2d');
      c.save();
      c.shadowColor = inRange ? 'rgba(255, 23, 68, 0.95)' : 'rgba(255, 183, 3, 0.8)';
      c.shadowBlur = 5;
      c.strokeStyle = inRange ? '#ffe566' : '#ff6b6b';
      c.lineWidth = inRange ? 2.2 : 1.6;
      c.strokeRect(3, 3, 74, 13);
      c.restore();
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  ccBarTexture(kind, widthPx) {
    const w = clamp(Math.round(widthPx), 2, 54);
    const key = `cc-bar:${kind}:${w}`;
    if (!this.textures.has(key)) {
      const palette = {
        stun: ['#fff3b0', '#ffb703'],
        freeze: ['#e0f7ff', '#38bdf8'],
        root: ['#fde68a', '#f59e0b'],
        silence: ['#f5d0fe', '#c084fc'],
      }[kind] || ['#fff3b0', '#ffb703'];
      const image = document.createElement('canvas'); image.width = 58; image.height = 5;
      const c = image.getContext('2d');
      c.fillStyle = 'rgba(8, 12, 20, 0.86)';
      c.fillRect(0, 0, 56, 5);
      const grad = c.createLinearGradient(1, 1, 1, 4);
      grad.addColorStop(0, palette[0]); grad.addColorStop(1, palette[1]);
      c.fillStyle = grad;
      c.fillRect(1, 1, w, 3);
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  activeCcStatus(actor, catalog, now) {
    let best = null;
    for (const buff of Object.values(actor.buffs || {})) {
      const dur = Number(buff.durationMs);
      if (!(dur > 0 && dur < 20000) || !Number.isFinite(buff.receivedAt)) continue;
      const rem = buff.receivedAt + dur - now;
      if (rem <= 40) continue;
      const row = catalog?.buffs?.[String(buff.templateId)];
      const eff = Number(row?.nEffectType);
      let kind = null;
      if (eff === 30 || eff === 62) kind = Number(row?.nBuffShowType) === 3 ? 'freeze' : 'stun';
      else if (eff === 36) kind = 'root';
      else if (eff === 35 || eff === 66) kind = 'silence';
      if (kind && (!best || rem > best.rem)) best = {kind, fraction: clamp(rem / dur, 0, 1), rem};
    }
    return best;
  }

  shieldTexture(widthPx) {
    const w = clamp(Math.round(widthPx), 2, 70);
    const key = `shield-bar:${w}`;
    if (!this.textures.has(key)) {
      const image = document.createElement('canvas'); image.width = 72; image.height = 6;
      const c = image.getContext('2d');
      c.fillStyle = 'rgba(6, 18, 32, 0.85)';
      c.fillRect(0, 0, w + 2, 5);
      const grad = c.createLinearGradient(1, 1, 1, 4);
      grad.addColorStop(0, '#ffffff');
      grad.addColorStop(1, '#7dd3fc');
      c.fillStyle = grad;
      c.fillRect(1, 1, w, 3);
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  minimapPingTexture(kind) {
    const key = `minimap-ping:${kind}`;
    if (!this.textures.has(key)) {
      const stroke = ({atk: '#ff4d4d', bak: '#ffd166', mst: '#38bdf8'})[kind] || '#38bdf8';
      const image = document.createElement('canvas'); image.width = 28; image.height = 28;
      const c = image.getContext('2d');
      c.beginPath(); c.arc(14, 14, 11, 0, Math.PI * 2);
      c.strokeStyle = stroke; c.lineWidth = 2.5; c.stroke();
      c.beginPath(); c.arc(14, 14, 4, 0, Math.PI * 2);
      c.fillStyle = '#fff'; c.fill();
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  nameTexture(actor, state, ai) {
    const self = actor.objectId === state.selfObjectId;
    const ownCamp = state.actors[String(state.selfObjectId)]?.camp;
    const color = self ? '#48dd3b' : actor.camp === 0 ? '#ffff00'
      : actor.camp === ownCamp ? '#28baee' : '#ff0000';
    const text = vietnameseNpcName(actor,ai);
    if (!text) return null;
    const streak = !ai ? (Number(state.streaks?.[String(actor.objectId)]) || 0) : 0;
    const streakTag = streak >= 3 ? ` 🔥${streak}` : '';
    // ResModel.getSmallVipLevelImage uses VipData.SUPER_VIP_OFFSET=100.
    const vipLevel = Number(actor.vipLevel) || 0, offset = this.catalog?.vip?.superOffset || 100;
    const vip = !ai && vipLevel > 0
      ? this.catalog?.vip?.[vipLevel >= offset ? 'super' : 'normal']?.[String(vipLevel % offset)] : null;
    const vipImage = this.image(vip);
    const key = `name:${text}:${color}:${vipImage ? vip.sha256 : ''}:${streakTag}`;
    if (!this.textures.has(key)) {
      const image = document.createElement('canvas'), c = image.getContext('2d');
      c.font = 'bold 16px Tahoma, Arial, sans-serif';
      const textWidth = c.measureText(text).width;
      const streakWidth = streakTag ? c.measureText(streakTag).width : 0;
      const vipW = vipImage ? vip.width + 2 : 0;
      const totalWidth = textWidth + vipW + streakWidth;
      image.width = Math.ceil(totalWidth + 8); image.height = 30;
      c.font = 'bold 16px Tahoma, Arial, sans-serif'; c.textBaseline = 'top';
      c.strokeStyle = '#000'; c.lineWidth = 2; c.lineJoin = 'round'; c.fillStyle = color;
      c.strokeText(text, 2, 2); c.fillText(text, 2, 2);
      if (vipImage) c.drawImage(vipImage, Math.trunc(textWidth) + 4, 7);
      if (streakTag) {
        const sx = Math.trunc(textWidth + vipW) + 3;
        c.fillStyle = streak >= 5 ? '#ff7b29' : '#ffd15c';
        c.strokeText(streakTag, sx, 2); c.fillText(streakTag, sx, 2);
      }
      image.nativeOffsetX = -Math.trunc(totalWidth / 2) - 2;
      this.textures.set(key, image);
    }
    return this.textures.get(key);
  }

  drawActor(actor, state, now) {
    if (actor.dead || actor.removed) return;
    const view = this.view, catalog = view.prepared.catalog, ai = aiNpcTemplate(catalog, actor);
    const shadow = Number(ai?.nType) === 4;
    const isNpc = !!ai && !shadow;
    const selfActor = state.actors[String(state.selfObjectId)];
    const self = actor.objectId === state.selfObjectId;
    const ownCamp = selfActor?.camp;
    const isEnemyHero = !isNpc && actor.camp !== 0 && actor.camp !== ownCamp;
    const position = visualXY(actor, now);
    const x = position.x + (isNpc ? -36 : -22), y = position.y + 63;
    if (actorLifeBarVisible(catalog, actor) && actor.maxHp > 0) {
      const color = self ? 'green' : actor.camp === 0 ? 'yellow' : actor.camp === ownCamp ? 'blue' : 'red';
      const sequence = this.catalog?.effects?.[`life_${color}`];
      // MathScriptTemplate301 (last ordinal) defines VAL1=25 for the current client.
      if (!isNpc && Math.trunc(actor.hp * 100 / actor.maxHp) <= 25) {
        const warn = this.effect('life_warn', now);
        if (warn) view.drawSequence(warn.sequence, warn.index, x, y);
      }
      if (sequence) {
        const nativeFrame = Math.trunc(actor.hp * 70 / actor.maxHp);
        const index = clamp(nativeFrame - 1, 0, sequence.frames.length - 1);
        view.drawSequence(sequence, index, x, y);
        if (!isNpc) {
          const trail = this.sampleDamageTrail(actor, now);
          if (trail) this.drawCanvas(this.trailTexture(trail.widthPx), x + 1 + trail.startPx, y + 2, 0.92);
        }
        const selfTank = Number(selfActor?.tankId);
        const execRatio = isEnemyHero && selfTank === QUAN_VU_TANK_ID ? 0.30 : 0;
        const bonusRatio = isEnemyHero
          ? (selfTank === QUAN_VU_TANK_ID ? 0.50 : MISSING_HP_FINISHERS.has(selfTank) ? 0.30 : 0) : 0;
        this.drawCanvas(this.grid(actor.maxHp, execRatio, bonusRatio), x, y);
      }
      if (actor.shield > 0) {
        const shieldW = Math.max(3, Math.trunc(clamp(actor.shield / actor.maxHp, 0, 1) * 70));
        this.drawCanvas(this.shieldTexture(shieldW), x, y - 4);
      }
      if (!isNpc) {
        const cc = this.activeCcStatus(actor, catalog, now);
        if (cc) {
          const ccY = actor.shield > 0 ? y - 9 : y - 5;
          this.drawCanvas(this.ccBarTexture(cc.kind, Math.max(2, Math.round(cc.fraction * 54))), x + 7, ccY);
        }
      }
      if (isEnemyHero && !shadow) {
        const serverExec = Object.values(actor.buffs || {}).some(b => Number(b.templateId) === QUAN_VU_HINT_BUFF);
        const approachExec = !serverExec && Number(selfActor?.tankId) === QUAN_VU_TANK_ID
          && !selfActor.dead && actor.hp <= actor.maxHp * 0.30
          && !!cooldownView(state, selfActor.objectId, 2, now)?.ready;
        if (serverExec || approachExec) {
          const pulse = 0.5 + 0.5 * Math.sin(now / 85);
          // 1. Glowing gold-crimson frame around the enemy's HP bar
          const barGlow = this.executeBarGlowTexture(serverExec);
          this.drawCanvas(barGlow, x - 4, y - 3, serverExec ? (0.85 + 0.15 * pulse) : 0.78);
          // 2. Pyke-X / Target Lock crosshair ring right on the enemy tank body when in Space range
          if (serverExec) {
            const ring = this.executeRingTexture();
            const ringScale = 0.94 + 0.12 * pulse;
            this.drawCanvas(ring, position.x - ring.width / 2, position.y - ring.height / 2,
              0.82 + 0.18 * pulse, ringScale);
          }
          // 3. Large bouncing crimson-gold overhead guillotine blade-arrow
          const bounce = Math.sin(now / 95) * (serverExec ? 7.5 : 4.5);
          const marker = this.executeMarkerTexture(serverExec);
          const markerScale = serverExec ? (1.0 + 0.12 * pulse) : 0.90;
          this.drawCanvas(marker, position.x - marker.width / 2, position.y - 114 + bounce,
            serverExec ? 1 : 0.92, markerScale);
        }
      }
    }
    if (!isNpc && actor.maxMp > 0) {
      this.drawImage(this.asset(`${UI}img_mp_bg.png`), position.x - 22, position.y + 76);
      const progress = this.asset(`${UI}img_mp_bar.png`);
      if (progress) {
        const width = Math.max(0, Math.trunc(progress.width * clamp(actor.mp / actor.maxMp, 0, 1)));
        if (width) view.drawFrame(progress, {sx: 0, sy: 0, w: width, h: progress.height,
          offsetX: 0, offsetY: 0}, position.x - 20, position.y + 78);
      }
    }
    if (!isNpc) this.speakers.push({actor, position});
    if (!ai || Number(ai.isShowName) === 1) {
      const name = this.nameTexture(actor, state, ai);
      if (name) this.drawCanvas(name, position.x + name.nativeOffsetX,
        position.y + (!isNpc && actor.maxMp > 0 ? 82 : 72));
    }
    if (self) {
      const life = `${actor.objectId}:${actor.lifeEpoch}`;
      if (this.selfLife !== life) { this.selfLife = life; this.selfStartedAt = actor.lastSnapshotAt ?? now; }
      const spawn = this.effect('self_tank_arrow', now, this.selfStartedAt, {loop: false});
      this.drawn.spawnArrow = spawn
        ? view.drawSequence(spawn.sequence, spawn.index, position.x, position.y, 0, 1, {autoCenter: true}) : false;
    }
  }

  drawSelfMarker(state, now) {
    const actor = state.actors[String(state.selfObjectId)];
    this.drawn.selfMarker = false;
    if (!actor || actor.dead || actor.removed) return;
    const position = visualXY(actor, now);
    const effect = this.effect('self_mark', now, this.selfStartedAt);
    if (effect) this.drawn.selfMarker = this.view.drawSequence(effect.sequence, effect.index,
      Math.trunc(position.x - 46), position.y - 75);
  }

  drawMapNpc(object) {
    if (object.dead || object.removed || !(object.maxHp > 0)) return;
    const view = this.view, template = view.mapNpcTemplate(object)?.raw;
    const cannon = Number(template?.iType) === 4;
    if (!cannon && Number(template?.iCopItType) !== 1) return;
    const self = view.client.combat.actors[String(view.client.combat.selfObjectId)];
    const color = object.camp === 0 ? 'yellow' : object.camp === self.camp ? 'blue' : 'red';
    const sequence = this.catalog?.effects?.[`life_${color}`];
    if (!sequence) return;
    const x = object.x - 36, y = object.y + Math.trunc(Number(template.iImgHeight) / 2) - (cannon ? 30 : 16);
    view.drawSequence(sequence, clamp(Math.trunc(object.hp * 70 / object.maxHp) - 1, 0, sequence.frames.length - 1), x, y);
    this.drawCanvas(this.grid(object.maxHp), x, y);
  }

  consume(events) {
    const camera = this.view.roboCamera.snapshot();
    for (const event of events) {
      if (event.kind !== 'hpChange' || !event.position || !Number.isFinite(event.packet?.delta)) continue;
      const {x, y} = event.position;
      // Native ScrollTool.isInScroll tests a 36px margin at event creation.
      if (x < camera.beginX - 36 || x >= camera.beginX + camera.viewWidth + 36
          || y < camera.beginY - 36 || y >= camera.beginY + camera.viewHeight + 36) continue;
      const now = event.receivedAt, key = `${Math.trunc(x)},${Math.trunc(y)}`;
      // EffectLayer.bubbleNum owns one shared 84ms window, not a sliding
      // expiry per point. Keep its native string membership semantics.
      if (now - this.floatMutexAt > 84) { this.floatMutex = ''; this.floatMutexAt = now; }
      const duplicate = this.floatMutex.indexOf(key) !== -1;
      const record = createRoboFloat(event, now, {duplicate});
      if (!duplicate) this.floatMutex += `${key}$`;
      this.floats.push(record);
      this.floatHistory.push({nativeReceivedAt: now, delta: event.packet.delta, type: record.type,
        objectId: event.packet.objectId ?? null, glyphs: record.glyphs.map(glyph => glyph.logical)});
      if (this.floatHistory.length > 48) this.floatHistory.shift();
    }
  }

  drawFloats(now) {
    const list = this.floats;
    if (!list.length) return;
    let write = 0;
    for (let i = 0; i < list.length; i++) {
      const record = list[i];
      const sample = sampleRoboFloat(record, now);
      if (sample.expired) continue;
      list[write++] = record;
      if (!sample.visible) continue;
      for (const glyph of sample.glyphs) {
        const asset = this.asset(glyph.logical);
        if (asset) this.view.drawFrame(asset, {sx: glyph.sx, sy: glyph.sy, w: glyph.sw, h: glyph.sh,
          offsetX: glyph.offsetX, offsetY: glyph.offsetY}, sample.x, sample.y, 0, sample.alpha);
      }
    }
    list.length = write;
  }

  drawMinimap(actors, state, now) {
    const view = this.view, surface = view.surface, self = state.actors[String(state.selfObjectId)];
    const map = this.catalog?.maps?.[String(state.mapId)], background = this.image(map?.minimap);
    if (!background || !self) return;
    const left = 0, top = view.height - 211, size = 200;
    const screenImage = (image, x, y, width = image.width, height = image.height, alpha = 1) =>
      surface.draw(image, {sw: image.width, sh: image.height, x: x + width / 2,
        y: y + height / 2, width, height, alpha});
    screenImage(background, left, top, size, size);
    const sx = size / view.geometry.width, sy = size / view.geometry.height;
    const camera = view.roboCamera.snapshot();
    const frameWidth = Math.trunc(camera.viewWidth * sx), frameHeight = Math.trunc(camera.viewHeight * sy);
    const frameKey = `minimap-camera:${frameWidth}:${frameHeight}`;
    if (!this.textures.has(frameKey)) {
      // The native vector outline is rasterized only when viewport size changes.
      // Its per-frame movement and all map/icons use the main render backend.
      const frame = document.createElement('canvas'); frame.width = frameWidth + 8; frame.height = frameHeight + 8;
      const context = frame.getContext('2d');
      context.strokeStyle = '#ccff00'; context.lineWidth = 1;
      context.shadowColor = '#160000cc'; context.shadowBlur = 2;
      context.strokeRect(3.5, 3.5, frameWidth, frameHeight);
      this.textures.set(frameKey, frame);
    }
    screenImage(this.textures.get(frameKey), left + camera.beginX * sx - 3, top + camera.beginY * sy - 3);
    const draw = (asset, x, y) => {
      const image = this.image(asset);
      if (image) screenImage(image, left + x * sx - asset.width / 2, top + y * sy - asset.height / 2,
        asset.width, asset.height);
    };
    const modeResources=view.prepared.catalog.modePresentation?.resources||{};
    for(const definition of view.prepared.map.flags||[]) {
      const flag=state.flags?.[String(definition.index)]||definition;
      const color=!flag.camp?'null':flag.camp===self.camp?'blue':'red';
      draw(modeResources['small_flag_'+color],...definition.position);
      if(flag.locked)draw(modeResources.small_flag_lock,...definition.position);
    }
    for (const object of Object.values(state.objects)) {
      if (object.dead || object.removed || (object.maxHp > 0 && object.hp <= 0)) continue;
      if ((object.objectId >>> 26) === 3 && Number(view.mapNpcTemplate(object)?.raw.iType) === 4) {
        const color = object.camp === self.camp ? 'blue' : 'red';
        draw(this.asset(`${UI}cannon_${color}.png`), object.x, object.y);
      }
      if ((object.objectId >>> 26) === 3 && Number(view.mapNpcTemplate(object)?.raw.iType) === 3) {
        const sequence=resourceSequence(view.store,modeResources['small_base_'+(object.camp===self.camp?'blue':'red')]);
        if(sequence){
          const index=Math.max(0,Math.min(sequence.frames.length-1,Math.trunc(100*object.hp/object.maxHp)-1));
          const frame=sequence.frames[index],asset=frame.asset||(frame.assetIndex!=null?sequence.assets?.[frame.assetIndex]:null)||sequence.asset;
          const image=this.image(asset);
          if(image)surface.draw(image,{sx:frame.sx,sy:frame.sy,sw:frame.w,sh:frame.h,
            x:left+object.x*sx,y:top+object.y*sy,width:frame.w,height:frame.h});
        }
      }
    }
    for (const actor of actors) {
      if (actor.dead || actor.removed) continue;
      const position = visualXY(actor, now), ai = aiNpcTemplate(view.prepared.catalog, actor);
      if (ai) {
        if (Number(ai.iLifeShowType) === 1 || actor.maxHp === -1) continue;
        const color = actor.camp === 0 ? 'yellow' : actor.camp === self.camp ? 'blue' : 'red';
        draw(this.asset(`zh_CN/computer_${color}.png`), position.x, position.y);
      } else {
        const color = actor.objectId === self.objectId ? 'green' : actor.camp === self.camp ? 'blue' : 'red';
        draw(this.asset(`${UI}img_micro_${color}_bg.png`), position.x, position.y);
        draw(view.prepared.catalog.tanks?.[String(actor.tankId)]?.hudIcon, position.x, position.y);
      }
    }
    for (const sig of state.signals || []) {
      const age = now - sig.receivedAt;
      if (age < 0 || age > 3800) continue;
      const target = sig.targetId ? (state.actors[String(sig.targetId)] || state.objects[String(sig.targetId)]) : null;
      const targetPos = target && !target.removed && !target.dead ? visualXY(target, now) : null;
      const wx = targetPos ? targetPos.x : sig.x, wy = targetPos ? targetPos.y : sig.y;
      const pingImg = this.minimapPingTexture(sig.kind);
      const scale = 0.65 + ((age % 900) / 900) * 0.75;
      const w = 28 * scale;
      const alpha = age > 3000 ? (3800 - age) / 800 : 0.95;
      screenImage(pingImg, left + wx * sx - w / 2, top + wy * sy - w / 2, w, w, alpha);
    }
    this.drawn.minimap = true; this.drawn.minimapBackend = surface.backend;
  }

  snapshot() { return {...this.drawn, labelTextures: this.textures.size, activeFloats: this.floats.length,
    nativeFloatHistory: this.floatHistory.map(row => ({...row}))}; }
}
