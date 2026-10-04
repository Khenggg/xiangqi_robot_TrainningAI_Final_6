async (page) => {
 return await page.evaluate(async()=>{const b=await import('/board.mjs');return {url:location.href,group:!!b.getActiveBoardGroup(),placement:b.getScenePlacement()};});
}
