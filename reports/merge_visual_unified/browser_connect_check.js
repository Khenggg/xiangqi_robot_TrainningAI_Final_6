async (page) => {
  await page.waitForFunction(async () => (await import('/board.mjs')).getActiveBoardGroup() !== null);
  const read = () => page.evaluate(async () => {
    const b=await import('/board.mjs');
    const g=b.getActiveBoardGroup();
    return {position:g.position.toArray(),quaternion:g.quaternion.toArray(),cells:[[0,0],[0,8],[9,0],[9,8],[2,7]].map(([r,c])=>b.boardPointToXYZ(r,c).toArray())};
  });
  const before=await read();
  await page.screenshot({path:'reports/merge_visual_unified/viewer_offline.png'});
  await page.getByRole('textbox',{name:'WebSocket:'}).fill('ws://127.0.0.1:8877');
  await page.getByRole('button',{name:'Connect live'}).click();
  await page.getByText('SIMULATION',{exact:false}).first().waitFor();
  const after=await read();
  await page.screenshot({path:'reports/merge_visual_unified/viewer_live.png'});
  return {before,after,unchanged:JSON.stringify(before)===JSON.stringify(after)};
}
