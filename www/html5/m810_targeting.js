import {visualPosition, visualXY} from './combat_state.js';
import {resourceSequence} from './battle_effects.js';

const PUBLIC_HAZARD_RADII = Object.freeze({
  388311: 120, 358305: 120, 358301: 96, 358303: 96, 358601: 196, 358602: 196, 358901: 300,
  303301: 300, 303402: 72, 306301: 264, 306311: 264, 308521: 168, 311301: 240, 312411: 192,
  313302: 192, 315303: 144, 315304: 144, 315403: 144, 318304: 144, 324301: 168, 326309: 168,
  326313: 168, 327201: 96, 328311: 120, 334306: 288, 335301: 264, 335304: 264, 340201: 108,
  349311: 192, 353301: 192, 354401: 72, 356314: 216, 357301: 144, 357304: 144, 357305: 144,
  362201: 144, 363204: 144, 368321: 196, 372201: 108, 372403: 168, 373201: 144, 373202: 144,
  374402: 120, 376401: 96, 379401: 196, 379402: 196, 380221: 192, 381301: 216, 381302: 216,
  381401: 144, 381403: 144, 382201: 144, 382301: 196, 382401: 144, 382402: 144, 384213: 144,
  8190411: 192, 8190412: 192,
});

/** SelfTank.showSkillRange; ranges are presentation metadata, never hit tests. */
export function nativeSkillPreview(skill,from,to) {
  if(!skill||!(Number(skill.iRange)>0)||!from||!to)return null;
  const type=Number(skill.iSRangeType)||0,target=Number(skill.iSType),radius=Number(skill.iSelectRange)||0;
  const param=Number(skill.iSRangeParam)||0,range=Number(skill.iRange)+(type===2?36:0);
  const dx=to.x-from.x,dy=to.y-from.y,distance=Math.hypot(dx,dy),heading=Math.atan2(dy,dx);
  const result={from,to,range,maxRing:distance>range,shape:null,heading};
  if(![0,1,10,11].includes(target))return result;
  if(type===0&&target===0)result.shape={kind:'circle',radius};
  else if(type===3)result.shape={kind:'asset',asset:'select_arrow',x:from.x,y:from.y,rotation:heading+Math.PI/2,
    scaleX:param>0&&radius>0?param/48:1,scaleY:param>0&&radius>0?radius/165:Math.min(range,Math.max(165,distance))/165};
  else if(type===1||type===5)result.shape={kind:'asset',asset:param?'select_rect':'select_arrow',x:from.x,y:from.y,
    rotation:heading+Math.PI/2,scaleX:param?param/70:1,scaleY:param?radius/225:range/165};
  else if(type===2)result.shape={kind:'sector',radius,angle:param,rotation:heading-Math.PI/2};
  else if(type===6)result.shape={kind:'asset',asset:'select_vertical_dir',x:to.x,y:to.y,
    rotation:heading-Math.PI/2,scaleX:param/215,scaleY:1};
  return result;
}

export function drawHazardTelegraphs(view, state, now) {
  const self = state.actors[String(state.selfObjectId)];
  if (!self || state.result) return;
  const c = view.context, zoom = view.camera.zoom;
  let drawnAny = false;
  for (const object of Object.values(state.objects || {})) {
    if (!object || object.removed || object.dead || !object.camp || object.camp === self.camp) continue;
    const radius = PUBLIC_HAZARD_RADII[object.templateId];
    if (!radius) continue;
    const pos = visualXY(object, now), screen = view.screenPoint(pos.x, pos.y), rScreen = radius * zoom;
    if (screen.x < -rScreen || screen.y < -rScreen || screen.x > view.width + rScreen || screen.y > view.height + rScreen) continue;
    const pulse = 0.5 + 0.5 * Math.sin(now / 120);
    if (!drawnAny) { c.save(); drawnAny = true; }
    c.beginPath();
    c.arc(screen.x, screen.y, rScreen, 0, Math.PI * 2);
    c.fillStyle = `rgba(255, 48, 48, ${(0.08 + pulse * 0.08).toFixed(3)})`;
    c.fill();
    c.lineWidth = 2;
    c.strokeStyle = `rgba(255, 86, 86, ${(0.55 + pulse * 0.35).toFixed(3)})`;
    c.setLineDash([8, 5]);
    c.stroke();
    c.setLineDash([]);
  }
  if (drawnAny) { c.restore(); view.overlayDirty = true; }
}

export function drawWorldSignals(view, state, now) {
  const signals = state.signals;
  if (!signals?.length || state.result) return;
  const c = view.context, zoom = view.camera.zoom;
  const palette = {
    atk: {stroke: '#ff5252', fill: 'rgba(255,82,82,0.22)', icon: '⚔️ TẤN CÔNG'},
    bak: {stroke: '#ffd166', fill: 'rgba(255,209,102,0.20)', icon: '🛡️ RÚT LUI'},
    mst: {stroke: '#38bdf8', fill: 'rgba(56,189,248,0.20)', icon: '📍 TẬP HỢP'},
  };
  let drawnAny = false;
  for (const sig of signals) {
    const age = now - sig.receivedAt;
    if (age < 0 || age > 3800) continue;
    const target = sig.targetId ? (state.actors[String(sig.targetId)] || state.objects[String(sig.targetId)]) : null;
    const targetPos = target && !target.removed && !target.dead ? visualXY(target, now) : null;
    const wx = targetPos ? targetPos.x : sig.x, wy = targetPos ? targetPos.y : sig.y;
    const screen = view.screenPoint(wx, wy);
    if (screen.x < -120 || screen.y < -120 || screen.x > view.width + 120 || screen.y > view.height + 120) continue;
    const style = palette[sig.kind] || palette.mst;
    const alpha = age > 3000 ? (3800 - age) / 800 : 1;
    const wave = (age % 950) / 950;
    if (!drawnAny) { c.save(); drawnAny = true; }
    c.globalAlpha = alpha;
    c.beginPath();
    c.arc(screen.x, screen.y, (22 + wave * 42) * zoom, 0, Math.PI * 2);
    c.strokeStyle = style.stroke;
    c.lineWidth = 2.5;
    c.stroke();
    c.beginPath();
    c.arc(screen.x, screen.y, 16 * zoom, 0, Math.PI * 2);
    c.fillStyle = style.fill;
    c.fill();
    c.strokeStyle = style.stroke;
    c.lineWidth = 2;
    c.stroke();
    const label = `${style.icon} · ${sig.name}`;
    c.font = 'bold 12px Tahoma, Arial, sans-serif';
    const tw = Math.ceil(c.measureText(label).width) + 14;
    const bx = Math.round(screen.x - tw / 2), by = Math.round(screen.y - 38 * zoom - 12);
    c.fillStyle = 'rgba(8, 15, 26, 0.88)';
    c.strokeStyle = style.stroke;
    c.lineWidth = 1.5;
    c.beginPath();
    c.roundRect(bx, by, tw, 22, 6);
    c.fill();
    c.stroke();
    c.fillStyle = '#ffffff';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    c.fillText(label, screen.x, by + 11);
  }
  if (drawnAny) { c.restore(); view.overlayDirty = true; }
}

export function drawNativeTargeting(view,state,now) {
  drawHazardTelegraphs(view, state, now);
  drawWorldSignals(view, state, now);
  const input=view.input.snapshot(),self=state.actors[String(state.selfObjectId)];
  if(!self||self.dead||self.removed||self.hp<=0||state.result)return;
  const slots=state.skills?.[String(self.objectId)]||{};
  if(input.showAttackRange){
    const basicSkill=view.prepared.catalog.skills?.[String(slots['0']?.skillId)];
    const basicRange=Number(basicSkill?.iFlyRange)||Number(basicSkill?.iRange)||0;
    if(basicRange>0){
      const pos=visualXY(self,now),origin=view.screenPoint(pos.x,pos.y),zoom=view.camera.zoom;
      const c=view.context;
      view.overlayDirty=true;
      c.save();
      c.beginPath();
      c.arc(origin.x,origin.y,basicRange*zoom,0,Math.PI*2);
      c.strokeStyle='rgba(110, 231, 183, 0.52)';
      c.lineWidth=1.5;
      c.setLineDash([7,6]);
      c.stroke();
      c.restore();
    }
  }
  // Feedback and inspection are presentation-only. Never select a slot or
  // substitute their aim for the live input/cast path.
  const current=preview=>preview&&preview.skillId>0&&slots[String(preview.slot)]?.skillId===preview.skillId;
  const held=current(input.heldCast);
  const warning=!held&&current(input.rangeFeedback)&&input.rangeFeedback.expiresAt>now;
  const hover=!held&&!warning&&current(input.hoveredSkill);
  const activeSlot=held?input.heldCast.slot:input.selectedSlot;
  if(!warning&&!hover&&(!input.active||!activeSlot||(!input.aim&&!held)))return;
  const slot=warning?input.rangeFeedback.slot:hover?input.hoveredSkill.slot:activeSlot;
  const entry=slots[String(slot)];
  const skill=view.prepared.catalog.skills[String(entry?.skillId)];
  const from=visualPosition(self,now);
  let aim=input.aim;
  if(warning||hover||held&&!aim){
    aim=input.lastMapAim||aim;
    if(!aim||!Number.isFinite(aim.x)||!Number.isFinite(aim.y)
        ||Math.hypot(aim.x-from.x,aim.y-from.y)<.001){
      const angle=(Number(self.cannonAngle)||0)*Math.PI/180,range=Number(skill?.iRange)||0;
      aim={x:from.x+Math.sin(angle)*range,y:from.y-Math.cos(angle)*range};
    }
  }
  const value=nativeSkillPreview(skill,from,aim);
  if(!value)return;
  const c=view.context,origin=view.screenPoint(value.from.x,value.from.y),zoom=view.camera.zoom;
  view.overlayDirty = true;
  c.save();c.translate(origin.x,origin.y);c.scale(zoom,zoom);
  if(warning||hover||held||value.maxRing){c.strokeStyle=warning?'#ff0000':'#02f0ff';c.lineWidth=2;c.beginPath();c.arc(0,0,value.range,0,Math.PI*2);c.stroke();}
  const shape=warning?null:value.shape;
  if(shape?.kind==='circle'){
    const cx=held||activeSlot?(aim.x-value.from.x):0,cy=held||activeSlot?(aim.y-value.from.y):0;
    c.fillStyle=hover?'rgba(2,240,255,.26)':held?'rgba(2,240,255,.28)':'rgba(255,0,0,.3)';
    c.strokeStyle='rgba(2,240,255,.75)';c.lineWidth=1.5;
    c.beginPath();c.arc(cx,cy,shape.radius,0,Math.PI*2);c.fill();c.stroke();
  }
  if(shape?.kind==='sector'){
    c.rotate(shape.rotation);c.beginPath();c.moveTo(0,36);
    for(let i=0;i<shape.angle;i++){const a=((180-shape.angle)/2+i)*Math.PI/180;c.lineTo(shape.radius*Math.cos(a),shape.radius*Math.sin(a)+36);}
    c.closePath();c.fillStyle='rgba(2,240,255,.35)';c.strokeStyle='rgba(2,240,255,.65)';c.lineWidth=2.5;c.fill();c.stroke();
  }
  c.restore();
  if(shape?.kind==='asset'){
    const sequence=resourceSequence(view.store,view.prepared.catalog.modePresentation?.resources?.[shape.asset]);
    if(sequence)view.drawSequence(sequence,Math.floor(Math.max(0,now-view.animationStart)/sequence.frameMs)%sequence.frames.length,
      shape.x,shape.y,shape.rotation,1,{scaleX:shape.scaleX,scaleY:shape.scaleY});
  }
}
