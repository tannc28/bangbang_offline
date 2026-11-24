/* Presentation-only camera for the current native Robo scene.
 * Source: ScreenManager.setStageData; ScrollDefine; ScrollManagerBase
 * updateScrollPos/updateScrollRectSize; MapDataModel.setMapBeginPos/reset.
 * See evidence/robo_scene_audit/ROBO_SCENE_AUDIT.md in the M7 workspace.
 * No combat, movement, collision or server state is changed here.
 */

const MIN_VIEW_WIDTH = 1000;
const MIN_VIEW_HEIGHT = 600;
const FREE_WIDTH = 200;
const FREE_HEIGHT = 50;

// AS3 int parameters/locals truncate toward zero and convert to signed int32.
const int32 = value => Number(value) | 0;

function followAxis(begin, position, viewSize, mapSize, freeSize) {
  const distance = Number(position) - Number(begin);
  const upper = (viewSize + freeSize) / 2;
  const lower = (viewSize - freeSize) / 2;
  if (distance > upper) {
    begin = begin + distance - upper;
    if (begin > mapSize - viewSize) begin = mapSize - viewSize;
  }
  if (distance < lower) {
    begin = begin - (lower - distance);
    if (begin < 0) begin = 0;
  }
  return Math.max(0, Math.min(begin, Math.max(0, mapSize - viewSize)));
}

export class RoboCamera {
  constructor({stageWidth = MIN_VIEW_WIDTH, stageHeight = MIN_VIEW_HEIGHT,
    mapWidth = 2400, mapHeight = 2400, centerSmallMap = false} = {}) {
    this.beginX = 0;
    this.beginY = 0;
    this.followedX = 0;
    this.followedY = 0;
    this.panOverride = null;
    this.resize(stageWidth, stageHeight, mapWidth, mapHeight, {centerSmallMap});
  }

  reset() {
    this.beginX = 0;
    this.beginY = 0;
    this.followedX = 0;
    this.followedY = 0;
    this.panOverride = null;
    return this.snapshot();
  }

  panTo(worldX, worldY, until = 0) {
    this.panOverride = {x: Number(worldX) || 0, y: Number(worldY) || 0, until};
    this.beginX = Math.max(0, Math.min(this.panOverride.x - this.viewWidth / 2, Math.max(0, this.mapWidth - this.viewWidth)));
    this.beginY = Math.max(0, Math.min(this.panOverride.y - this.viewHeight / 2, Math.max(0, this.mapHeight - this.viewHeight)));
    return this.snapshot();
  }

  clearPan() {
    this.panOverride = null;
  }

  resize(stageWidth, stageHeight, mapWidth = this.mapWidth, mapHeight = this.mapHeight,
    {centerSmallMap = false} = {}) {
    this.stageWidth = int32(stageWidth);
    this.stageHeight = int32(stageHeight);
    this.viewWidth = Math.max(MIN_VIEW_WIDTH, this.stageWidth);
    this.viewHeight = Math.max(MIN_VIEW_HEIGHT, this.stageHeight);
    this.mapWidth = int32(mapWidth);
    this.mapHeight = int32(mapHeight);
    this.zoom = 1;
    this.stageOffsetX = 0;
    this.stageOffsetY = 0;
    if (centerSmallMap && this.mapWidth > 0 && this.stageWidth >= this.mapWidth) {
      this.viewWidth = this.mapWidth;
      this.stageOffsetX = (Number(stageWidth) - this.mapWidth) / 2;
    }
    if (centerSmallMap && this.mapHeight > 0 && this.stageHeight >= this.mapHeight) {
      this.viewHeight = this.mapHeight;
      this.stageOffsetY = (Number(stageHeight) - this.mapHeight) / 2;
    }
    return this.follow(this.followedX, this.followedY);
  }

  follow(worldX, worldY, now = 0) {
    this.followedX = Number(worldX) || 0;
    this.followedY = Number(worldY) || 0;
    if (this.panOverride) {
      if (!this.panOverride.until || now < this.panOverride.until) return this.snapshot();
      this.panOverride = null;
    }
    this.beginX = followAxis(this.beginX, this.followedX,
      this.viewWidth, this.mapWidth, FREE_WIDTH);
    this.beginY = followAxis(this.beginY, this.followedY,
      this.viewHeight, this.mapHeight, FREE_HEIGHT);
    return this.snapshot();
  }

  snapshot() {
    return {
      beginX: this.beginX,
      beginY: this.beginY,
      viewWidth: this.viewWidth,
      viewHeight: this.viewHeight,
      zoom: this.zoom,
      centerX: this.beginX + this.viewWidth / 2,
      centerY: this.beginY + this.viewHeight / 2,
      // Positive offsets are presentation-only margins around a small PvE
      // map. The camera center already includes this placement; all drawing
      // and screen/world input use the same transform, with no second shift.
      // Smaller windows retain the native minimum logical viewport/clipping.
      stageOffsetX: this.stageOffsetX,
      stageOffsetY: this.stageOffsetY,
      stageWidth: this.stageWidth,
      stageHeight: this.stageHeight,
      mapWidth: this.mapWidth,
      mapHeight: this.mapHeight,
      followedX: this.followedX,
      followedY: this.followedY,
    };
  }
}
