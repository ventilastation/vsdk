// Pack the generated cloud artwork into adjoining 16x16 tile frames.
// npm install --no-save --package-lock=false sharp, then run at the SDK root.
const sharp = require('sharp');
const path = require('node:path');
const directory = path.resolve(__dirname, '..');
const shapes = [[1,1],[2,1],[3,2],[1,1],[2,1],[3,2]];

(async () => {
  const atlas = await sharp(path.join(__dirname, 'cloud-atlas.png'))
    .ensureAlpha().raw().toBuffer({resolveWithObject:true});
  const tiles = [];
  for (const [index, [columns, rows]] of shapes.entries()) {
    const left = Math.round((index % 3) * atlas.info.width / 3);
    const top = Math.round(Math.floor(index / 3) * atlas.info.height / 2);
    const width = Math.round((index % 3 + 1) * atlas.info.width / 3) - left;
    const height = Math.round((Math.floor(index / 3) + 1) * atlas.info.height / 2) - top;
    const cell = await sharp(atlas.data, {raw:atlas.info}).extract({left,top,width,height})
      .raw().toBuffer({resolveWithObject:true});
    let x0=width, y0=height, x1=-1, y1=-1;
    for (let y=0; y<height; y++) for (let x=0; x<width; x++) {
      const alpha = (y*width+x)*4+3;
      // Remove the atlas's faint surrounding glow; the console uses binary alpha.
      cell.data[alpha] = cell.data[alpha] >= 200 ? 255 : 0;
      if (cell.data[alpha]) {
        x0=Math.min(x0,x); y0=Math.min(y0,y);
        x1=Math.max(x1,x); y1=Math.max(y1,y);
      }
    }
    if (x1 < x0) throw new Error(`Cloud cell ${index} is empty`);
    const cloud = await sharp(cell.data,{raw:cell.info})
      .extract({left:x0,top:y0,width:x1-x0+1,height:y1-y0+1})
      .resize(columns*16-2,rows*16-2,{fit:'contain',kernel:'nearest',background:'#00000000'})
      .extend({top:1,bottom:1,left:1,right:1,background:'#00000000'})
      .modulate({brightness:0.7}).raw().toBuffer({resolveWithObject:true});
    // The polar renderer reverses each tile's two image axes. Reverse the
    // source-cell order too, so a multi-cell cloud stays joined as one image.
    for (let row=0; row<rows; row++) for (let col=0; col<columns; col++) {
      tiles.push(await sharp(cloud.data,{raw:cloud.info})
        .extract({left:(columns-1-col)*16,top:(rows-1-row)*16,width:16,height:16})
        .png().toBuffer());
    }
  }
  await sharp({create:{width:tiles.length*16,height:16,channels:4,background:'#00000000'}})
    .composite(tiles.map((input,index)=>({input,left:index*16,top:0})))
    .png().toFile(path.join(directory,'images','clouds.png'));
  console.log(`Packed ${shapes.length} clouds into ${tiles.length} tiles`);
})();
