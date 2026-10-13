// Asset packing only: the artwork itself comes from source-atlas.png.
// At the SDK root: npm install --no-save --package-lock=false sharp
// Then run this file from any working directory.
const sharp = require('sharp');
const path = require('node:path');
const directory = path.resolve(__dirname, '..');
const source = path.join(__dirname, 'source-atlas.png');

let atlas;
async function frame(row, column, size, padding, brightness=1) {
  const metadata = atlas.info;
  const left = Math.round(column * metadata.width / 8);
  const top = Math.round(row * metadata.height / 4);
  const width = Math.round((column + 1) * metadata.width / 8) - left;
  const height = Math.round((row + 1) * metadata.height / 4) - top;
  const { data, info } = await sharp(atlas.data, {raw: atlas.info}).extract({left, top, width, height})
    .ensureAlpha().raw().toBuffer({resolveWithObject: true});
  let x0 = width, y0 = height, x1 = 0, y1 = 0;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    if (data[(y * width + x) * info.channels + 3] > 96) {
      x0 = Math.min(x0, x); y0 = Math.min(y0, y);
      x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    }
  }
  for (let i = 3; i < data.length; i += 4) data[i] = data[i] > 96 ? 255 : 0;
  return sharp(data, {raw: info}).extract({left:x0, top:y0,
    width:x1-x0+1, height:y1-y0+1})
    .resize(size-padding*2, size-padding*2, {fit:'contain',
      kernel:'nearest', background:'#00000000'})
    .extend({top:padding,bottom:padding,left:padding,right:padding,
      background:'#00000000'}).modulate({brightness}).png().toBuffer();
}

async function strip(name, row, columns, size, padding=1, brightness=1) {
  const frames = [];
  for (const [index, column] of columns.entries()) {
    frames.push(await frame(row,column,size,padding,
      Array.isArray(brightness) ? brightness[index] : brightness));
  }
  await sharp({create:{width:size*frames.length,height:size,channels:4,
    background:'#00000000'}}).composite(frames.map((input,index)=>({input,
      left:index*size,top:0}))).png().toFile(path.join(directory,'images',name));
}

(async()=>{
  atlas = await sharp(source).ensureAlpha().raw().toBuffer({resolveWithObject: true});
  // Generated lean poses face right then left, so swap them in each set.
  await strip('dreamer.png',0,[0,2,1,3,4,6,5,7],19);
  // Subdued at rest; the game occasionally plays a brightening pulse.
  await strip('seed.png',1,[0,1,2,3],9,1,[0.85,1,1.15,1.3]);
  await strip('flowers.png',2,[0,1,2,3,4,5,6,7],17);
  const icon = await frame(0,0,29,1);
  await sharp({create:{width:64,height:30,channels:4,background:'#00000000'}})
    .composite([{input:icon,left:18,top:0}]).png()
    .toFile(path.join(directory,'menu.png'));
})();
