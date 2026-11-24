/* Game360MainFrame: stretch the sea backdrop, center the 1000x600
 * middle canvas, and anchor the 760x46 MenuButtonFrame right=-2/bottom=4.
 * Small HTML viewports shrink to fit; 1080p/2K/4K windows scale up crisply.
 */
export const FLASH_WORLD_MIN = Object.freeze({width:1000,height:600});
export const FLASH_MENU = Object.freeze({width:760,height:46,right:-2,bottom:4});

export function maxOutsideScale() {
  try {
    const pref = globalThis.localStorage?.getItem?.('bb-ui-scale');
    if (pref === '1' || pref === 'native') return 1;
    const parsed = Number(pref);
    if (Number.isFinite(parsed) && parsed >= 1 && parsed <= 2) return parsed;
  } catch { /* Storage unavailable in sandboxed or Node environments. */ }
  return 1.55;
}

export function flashOutsideLayout(width,height,panel=FLASH_WORLD_MIN) {
  width=Math.max(1,Number(width)||1);height=Math.max(1,Number(height)||1);
  const panelWidth=Math.max(1,Number(panel.width)||1000),panelHeight=Math.max(1,Number(panel.height)||600);
  const reqW=Math.max(1000,panelWidth),reqH=Math.max(600,panelHeight);
  const rawFit=Math.min(width/reqW,height/reqH);
  const maxScale=maxOutsideScale();
  const scale=rawFit<=1?rawFit:Math.max(1,Math.min(maxScale,(width*.96)/reqW,(height*.95)/reqH));
  const worldWidth=width/scale,worldHeight=height/scale;
  return {scale,width:worldWidth,height:worldHeight,
    panel:{x:(worldWidth-panelWidth)/2,y:(worldHeight-panelHeight)/2,width:panelWidth,height:panelHeight},
    middle:{x:(worldWidth-1000)/2,y:(worldHeight-600)/2,width:1000,height:600},
    menu:{x:worldWidth-FLASH_MENU.width-FLASH_MENU.right,y:worldHeight-FLASH_MENU.height-FLASH_MENU.bottom,
      width:FLASH_MENU.width,height:FLASH_MENU.height}};
}

// The chapter map is a navigable outside screen with the native bottom dock,
// not a blocking dialog. Equipment/companion windows can be opened above it.
export const outsideModalScreen=screen=>['garage','crystals','inventory','shop','profile','military','leaderboard','guild','companions','mailbox','worldboss'].includes(screen);
